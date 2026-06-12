"""
RAG 笔记生成器 — 迭代三阶段三升级

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
            return self._fallback(paper_title, abstract, topic, skill_content)

        # 2. 用 Embedding API 向量化
        texts = [b["text"][:800] for b in blocks]  # 截断过长的段落
        try:
            vecs = self.llm.embed(texts)
        except Exception:
            # 降级：用 BM25
            return self._fallback_bm25(pdf_path, paper_title, abstract, topic, skill_content)

        embeddings = np.array(vecs, dtype=np.float32)
        if embeddings.shape[1] < 10:
            # 零向量降级 → 用 BM25
            return self._fallback_bm25(pdf_path, paper_title, abstract, topic, skill_content)

        # 3. 逐节检索 + 生成
        sections_output = []
        for section in self.SECTIONS:
            section_text = self._generate_section(
                section, blocks, embeddings, paper_title, abstract, topic, skill_content
            )
            sections_output.append(f"- **{section['name']}**：{section_text}")

        body = "\n\n".join(sections_output)
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
            query_vecs = self.llm.embed([query[:1000]])
            query_emb = np.array(query_vecs, dtype=np.float32)
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
            prompt = f"""你是严谨的学术研究员。请为以下论文撰写「{section['name']}」部分的笔记。

研究主题：{topic}
论文标题：{paper_title}

{skill_content}

【检索到的论文原文段落】
{rag_text}

核心要求：至少 {section['min_words']} 字，只输出笔记内容本身，不要加标题前缀或解释。"""
        else:
            # 通道 B：默认兜底 — 使用完整的默认格式要求（现有逻辑不变）
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

        try:
            result = self.llm.chat(
                "你是严谨的学术研究员。只输出笔记内容。",
                prompt, []
            ).strip()
            return result
        except Exception:
            return f"（生成失败）"

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
