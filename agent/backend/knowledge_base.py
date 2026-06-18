"""
全局知识库 — 跨 Session 知识共享

扫描所有 Session 的论文、笔记、综述草稿，建立全局索引，
支持跨 Session 的 BM25 文本检索，为首页全局对话提供 RAG 能力。
"""

import json
import re
import datetime
from pathlib import Path
from typing import Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class GlobalKnowledgeBase:
    """全局知识库，聚合所有 Session 的数据"""

    def __init__(self, sessions_dir: str):
        self.sessions_dir = Path(sessions_dir)
        self._vectorizer: Optional[TfidfVectorizer] = None
        self._matrix: Optional[np.ndarray] = None
        self._chunks: list[dict] = []
        self._stats: dict = {}
        self._last_build: Optional[str] = None

    # ━━━ 索引构建 ━━━

    def build_index(self, force: bool = False) -> dict:
        """扫描所有 Session 并构建全局 BM25 索引。返回统计信息。"""
        if not force and self._chunks and self._last_build:
            # 简单检查：sessions 目录是否有新 session
            current_dirs = set(d.name for d in self._iter_session_dirs())
            if len(current_dirs) <= len(self._stats.get("session_ids", [])):
                return self._stats

        all_chunks = []
        session_papers = {}  # session_id -> list of paper summaries
        total_papers = 0
        total_notes_chars = 0
        total_drafts = 0
        session_ids = []

        for session_dir in self._iter_session_dirs():
            sid = session_dir.name
            session_ids.append(sid)

            # 加载元数据
            meta = self._read_json(session_dir / "metadata.json")
            topic = meta.get("topic", "") if meta else ""

            # 加载论文列表
            papers = self._read_json(session_dir / "papers" / "papers_list.json") or []
            session_papers[sid] = []
            for p in papers:
                pid = p.get("paper_id", "")
                title = p.get("title", "")
                abstract = p.get("abstract", p.get("summary", ""))
                authors = p.get("authors", "")
                source = p.get("source", "")

                # 论文摘要作为可检索块
                if abstract:
                    all_chunks.append({
                        "text": f"[论文] {title}\n作者：{authors}\n摘要：{abstract}",
                        "session_id": sid,
                        "topic": topic,
                        "paper_id": pid,
                        "title": title,
                        "type": "paper_abstract",
                    })
                session_papers[sid].append({
                    "paper_id": pid,
                    "title": title,
                    "authors": authors,
                    "source": source,
                })
                total_papers += 1

            # 加载笔记
            notes_path = session_dir / "notes" / "draft_notes.md"
            if notes_path.exists():
                notes_text = notes_path.read_text(encoding="utf-8")
                total_notes_chars += len(notes_text)
                # 按 ## 标题分块
                note_sections = re.split(r"\n(?=## )", notes_text)
                for sec in note_sections:
                    sec = sec.strip()
                    if len(sec) > 50:
                        all_chunks.append({
                            "text": f"[笔记] 主题：{topic}\n{sec[:2000]}",
                            "session_id": sid,
                            "topic": topic,
                            "type": "note",
                        })

            # 加载综述草稿
            draft_dir = session_dir / "draft"
            if draft_dir.exists():
                draft_files = sorted(draft_dir.glob("draft_v*.md"), reverse=True)
                if draft_files:
                    draft_text = draft_files[0].read_text(encoding="utf-8")
                    total_drafts += 1
                    # 按 ## 标题分块
                    draft_sections = re.split(r"\n(?=## )", draft_text)
                    for sec in draft_sections:
                        sec = sec.strip()
                        if len(sec) > 50:
                            all_chunks.append({
                                "text": f"[综述] 主题：{topic}\n{sec[:2000]}",
                                "session_id": sid,
                                "topic": topic,
                                "type": "draft",
                            })

        self._chunks = all_chunks
        self._stats = {
            "session_count": len(session_ids),
            "session_ids": session_ids,
            "total_papers": total_papers,
            "total_notes_chars": total_notes_chars,
            "total_drafts": total_drafts,
            "total_chunks": len(all_chunks),
            "session_papers": session_papers,
        }
        self._last_build = datetime.datetime.now().isoformat()

        # 构建 BM25 索引
        if all_chunks:
            texts = [c["text"] for c in all_chunks]
            self._vectorizer = TfidfVectorizer(
                tokenizer=self._tokenize,
                max_features=8000,
                ngram_range=(1, 2),
            )
            try:
                self._matrix = self._vectorizer.fit_transform(texts)
            except ValueError:
                self._vectorizer = TfidfVectorizer(max_features=1000)
                self._matrix = self._vectorizer.fit_transform(texts)
        else:
            self._vectorizer = None
            self._matrix = None

        return self._stats

    # ━━━ 检索 ━━━

    def search(self, query: str, top_k: int = 8) -> list[dict]:
        """跨 Session 检索，返回 Top-K 相关片段"""
        if not self._chunks or self._matrix is None or self._vectorizer is None:
            self.build_index(force=True)
            if not self._chunks:
                return []

        try:
            query_vec = self._vectorizer.transform([query])
            scores = cosine_similarity(query_vec, self._matrix).flatten()
            top_indices = np.argsort(scores)[::-1][:top_k]

            results = []
            for idx in top_indices:
                score = float(scores[idx])
                if score < 0.02:
                    continue
                chunk = dict(self._chunks[idx])
                chunk["score"] = round(score, 4)
                # 截断过长文本
                if len(chunk.get("text", "")) > 1500:
                    chunk["text"] = chunk["text"][:1500] + "..."
                results.append(chunk)
            return results
        except Exception:
            return []

    # ━━━ 统计 ━━━

    def get_stats(self) -> dict:
        """获取全局知识库统计信息"""
        if not self._stats:
            self.build_index()
        return {
            "session_count": self._stats.get("session_count", 0),
            "total_papers": self._stats.get("total_papers", 0),
            "total_notes_chars": self._stats.get("total_notes_chars", 0),
            "total_drafts": self._stats.get("total_drafts", 0),
            "total_chunks": self._stats.get("total_chunks", 0),
            "last_build": self._last_build,
        }

    def get_session_summaries(self) -> list[dict]:
        """获取所有 Session 的摘要列表（供前端展示）"""
        if not self._stats:
            self.build_index()
        summaries = []
        for sid in self._stats.get("session_ids", []):
            session_dir = self.sessions_dir / sid
            meta = self._read_json(session_dir / "metadata.json")
            if not meta:
                continue
            papers = self._stats.get("session_papers", {}).get(sid, [])
            summaries.append({
                "session_id": sid,
                "topic": meta.get("topic", "") if meta else "",
                "state": meta.get("state", "") if meta else "",
                "paper_count": len(papers),
                "created_at": meta.get("created_at", "") if meta else "",
            })
        return summaries

    # ━━━ 辅助 ━━━

    def _iter_session_dirs(self) -> list[Path]:
        """Return only real user session directories, excluding internal stores."""
        if not self.sessions_dir.exists():
            return []
        return [
            d for d in sorted(self.sessions_dir.iterdir(), reverse=True)
            if d.is_dir() and not d.name.startswith(".") and (d / "metadata.json").exists()
        ]

    @staticmethod
    def _read_json(path: Path) -> Optional[dict | list]:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, Exception):
                return None
        return None

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """中英文混合分词"""
        tokens = []
        eng_words = re.findall(r"[a-zA-Z]+(?:-[a-zA-Z]+)*", text.lower())
        tokens.extend(eng_words)
        chinese = re.sub(r"[^\u4e00-\u9fff]", "", text)
        for i in range(len(chinese) - 1):
            tokens.append(chinese[i:i + 2])
        tokens.extend(list(chinese))
        return tokens
