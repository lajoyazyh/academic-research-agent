"""
工具注册中心：管理所有可用工具的元数据、启用/禁用状态、配置参数。
支持持久化到 JSON 配置文件。
"""
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict


@dataclass
class ToolMeta:
    """工具的元数据描述"""
    name: str
    description: str
    category: str  # "search" | "pdf" | "file" | "chat" | "notes" | "register"
    parameters: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)  # 工具级可调参数

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ToolMeta":
        return cls(**{k: d.get(k) for k in ["name", "description", "category", "parameters", "enabled", "config"]})


# ━━━ 内置工具注册表（单一数据源）━━━
BUILTIN_TOOLS: Dict[str, ToolMeta] = {
    "arxiv_search": ToolMeta(
        name="arxiv_search",
        description="在 arXiv 上搜索学术论文，返回论文 ID、标题和发布时间",
        category="search",
        parameters={"query": "搜索关键词", "max_results": "最大返回数，默认5（可选）"},
        enabled=True,
        config={"max_results": 5},
    ),
    "arxiv_fetch": ToolMeta(
        name="arxiv_fetch",
        description="根据 arXiv ID 获取论文的详细元数据（标题、作者、摘要等）",
        category="search",
        parameters={"paper_id": "arXiv 论文 ID"},
        enabled=True,
    ),
    "arxiv_pdf_reader": ToolMeta(
        name="arxiv_pdf_reader",
        description="下载并解析 arXiv PDF 全文内容",
        category="pdf",
        parameters={"paper_id": "arXiv 论文 ID", "read_full": "是否读取更多页，默认 false"},
        enabled=True,
        config={"read_full_default": False},
    ),
    "arxiv_download_pdf": ToolMeta(
        name="arxiv_download_pdf",
        description="仅下载 PDF 原文到 papers/ 目录（不解析，轻量快速）",
        category="pdf",
        parameters={"paper_id": "arXiv ID 或 PDF 链接"},
        enabled=True,
    ),
    "semantic_scholar_search": ToolMeta(
        name="semantic_scholar_search",
        description="在 Semantic Scholar 上搜索论文，返回标题、作者、摘要和引用数",
        category="search",
        parameters={"query": "搜索关键词", "limit": "最大返回数，默认5（可选）"},
        enabled=True,
        config={"limit": 5},
    ),
    "semantic_scholar_fetch": ToolMeta(
        name="semantic_scholar_fetch",
        description="根据 Semantic Scholar Paper ID 获取论文详细信息",
        category="search",
        parameters={"paper_id": "Semantic Scholar Paper ID"},
        enabled=True,
    ),
    "crossref_search": ToolMeta(
        name="crossref_search",
        description="在 Crossref 中按关键词检索文献元数据，返回 DOI、题目、作者等",
        category="search",
        parameters={"query": "检索关键词", "rows": "最大返回数，默认5（可选）"},
        enabled=True,
        config={"rows": 5},
    ),
    "crossref_fetch_doi": ToolMeta(
        name="crossref_fetch_doi",
        description="通过 DOI 从 Crossref 获取论文完整元数据",
        category="search",
        parameters={"doi": "论文 DOI"},
        enabled=True,
    ),
    "openalex_search": ToolMeta(
        name="openalex_search",
        description="在 OpenAlex 上检索综合领域论文（含社科、医学等），返回标题、摘要、引用数",
        category="search",
        parameters={"query": "搜索关键词", "limit": "最大返回数，默认5（可选）"},
        enabled=True,
        config={"limit": 5},
    ),
    "clear_notes": ToolMeta(
        name="clear_notes",
        description="清空临时研究笔记文件",
        category="file",
        parameters={},
        enabled=True,
    ),
    "append_note": ToolMeta(
        name="append_note",
        description="记录单篇论文的深度阅读笔记（结构化 Markdown）",
        category="file",
        parameters={"content": "结构化 Markdown 笔记，需包含论文id、标题、作者等"},
        enabled=True,
    ),
    # ━━━ 新增：对话检索 / 笔记生成 / 收录管理工具 ━━━
    "retriever": ToolMeta(
        name="retriever",
        description="BM25 检索器：从已下载的 PDF 全文中检索与查询最相关的段落（用于对话 RAG）",
        category="chat",
        parameters={"query": "检索查询文本", "top_k": "返回段落数，默认5（可选）"},
        enabled=True,
        config={"top_k": 5},
    ),
    "rag_note_generator": ToolMeta(
        name="rag_note_generator",
        description="基于 Embedding 向量检索生成 6 段式深度学术笔记（研究背景、核心方法、实验设置、关键结果、消融与分析、亮点与不足）",
        category="notes",
        parameters={"pdf_path": "PDF 文件路径", "paper_title": "论文标题", "abstract": "论文摘要", "topic": "研究主题"},
        enabled=True,
        config={"embedding_top_k": 5},
    ),
    "paper_register": ToolMeta(
        name="paper_register",
        description="审核论文摘要并收录（下载 PDF + 登记到论文列表），一步完成",
        category="register",
        parameters={"paper_id": "arXiv ID", "title": "论文标题", "authors": "作者列表", "abstract": "论文摘要"},
        enabled=True,
    ),
}


