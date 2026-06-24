"""
BM25 + Embedding 混合检索器 — RAG upgrade

基于 sklearn TfidfVectorizer 实现轻量级 BM25 检索 + 智谱 Embedding 向量语义检索，
混合打分：score = 0.3 * BM25_score + 0.7 * embedding_score，
不需要外部向量数据库，直接从 PDF 段落块中检索与 query 最相关的 Top-K 段落。
"""

import re
import hashlib
import json
import numpy as np
from pathlib import Path
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


class HybridRetriever:
    """BM25 + Embedding 混合检索器

    混合打分：score = 0.3 * BM25_score + 0.7 * embedding_score
    Embedding 向量首次计算后缓存到磁盘，后续复用。
    """

    _EMBED_CACHE_DIR = None  # 类级别缓存目录

    def __init__(self):
        self.bm25 = BM25Retriever()
        self._embedding_vectors: np.ndarray | None = None
        self._embed_cache_path: Path | None = None

    def index(self, chunks: list[dict], cache_key: str = "") -> int:
        """构建 BM25 索引，Embedding 向量延迟计算。"""
        count = self.bm25.index(chunks)
        if cache_key and count > 0:
            # 设置 Embedding 缓存路径
            if HybridRetriever._EMBED_CACHE_DIR is None:
                from pathlib import Path as _Path
                HybridRetriever._EMBED_CACHE_DIR = _Path(__file__).resolve().parent.parent / "sessions" / ".embed_cache"
            HybridRetriever._EMBED_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            safe_key = hashlib.md5(cache_key.encode()).hexdigest()[:16]
            self._embed_cache_path = HybridRetriever._EMBED_CACHE_DIR / f"{safe_key}.npy"
            # 尝试加载缓存
            if self._embed_cache_path.exists():
                try:
                    self._embedding_vectors = np.load(str(self._embed_cache_path))
                except Exception:
                    self._embedding_vectors = None
        return count

    def _ensure_embeddings(self) -> None:
        """确保 Embedding 向量已计算（懒加载 + 缓存）"""
        if self._embedding_vectors is not None:
            return
        if not self.bm25.chunks:
            return

        from llms.client import LLMClient
        llm = LLMClient()
        texts = [c["text"] for c in self.bm25.chunks]
        batch_size = 20
        all_vectors = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            try:
                vecs = llm.embed(batch)
                all_vectors.extend(vecs)
            except Exception:
                # 降级：用零向量填充
                all_vectors.extend([[0.0] * 1536 for _ in batch])

        if all_vectors:
            self._embedding_vectors = np.array(all_vectors, dtype=np.float32)
            # 写入缓存
            if self._embed_cache_path:
                try:
                    np.save(str(self._embed_cache_path), self._embedding_vectors)
                except Exception:
                    pass

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """混合检索：BM25 + Embedding 加权融合"""
        if not self.bm25.chunks:
            return []

        # 1. BM25 检索
        bm25_results = self.bm25.search(query, top_k=min(top_k * 3, len(self.bm25.chunks)))

        # 2. Embedding 语义检索
        self._ensure_embeddings()
        if self._embedding_vectors is not None and len(self._embedding_vectors) > 0:
            try:
                from llms.client import LLMClient
                llm = LLMClient()
                query_vecs = llm.embed([query])
                if query_vecs and not all(v == 0.0 for v in query_vecs[0]):
                    query_vec = np.array(query_vecs[0], dtype=np.float32)
                    # 余弦相似度
                    q_norm = query_vec / (np.linalg.norm(query_vec) + 1e-10)
                    d_norm = self._embedding_vectors / (np.linalg.norm(self._embedding_vectors, axis=1, keepdims=True) + 1e-10)
                    embed_scores = np.dot(d_norm, q_norm)

                    # 3. 混合打分：0.3 * BM25 + 0.7 * Embedding
                    bm25_score_map = {}
                    for r in bm25_results:
                        # 用 text 内容做 key 匹配
                        bm25_score_map[r.get("text", "")[:80]] = r.get("score", 0)

                    combined = []
                    for idx, chunk in enumerate(self.bm25.chunks):
                        bm25_s = bm25_score_map.get(chunk.get("text", "")[:80], 0)
                        embed_s = float(embed_scores[idx]) if idx < len(embed_scores) else 0
                        hybrid_s = 0.3 * bm25_s + 0.7 * embed_s
                        if hybrid_s > 0.01:
                            combined.append((hybrid_s, idx))

                    combined.sort(key=lambda x: x[0], reverse=True)
                    top_indices = [idx for _, idx in combined[:top_k]]

                    results = []
                    for idx in top_indices:
                        chunk = dict(self.bm25.chunks[idx])
                        chunk["score"] = round(combined[top_indices.index(idx)][0], 4)
                        results.append(chunk)
                    return results
            except Exception:
                pass

        # Fallback: 纯 BM25
        return bm25_results[:top_k]


