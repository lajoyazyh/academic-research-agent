"""
BM25 检索器 — 迭代三 RAG 升级

基于 sklearn TfidfVectorizer 实现轻量级 BM25 检索，
不需要外部向量数据库，直接从 PDF 段落块中检索与 query 最相关的 Top-K 段落。
"""

import re
import numpy as np
from typing import Any
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class BM25Retriever:
    """轻量级 BM25 检索器"""

    def __init__(self):
        self.vectorizer: TfidfVectorizer | None = None
        self.chunks: list[dict] = []
        self.matrix: np.ndarray | None = None

    def index(self, chunks: list[dict]) -> int:
        """
        构建检索索引。
        chunks: 来自 extract_full_text_from_pdf 的段落块列表。
        返回索引的段落数。
        """
        if not chunks:
            self.chunks = []
            self.matrix = None
            self.vectorizer = None
            return 0

        self.chunks = chunks
        texts = [c["text"] for c in chunks]

        # 中文 + 英文混合分词
        self.vectorizer = TfidfVectorizer(
            tokenizer=self._tokenize,
            max_features=5000,
            stop_words=None,
            ngram_range=(1, 2),
        )
        try:
            self.matrix = self.vectorizer.fit_transform(texts)
        except ValueError:
            # 文本太少时降级
            self.vectorizer = TfidfVectorizer(max_features=1000)
            self.matrix = self.vectorizer.fit_transform(texts)

        return len(chunks)

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """
        检索与 query 最相关的 Top-K 段落。
        返回带相似度分数的段落列表。
        """
        if not self.chunks or self.matrix is None or self.vectorizer is None:
            return []

        try:
            query_vec = self.vectorizer.transform([query])
            scores = cosine_similarity(query_vec, self.matrix).flatten()
            top_indices = np.argsort(scores)[::-1][:top_k]

            results = []
            for idx in top_indices:
                score = float(scores[idx])
                if score < 0.01:  # 过滤完全不相关的结果
                    continue
                chunk = dict(self.chunks[idx])
                chunk["score"] = round(score, 4)
                results.append(chunk)
            return results
        except Exception:
            return []

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """中英文混合分词"""
        tokens = []
        # 英文单词
        eng_words = re.findall(r"[a-zA-Z]+(?:-[a-zA-Z]+)*", text.lower())
        tokens.extend(eng_words)
        # 中文按 2-gram 字符切分
        chinese = re.sub(r"[^\u4e00-\u9fff]", "", text)
        for i in range(len(chinese) - 1):
            tokens.append(chinese[i:i + 2])
        # 单个中文字符
        tokens.extend(list(chinese))
        return tokens


# ━━━━━ 全局检索器缓存（按 session_id）━━━━━
_RETRIEVER_CACHE: dict[str, BM25Retriever] = {}


def get_retriever_for_session(session_id: str, papers_dir: str) -> BM25Retriever:
    """
    获取某个 Session 的 BM25 检索器（懒加载 + 缓存）。
    """
    if session_id in _RETRIEVER_CACHE:
        return _RETRIEVER_CACHE[session_id]

    from tools.pdf_tools import extract_all_session_pdfs

    retriever = BM25Retriever()
    chunks = extract_all_session_pdfs(session_id, papers_dir)
    count = retriever.index(chunks)

    if count > 0:
        _RETRIEVER_CACHE[session_id] = retriever
    return retriever


def invalidate_retriever_cache(session_id: str = None):
    """清除检索器缓存"""
    if session_id:
        _RETRIEVER_CACHE.pop(session_id, None)
    else:
        _RETRIEVER_CACHE.clear()


def search_session_papers(session_id: str, papers_dir: str, query: str, top_k: int = 5) -> list[dict]:
    """
    一站式检索：提取 PDF → 索引 → 检索 → 返回 Top-K 段落。
    """
    retriever = get_retriever_for_session(session_id, papers_dir)
    return retriever.search(query, top_k)