class ToolRegistry:
    """工具注册中心：加载/保存配置，管理启用状态"""

    def __init__(self, config_path: str = None):
        self._config_path = config_path
        self._tools: Dict[str, ToolMeta] = {}
        self._load()

    def _load(self):
        """从配置文件加载，fallback 到内置默认"""
        self._tools = {name: ToolMeta(**asdict(meta)) for name, meta in BUILTIN_TOOLS.items()}

        if self._config_path and os.path.exists(self._config_path):
            try:
                saved = json.loads(Path(self._config_path).read_text(encoding="utf-8"))
                if isinstance(saved, dict):
                    for name, data in saved.items():
                        if name in self._tools:
                            # 只覆盖 enabled 和 config 字段
                            if "enabled" in data:
                                self._tools[name].enabled = bool(data["enabled"])
                            if "config" in data and isinstance(data["config"], dict):
                                self._tools[name].config.update(data["config"])
            except (json.JSONDecodeError, Exception):
                pass

    def _save(self):
        """持久化当前配置"""
        if not self._config_path:
            return
        os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
        data = {name: {"enabled": meta.enabled, "config": meta.config} for name, meta in self._tools.items()}
        Path(self._config_path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_all(self) -> List[ToolMeta]:
        """获取所有工具元数据"""
        return list(self._tools.values())

    def get_enabled(self) -> List[ToolMeta]:
        """获取已启用的工具"""
        return [t for t in self._tools.values() if t.enabled]

    def get_disabled(self) -> List[ToolMeta]:
        """获取已禁用的工具"""
        return [t for t in self._tools.values() if not t.enabled]

    def set_enabled(self, name: str, enabled: bool) -> bool:
        """设置工具的启用状态"""
        if name not in self._tools:
            return False
        self._tools[name].enabled = enabled
        self._save()
        return True

    def set_config(self, name: str, key: str, value: Any) -> bool:
        """设置工具的某个配置参数"""
        if name not in self._tools:
            return False
        self._tools[name].config[key] = value
        self._save()
        return True

    def batch_set_enabled(self, enabled_map: Dict[str, bool]) -> Dict[str, bool]:
        """批量设置工具启用状态"""
        result = {}
        for name, enabled in enabled_map.items():
            result[name] = self.set_enabled(name, enabled)
        return result

    def reset_to_defaults(self):
        """重置为内置默认配置"""
        self._tools = {name: ToolMeta(**asdict(meta)) for name, meta in BUILTIN_TOOLS.items()}
        self._save()

    def get_tool(self, name: str) -> Optional[ToolMeta]:
        """获取单个工具元数据"""
        return self._tools.get(name)


# 全局单例
_registry: Optional[ToolRegistry] = None


def get_registry(config_path: str = None) -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry(config_path)
    return _registry
