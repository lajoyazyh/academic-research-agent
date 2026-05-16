
import math
from typing import List, Dict, Any, Iterable, Sequence, cast
from difflib import SequenceMatcher
import re
import numpy as np
import json
import os
from dotenv import load_dotenv, find_dotenv
from pydantic import SecretStr

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

load_dotenv(find_dotenv(usecwd=True))
if not os.getenv("OPENAI_API_KEY") and os.getenv("ZHIPU_API_KEY"):
    os.environ["OPENAI_API_KEY"] = os.getenv("ZHIPU_API_KEY", "")
if not os.getenv("OPENAI_BASE_URL") and os.getenv("ZHIPU_BASE_URL"):
    os.environ["OPENAI_BASE_URL"] = os.getenv("ZHIPU_BASE_URL", "")
if not os.getenv("OPENAI_API_BASE") and os.getenv("ZHIPU_BASE_URL"):
    os.environ["OPENAI_API_BASE"] = os.getenv("ZHIPU_BASE_URL", "")

# 尝试导入 ragas，若不可用则使用回退评估器
try:
    from ragas import evaluate
    from ragas.metrics import (
        answer_relevancy,
        context_precision, context_recall, answer_correctness,
        answer_similarity
    )
    from datasets import Dataset
    RAGAS_AVAILABLE = True
except Exception:
    RAGAS_AVAILABLE = False

_USE_RAGAS = os.getenv("EVAL_USE_RAGAS", "true").strip().lower() in {"1", "true", "yes", "on"}
if not _USE_RAGAS:
    RAGAS_AVAILABLE = False

_USE_ANSWER_CORRECTNESS = os.getenv("RAGAS_INCLUDE_ANSWER_CORRECTNESS", "false").strip().lower() in {"1", "true", "yes", "on"}

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9\u4e00-\u9fff]+")



def _string_similarity(a: str, b: str) -> float:
    """计算两个字符串的相似度 (0-1)"""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _tokenize_text(value: str) -> List[str]:
    return [token.lower() for token in _TOKEN_PATTERN.findall(value or "") if token]


def _overlap_ratio(left_tokens: List[str], right_tokens: List[str]) -> float:
    left_set = set(left_tokens)
    right_set = set(right_tokens)
    if not left_set or not right_set:
        return 0.0
    return float(len(left_set & right_set) / len(right_set))


def _token_f1(left_tokens: List[str], right_tokens: List[str]) -> float:
    left_set = set(left_tokens)
    right_set = set(right_tokens)
    if not left_set or not right_set:
        return 0.0
    overlap = len(left_set & right_set)
    precision = overlap / len(left_set)
    recall = overlap / len(right_set)
    if precision + recall == 0:
        return 0.0
    return float(2 * precision * recall / (precision + recall))


def _context_support_score(answer_tokens: List[str], contexts: List[str]) -> float:
    if not answer_tokens or not contexts:
        return 0.0
    context_tokens = set()
    for context in contexts:
        context_tokens.update(_tokenize_text(context))
    if not context_tokens:
        return 0.0
    return float(len(set(answer_tokens) & context_tokens) / len(set(answer_tokens)))


def _normalize_ground_truths(ground_truths: Sequence[Any]) -> List[str]:
    normalized: List[str] = []
    for value in ground_truths or []:
        if value is None:
            continue
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                continue
            if stripped.startswith("["):
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, list):
                        normalized.extend(str(item) for item in parsed if item is not None)
                        continue
                except Exception:
                    pass
            normalized.append(stripped)
        elif isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
            normalized.extend(str(item) for item in value if item is not None)
        else:
            normalized.append(str(value))
    return normalized


def _sanitize_for_json(obj: Any) -> Any:
    """Replace nan/inf floats with 0.0 across dicts, lists and scalars."""
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return 0.0
        return obj
    return obj


