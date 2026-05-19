"""
SessionManager - 迭代三核心：会话状态管理与数据持久化

管理 Session 的完整生命周期：
- 创建/加载/更新 Session
- 论文列表、笔记、综述草稿的 CRUD
- 状态机转换
- 用户上传论文的三种方式
"""

import json
import os
import uuid
import shutil
import datetime
from pathlib import Path
from typing import Any, Optional
from enum import Enum


# ━━━━━ 状态机枚举 ━━━━━
class SessionState(Enum):
    PLANNING = "planning"
    PLAN_CONFIRMED = "plan_confirmed"
    SEARCHING = "searching"
    SEARCH_COMPLETE = "search_complete"
    REVIEWING_NOTES = "reviewing_notes"
    WRITING = "writing"
    REVIEWING_DRAFT = "reviewing_draft"
    COMPLETE = "complete"


# 合法的状态转移映射
VALID_TRANSITIONS = {
    SessionState.PLANNING: [SessionState.PLAN_CONFIRMED],
    SessionState.PLAN_CONFIRMED: [SessionState.SEARCHING, SessionState.PLANNING],
    SessionState.SEARCHING: [SessionState.SEARCH_COMPLETE],
    SessionState.SEARCH_COMPLETE: [SessionState.REVIEWING_NOTES, SessionState.SEARCHING],
    SessionState.REVIEWING_NOTES: [SessionState.WRITING],
    SessionState.WRITING: [SessionState.REVIEWING_DRAFT],
    SessionState.REVIEWING_DRAFT: [SessionState.WRITING, SessionState.COMPLETE],
    SessionState.COMPLETE: [],
}

# 状态中文标签
STATE_LABELS = {
    "planning": "规划中",
    "plan_confirmed": "关键词已确认",
    "searching": "搜索中",
    "search_complete": "搜索完成",
    "reviewing_notes": "笔记审核中",
    "writing": "撰写中",
    "reviewing_draft": "初稿评审中",
    "complete": "已完成",
}