# ━━━━━ 全局检索器缓存（按 session_id）━━━━━
_RETRIEVER_CACHE: dict[str, HybridRetriever] = {}


def get_retriever_for_session(session_id: str, papers_dir: str) -> HybridRetriever:
    """
    获取某个 Session 的混合检索器（懒加载 + 缓存）。
    """
    if session_id in _RETRIEVER_CACHE:
        return _RETRIEVER_CACHE[session_id]

    from tools.pdf_tools import extract_all_session_pdfs

    retriever = HybridRetriever()
    chunks = extract_all_session_pdfs(session_id, papers_dir)
    count = retriever.index(chunks, cache_key=session_id)

    if count > 0:
        _RETRIEVER_CACHE[session_id] = retriever
    return retriever


def invalidate_retriever_cache(session_id: str = None):
    """清除检索器缓存（含 Embedding 缓存）"""
    if session_id:
        _RETRIEVER_CACHE.pop(session_id, None)
        # 同时清除 Embedding 磁盘缓存
        if HybridRetriever._EMBED_CACHE_DIR:
            safe_key = hashlib.md5(session_id.encode()).hexdigest()[:16]
            cache_file = HybridRetriever._EMBED_CACHE_DIR / f"{safe_key}.npy"
            if cache_file.exists():
                try:
                    cache_file.unlink()
                except Exception:
                    pass
    else:
        _RETRIEVER_CACHE.clear()


def search_session_papers(session_id: str, papers_dir: str, query: str, top_k: int = 5) -> list[dict]:
    """
    一站式混合检索：提取 PDF → 索引 → BM25 + Embedding 混合检索 → 返回 Top-K 段落。
    """
    retriever = get_retriever_for_session(session_id, papers_dir)
    return retriever.search(query, top_k)


def iterative_search(
    session_id: str,
    papers_dir: str,
    query: str,
    top_k: int = 10,
    max_rounds: int = 2,
) -> list[dict]:
    """
    迭代式混合检索：首次检索后，若结果不足或 LLM 判断需要补充，
    自动生成追问 query 进行第二轮检索，合并去重后返回。

    参数：
        session_id: 会话 ID
        papers_dir: PDF 目录路径
        query: 用户原始问题
        top_k: 每轮检索返回数量
        max_rounds: 最大检索轮数（默认 2 轮）
    
    返回：合并去重后的段落列表，按混合分数排序。
    """
    retriever = get_retriever_for_session(session_id, papers_dir)
    if not retriever.bm25.chunks:
        return []

    # 第一轮：直接用原始 query 检索
    first_results = retriever.search(query, top_k=top_k)
    if not first_results or max_rounds <= 1:
        return first_results

    # 判断是否需要第二轮检索
    # 条件：结果数量少于 top_k 的一半，或者最高分低于阈值
    need_second_round = False
    if len(first_results) < max(3, top_k // 2):
        need_second_round = True
    elif first_results and first_results[0].get("score", 0) < 0.1:
        need_second_round = True

    if not need_second_round:
        return first_results

    # 第二轮：用 LLM 生成追问 query（换一个角度）
    try:
        from llms.client import LLMClient
        llm = LLMClient()
        # 取第一轮结果的前 3 个作为上下文
        context_snippets = "\n".join([
            f"- {r.get('text', '')[:200]}" for r in first_results[:3]
        ]) if first_results else "（无）"
        
        expansion_prompt = f"""你是一个学术检索助手。用户提出了一个问题，但初次检索结果不够理想。
请基于用户的问题和已有检索片段，生成 1-2 个不同角度的检索查询（用英文关键词组合），
帮助从论文全文中找到更相关的内容。

用户问题：{query}

已有检索片段：
{context_snippets}

请直接输出检索查询，每行一个，不要加序号或解释。每个查询 5-15 个英文单词。"""
        
        raw = llm.chat("你是一个学术检索查询生成器。只输出检索查询，每行一个。", expansion_prompt, [])
        expanded_queries = [q.strip() for q in raw.strip().split("\n") if q.strip() and len(q.strip()) > 3]
        
        # 合并去重：用 text 前 80 字符做 key
        seen_keys = {r.get("text", "")[:80] for r in first_results}
        merged = list(first_results)
        
        for eq in expanded_queries[:2]:  # 最多 2 个扩展查询
            extra = retriever.search(eq, top_k=max(3, top_k // 2))
            for r in extra:
                key = r.get("text", "")[:80]
                if key not in seen_keys:
                    seen_keys.add(key)
                    merged.append(r)
        
        # 按分数重新排序
        merged.sort(key=lambda x: x.get("score", 0), reverse=True)
        return merged[:top_k]
    except Exception:
        return first_results

