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
                "- 优先收录近 3 年顶会/知名期刊论文\n"
                "- 摘要需与研究主题有明确关联\n"
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
                "- 不要用 DOI 调用 paper_register，只接受 arXiv ID\n"
                "- crossref_search 传入论文标题/作者名\n"
                "- HTTP 429 立即换数据库\n"
            ),
        },
        "notes": {
            "title": "默认笔记生成策略",
            "content": (
                "## 笔记维度\n"
                "为每篇论文从以下六个维度生成笔记：\n"
                "1. **研究背景**：该论文解决的问题、研究动机和背景\n"
                "2. **核心方法**：提出的方法、模型架构、算法框架\n"
                "3. **实验设置**：使用的数据集、评估基准、实现细节\n"
                "4. **关键结果**：主要性能指标、与基线对比、核心发现\n"
                "5. **消融与分析**：消融实验、可视化分析、案例研究\n"
                "6. **亮点与不足**：创新贡献、局限性、未来工作方向\n\n"
                "## 写作要求\n"
                "- 使用中文撰写，专业术语保留英文\n"
                "- 引述原文中的具体方法名、数据、实验指标\n"
                "- 每个维度至少 60-150 字\n"
                "- 信息不足处标注「未提及」，不编造内容\n"
            ),
        },
        "write": {
            "title": "默认综述生成策略",
            "content": (
                "## 综述结构\n"
                "按以下四节组织综述：\n"
                "1. **引言与背景**：研究领域的背景、意义和发展脉络\n"
                "2. **核心论文方法对比**：用表格或分点对比各论文的方法、数据集、指标\n"
                "3. **实验结果与工程实践分析**：深入分析实验结果，提炼工程实践启示\n"
                "4. **局限性与未来研究方向**：总结当前方法的局限，展望未来趋势\n\n"
                "## 写作要求\n"
                "- 学术严谨，逻辑清晰，避免空话套话\n"
                "- 具体引用论文中的方法名、数据集、指标数值\n"
                "- 每节至少 3 个要点，每个要点有具体论文支撑\n"
                "- 使用 Markdown 格式，适当使用表格和列表\n"
                "- 与已完成章节保持衔接，但不要重复\n\n"
                "## ⚠️ 严格禁止\n"
                "- **绝对禁止**输出任何形式的省略占位符，包括但不限于：\n"
                "  - 「（此处省略...）」\n"
                "  - 「（具体内容与上一版草稿相同）」\n"
                "  - 「（详见上文）」\n"
                "  - 「...（略）...」\n"
                "  - 「（同上）」\n"
                "- 任何以括号包裹的'省略'、'略'、'同上'、'见上文'等表述\n"
                "- 如果某节内容确实缺乏足够素材，应基于已有笔记进行合理推断和总结，\n"
                "  并用「根据现有资料」「初步分析表明」等措辞引导，而不是留空或省略\n"
                "- 每一节都必须是完整的、可直接阅读的正文内容\n"
            ),
        },
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

    def get_defaults(self) -> dict:
        """获取所有类型的默认 Skill 内容"""
        return dict(self.DEFAULT_SKILLS)

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