class SessionManager:
    """Session 生命周期管理器"""

    def __init__(self, sessions_root: str):
        """
        Args:
            sessions_root: Session 存储根目录，如 agent/sessions/
        """
        self.root = Path(sessions_root)
        self.root.mkdir(parents=True, exist_ok=True)

    # ━━━━━ 基础 CRUD ━━━━━

    def create_session(self, topic: str, keywords: list = None) -> dict:
        """创建新 Session，生成唯一 ID 和完整目录结构
        keywords: 可选的初始关键词列表（字符串或已结构化数组）
        """
        session_id = f"sess_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        session_dir = self.root / session_id

        # 创建目录结构
        (session_dir / "plan").mkdir(parents=True, exist_ok=True)
        (session_dir / "papers").mkdir(parents=True, exist_ok=True)
        (session_dir / "notes").mkdir(parents=True, exist_ok=True)
        (session_dir / "draft").mkdir(parents=True, exist_ok=True)
        (session_dir / "traces").mkdir(parents=True, exist_ok=True)

        now = datetime.datetime.now().isoformat()
        initial_state = SessionState.PLAN_CONFIRMED.value if keywords else SessionState.PLANNING.value
        metadata = {
            "session_id": session_id,
            "topic": topic,
            "state": initial_state,
            "created_at": now,
            "updated_at": now,
            "rewrite_count": 0,
        }
        self._write_json(session_dir / "metadata.json", metadata)

        # 保存初始关键词（如果有）到 plan/confirmed_keywords.json
        if keywords:
            # Normalize keywords: accept comma/newline separated string or list of dicts/strings
            norm = []
            if isinstance(keywords, str):
                parts = [p.strip() for p in keywords.replace('，', ',').split(',') if p.strip()]
                norm = [{"original": p, "english": "", "synonyms": ""} for p in parts]
            elif isinstance(keywords, list):
                for k in keywords:
                    if isinstance(k, str):
                        norm.append({"original": k, "english": "", "synonyms": ""})
                    elif isinstance(k, dict):
                        norm.append(k)
            if norm:
                self._write_json(session_dir / "plan" / "confirmed_keywords.json", norm)

        return self.load_session(session_id)

    def load_session(self, session_id: str) -> Optional[dict]:
        """从磁盘加载完整 Session 状态"""
        session_dir = self.root / session_id
        if not session_dir.exists():
            return None

        metadata = self._read_json(session_dir / "metadata.json")
        if not metadata:
            return None

        # 加载关键词
        keywords = self._read_json(session_dir / "plan" / "confirmed_keywords.json") or []

        # 加载论文列表
        papers = self._read_json(session_dir / "papers" / "papers_list.json") or []

        # 加载笔记
        notes_path = session_dir / "notes" / "draft_notes.md"
        notes = notes_path.read_text(encoding="utf-8") if notes_path.exists() else ""

        # 加载初始规划
        plan_path = session_dir / "plan" / "initial_plan.md"
        initial_plan = plan_path.read_text(encoding="utf-8") if plan_path.exists() else ""

        # 加载最新草稿
        draft = ""
        draft_version = 0
        draft_dir = session_dir / "draft"
        if draft_dir.exists():
            draft_files = sorted(draft_dir.glob("draft_v*.md"), reverse=True)
            if draft_files:
                draft = draft_files[0].read_text(encoding="utf-8")
                # 从文件名提取版本号
                import re
                m = re.search(r"draft_v(\d+)", draft_files[0].name)
                if m:
                    draft_version = int(m.group(1))

        # 加载轨迹
        traces = self._read_json(session_dir / "traces" / "run_traces.json") or []

        return {
            "session_id": metadata.get("session_id", session_id),
            "topic": metadata.get("topic", ""),
            "state": metadata.get("state", "planning"),
            "created_at": metadata.get("created_at", ""),
            "updated_at": metadata.get("updated_at", ""),
            "rewrite_count": metadata.get("rewrite_count", 0),
            "initial_plan": initial_plan,
            "keywords": keywords,
            "papers": papers,
            "notes": notes,
            "draft": draft,
            "draft_version": draft_version,
            "traces": traces,
        }

    def list_sessions(self) -> list[dict]:
        """列出所有 Session 摘要"""
        sessions = []
        for d in sorted(self.root.iterdir(), reverse=True):
            if not d.is_dir():
                continue
            meta = self._read_json(d / "metadata.json")
            if meta:
                # attempt to include quick metrics: paper count and note size
                papers = self._read_json(d / "papers" / "papers_list.json") or []
                notes_path = d / "notes" / "draft_notes.md"
                note_size = notes_path.stat().st_size if notes_path.exists() else 0
                sessions.append({
                    "session_id": meta.get("session_id", d.name),
                    "topic": meta.get("topic", ""),
                    "state": meta.get("state", "planning"),
                    "state_label": STATE_LABELS.get(meta.get("state", ""), "未知"),
                    "created_at": meta.get("created_at", ""),
                    "updated_at": meta.get("updated_at", ""),
                    "paper_count": len(papers),
                    "note_size": note_size,
                })
        return sessions

    def update_session_state(self, session_id: str, new_state: str) -> dict:
        """更新 Session 状态（带状态机校验）"""
        session = self.load_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} 不存在")

        current = SessionState(session["state"])
        target = SessionState(new_state)

        # 校验状态转移合法性
        if target not in VALID_TRANSITIONS.get(current, []):
            allowed = [s.value for s in VALID_TRANSITIONS.get(current, [])]
            raise ValueError(
                f"非法状态转移：{current.value} → {target.value}。"
                f"允许的转移：{allowed}"
            )

        session_dir = self.root / session_id
        metadata = self._read_json(session_dir / "metadata.json") or {}
        metadata["state"] = new_state
        metadata["updated_at"] = datetime.datetime.now().isoformat()
        self._write_json(session_dir / "metadata.json", metadata)

        return self.load_session(session_id)

    def delete_session(self, session_id: str) -> bool:
        """删除整个 Session 目录"""
        session_dir = self.root / session_id
        if session_dir.exists():
            shutil.rmtree(session_dir)
            return True
        return False

    # ━━━━━ 关键词管理 ━━━━━

    def save_keywords(self, session_id: str, keywords: list[dict]) -> dict:
        """保存用户确认后的关键词列表"""
        session_dir = self.root / session_id
        if not session_dir.exists():
            raise ValueError(f"Session {session_id} 不存在")

        self._write_json(session_dir / "plan" / "confirmed_keywords.json", keywords)

        # 更新元数据时间
        self._touch_metadata(session_dir)
        return self.load_session(session_id)

    def save_initial_plan(self, session_id: str, plan_md: str) -> None:
        """保存初始规划 Markdown"""
        session_dir = self.root / session_id
        if not session_dir.exists():
            raise ValueError(f"Session {session_id} 不存在")
        (session_dir / "plan" / "initial_plan.md").write_text(plan_md, encoding="utf-8")

    # ━━━━━ 论文管理 ━━━━━

    def get_papers(self, session_id: str) -> list[dict]:
        """获取论文列表"""
        session_dir = self.root / session_id
        if not session_dir.exists():
            return []
        return self._read_json(session_dir / "papers" / "papers_list.json") or []

    def save_papers_list(self, session_id: str, papers: list[dict]) -> None:
        """保存论文列表（自动标准化）"""
        session_dir = self.root / session_id
        if not session_dir.exists():
            raise ValueError(f"Session {session_id} 不存在")
        self._write_json(session_dir / "papers" / "papers_list.json", self._normalize_papers(papers))
        self._touch_metadata(session_dir)

    def add_paper(self, session_id: str, paper: dict) -> dict:
        """添加单篇论文到列表（去重 + 标准化字段）"""
        papers = self.get_papers(session_id)
        paper_id = paper.get("paper_id", "")
        # 去重
        if not any(p.get("paper_id") == paper_id for p in papers):
            # 标准化所有字段
            norm = {
                "paper_id": paper_id,
                "title": paper.get("title", ""),
                "authors": paper.get("authors", ""),
                "source": paper.get("source", "agent_search"),
                "source_type": paper.get("source_type", ""),
                "status": paper.get("status", "pending"),
                "added_at": paper.get("added_at", datetime.datetime.now().isoformat()),
                "abstract": paper.get("abstract", paper.get("summary", "")),
                "notes": paper.get("notes", ""),
                "has_notes": paper.get("has_notes", False),
            }
            papers.append(norm)
            self.save_papers_list(session_id, papers)
        return self.load_session(session_id)

    def delete_paper(self, session_id: str, paper_id: str) -> dict:
        """删除单篇论文"""
        papers = self.get_papers(session_id)
        papers = [p for p in papers if p.get("paper_id") != paper_id]
        self.save_papers_list(session_id, papers)

        # 同时清理 PDF 文件
        paper_dir = self.root / session_id / "papers" / paper_id
        if paper_dir.exists():
            shutil.rmtree(paper_dir)

        return self.load_session(session_id)

    def batch_delete_papers(self, session_id: str, paper_ids: list[str]) -> dict:
        """批量删除论文"""
        papers = self.get_papers(session_id)
        papers = [p for p in papers if p.get("paper_id") not in paper_ids]
        self.save_papers_list(session_id, papers)

        for pid in paper_ids:
            paper_dir = self.root / session_id / "papers" / pid
            if paper_dir.exists():
                shutil.rmtree(paper_dir)

        return self.load_session(session_id)

    def update_paper_status(self, session_id: str, paper_id: str, status: str) -> dict:
        """更新论文审查状态（accepted/rejected/pending）"""
        papers = self.get_papers(session_id)
        for p in papers:
            if p.get("paper_id") == paper_id:
                p["status"] = status
                break
        self.save_papers_list(session_id, papers)
        return self.load_session(session_id)
    def update_paper_notes(self, session_id: str, paper_id: str, notes: str) -> dict:
        """保存单篇论文的独立笔记"""
        papers = self.get_papers(session_id)
        for p in papers:
            if p.get("paper_id") == paper_id:
                p["notes"] = notes
                p["has_notes"] = bool(notes.strip())
                break
        self.save_papers_list(session_id, papers)
        return self.load_session(session_id)

    def batch_update_paper_notes(self, session_id: str, paper_notes_map: dict) -> dict:
        """批量更新多篇论文的笔记：{paper_id: notes_text}"""
        papers = self.get_papers(session_id)
        for p in papers:
            pid = p.get("paper_id", "")
            if pid in paper_notes_map:
                p["notes"] = paper_notes_map[pid]
                p["has_notes"] = bool(paper_notes_map[pid].strip())
        self.save_papers_list(session_id, papers)
        return self.load_session(session_id)

    def _normalize_papers(self, papers: list[dict]) -> list[dict]:
        """标准化 papers 列表，确保每条都包含所有必需字段"""
        for p in papers:
            p.setdefault("title", "")
            p.setdefault("authors", "")
            p.setdefault("source", "agent_search")
            p.setdefault("source_type", "")
            p.setdefault("status", "pending")
            p.setdefault("abstract", "")
            p.setdefault("notes", "")
            p.setdefault("has_notes", False)
        return papers
    def get_paper_dir(self, session_id: str, paper_id: str) -> Path:
        """获取某篇论文的存储目录"""
        paper_dir = self.root / session_id / "papers" / paper_id
        paper_dir.mkdir(parents=True, exist_ok=True)
        return paper_dir

    # ━━━━━ 笔记管理 ━━━━━

    def get_notes(self, session_id: str) -> str:
        """获取笔记草稿"""
        notes_path = self.root / session_id / "notes" / "draft_notes.md"
        if notes_path.exists():
            return notes_path.read_text(encoding="utf-8")
        return ""

    def save_notes(self, session_id: str, content: str, version_note: str = "") -> dict:
        """保存笔记（带版本备份）"""
        session_dir = self.root / session_id
        if not session_dir.exists():
            raise ValueError(f"Session {session_id} 不存在")

        notes_path = session_dir / "notes" / "draft_notes.md"
        history_dir = session_dir / "notes" / "edit_history"
        history_dir.mkdir(parents=True, exist_ok=True)

        # 如果已有笔记，先备份
        if notes_path.exists():
            old_content = notes_path.read_text(encoding="utf-8")
            if old_content.strip() != content.strip():
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = history_dir / f"notes_v{ts}.md"
                backup_path.write_text(old_content, encoding="utf-8")
                # 记录编辑历史
                edit_log = {
                    "timestamp": ts,
                    "version_note": version_note,
                    "size_before": len(old_content),
                    "size_after": len(content),
                }
                log_path = history_dir / "edit_log.json"
                logs = self._read_json(log_path) or []
                logs.append(edit_log)
                self._write_json(log_path, logs)

        notes_path.write_text(content, encoding="utf-8")
        self._touch_metadata(session_dir)
        return self.load_session(session_id)

    # ━━━━━ 草稿管理 ━━━━━

    def get_draft(self, session_id: str, version: int = None) -> str:
        """获取综述草稿（默认最新版本）"""
        draft_dir = self.root / session_id / "draft"
        if not draft_dir.exists():
            return ""

        if version is not None:
            draft_path = draft_dir / f"draft_v{version}.md"
            return draft_path.read_text(encoding="utf-8") if draft_path.exists() else ""

        # 获取最新版本
        draft_files = sorted(draft_dir.glob("draft_v*.md"), reverse=True)
        if draft_files:
            return draft_files[0].read_text(encoding="utf-8")
        return ""

    def save_draft(self, session_id: str, content: str, version: int = None) -> dict:
        """保存综述草稿"""
        session_dir = self.root / session_id
        if not session_dir.exists():
            raise ValueError(f"Session {session_id} 不存在")

        draft_dir = session_dir / "draft"
        draft_dir.mkdir(parents=True, exist_ok=True)

        if version is None:
            # 自动计算下一个版本号
            existing = list(draft_dir.glob("draft_v*.md"))
            version = len(existing) + 1

        draft_path = draft_dir / f"draft_v{version}.md"
        draft_path.write_text(content, encoding="utf-8")

        # 更新重写计数
        metadata = self._read_json(session_dir / "metadata.json") or {}
        metadata["rewrite_count"] = version - 1
        metadata["updated_at"] = datetime.datetime.now().isoformat()
        self._write_json(session_dir / "metadata.json", metadata)

        return self.load_session(session_id)

    def save_feedback(self, session_id: str, feedback: str) -> dict:
        """保存用户反馈"""
        session_dir = self.root / session_id
        if not session_dir.exists():
            raise ValueError(f"Session {session_id} 不存在")

        feedback_path = session_dir / "draft" / "user_feedback.md"
        feedback_path.write_text(feedback, encoding="utf-8")
        return self.load_session(session_id)

    def get_feedback(self, session_id: str) -> str:
        """获取用户反馈"""
        feedback_path = self.root / session_id / "draft" / "user_feedback.md"
        if feedback_path.exists():
            return feedback_path.read_text(encoding="utf-8")
        return ""

    # ━━━━━ 轨迹管理 ━━━━━

    def save_traces(self, session_id: str, traces: list[dict]) -> None:
        """保存 Agent 运行轨迹"""
        session_dir = self.root / session_id
        if not session_dir.exists():
            raise ValueError(f"Session {session_id} 不存在")
        self._write_json(session_dir / "traces" / "run_traces.json", traces)

    # ━━━━━ 工具方法 ━━━━━

    def _read_json(self, path: Path) -> Optional[Any]:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, Exception):
                return None
        return None

    def _write_json(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _touch_metadata(self, session_dir: Path) -> None:
        metadata = self._read_json(session_dir / "metadata.json") or {}
        metadata["updated_at"] = datetime.datetime.now().isoformat()
        self._write_json(session_dir / "metadata.json", metadata)
