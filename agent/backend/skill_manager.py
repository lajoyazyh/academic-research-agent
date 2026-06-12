"""
Skills 管理器 — 迭代三扩展：用户自定义 Agent 行为策略

管理 Skill 的完整生命周期：
- 创建/加载/更新/删除 Skill
- 按类型筛选（search / notes / write）
- JSON 文件持久化到 sessions/.skills/ 目录
- 软删除支持（7 天恢复期）
"""

import json
import os
import uuid
import datetime
from pathlib import Path
from typing import Optional


class SkillManager:
    """Skills 生命周期管理器"""

    VALID_TYPES = {"search", "notes", "write"}
    TYPE_LABELS = {
        "search": "AI检索论文",
        "notes": "笔记生成",
        "write": "综述生成",
    }

    def __init__(self, base_dir: str):
        """
        Args:
            base_dir: 存储根目录，如 agent/sessions/
        """
        self._base_dir = Path(base_dir)
        self._skills_dir = self._base_dir / ".skills"
        self._skills_dir.mkdir(parents=True, exist_ok=True)

    # ━━━━━ 基础 CRUD ━━━━━

    def create_skill(self, title: str, skill_type: str, content: str) -> dict:
        """创建新 Skill"""
        if skill_type not in self.VALID_TYPES:
            raise ValueError(f"无效的 skill 类型: {skill_type}，可选值: {self.VALID_TYPES}")

        title = title.strip()
        if not title:
            raise ValueError("标题不能为空")
        if not content.strip():
            raise ValueError("Skill 内容不能为空")

        # 同类型同名检查
        existing = self.list_skills(skill_type=skill_type)
        if any(s.get("title") == title for s in existing):
            raise ValueError(f"已存在同类型同名 Skill「{title}」")

        skill_id = f"skill_{uuid.uuid4().hex[:12]}"
        now = datetime.datetime.now().isoformat()

        skill = {
            "skill_id": skill_id,
            "title": title,
            "type": skill_type,
            "content": content,
            "created_at": now,
            "updated_at": now,
            "deleted": False,
            "deleted_at": None,
        }

        self._write_skill(skill_id, skill)
        self._update_index()
        return skill

    def get_skill(self, skill_id: str) -> Optional[dict]:
        """获取单个 Skill 完整数据"""
        return self._read_skill(skill_id)

    def list_skills(self, skill_type: str = None) -> list[dict]:
        """列出 Skill（可按类型过滤），返回摘要列表（不含 content）"""
        skills = []
        index = self._read_index()

        for entry in index:
            if entry.get("deleted"):
                continue
            if skill_type and entry.get("type") != skill_type:
                continue
            skills.append(entry)

        skills.sort(key=lambda s: s.get("created_at", ""), reverse=True)
        return skills

    def update_skill(self, skill_id: str, title: str = None, content: str = None) -> dict:
        """更新 Skill 标题或内容"""
        skill = self._read_skill(skill_id)
        if not skill:
            raise ValueError(f"Skill {skill_id} 不存在")
        if skill.get("deleted"):
            raise ValueError(f"Skill {skill_id} 已被删除")

        if title is not None:
            title = title.strip()
            if not title:
                raise ValueError("标题不能为空")
            # 同类型同名检查（排除自身）
            existing = self.list_skills(skill_type=skill["type"])
            if any(s.get("title") == title and s.get("skill_id") != skill_id for s in existing):
                raise ValueError(f"已存在同类型同名 Skill「{title}」")
            skill["title"] = title

        if content is not None:
            if not content.strip():
                raise ValueError("Skill 内容不能为空")
            skill["content"] = content

        skill["updated_at"] = datetime.datetime.now().isoformat()
        self._write_skill(skill_id, skill)
        self._update_index()
        return skill

    def delete_skill(self, skill_id: str, soft: bool = True) -> bool:
        """删除 Skill（默认软删除，保留 7 天）"""
        skill = self._read_skill(skill_id)
        if not skill:
            return False

        if soft:
            skill["deleted"] = True
            skill["deleted_at"] = datetime.datetime.now().isoformat()
            self._write_skill(skill_id, skill)
        else:
            self._skill_path(skill_id).unlink(missing_ok=True)

        self._update_index()
        return True

    def get_skill_usage(self, skill_id: str) -> list[dict]:
        """获取引用该 Skill 的 Session 列表"""
        sessions_using = []
        if not self._base_dir.exists():
            return sessions_using

        for session_dir in self._base_dir.iterdir():
            if not session_dir.is_dir() or session_dir.name.startswith("."):
                continue
            meta_path = session_dir / "metadata.json"
            if not meta_path.exists():
                continue
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                skills = meta.get("skills", {})
                for phase, sid in skills.items():
                    if sid == skill_id:
                        sessions_using.append({
                            "session_id": session_dir.name,
                            "topic": meta.get("topic", ""),
                            "phase": phase,
                        })
                        break
            except (json.JSONDecodeError, Exception):
                continue

        return sessions_using

    # ━━━━━ 文件操作 ━━━━━

    def _skill_path(self, skill_id: str) -> Path:
        return self._skills_dir / f"{skill_id}.json"

    def _read_skill(self, skill_id: str) -> Optional[dict]:
        path = self._skill_path(skill_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            return None

    def _write_skill(self, skill_id: str, data: dict) -> None:
        path = self._skill_path(skill_id)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _index_path(self) -> Path:
        return self._skills_dir / "_index.json"

    def _read_index(self) -> list[dict]:
        path = self._index_path()
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            return []

    def _write_index(self, index: list[dict]) -> None:
        path = self._index_path()
        path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    def _update_index(self) -> None:
        """从各 skill JSON 文件重建索引"""
        index = []
        for f in sorted(self._skills_dir.glob("skill_*.json")):
            data = self._read_skill(f.stem)
            if data:
                index.append({
                    "skill_id": data.get("skill_id", f.stem),
                    "title": data.get("title", ""),
                    "type": data.get("type", ""),
                    "created_at": data.get("created_at", ""),
                    "updated_at": data.get("updated_at", ""),
                    "deleted": data.get("deleted", False),
                    "deleted_at": data.get("deleted_at"),
                })
        self._write_index(index)


# 全局单例
_skill_manager: Optional[SkillManager] = None


def get_skill_manager(base_dir: str = None) -> SkillManager:
    global _skill_manager
    if _skill_manager is None:
        _skill_manager = SkillManager(base_dir or "")
    return _skill_manager
