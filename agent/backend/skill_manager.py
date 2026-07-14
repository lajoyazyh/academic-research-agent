"""
Skills 管理器 — Extension: 用户自定义 Agent 行为策略

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
from backend.tenant import tenant_path
from prompts.review_skills import DEFAULT_REVIEW_SKILL, REVIEW_PRESETS


class SkillManager:
    """Skills 生命周期管理器"""

    VALID_TYPES = {"search", "notes", "write"}
    TYPE_LABELS = {
        "search": "AI检索论文",
        "notes": "笔记生成",
        "write": "综述生成",
    }

    # ━━━ 内置默认 Skill（从 main.py 实际提示词提取，留空时使用）━━━

    DEFAULT_SKILLS = {
        "search": {
            "title": "默认搜索策略",
            "content": (
                "## 数据库优先级\n"
                "- CS/AI/理工科优先使用 arxiv_search（结果最完整）\n"
                "- OpenAlex 补充跨学科论文\n"
                "- Semantic Scholar 只在大规模检索或补充时使用（限流严格）\n\n"
                "## 搜索策略\n"
                "- 中文主题必须翻译为英文关键词后搜索\n"
                "- 审核摘要质量后决定是否收录\n"
                "- 同一关键词同一数据库最多搜索 2 次，之后换关键词或数据库\n"
                "- HTTP 429 立即切换数据库，不反复重试\n\n"
                "## 收录标准\n"
                "- 先写清主题相关性、时间范围、研究类型和排除条件，再开始检索\n"
                "- 同时保留奠基性研究与近年进展，不能仅按年份或引用量筛选\n"
                "- 每篇候选来源记录纳入/排除理由；摘要不足以判断时标记待核验\n"
                "- 优先保证方法与证据类型的多样性，避免只收录结论相近的论文\n"
                "- 收录后立即调用 paper_register 登记\n\n"
                "## 可用工具\n"
                "- arxiv_search：arXiv 搜索（返回标题+作者+摘要，最完整）\n"
                "- arxiv_fetch：按 arXiv ID 补全信息\n"
                "- paper_register：审核摘要 → 收录论文（下载 PDF + 登记到论文列表）\n"
                "- arxiv_pdf_reader：读取已下载 PDF 的内容\n"
                "- openalex_search：OpenAlex 跨学科搜索\n"
                "- crossref_search / crossref_fetch_doi：Crossref 搜索与 DOI 补全\n"
                "- semantic_scholar_search / semantic_scholar_fetch：Semantic Scholar 搜索\n\n"
                "## 关键经验\n"
                "- arxiv_search 返回结果已包含标题+作者+摘要，审核后立即调用 paper_register 收录\n"
                "- paper_register 支持 arXiv ID 与 DOI；登记前必须核对标题和摘要\n"
                "- crossref_search 传入论文标题/作者名\n"
                "- HTTP 429 立即换数据库\n"
            ),
        },
        "notes": {
            "title": "默认笔记生成策略",
            "content": (
                "## 证据卡片\n"
                "为每篇论文生成可直接进入证据矩阵的结构化笔记：\n"
                "1. **书目信息**：原始标题、作者、年份、DOI/arXiv ID 与来源链接\n"
                "2. **研究问题与设计**：研究对象、任务定义、研究类型和比较对象\n"
                "3. **样本/数据与方法**：样本量、数据集、模型、干预或分析方法\n"
                "4. **主要发现**：只记录原文可支持的定量或定性结论，保留指标口径\n"
                "5. **限制与偏倚风险**：作者声明的限制，以及样本、测量、对照、复现方面的风险\n"
                "6. **综述编码**：与研究问题的关联、可支持的主题、可能冲突的来源、证据强度（高/中/低及理由）\n"
                "7. **定位信息**：尽可能记录页码、章节或可复核的原文短语；无法定位时明确标注\n\n"
                "## 写作要求\n"
                "- 使用中文撰写，原始标题和专业术语保留原语言\n"
                "- 区分作者报告、笔记作者推断和当前无法验证的信息\n"
                "- 数字必须连同指标、数据集/样本和比较基线一起记录\n"
                "- 信息不足处标注「原文材料未提供」，不得用常识补齐\n"
                "- 不按固定字数灌水，优先保证每条证据可追溯、可比较\n"
            ),
        },
        "write": {
            "title": "证据综合型综述策略",
            "content": DEFAULT_REVIEW_SKILL,
        },
    }

    def __init__(self, base_dir: str):
        """
        Args:
            base_dir: 存储根目录，如 agent/sessions/
        """
        self._base_dir = Path(base_dir)
        self._skills_dir.mkdir(parents=True, exist_ok=True)

    @property
    def _skills_dir(self) -> Path:
        path = tenant_path(self._base_dir) / ".skills"
        path.mkdir(parents=True, exist_ok=True)
        return path

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

    def get_defaults(self) -> dict:
        """获取所有类型的默认 Skill 内容"""
        return dict(self.DEFAULT_SKILLS)

    def get_presets(self) -> dict:
        """Return immutable built-in presets that users can copy and adapt."""
        return dict(REVIEW_PRESETS)

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

