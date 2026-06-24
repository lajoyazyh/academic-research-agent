"""
RAG 笔记生成器 — RAG upgrade

基于智谱 Embedding API 实现向量语义检索，
从 PDF 全文中检索最相关段落，逐节生成深度学术笔记。

替代旧的"读前5页 → 直灌 LLM"方案。
"""

import numpy as np
from typing import Any

from tools.pdf_tools import extract_full_text_from_pdf
from llms.client import LLMClient


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """计算余弦相似度"""
    a_norm = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-10)
    b_norm = b / (np.linalg.norm(b, axis=0, keepdims=True) + 1e-10)
    return np.dot(a_norm, b_norm)


class RAGNoteGenerator:
    """
    基于 Embedding + 向量检索的学术笔记生成器。

    流程：
    1. 从 PDF 全量提取段落
    2. 用智谱 Embedding API 将段落转为向量
    3. 对每个笔记维度（核心方法、实验设置等），
       用向量检索出 Top-K 相关段落
    4. 每个维度单独调用 LLM 生成笔记
    5. 拼接为完整学术笔记
    """

    SECTIONS = [
        {
            "name": "研究背景",
            "query_keywords": [
                "problem", "challenge", "background", "introduction",
                "limitation", "issue", "gap", "motivation"
            ],
            "min_words": 80,
        },
        {
            "name": "核心方法",
            "query_keywords": [
                "method", "approach", "proposed", "architecture",
                "we propose", "introduce", "model", "framework"
            ],
            "min_words": 150,
        },
        {
            "name": "实验设置",
            "query_keywords": [
                "experiment", "dataset", "evaluation", "benchmark",
                "baseline", "setup", "implementation", "training"
            ],
            "min_words": 80,
        },
        {
            "name": "关键结果",
            "query_keywords": [
                "result", "performance", "achieve", "outperform",
                "accuracy", "improvement", "state-of-the-art", "table"
            ],
            "min_words": 100,
        },
        {
            "name": "消融与分析",
            "query_keywords": [
                "ablation", "analysis", "visualization", "case study",
                "component", "effect", "impact", "comparison"
            ],
            "min_words": 80,
        },
        {
            "name": "亮点与不足",
            "query_keywords": [
                "contribution", "limitation", "future work",
                "novel", "innovation", "challenge", "drawback"
            ],
            "min_words": 60,
        },
    ]

    def __init__(self):
        self.llm = LLMClient()
        self._embedding_failed = False  # 标记 Embedding API 是否已不可用

    def _try_embed(self, texts: list[str]) -> np.ndarray | None:
        """尝试调用 Embedding API，失败时返回 None 并标记不可用"""
        if self._embedding_failed:
            return None
        try:
            vecs = self.llm.embed(texts)
            emb = np.array(vecs, dtype=np.float32)
            if emb.shape[1] < 10:
                self._embedding_failed = True
                return None
            return emb
        except Exception:
            self._embedding_failed = True
            return None

    def generate(
        self,
        pdf_path: str,
        paper_title: str,
        abstract: str,
        topic: str,
        skill_content: str = "",
    ) -> str:
        """
        主入口：为一篇论文生成完整学术笔记。

        Args:
            pdf_path: PDF 文件路径
            paper_title: 论文标题
            abstract: 论文摘要
            topic: 研究主题
            skill_content: 用户自定义 notes Skill 内容（注入为系统提示词前缀）

        Returns:
            Markdown 格式的完整学术笔记
        """
        # 1. 全量提取段落
        blocks = extract_full_text_from_pdf(pdf_path)
        if not blocks:
            result = self._fallback(paper_title, abstract, topic, skill_content)
            if skill_content:
                result = self._self_repair_notes(result, skill_content)
            return result

        # 2. 用 Embedding API 向量化
        texts = [b["text"][:800] for b in blocks]  # 截断过长的段落
        embeddings = self._try_embed(texts)
        if embeddings is None:
            result = self._fallback_bm25(pdf_path, paper_title, abstract, topic, skill_content)
            if skill_content:
                result = self._self_repair_notes(result, skill_content)
            return result

        # 3. 逐节检索 — 收集所有相关段落
        all_rag_text = ""
        if skill_content:
            # 有 Skill 时：收集所有 RAG 段落，一次性生成整篇笔记（follow Skill 结构）
            all_passages = []
            for section in self.SECTIONS:
                keywords = " ".join(section["query_keywords"])
                query = f"{paper_title} {abstract[:300]} {topic} {keywords}"
                try:
                    query_emb = self._try_embed([query[:1000]])
                    if query_emb is None:
                        break
                    scores = _cosine_similarity(embeddings, query_emb[0]).flatten()
                    top_k = min(3, len(blocks))
                    top_indices = np.argsort(scores)[::-1][:top_k]
                    for idx in top_indices:
                        if float(scores[idx]) > 0.3:
                            b = blocks[idx]
                            all_passages.append(f"【第{b['page']}页·{section['name']}相关】{b['text'][:500]}")
                except Exception:
                    pass
            if all_passages:
                all_rag_text = "\n\n".join(all_passages[:20])
            else:
                all_rag_text = abstract

            # 一次性生成整篇笔记，完全按照 Skill 结构
            full_prompt = f"""你是严谨的学术研究员。请为以下论文生成完整的学术笔记。

论文标题：{paper_title}
研究主题：{topic}

{skill_content}

【论文原文段落（多维度检索结果）】
{all_rag_text}

核心要求：
- 严格按照上述 Skill 定义的格式和结构输出笔记
- 如果 Skill 指定了具体章节名，必须完全使用这些章节名
- 信息不足处标注"未提及"，不编造内容
- 只输出笔记本身，不要加额外说明"""
            try:
                result = self.llm.chat(
                    "你是严谨的学术研究员。严格按照Skill格式输出完整笔记，不添加额外说明。",
                    full_prompt, []
                ).strip()
                if result:
                    # 自检自修
                    result = self._self_repair_notes(result, skill_content)
                    return f"## 论文笔记：{paper_title}\n\n{result}"
            except Exception:
                pass
            # 自生成失败时，回退到下面逐节生成
            print(f"[NotesSkill] Full generation failed, falling back to section-by-section")

        # 无 Skill 或自生成回退：逐节检索 + 生成（原有逻辑）
        sections_output = []
        for section in self.SECTIONS:
            section_text = self._generate_section(
                section, blocks, embeddings, paper_title, abstract, topic, skill_content
            )
            sections_output.append(f"- **{section['name']}**：{section_text}")

        body = "\n\n".join(sections_output)

        # 自我修复：当有 Skill 时，调用 LLM 检查并修复笔记格式
        if skill_content:
            body = self._self_repair_notes(body, skill_content)

        # ━━━ 通用自审 (Self-Critique) ━━━
        body = self._self_critique(paper_title, topic, body)

        return f"## 论文笔记：{paper_title}\n\n{body}"

    def _generate_section(
        self,
        section: dict,
        blocks: list[dict],
        embeddings: np.ndarray,
        paper_title: str,
        abstract: str,
        topic: str,
        skill_content: str = "",
    ) -> str:
        """为单个维度检索 + 生成笔记"""
        # 构建查询
        keywords = " ".join(section["query_keywords"])
        query = f"{paper_title} {abstract[:300]} {topic} {keywords}"

        # 向量检索 Top-5
        try:
            query_emb = self._try_embed([query[:1000]])
            if query_emb is None:
                rag_text = abstract or "（无法检索原文）"
            else:
                scores = _cosine_similarity(embeddings, query_emb[0]).flatten()
                top_k = min(5, len(blocks))
                top_indices = np.argsort(scores)[::-1][:top_k]

                # 收集原文段落
                passages = []
                for idx in top_indices:
                    if float(scores[idx]) > 0.3:
                        b = blocks[idx]
                        passages.append(
                            f"【第{b['page']}页】{b['text'][:500]}"
                        )
                rag_text = "\n\n".join(passages) if passages else abstract
        except Exception:
            rag_text = abstract or "（无法检索原文）"

        # LLM 生成 — 双通道：有 Skill 时替换默认格式要求，无 Skill 时使用完整默认
        if skill_content:
            # 通道 A：Skill 优先 — 用 Skill 内容替换默认写作要求，仅保留最小核心约束
            channel = "A"
            prompt = f"""你是严谨的学术研究员。请为以下论文撰写「{section['name']}」部分的笔记。

研究主题：{topic}
论文标题：{paper_title}

{skill_content}

【检索到的论文原文段落】
{rag_text}

核心要求：至少 {section['min_words']} 字，只输出笔记内容本身，不要加标题前缀或解释。"""
        else:
            # 通道 B：默认兜底 — 使用完整的默认格式要求（现有逻辑不变）
            channel = "B"
            prompt = f"""你是严谨的学术研究员。请为以下论文撰写「{section['name']}」部分的笔记。
研究主题：{topic}
论文标题：{paper_title}

【检索到的论文原文段落】
{rag_text}

要求：
- 以一段连贯的文字输出，不要用编号列表
- 引述原文中的具体方法名、数据、实验指标
- 至少 {section['min_words']} 字
- 只输出笔记内容本身，不要加标题前缀或解释"""
        print(f"[NotesSkill] {section['name']}: Channel {channel} | skill_len={len(skill_content) if skill_content else 0}")

        try:
            result = self.llm.chat(
                "你是严谨的学术研究员。只输出笔记内容。",
                prompt, []
            ).strip()
            return result
        except Exception:
            return f"（生成失败）"

    def _self_repair_notes(self, raw_notes: str, skill_content: str) -> str:
        """后生成自我修复：当使用了 Skill 时，根据 Skill 要求完全重写笔记格式。

        采用混合策略：
        1. 先用 Skill 要求完全重写笔记（不考虑原结构）
        2. 再检验是否符合要求，不符合则二次修正

        Args:
            raw_notes: 原始生成的笔记
            skill_content: Skill 的格式化要求

        Returns:
            修复后的笔记（修复失败时返回原文）
        """
        # ━━━ 第一轮：基于 Skill 要求完全重写 ━━━
        rewrite_prompt = f"""You are a strict formatting enforcer.

Your task: COMPLETELY REWRITE the notes below according to the formatting requirements. Do NOT just adjust the existing format — rewrite from scratch following the EXACT structure specified in the requirements.

CRITICAL RULES:
1. The skill requirements OVERRIDE any existing structure in the notes
2. Output structure MUST match the skill requirements EXACTLY — section names, heading levels, bullet style, everything
3. Preserve ALL academic facts from the original notes (methods, data, results)
4. If a required section has no data, write "未提及" (not mentioned) — do NOT invent content
5. Output ONLY the final formatted notes — no explanations, no markdown code blocks, no commentary

【FORMATTING REQUIREMENTS — THIS IS THE ONLY ALLOWED STRUCTURE】
{skill_content}

【ORIGINAL NOTES — EXTRACT ALL FACTS FROM HERE】
{raw_notes}

CRITICAL: Output ONLY the fully rewritten notes. The output must be the final notes text directly."""
        try:
            result = self.llm.chat(
                "You are a strict formatting enforcer. Completely rewrite the notes following the required structure exactly. Output ONLY the final notes text.",
                rewrite_prompt, []
            ).strip()
            if result:
                repaired = result
            else:
                repaired = raw_notes
        except Exception:
            repaired = raw_notes

        # ━━━ 第二轮：逐项验证和修正 ━━━
        verify_prompt = f"""You are a strict quality checker.

CHECK the notes below against EVERY requirement in the skill. For each formatting requirement, verify compliance. If anything is wrong, fix it.

【REQUIREMENTS】
{skill_content}

【NOTES TO VERIFY】
{repaired}

IMPORTANT:
- If section names don't match the requirements, rename them
- If bullet style is wrong, fix it
- If required sections are missing, add them with "未提及"
- Output ONLY the verified/fixed notes text"""
        try:
            result = self.llm.chat(
                "You are a quality checker. Output ONLY the corrected notes text — no explanations.",
                verify_prompt, []
            ).strip()
            if result:
                repaired = result
        except Exception:
            pass

        return repaired

    def _self_critique(self, paper_title: str, topic: str, raw_notes: str) -> str:
        """后生成通用自审 (Self-Critique)：检查笔记完备性与一致性，自动修复缺失。

        无论是否使用 Skill，生成后都对笔记进行四维审查：
        1. 六个维度（背景/方法/实验/结果/消融/亮点）是否齐全
        2. 是否引用了具体方法名、数据、指标（不是空泛描述）
        3. 是否与论文标题和研究主题一致
        4. 是否有明显重复段落

        发现不合格项时自动调用 LLM 补全/修复，最多 1 轮自审。
        """
        critique_prompt = f"""你是严格的学术笔记质检员。请检查以下笔记的质量。

论文标题：{paper_title}
研究主题：{topic}

【质量检查清单】
1. ✅ 是否覆盖了 6 个维度（研究背景/核心方法/实验设置/关键结果/消融分析/亮点不足）？
2. ✅ 核心方法部分是否引用了具体的模型名、算法名、框架名（不是空泛的"提出了一种方法"）？
3. ✅ 关键结果部分是否列出了具体的数值指标（如准确率、F1、BLEU 等）？
4. ✅ 内容是否与论文标题「{paper_title}」切合（不是通用模板填充）？
5. ✅ 是否有明显的段落重复？

【待检查笔记】
{raw_notes}

如果发现问题，请在原文基础上**直接修复并输出完整笔记**。
如果质量合格，请**原样输出笔记，不做任何修改**。

修复规则：
- 缺失维度：根据上下文合理补充，不确定处标注"据已有信息推断"
- 空泛描述：用更具体的表述替代，或标注"原文未提供详情"
- 重复段落：合并或删除
- 不要添加额外解释，只输出最终笔记"""
        try:
            result = self.llm.chat(
                "你是严格的学术笔记质检员。直接输出质检后的完整笔记，不做额外说明。",
                critique_prompt, []
            ).strip()
            if result and len(result) > 100:
                return result
        except Exception:
            pass
        return raw_notes

    def _fallback(self, paper_title: str, abstract: str, topic: str, skill_content: str = "") -> str:
        """PDF 不可用时的降级"""
        if skill_content:
            # 通道 A：Skill 优先 — 仅给 Skill + 摘要，不附加默认格式
            prompt = f"""你是严谨的学术研究员。请基于论文的摘要信息，撰写学术笔记。

研究主题：{topic}
论文标题：{paper_title}
摘要：{abstract or '无'}

{skill_content}

核心要求：基于摘要内容如实撰写，不确定处用"据摘要显示"。直接输出笔记。"""
        else:
            # 通道 B：默认兜底 — 使用完整的默认格式
            prompt = f"""你是严谨的学术研究员。请基于论文的摘要信息，撰写简要学术笔记。

研究主题：{topic}
论文标题：{paper_title}
摘要：{abstract or '无'}

请按以下格式输出：
## 论文笔记：{paper_title}

- ### **研究背景**：该论文要解决什么问题？这个问题的来源和重要性是什么？（80字）
- ### **核心方法**：论文提出的技术核心是什么？用了什么模型/算法/框架？（150字）
- ### **实验设置**：如果有实验的话，论文的实验方法是什么？结果怎么样？如果是理工科实验，论文在什么数据上做了什么实验？和哪些基线比？（80字）
- ### **关键结果**：主要发现和实验结论是什么？（100字）
- ### **与研究主题的关联**：该论文如何支撑「{topic}」的研究？（60字）
- ### **亮点与不足**：主要贡献、创新点以及潜在局限（60字）

写作要求：基于摘要内容如实撰写，不确定处用"据摘要显示"。直接输出笔记。"""
        try:
            return self.llm.chat("你是学术研究员。", prompt, []).strip()
        except Exception:
            return f"## 论文笔记：{paper_title}\n\n- **核心方法**：（暂无详细信息）\n- **关键发现**：{abstract or '暂无摘要'}"

    def _fallback_bm25(
        self, pdf_path: str, paper_title: str, abstract: str, topic: str, skill_content: str = ""
    ) -> str:
        """Embedding 不可用时降级为 BM25"""
        from tools.retriever import BM25Retriever
        from tools.pdf_tools import extract_full_text_from_pdf

        blocks = extract_full_text_from_pdf(pdf_path)
        if not blocks:
            return self._fallback(paper_title, abstract, topic, skill_content)

        retriever = BM25Retriever()
        retriever.index(blocks)

        sections_out = []
        for section in self.SECTIONS:
            query = f"{paper_title} {abstract[:200]} {topic} {' '.join(section['query_keywords'])}"
            passages = retriever.search(query, top_k=3)
            rag_text = "\n\n".join(
                f"【第{p['page']}页】{p['text'][:400]}" for p in passages
            ) if passages else abstract

            if skill_content:
                # 通道 A：Skill 优先 — 替换默认写作要求
                prompt = f"""你是学术研究员。请为论文《{paper_title}》撰写「{section['name']}」笔记。

研究主题：{topic}

{skill_content}

【原文段落】
{rag_text}

核心要求：至少 {section['min_words']} 字，只输出笔记内容。"""
            else:
                # 通道 B：默认兜底
                prompt = f"""你是学术研究员。请为论文《{paper_title}》撰写「{section['name']}」笔记。

研究主题：{topic}

【原文段落】
{rag_text}

要求：以一段连贯的文字输出（{section['min_words']}字），引用原文中的具体方法/数据/结论。只输出笔记内容，不要编号列表。"""
            try:
                note = self.llm.chat("你是严谨的学术研究员。", prompt, []).strip()
            except Exception:
                note = "（生成失败）"
            sections_out.append(f"- **{section['name']}**：{note}")

        return f"## 论文笔记：{paper_title}\n\n" + "\n\n".join(sections_out)