def _records_to_score_summary(records: Sequence[Dict[str, Any]], metric_names: Sequence[str]) -> Dict[str, float]:
    summary: Dict[str, float] = {}
    for metric_name in metric_names:
        values = []
        for record in records:
            value = record.get(metric_name)
            if isinstance(value, (int, float)):
                values.append(float(value))
        if values:
            summary[metric_name] = float(np.mean(values))
    # sanitize nan / inf after `np.mean`
    for key in list(summary.keys()):
        summary[key] = _to_float(summary[key], 0.0)
    return summary


def _build_ragas_llm():
    """创建兼容智谱/OpenAI 的 ragas LLM，自动过滤不兼容参数。"""
    api_key = os.getenv("ZHIPU_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("ZHIPU_BASE_URL") or os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE")
    model_name = os.getenv("ZHIPU_MODEL", "glm-4")
    if not api_key or not base_url:
        return None
    return _ZhipuCompatibleChatOpenAI(
        model=model_name,
        api_key=cast(Any, api_key),
        base_url=base_url,
        temperature=0.01,
        max_retries=2,
        timeout=120,
    )


class _ZhipuCompatibleChatOpenAI(ChatOpenAI):
    """移除智谱不支持的请求参数（response_format 等）。"""

    def __init__(self, **kwargs: Any):
        kwargs.pop("response_format", None)
        super().__init__(**kwargs)

        # 暴力拦截底层 OpenAI client，彻底清洗发送给智谱 API 的 payload
        orig_create = self.client.create
        def patched_create(*args, **kw):
            allowed_keys = {"model", "messages", "request_id", "do_sample", "stream", "temperature", "top_p", "max_tokens", "stop", "tools", "tool_choice", "user"}
            bad_keys = [k for k in kw.keys() if k not in allowed_keys]
            for bk in bad_keys:
                kw.pop(bk, None)
                
            # Zhipu backend often chokes on scientific notation (like 1e-08) or 0
            if "temperature" in kw and (kw["temperature"] is None or float(kw["temperature"]) < 0.01):
                kw["temperature"] = 0.01
            if "top_p" in kw and (kw["top_p"] is None or float(kw["top_p"]) >= 1.0):
                kw["top_p"] = 0.99
                
            if "messages" in kw:
                for msg in kw["messages"]:
                    if isinstance(msg, dict):
                        msg_allowed = {"role", "content", "tool_calls", "tool_call_id"}
                        msg_bad = [k for k in msg.keys() if k not in msg_allowed]
                        for mbk in msg_bad:
                            msg.pop(mbk, None)
            try:
                return orig_create(*args, **kw)
            except Exception as e:
                import json
                try:
                    with open("zhipu_error_payload.json", "w") as f:
                        json.dump(kw, f, ensure_ascii=False, indent=2)
                except:
                    pass
                print(f"ZHIPU API ERROR payload saved to zhipu_error_payload.json")
                raise
        self.client.create = patched_create

        orig_acreate = self.async_client.create
        async def patched_acreate(*args, **kw):
            # Zhipu allows specific keys. Force pop everything else known to cause issues.
            allowed_keys = {"model", "messages", "request_id", "do_sample", "stream", "temperature", "top_p", "max_tokens", "stop", "tools", "tool_choice", "user"}
            bad_keys = [k for k in kw.keys() if k not in allowed_keys]
            for bk in bad_keys:
                kw.pop(bk, None)
                
            if "temperature" in kw and (kw["temperature"] is None or float(kw["temperature"]) < 0.01):
                kw["temperature"] = 0.01
            if "top_p" in kw and (kw["top_p"] is None or float(kw["top_p"]) >= 1.0):
                kw["top_p"] = 0.99
                
            if "messages" in kw:
                for msg in kw["messages"]:
                    if isinstance(msg, dict):
                        # only keep role, content, tool_calls, tool_call_id
                        msg_allowed = {"role", "content", "tool_calls", "tool_call_id"}
                        msg_bad = [k for k in msg.keys() if k not in msg_allowed]
                        for mbk in msg_bad:
                            msg.pop(mbk, None)

            try:
                return await orig_acreate(*args, **kw)
            except Exception as e:
                import json
                try:
                    with open("zhipu_error_payload.json", "w") as f:
                        json.dump(kw, f, ensure_ascii=False, indent=2)
                except:
                    pass
                print(f"ZHIPU API ERROR payload saved to zhipu_error_payload.json")
                raise
        self.async_client.create = patched_acreate

    def _clean_kwargs(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = dict(kwargs)
        cleaned.pop("seed", None)
        cleaned.pop("logprobs", None)
        cleaned.pop("top_logprobs", None)
        cleaned.pop("stream_options", None)
        cleaned.pop("response_format", None)
        return cleaned

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return super()._generate(messages, stop=stop, run_manager=run_manager, **self._clean_kwargs(kwargs))

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return await super()._agenerate(messages, stop=stop, run_manager=run_manager, **self._clean_kwargs(kwargs))


def _build_ragas_embeddings():
    api_key = os.getenv("ZHIPU_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("ZHIPU_BASE_URL") or os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE")
    embedding_model = (
        os.getenv("ZHIPU_EMBEDDING_MODEL")
        or os.getenv("RAGAS_EMBEDDING_MODEL")
        or os.getenv("OPENAI_EMBEDDING_MODEL")
        or "embedding-2"
    )
    if not api_key or not base_url:
        return None
    return OpenAIEmbeddings(
        model=embedding_model,
        api_key=cast(Any, api_key),
        base_url=base_url,
        max_retries=2,
        timeout=60,
    )


def _result_oriented_metric_pack():
    metrics = [answer_relevancy, answer_similarity]
    metric_names = ["answer_relevancy", "answer_similarity"]
    if _USE_ANSWER_CORRECTNESS:
        metrics.append(answer_correctness)
        metric_names.append("answer_correctness")
    return metrics, metric_names


def _explicit_metric_pack():
    metrics = [answer_relevancy, context_precision, context_recall, answer_similarity]
    metric_names = [
        "answer_relevancy",
        "context_precision",
        "context_recall",
        "answer_similarity",
    ]
    if _USE_ANSWER_CORRECTNESS:
        metrics.append(answer_correctness)
        metric_names.append("answer_correctness")
    return metrics, metric_names


def _simple_evaluate(
    questions: List[str],
    answers: List[str],
    contexts: List[List[str]],
    ground_truths: List[str],
    method_name: str = "simple_string_similarity",
    error_message: str | None = None,
) -> Dict[str, Any]:
    """简单的字符串相似度评估，用于 ragas 不可用时"""
    normalized_ground_truths = _normalize_ground_truths(ground_truths)
    if not answers or not normalized_ground_truths:
        return {
            "backend": "fallback",
            "method": method_name,
            "sample_count": 0,
            "scores": {
                "similarity_score": 0.0,
                "truth_coverage_score": 0.0,
                "token_f1_score": 0.0,
                "context_support_score": 0.0,
            },
            "error": error_message or "Missing answers or ground truths"
        }

    normalized_contexts = list(contexts or [])
    if len(normalized_contexts) < len(answers):
        normalized_contexts.extend([[] for _ in range(len(answers) - len(normalized_contexts))])

    records = []
    scores = []
    truth_coverages = []
    token_f1_scores = []
    context_support_scores = []

    for answer, truth, context_items in zip(answers, normalized_ground_truths, normalized_contexts):
        answer_tokens = _tokenize_text(answer)
        truth_tokens = _tokenize_text(truth)
        context_list = [str(item) for item in context_items if item is not None]

        similarity_score = _string_similarity(answer, truth)
        truth_coverage_score = _overlap_ratio(answer_tokens, truth_tokens)
        token_f1_score = _token_f1(answer_tokens, truth_tokens)
        context_support_score = _context_support_score(answer_tokens, context_list)

        scores.append(similarity_score)
        truth_coverages.append(truth_coverage_score)
        token_f1_scores.append(token_f1_score)
        context_support_scores.append(context_support_score)
        records.append(
            {
                "question": None,
                "answer": answer,
                "ground_truth": truth,
                "similarity_score": float(similarity_score),
                "truth_coverage_score": float(truth_coverage_score),
                "token_f1_score": float(token_f1_score),
                "context_support_score": float(context_support_score),
                "context_count": len(context_list),
            }
        )
    
    avg_score = np.mean(scores) if scores else 0.0
    metric_names = [
        "similarity_score",
        "truth_coverage_score",
        "token_f1_score",
        "context_support_score",
    ]
    return {
        "backend": "fallback",
        "method": method_name,
        "sample_count": len(scores),
        "metric_names": metric_names,
        "scores": {
            "similarity_score": float(avg_score),
            "truth_coverage_score": float(np.mean(truth_coverages)) if truth_coverages else 0.0,
            "token_f1_score": float(np.mean(token_f1_scores)) if token_f1_scores else 0.0,
            "context_support_score": float(np.mean(context_support_scores)) if context_support_scores else 0.0,
        },
        "records": records,
        "individual_scores": [
            {
                "similarity_score": float(similarity),
                "truth_coverage_score": float(coverage),
                "token_f1_score": float(token_f1),
                "context_support_score": float(context_support),
            }
            for similarity, coverage, token_f1, context_support in zip(
                scores,
                truth_coverages,
                token_f1_scores,
                context_support_scores,
            )
        ],
        **({"error": error_message} if error_message else {})
    }


def _build_llm_judge():
    api_key = os.getenv("ZHIPU_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("ZHIPU_BASE_URL") or os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE")
    model_name = os.getenv("ZHIPU_MODEL") or os.getenv("OPENAI_MODEL") or "glm-4"
    if not api_key or not base_url:
        return None
    return _ZhipuCompatibleChatOpenAI(
        model=model_name,
        api_key=cast(Any, api_key),
        base_url=base_url,
        temperature=0.01,
        max_retries=2,
        timeout=120,
    )


def _extract_json_payload(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    candidates = [text.strip()]
    match = re.search(r"\{.*\}", text, re.S)
    if match:
        candidates.insert(0, match.group(0))
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
            if isinstance(payload, dict):
                return payload
        except Exception:
            continue
    return {}


def _clean_context_string(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    # Remove system truncation warnings
    text = re.sub(r"\.\.\.\[警告：为防止大模型上下文超限，PDF后续内容已被系统自动截断\]\.\.\.", "", text)
    # Remove success logs like ✅ 笔记已成功...
    text = re.sub(r"✅\s*.*?(\n|$)", "\n", text)
    return text.strip()

def _stringify_contexts(context_items: Sequence[Any]) -> str:
    if not context_items:
        return "无"
    parts = []
    for index, item in enumerate(context_items, start=1):
        if item is None:
            continue
        cleaned_item = _clean_context_string(item)
        if cleaned_item:
            parts.append(f"[{index}] {cleaned_item}")
    return "\n".join(parts) if parts else "无"


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except Exception:
        return default


class LLMBasedEvaluator:
    """按 README 中定义的指标进行评估：ragas 负责基础指标，LLM 负责补充指标。"""

    def __init__(self, method: str):
        self.method = method
        self.llm = _build_llm_judge()

        if method == "result_oriented":
            self.ragas_metrics = [answer_similarity] if RAGAS_AVAILABLE else []
            self.ragas_metric_names = ["answer_similarity"]
            self.llm_metric_names = ["answer_correctness", "answer_similarity", "completeness_score", "relevance_score"]
            self.metric_names = self.ragas_metric_names + self.llm_metric_names
            self.judge_focus = "结果导向：重点判断最终答案的正确性、完整性、指令相关性与语义一致性。"
        elif method == "process_oriented":
            self.ragas_metrics = [context_precision] if RAGAS_AVAILABLE else []
            self.ragas_metric_names = ["context_precision"]
            self.llm_metric_names = ["grounding_score", "reasoning_score", "step_coherence_score"]
            self.metric_names = self.ragas_metric_names + self.llm_metric_names
            self.judge_focus = "过程导向：重点判断检索质量、证据依赖、推理逻辑与步骤连贯性。"
        else:
            self.ragas_metrics = [context_precision] if RAGAS_AVAILABLE else []
            self.ragas_metric_names = ["context_precision"]
            self.llm_metric_names = ["answer_correctness", "answer_similarity", "context_recall", "faithfulness_score", "helpfulness_score", "relevance_score", "reasoning_score"]
            self.metric_names = self.ragas_metric_names + self.llm_metric_names
            self.judge_focus = "综合指标：同时覆盖结果质量、证据忠实性、检索覆盖、指令相关性和实用性。"

    def _generate_reference(self, question: str, contexts: Sequence[Any], hint: str | None = None) -> Dict[str, Any]:
        if self.llm is None:
            raise RuntimeError("LLM not configured")
        prompt = f"""
你是一个严谨的测试集构造助手。请根据问题生成一条可作为参考标准答案的 ground truth。

要求：
1. 只输出 JSON，不要输出任何解释性文字。
2. ground_truth 要简洁、明确、可用于评测。
3. 如果题目有歧义，请给出最可能的标准答案。

问题：{question}
上下文：
{_stringify_contexts(contexts)}
已有参考（可选，仅供参考）：{hint or '无'}

请输出：
{{
  "ground_truth": "...",
  "reason": "..."
}}
""".strip()
        raw = self.llm.invoke(prompt)
        payload = _extract_json_payload(getattr(raw, "content", str(raw)))
        ground_truth = payload.get("ground_truth") or payload.get("reference_answer") or payload.get("answer")
        reason = payload.get("reason") or payload.get("explanation") or ""
        if not ground_truth:
            ground_truth = hint or ""
        return {"ground_truth": str(ground_truth).strip(), "reason": str(reason).strip()}

    def _judge_sample(self, question: str, answer: str, reference: str, contexts: Sequence[Any]) -> Dict[str, Any]:
        if self.llm is None:
            raise RuntimeError("LLM not configured")

        prompt = f"""
你是评测裁判。请根据问题、参考答案、候选答案和上下文，对该样本打分。

评测维度：{self.judge_focus}

打分要求：
1. 所有分数都必须在 0 到 1 之间。
2. 只输出 JSON，不要输出任何其他文字。
3. overall_score 是综合分数。

问题：{question}
参考答案：{reference}
候选答案：{answer}
上下文：
{_stringify_contexts(contexts)}

请输出：
{{
  "overall_score": 0.0,
  "correctness_score": 0.0,
  "completeness_score": 0.0,
  "relevance_score": 0.0,
  "grounding_score": 0.0,
  "reasoning_score": 0.0,
  "step_coherence_score": 0.0,
  "faithfulness_score": 0.0,
  "helpfulness_score": 0.0,
  "context_recall": 0.0,
  "reason": "..."
}}
""".strip()
        raw = self.llm.invoke(prompt)
        payload = _extract_json_payload(getattr(raw, "content", str(raw)))
        result = {
            "overall_score": _to_float(payload.get("overall_score"), 0.0),
            "correctness_score": _to_float(payload.get("correctness_score"), 0.0),
            "completeness_score": _to_float(payload.get("completeness_score"), 0.0),
            "relevance_score": _to_float(payload.get("relevance_score"), 0.0),
            "grounding_score": _to_float(payload.get("grounding_score"), 0.0),
            "reasoning_score": _to_float(payload.get("reasoning_score"), 0.0),
            "step_coherence_score": _to_float(payload.get("step_coherence_score"), 0.0),
            "faithfulness_score": _to_float(payload.get("faithfulness_score"), 0.0),
            "helpfulness_score": _to_float(payload.get("helpfulness_score"), 0.0),
            "context_recall": _to_float(payload.get("context_recall"), 0.0),
            "reason": str(payload.get("reason") or payload.get("explanation") or "").strip(),
        }

        if self.method == "result_oriented" and result["overall_score"] == 0.0:
            result["overall_score"] = float(np.mean([result["correctness_score"], result["completeness_score"], result["relevance_score"]]))
        elif self.method == "process_oriented" and result["overall_score"] == 0.0:
            result["overall_score"] = float(np.mean([result["grounding_score"], result["reasoning_score"], result["step_coherence_score"]]))
        elif self.method == "explicit_metrics" and result["overall_score"] == 0.0:
            result["overall_score"] = float(np.mean([result["correctness_score"], result["faithfulness_score"], result["helpfulness_score"], result["relevance_score"]]))

        return result

    def evaluate(self, questions: List[str], answers: List[str], contexts: List[List[str]], ground_truths: List[str]) -> Dict[str, Any]:
        if not RAGAS_AVAILABLE:
            raise RuntimeError("ragas is not available or disabled; evaluation requires ragas")
        if self.llm is None:
            raise RuntimeError("LLM not configured for judge metrics")

        normalized_questions = [str(item).strip() for item in questions if item is not None]
        normalized_answers = [str(item).strip() for item in answers if item is not None]
        normalized_contexts = list(contexts or [])
        normalized_hints = _normalize_ground_truths(ground_truths)

        if len(normalized_contexts) < len(normalized_questions):
            normalized_contexts.extend([[] for _ in range(len(normalized_questions) - len(normalized_contexts))])
        if len(normalized_hints) < len(normalized_questions):
            normalized_hints.extend([""] * (len(normalized_questions) - len(normalized_hints)))

        records: List[Dict[str, Any]] = []
        for index, question in enumerate(normalized_questions):
            answer = normalized_answers[index] if index < len(normalized_answers) else ""
            raw_context_items = normalized_contexts[index] if index < len(normalized_contexts) else []
            context_items = [_clean_context_string(c) for c in raw_context_items if c is not None and _clean_context_string(c)]
            hint = normalized_hints[index] if index < len(normalized_hints) else ""

            if hint.strip():
                reference = hint.strip()
                ref_reason = "来自数据集 ground_truths"
            else:
                generated = self._generate_reference(question, context_items, hint)
                reference = generated.get("ground_truth", "")
                ref_reason = generated.get("reason", "")

            records.append({
                "question": question,
                "answer": answer,
                "contexts": context_items,
                "reference": reference,
                "reference_reason": ref_reason,
            })

        if self.ragas_metrics:
            try:
                dataset = Dataset.from_dict({
                    "question": [r["question"] for r in records],
                    "answer": [r["answer"] for r in records],
                    "contexts": [r["contexts"] for r in records],
                    "ground_truth": [r["reference"] for r in records],
                })
                llm = _build_ragas_llm()
                embeddings = _build_ragas_embeddings()
                if llm is None or embeddings is None:
                    raise RuntimeError("Missing Zhipu/OpenAI-compatible ragas LLM or embeddings configuration")
                ragas_result = evaluate(dataset, metrics=self.ragas_metrics, llm=llm, embeddings=embeddings, raise_exceptions=False)
                ragas_records = cast(Any, ragas_result.to_pandas()).to_dict(orient="records")
                for i, rr in enumerate(ragas_records):
                    for metric_name in self.ragas_metric_names:
                        if metric_name in rr:
                            records[i][metric_name] = _to_float(rr.get(metric_name), 0.0)
            except Exception as exc:
                raise RuntimeError(f"ragas evaluation failed: {exc}")

        for rec in records:
            judged = self._judge_sample(rec["question"], rec["answer"], rec["reference"], rec["contexts"])
            rec.update(judged)

        summary = _records_to_score_summary(records, self.metric_names + ["overall_score"])

        # 兜底过滤：移除 ragas faithfulness（始终为 0，不可用）
        _EXCLUDED_METRICS = {"faithfulness"}
        for rec in records:
            for key in _EXCLUDED_METRICS:
                rec.pop(key, None)
        for key in _EXCLUDED_METRICS:
            summary.pop(key, None)

        raw_result = {
            "backend": "ragas+llm",
            "method": self.method,
            "sample_count": len(records),
            "metric_names": self.metric_names + ["overall_score"],
            "scores": summary,
            "records": records,
        }
        # sanitize any remaining nan/inf before FastAPI JSON serialization
        return cast(Dict[str, Any], _sanitize_for_json(raw_result))


def get_evaluator(method: str):
    if method in {"result_oriented", "process_oriented", "explicit_metrics"}:
        return LLMBasedEvaluator(method)
    raise ValueError(f"Unsupported evaluation method: {method}")
