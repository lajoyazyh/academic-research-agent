"""
SessionManager - Core: 会话状态管理与数据持久化

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
from backend.tenant import tenant_path


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
    SessionState.REVIEWING_NOTES: [SessionState.WRITING, SessionState.SEARCHING, SessionState.SEARCH_COMPLETE, SessionState.COMPLETE],
    SessionState.WRITING: [SessionState.REVIEWING_DRAFT, SessionState.SEARCHING],
    SessionState.REVIEWING_DRAFT: [SessionState.WRITING, SessionState.COMPLETE, SessionState.SEARCHING],
    SessionState.COMPLETE: [SessionState.SEARCHING],
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
        self._base_root = Path(sessions_root)
        self._base_root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        """Resolve storage from the authenticated request instead of sharing users."""
        return tenant_path(self._base_root)

    # ━━━━━ 基础 CRUD ━━━━━

    def create_session(self, topic: str, keywords: list = None, skills: dict = None) -> dict:
        """创建新 Session，生成唯一 ID 和完整目录结构
        keywords: 可选的初始关键词列表（字符串或已结构化数组）
        skills: 可选的自定义 Skill 配置 {"search": "skill_xxx", "notes": null, "write": null}
        """
        session_id = f"sess_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        session_dir = self.root / session_id

        # 创建目录结构
        (session_dir / "plan").mkdir(parents=True, exist_ok=True)
        (session_dir / "papers").mkdir(parents=True, exist_ok=True)
        (session_dir / "notes").mkdir(parents=True, exist_ok=True)
        (session_dir / "review").mkdir(parents=True, exist_ok=True)
        (session_dir / "repositories").mkdir(parents=True, exist_ok=True)
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
            "skills": skills or {},
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
        """从磁盘加载完整 Session 状态，自动修复卡住的运行状态"""
        session_dir = self.root / session_id
        if not session_dir.exists():
            return None

        metadata = self._read_json(session_dir / "metadata.json")
        if not metadata:
            return None

        # ━━━ 自动修复卡住的状态 ━━━
        state = metadata.get("state", "planning")
        updated_at_str = metadata.get("updated_at", "")
        stuck_states = {"searching", "writing", "reviewing_notes"}
        if state in stuck_states:
            # 检查是否卡住了：最后更新时间超过 10 分钟
            should_fix = True
            if updated_at_str:
                try:
                    updated_at = datetime.datetime.fromisoformat(updated_at_str)
                    delta = datetime.datetime.now() - updated_at
                    if delta.total_seconds() < 600:  # 10 分钟以内，可能是真的在运行
                        # 再检查 RUNS 内存是否有活跃任务
                        should_fix = False  # 默认不修，让前端通过 polling 检查
                except Exception:
                    pass
            if should_fix:
                # 回退到上一个稳定状态
                fallback_map = {
                    "searching": "plan_confirmed",
                    "writing": "reviewing_notes",
                    "reviewing_notes": "writing",
                }
                new_state = fallback_map.get(state, "plan_confirmed")
                metadata["state"] = new_state
                metadata["updated_at"] = datetime.datetime.now().isoformat()
                self._write_json(session_dir / "metadata.json", metadata)

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

        # 加载最新综述：优先使用 get_review（它会优先读取 current_review.md），并尝试确定版本号
        review = self.get_review(session_id)
        review_version = 0
        review_dir = session_dir / "review"
        if review_dir.exists():
            review_files = sorted(review_dir.glob("review_v*.md"), reverse=True)
            if review_files:
                # 从最新的版本化文件名中解析版本号（如果存在）
                import re
                m = re.search(r"review_v(\d+)", review_files[0].name)
                if m:
                    try:
                        review_version = int(m.group(1))
                    except Exception:
                        review_version = 0

        # 加载轨迹
        traces = self._read_json(session_dir / "traces" / "run_traces.json") or []

        # 加载深度分析结果
        analysis = self._read_json(session_dir / "analysis" / "analysis_results.json") or {}

        # GitHub repository sources are optional and remain compatible with
        # sessions created before repository research was introduced.
        repositories = self._read_json(session_dir / "repositories" / "sources.json") or []
        review_quality = self._read_json(session_dir / "review" / "quality.json") or {}

        # 加载聊天历史（多会话模式，自动迁移旧版）
        self._migrate_legacy_chat(session_id)
        conversations = self.list_conversations(session_id)

        return {
            "session_id": metadata.get("session_id", session_id),
            "topic": metadata.get("topic", ""),
            "state": metadata.get("state", "planning"),
            "created_at": metadata.get("created_at", ""),
            "updated_at": metadata.get("updated_at", ""),
            "rewrite_count": metadata.get("rewrite_count", 0),
            "skills": metadata.get("skills", {}),
            "review_referenced_papers": metadata.get("review_referenced_papers", []),
            "initial_plan": initial_plan,
            "keywords": keywords,
            "papers": papers,
            "notes": notes,
            "review": review,
            "review_version": review_version,
            "draft": review,
            "draft_version": review_version,
            "traces": traces,
            "analysis": analysis,
            "repositories": repositories,
            "review_quality": review_quality,
            "conversations": conversations,
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
        """保存论文列表（自动标准化，并排除被手动删除过的论文）"""
        session_dir = self.root / session_id
        if not session_dir.exists():
            raise ValueError(f"Session {session_id} 不存在")
            
        deleted_list_path = session_dir / "papers" / "deleted_papers.json"
        deleted_ids = set(self._read_json(deleted_list_path) or [])
        
        filtered_papers = [p for p in papers if p.get("paper_id") not in deleted_ids]
        
        self._write_json(session_dir / "papers" / "papers_list.json", self._normalize_papers(filtered_papers))
        self._touch_metadata(session_dir)

    def undelete_paper(self, session_id: str, paper_id: str) -> None:
        """从删除列表中移除论文 ID，允许其重新被加入论文列表"""
        session_dir = self.root / session_id
        deleted_list_path = session_dir / "papers" / "deleted_papers.json"
        deleted_ids = self._read_json(deleted_list_path) or []
        if paper_id in deleted_ids:
            deleted_ids.remove(paper_id)
            self._write_json(deleted_list_path, deleted_ids)

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

        # 清理 PDF 文件及可能存在的 txt 提取结果
        pdf_file = self.root / session_id / "papers" / f"{paper_id}.pdf"
        if pdf_file.exists():
            pdf_file.unlink()
            
        txt_file = self.root / session_id / "papers" / f"{paper_id}.txt"
        if txt_file.exists():
            txt_file.unlink()
            
        # 记录被删除的论文 ID，防止重新跑 agent 时被再次加回来
        deleted_list_path = self.root / session_id / "papers" / "deleted_papers.json"
        deleted_ids = set(self._read_json(deleted_list_path) or [])
        deleted_ids.add(paper_id)
        self._write_json(deleted_list_path, list(deleted_ids))
            
        return self.load_session(session_id)

    def batch_delete_papers(self, session_id: str, paper_ids: list[str]) -> dict:
        """批量删除论文"""
        papers = self.get_papers(session_id)
        papers = [p for p in papers if p.get("paper_id") not in paper_ids]
        self.save_papers_list(session_id, papers)

        deleted_list_path = self.root / session_id / "papers" / "deleted_papers.json"
        deleted_ids = set(self._read_json(deleted_list_path) or [])

        for pid in paper_ids:
            pdf_file = self.root / session_id / "papers" / f"{pid}.pdf"
            if pdf_file.exists():
                pdf_file.unlink()
            txt_file = self.root / session_id / "papers" / f"{pid}.txt"
            if txt_file.exists():
                txt_file.unlink()
            deleted_ids.add(pid)
            
        self._write_json(deleted_list_path, list(deleted_ids))

        return self.load_session(session_id)

    def update_paper_status(self, session_id: str, paper_id: str, status: str) -> dict:
        """更新论文审查状态（accepted/rejected/pending）"""
        if status not in {"accepted", "rejected", "pending"}:
            raise ValueError(f"不支持的论文状态: {status}")
        papers = self.get_papers(session_id)
        found = False
        for p in papers:
            if p.get("paper_id") == paper_id:
                p["status"] = status
                found = True
                break
        if not found:
            raise ValueError(f"论文 {paper_id} 不存在")
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
            # Ensure keys exist with sensible defaults
            p.setdefault("title", "")
            p.setdefault("authors", "")
            p.setdefault("source", "agent_search")
            p.setdefault("source_type", "")
            p.setdefault("status", "pending")
            p.setdefault("abstract", "")
            p.setdefault("notes", "")

            # Normalize values: if a field is a list, join it. For most fields we then
            # truncate at the first line break (handling literal "\\n" sequences),
            # but for the 'notes' field we must preserve the full multi-line content.
            for key in ("title", "authors", "source", "source_type", "status", "abstract", "notes"):
                val = p.get(key, "")
                # Convert lists to comma-separated string
                if isinstance(val, (list, tuple)):
                    try:
                        val = ", ".join(str(x) for x in val)
                    except Exception:
                        val = ""

                # For 'notes' we intentionally preserve the full text (no truncation at newlines)
                if key == "notes":
                    if isinstance(val, str):
                        p[key] = val.strip()
                    else:
                        p[key] = str(val)
                    continue

                # For other string fields, prefer truncating at a literal "\\n" sequence if present
                # (some upstream outputs encode newlines as the two-character sequence "\\n").
                # Otherwise fall back to actual line breaks.
                if isinstance(val, str):
                    try:
                        if "\\n" in val:
                            # Split on the literal backslash-n sequence and take the first segment
                            parts = val.split("\\n")
                            val = parts[0].strip() if parts else ""
                        else:
                            # splitlines returns all real lines; take the first non-empty line if present
                            lines = val.splitlines()
                            if lines:
                                val = lines[0].strip()
                            else:
                                val = val.strip()
                    except Exception:
                        val = val.strip() if isinstance(val, str) else str(val)
                else:
                    # Fallback: coerce to string
                    val = str(val)

                p[key] = val

            # Update has_notes based on notes content
            p.setdefault("has_notes", bool(p.get("notes", "").strip()))

        return papers
    def get_paper_dir(self, session_id: str, paper_id: str) -> Path:
        """获取某篇论文的存储目录"""
        paper_dir = self.root / session_id / "papers" / paper_id
        paper_dir.mkdir(parents=True, exist_ok=True)
        return paper_dir
    
    def get_agent_search_paper_path(self, session_id: str, paper_id: str) -> Path:
        """获取某篇Agent查找的论文的存储目录"""
        paper=paper_id+".pdf"
        paper_dir = self.root / session_id / "papers" / paper
        return paper_dir
    
    def get_user_custom_paper_path(self, session_id: str, paper_id: str) -> Path:
        """获取某篇用户搜索的论文的存储目录"""
        paper=paper_id+".pdf"
        paper_dir = self.root / session_id / "papers" / paper
        return paper_dir

    def get_user_upload_paper_path(self, session_id: str, paper_id: str) -> Path:
        """获取某篇用户上传的论文的存储目录"""
        paper_dir = self.root / session_id / "papers" / paper_id
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

    # ━━━━━ 综述管理 ━━━━━

    def get_review(self, session_id: str, version: int = None) -> str:
        """获取综述（默认最新版本）"""
        review_dir = self.root / session_id / "review"
        if not review_dir.exists():
            return self.get_draft(session_id, version)

        if version is not None:
            review_path = review_dir / f"review_v{version}.md"
            return review_path.read_text(encoding="utf-8") if review_path.exists() else ""

        # 获取最新版本
        # 优先使用 current_review.md（用于快速同步最新综述），否则回退到按版本的文件
        current_path = review_dir / "current_review.md"
        if current_path.exists():
            try:
                return current_path.read_text(encoding="utf-8")
            except Exception:
                pass

        review_files = sorted(review_dir.glob("review_v*.md"), reverse=True)
        if review_files:
            try:
                return review_files[0].read_text(encoding="utf-8")
            except Exception:
                return ""
        return self.get_draft(session_id, version)

    def get_draft(self, session_id: str, version: int = None) -> str:
        """兼容旧接口：读取旧 draft 目录中的综述草稿。"""
        draft_dir = self.root / session_id / "draft"
        if not draft_dir.exists():
            return ""

        if version is not None:
            draft_path = draft_dir / f"draft_v{version}.md"
            return draft_path.read_text(encoding="utf-8") if draft_path.exists() else ""

        current_path = draft_dir / "current_draft.md"
        if current_path.exists():
            try:
                return current_path.read_text(encoding="utf-8")
            except Exception:
                pass

        draft_files = sorted(draft_dir.glob("draft_v*.md"), reverse=True)
        if draft_files:
            try:
                return draft_files[0].read_text(encoding="utf-8")
            except Exception:
                return ""
        return ""

    def save_review(self, session_id: str, content: str, version: int = None, referenced_papers: list[str] = None) -> dict:
        """保存综述
        
        Args:
            referenced_papers: 本次撰写实际引用的论文 paper_id 列表
        """
        session_dir = self.root / session_id
        if not session_dir.exists():
            raise ValueError(f"Session {session_id} 不存在")

        review_dir = session_dir / "review"
        review_dir.mkdir(parents=True, exist_ok=True)

        if version is None:
            # 自动计算下一个版本号
            existing = list(review_dir.glob("review_v*.md"))
            version = len(existing) + 1

        review_path = review_dir / f"review_v{version}.md"
        review_path.write_text(content, encoding="utf-8")

        # 额外写入一份 current_review.md，便于前端快速获取最新综述
        try:
            current_path = review_dir / "current_review.md"
            current_path.write_text(content, encoding="utf-8")
        except Exception:
            pass

        # 兼容旧前端和知识库索引：继续维护 draft 目录镜像。
        try:
            draft_dir = session_dir / "draft"
            draft_dir.mkdir(parents=True, exist_ok=True)
            (draft_dir / f"draft_v{version}.md").write_text(content, encoding="utf-8")
            (draft_dir / "current_draft.md").write_text(content, encoding="utf-8")
        except Exception:
            pass

        # 更新重写计数
        metadata = self._read_json(session_dir / "metadata.json") or {}
        metadata["rewrite_count"] = version - 1
        # 记录当前综述版本，便于外部接口快速获取
        metadata["review_version"] = version
        metadata["draft_version"] = version
        # 记录本次撰写实际引用的论文列表
        if referenced_papers is not None:
            metadata["review_referenced_papers"] = referenced_papers
        metadata["updated_at"] = datetime.datetime.now().isoformat()
        self._write_json(session_dir / "metadata.json", metadata)

        return self.load_session(session_id)

    def save_draft(self, session_id: str, content: str, version: int = None, referenced_papers: list[str] = None) -> dict:
        """兼容旧接口：保存草稿时写入新的 review 存储。"""
        return self.save_review(session_id, content, version=version, referenced_papers=referenced_papers)

    def save_feedback(self, session_id: str, feedback: str) -> dict:
        """保存用户反馈"""
        session_dir = self.root / session_id
        if not session_dir.exists():
            raise ValueError(f"Session {session_id} 不存在")

        feedback_path = session_dir / "review" / "user_feedback.md"
        feedback_path.write_text(feedback, encoding="utf-8")
        return self.load_session(session_id)

    def get_feedback(self, session_id: str) -> str:
        """获取用户反馈"""
        feedback_path = self.root / session_id / "review" / "user_feedback.md"
        if feedback_path.exists():
            return feedback_path.read_text(encoding="utf-8")
        return ""

    # ━━━━━ 轨迹管理 ━━━━━

    def save_traces(self, session_id: str, traces: list[dict], append: bool = False) -> None:
        """保存 Agent 运行轨迹，自动为缺失时间戳的条目补上
        Args:
            append: 如果为 True，追加到已有轨迹后面（用于追加调研场景）
        """
        session_dir = self.root / session_id
        if not session_dir.exists():
            raise ValueError(f"Session {session_id} 不存在")
        
        # 自动补充时间戳
        from datetime import datetime as _dt
        now = _dt.now().isoformat()
        for t in traces:
            if not t.get("timestamp"):
                t["timestamp"] = now
        
        if append:
            existing = self._read_json(session_dir / "traces" / "run_traces.json") or []
            section_header = {
                "timestamp": now,
                "thought": "",
                "action": "SECTION",
                "input": {},
                "observation": f"## 📌 追加调研 — {_dt.now().strftime('%Y-%m-%d %H:%M')}",
                "error_type": "section",
            }
            existing.append(section_header)
            existing.extend(traces)
            self._write_json(session_dir / "traces" / "run_traces.json", existing)
        else:
            self._write_json(session_dir / "traces" / "run_traces.json", traces)

    # ━━━━━ 多会话聊天管理 ━━━━━
    # 每个 Session 可包含多个独立的聊天会话（Conversation）
    # 存储结构：sessions/{id}/chats/_index.json + conv_{uuid}.json

    def _conv_dir(self, session_id: str) -> Path:
        d = self.root / session_id / "chats"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _conv_path(self, session_id: str, conv_id: str) -> Path:
        return self._conv_dir(session_id) / f"{conv_id}.json"

    def _conv_index_path(self, session_id: str) -> Path:
        return self._conv_dir(session_id) / "_index.json"

    def create_conversation(self, session_id: str, title: str = "") -> dict:
        """在 Session 下创建一个新的聊天会话"""
        import uuid as _uuid
        conv_id = f"conv_{_uuid.uuid4().hex[:8]}"
        now = datetime.datetime.now().isoformat()
        conv = {
            "conv_id": conv_id,
            "title": title or f"对话 {now[:16]}",
            "created_at": now,
            "message_count": 0,
        }
        # 保存空的会话消息文件
        self._write_json(self._conv_path(session_id, conv_id), [])
        # 更新索引
        index = self._read_json(self._conv_index_path(session_id)) or []
        index.append(conv)
        self._write_json(self._conv_index_path(session_id), index)
        self._touch_metadata(self.root / session_id)
        return conv

    def list_conversations(self, session_id: str) -> list[dict]:
        """列出 Session 下的所有聊天会话"""
        return self._read_json(self._conv_index_path(session_id)) or []

    def get_conversation_messages(self, session_id: str, conv_id: str) -> list[dict]:
        """获取某个聊天会话的所有消息"""
        return self._read_json(self._conv_path(session_id, conv_id)) or []

    def append_conversation_messages(self, session_id: str, conv_id: str, messages: list[dict]) -> None:
        """向聊天会话追加消息"""
        path = self._conv_path(session_id, conv_id)
        history = self._read_json(path) or []
        from datetime import datetime as _dt
        for msg in messages:
            if not msg.get("timestamp"):
                msg["timestamp"] = _dt.now().isoformat()
        history.extend(messages)
        self._write_json(path, history)

        # 更新索引中的 message_count
        self._update_conv_index(session_id, conv_id, len(history))

    def _update_conv_index(self, session_id: str, conv_id: str, message_count: int) -> None:
        """Update conversation metadata after message edits or compression."""
        index = self._read_json(self._conv_index_path(session_id)) or []
        now = datetime.datetime.now().isoformat()
        for c in index:
            if c.get("conv_id") == conv_id:
                c["message_count"] = message_count
                c["updated_at"] = now
                break
        self._write_json(self._conv_index_path(session_id), index)
        self._touch_metadata(self.root / session_id)

    def delete_conversation(self, session_id: str, conv_id: str) -> bool:
        """删除聊天会话"""
        path = self._conv_path(session_id, conv_id)
        if path.exists():
            path.unlink()
        index = self._read_json(self._conv_index_path(session_id)) or []
        new_index = [c for c in index if c.get("conv_id") != conv_id]
        self._write_json(self._conv_index_path(session_id), new_index)
        self._touch_metadata(self.root / session_id)
        return True

    # ━━━━━ 兼容旧版聊天的迁移 ━━━━━

    def _migrate_legacy_chat(self, session_id: str) -> str | None:
        """迁移旧版 chat_history.json → 新版 chats/ 多会话模式，返回默认 conv_id"""
        old_path = self.root / session_id / "chat_history.json"
        if not old_path.exists():
            return None

        old_messages = self._read_json(old_path) or []
        conv = self.create_conversation(session_id, "历史对话")
        if old_messages:
            self.append_conversation_messages(session_id, conv["conv_id"], old_messages)
        # 删除旧文件
        try:
            old_path.unlink()
        except Exception:
            pass
        return conv["conv_id"]

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

