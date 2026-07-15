import json
import os
import datetime
import re
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
from core.agent import BaseAgent
from core.tool_registry import get_registry
from tools.arxiv_tools import ArxivSearchTool, ArxivFetchTool
from tools.semantic_scholar_tools import SemanticScholarSearchTool, SemanticScholarFetchTool
from tools.crossref_tools import CrossrefSearchTool, CrossrefFetchByDoiTool
from tools.openalex_tools import OpenAlexSearchTool
from tools.pdf_tools import ArxivPdfReaderTool, ArxivDownloadPdfTool
from tools.file_tools import ClearNoteTool, AppendNoteTool
from llms.client import LLMClient
from prompts.review_skills import DEFAULT_REVIEW_SKILL


def _load_skill_info(skill_id: str = None) -> dict:
    """加载 Skill 内容和可观测状态，失败时返回明确的 fallback 信息。"""
    info = {
        "skill_id": skill_id or "",
        "skill_title": "",
        "content": "",
        "loaded": False,
        "fallback_default": True,
        "reason": "not_configured" if not skill_id else "not_loaded",
    }
    if not skill_id:
        return info
    try:
        from backend.skill_manager import get_skill_manager
        base_dir = os.path.dirname(__file__)
        skill = get_skill_manager(os.path.join(base_dir, "sessions")).get_skill(skill_id)
        if not skill:
            info["reason"] = "missing_file"
            return info
        info["skill_title"] = str(skill.get("title", "") or "")
        if skill.get("deleted"):
            info["reason"] = "deleted"
            return info
        content = str(skill.get("content", "") or "")
        if not content.strip():
            info["reason"] = "empty_content"
            return info
        info.update({
            "content": content,
            "loaded": True,
            "fallback_default": False,
            "reason": "active",
        })
        return info
    except Exception as exc:
        info["reason"] = f"load_error: {exc}"
        return info


def _load_skill_content(session_id: str = None, skill_id: str = None) -> str:
    """从 Session metadata 或直接 skill_id 加载 Skill 内容。
    返回 skill.md 的 Markdown 文本，失败时返回空字符串。
    """
    return _load_skill_info(skill_id=skill_id).get("content", "")


def _build_skill_trace(phase: str, skill_info: dict) -> dict:
    """构造统一的 Skill 可观测 trace。"""
    skill_id = skill_info.get("skill_id", "")
    skill_title = skill_info.get("skill_title", "")
    loaded = bool(skill_info.get("loaded", False))
    fallback = bool(skill_info.get("fallback_default", True))
    reason = skill_info.get("reason", "")
    return {
        "timestamp": datetime.datetime.now().isoformat(),
        "thought": f"Skill trace for {phase}",
        "action": "SKILL_STATUS",
        "input": {
            "phase": phase,
            "skill_id": skill_id,
            "skill_title": skill_title,
            "loaded": loaded,
            "fallback_default": fallback,
        },
        "observation": (
            f"skill_phase: {phase} | skill_id: {skill_id or '-'} | "
            f"skill_title: {skill_title or '-'} | loaded: {str(loaded).lower()} | "
            f"fallback_default: {str(fallback).lower()} | reason: {reason}"
        ),
        "error_type": "skill_info" if loaded else "skill_fallback",
    }


def _get_skills_for_session(session_id: str = None) -> dict:
    """从 Session metadata 读取 skills 配置，返回 {"search": skill_id, ...}"""
    if not session_id:
        return {}
    try:
        from backend.session_manager import SessionManager
        base_dir = os.path.dirname(__file__)
        session = SessionManager(os.path.join(base_dir, "sessions")).load_session(session_id)
        return (session or {}).get("skills", {})
    except Exception:
        return {}


WRITER_SECTION_TITLES = [
    "引言与背景",
    "核心论文方法对比",
    "实验结果与工程实践分析",
    "局限性与未来研究方向",
]


def _merge_referenced_papers(notes_content: str, papers_list: list[dict] = None) -> list[str]:
    """从笔记内容中提取被实际引用的论文 paper_id 列表"""
    if not papers_list:
        return []
    referenced = []
    notes_lower = notes_content.lower()
    for index, p in enumerate(papers_list, start=1):
        pid = p.get("paper_id", "")
        title = p.get("title", "")
        if f"[p{index}]" in notes_lower:
            referenced.append(pid)
        elif pid and pid.lower() in notes_lower:
            referenced.append(pid)
        elif title and len(title) > 10 and title.lower()[:40] in notes_lower:
            referenced.append(pid)
    return referenced


def _build_initial_plan(llm: LLMClient, topic: str) -> str:
    plan_prompt = f"""你是调研规划师。请为主题《{topic}》产出一个“可执行的检索计划”，仅用 Markdown 要点列出：
1) 关键词拆分（中英对照）
2) 数据源与调用顺序（必须明确说明优先级：医学/社科类及跨学科主题优先使用 openalex_search，CS/AI及理工科优先使用 arxiv_search。Semantic Scholar仅作严重缺失时的后备补充且要警惕限流）
3) 选取/排除标准（例如时间下限、核心概念匹配度）
4) 失败回退策略（0结果、限流、检索过泛时如何修改关键词）
5) 预期的3~5步行动序列（每步务必写明要调用的具体工具名，如 openalex_search, arxiv_search, arxiv_download_pdf 等）
输出只包含计划内容，不要写长段解释。
"""
    plan = llm.chat("你是严谨的研究规划师。", plan_prompt, []).strip()
    if not plan:
        plan = (
            "## 初步计划\n"
            "- 关键词：LLM Agent Memory; Agent memory; 记忆机制; context caching\n"
            "- 数据源顺序：arXiv/OpenAlex -> Semantic Scholar -> Crossref 补元数据\n"
            "- 选择标准：近3年；顶会/知名期刊；可获取PDF优先\n"
            "- 回退策略：关键词同义词/上位词；切换源；减少限制项\n"
            "- 行动序列：arxiv_search -> arxiv_fetch/pdf_reader -> openalex_search/semantic_scholar_search -> crossref_fetch_doi -> arxiv_download_pdf\n"
        )
    return plan


# ━━━ Writer RAG：从笔记中提取与当前章节最相关的段落 ━━━

# 每个章节的关键词映射，用于从笔记中检索相关段落
SECTION_KEYWORDS = {
    "摘要": ["背景", "方法", "结果", "结论", "contribution", "method", "result", "limitation"],
    "研究范围与证据基础": ["研究问题", "scope", "dataset", "sample", "来源", "纳入", "排除", "evidence"],
    "主题综合": ["theme", "mechanism", "方法", "发现", "result", "approach", "contribution"],
    "方法与证据对比": ["method", "dataset", "sample", "baseline", "metric", "evaluation", "方法", "数据", "指标"],
    "共识、分歧与解释": ["result", "finding", "comparison", "difference", "conflict", "一致", "分歧", "对比"],
    "局限性与研究空白": ["limitation", "future", "gap", "bias", "局限", "不足", "未来", "空白"],
    "结论": ["conclusion", "finding", "result", "contribution", "结论", "发现", "贡献"],
    "引言与背景": [
        "背景", "引言", "introduction", "background", "problem", "challenge",
        "limitation", "issue", "gap", "motivation", "研究背景", "问题定义",
        "related work", "相关工作", "概述",
    ],
    "核心论文方法对比": [
        "方法", "method", "approach", "proposed", "architecture", "model",
        "framework", "algorithm", "模型", "框架", "架构", "算法", "技术",
        "核心方法", "设计", "实现",
    ],
    "实验结果与工程实践分析": [
        "实验", "experiment", "result", "performance", "evaluation", "benchmark",
        "dataset", "accuracy", "数据", "指标", "baseline", "训练", "training",
        "测试", "比较", "对比", "效果",
    ],
    "局限性与未来研究方向": [
        "局限", "limitation", "future", "未来", "不足", "展望", "challenge",
        "drawback", "改进", "后续", "开放问题", "问题", "待解决",
    ],
}

# 通用关键词：当章节不在映射表中时使用
_DEFAULT_KEYWORDS = [
    "method", "result", "contribution", "approach", "model", "实验", "方法", "结果",
]


def _extract_relevant_paragraphs(
    notes_content: str, section_title: str, max_paragraphs: int = 6
) -> str:
    """从笔记内容中提取与当前章节最相关的段落。

    策略：用章节标题 + 映射关键词在笔记中做段落级匹配，
    返回得分最高的 max_paragraphs 个段落。
    """
    if not notes_content or not notes_content.strip():
        return ""

    # 以 ## 标题或 --- 分隔符将笔记拆分为段落
    paragraphs = []
    current = []
    for line in notes_content.split("\n"):
        # 段落边界：新的 Markdown 标题或分隔符
        stripped = line.strip()
        if stripped.startswith("## ") or stripped.startswith("---"):
            if current:
                paragraphs.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        paragraphs.append("\n".join(current).strip())

    # 过滤过短的段落
    paragraphs = [p for p in paragraphs if len(p) > 60]

    if not paragraphs:
        return notes_content[:5000]

    # 获取该章节的关键词列表
    keywords = SECTION_KEYWORDS.get(section_title, _DEFAULT_KEYWORDS)

    # 计算每段的得分（关键词命中次数 + 关键词密度）
    scored = []
    for para in paragraphs:
        para_lower = para.lower()
        # 命中计数
        hits = sum(1 for kw in keywords if kw.lower() in para_lower)
        # 标题精确匹配加 3 分
        title_bonus = 0
        if any(
            kw.lower() in para_lower.split("\n")[0].lower()
            for kw in keywords
        ):
            title_bonus = 3
        # 密度加分（命中数 / 段落长度 * 1000，避免短段落占便宜）
        density_score = (hits / max(1, len(para))) * 1000
        scored.append((hits + title_bonus + density_score, para))

    # 按得分降序排列，取 Top-N
    scored.sort(key=lambda x: x[0], reverse=True)

    top_paragraphs = [p for _, p in scored[:max_paragraphs] if _ > 0]

    if not top_paragraphs:
        # 如果关键词全部没命中，回退到笔记前 5000 字符
        return notes_content[:5000]

    return "\n\n---\n\n".join(top_paragraphs)


def _build_writer_outline(llm: LLMClient, topic: str, notes_content: str, skill_content: str = "") -> str:
    if skill_content:
        # 通道 A：Skill 优先 — 用 Skill 策略替换固定四标题要求
        outline_prompt = f"""你是学术综述写作规划师。请基于给定调研笔记，为主题《{topic}》生成一份中文 Markdown 大纲。

{skill_content}

大纲中的每个正式章节必须使用 `## 章节名`；章节下只写简短要点。不要输出一级标题、正文、前言或代码块。主题综合可以拆成 2–4 个具有信息量的二级章节。

【调研笔记】
{notes_content}

输出仅包含大纲本身，不要写正文段落。"""
    else:
        # 通道 B：默认兜底 — 固定四个二级标题
        outline_prompt = f"""你是学术综述写作规划师。请基于给定调研笔记，为主题《{topic}》生成一份中文 Markdown 大纲。
要求：
1. 必须包含以下四个二级标题：{', '.join(WRITER_SECTION_TITLES)}。
2. 每个二级标题下至少给出 3 条要点，突出方法、实验、指标与对比结论。
3. 输出仅包含大纲本身，不要写正文段落。

【调研笔记】
{notes_content}
"""

    outline = llm.chat("你是严谨的学术写作规划师。", outline_prompt, []).strip()
    if not outline:
        fallback = [f"## {title}\n- 待补充要点1\n- 待补充要点2\n- 待补充要点3" for title in WRITER_SECTION_TITLES]
        outline = "\n\n".join(fallback)
    return outline


def _compose_review_by_sections(llm: LLMClient, topic: str, notes_content: str, outline: str, skill_content: str = "") -> str:
    section_texts = []
    # 如果有 Skill，从 Skill 生成的大纲中提取章节标题；否则使用默认四标题
    if skill_content and outline:
        import re as _re
        _extracted = _re.findall(r'^## (.+)$', outline, _re.MULTILINE)
        _section_titles = _extracted if _extracted else WRITER_SECTION_TITLES
    else:
        _section_titles = WRITER_SECTION_TITLES

    for idx, section_title in enumerate(_section_titles, start=1):
        previous_text = "\n\n".join(section_texts)
        # ━━━ Writer RAG：提取与当前章节相关的段落 ━━━
        relevant_notes = _extract_relevant_paragraphs(notes_content, section_title)

        # ━━━ 公共反省略约束 ━━━
        _no_omit_rule = """【⚠️ 严格禁止省略】
- 绝对禁止输出任何省略占位符，如「（此处省略...）」「（具体内容与上一版草稿相同）」「...（略）...」「（同上）」「（详见上文）」等
- 本节必须是完整、可直接阅读的正文，不允许以任何理由留空或跳过
- 如果素材不足，基于已有笔记进行合理总结，使用「根据现有资料」「初步分析表明」等措辞"""
        if skill_content:
            # 通道 A：Skill 优先 — 替换默认写作要求
            section_prompt = f"""你是学术综述写作者。请只撰写《{topic}》综述的第 {idx} 节：{section_title}。

{skill_content}

{_no_omit_rule}

【整体大纲】
{outline}

【已完成章节】
{previous_text if previous_text else '（无）'}

【调研笔记（自动筛选相关段落）】
{relevant_notes}

使用 Markdown 二级标题 ## {section_title}，输出只包含本节内容，与已完成章节保持衔接。"""
        else:
            # 通道 B：默认兜底
            section_prompt = f"""你是学术综述写作者。请只撰写《{topic}》综述的第 {idx} 节：{section_title}。
写作要求：
1. 使用 Markdown 二级标题，标题必须是：## {section_title}。
2. 内容要具体引用笔记中的模型、方法、实验指标和对比结论，不要空话。
3. 与已完成章节保持衔接，但不要重复。
4. 输出只包含本节内容。

{_no_omit_rule}

【整体大纲】
{outline}

【已完成章节】
{previous_text if previous_text else '（无）'}

【调研笔记（自动筛选相关段落）】
{relevant_notes}
"""
        section = llm.chat("你是严谨、老练的学术综述作者。", section_prompt, []).strip()
        if not section.startswith("##"):
            section = f"## {section_title}\n\n{section}"
        section_texts.append(section)

    return "\n\n".join(section_texts)


def _self_repair_review(raw_review: str, skill_content: str, provider_config: dict | None = None) -> str:
    """后生成自我修复：当使用了 Skill 时，根据 Skill 要求完全重写综述格式。

    采用"完全重写"策略：不是修补格式，而是按照 Skill 的结构重新组织整个综述。

    Args:
        raw_review: 原始生成的综述
        skill_content: Skill 的格式化要求

    Returns:
        修复后的综述（修复失败时返回原文）
    """
    llm = LLMClient(provider_config)

    # ━━━ 基于 Skill 要求完全重写综述 ━━━
    rewrite_prompt = f"""You are a strict formatting enforcer.

Your task: COMPLETELY REWRITE the literature review below according to the formatting requirements. Do NOT adjust the existing format — rewrite following the EXACT structure specified in the requirements.

CRITICAL RULES:
1. The skill requirements OVERRIDE the existing structure completely
2. Section names, heading levels, organization — all from the skill requirements
3. Fix any duplicate content by merging repeated sections
4. Remove the outline blockquote section entirely — output only the review body
5. Preserve ALL academic facts (methods, data, results, comparisons)
6. Output ONLY the final review — no explanations or code blocks
7. ⚠️ ABSOLUTELY FORBIDDEN: any omission markers like "(此处省略...)", "(与上一版草稿相同)", "...(略)...", "(同上)", "(详见上文)" — every section must be complete, self-contained text

【FORMATTING REQUIREMENTS — THIS IS THE ONLY ALLOWED STRUCTURE】
{skill_content}

【ORIGINAL REVIEW — EXTRACT ALL FACTS FROM HERE】
{raw_review}

CRITICAL: Output ONLY the fully rewritten review. The output must be the final review text directly."""
    try:
        result = llm.chat(
            "You are a strict formatting enforcer. Completely rewrite the review following the required structure. Output ONLY the final review text.",
            rewrite_prompt, []
        ).strip()
        if result:
            repaired = result
        else:
            repaired = raw_review
    except Exception:
        repaired = raw_review

    # ━━━ 验证和修正 ━━━
    verify_prompt = f"""You are a strict quality checker.

CHECK the review below for:
1. Section structure matching the requirements
2. Any duplicate content
3. Any markdown code blocks or explanations that should not be there

If anything is wrong, fix it. Output ONLY the corrected review text.

【REQUIREMENTS】
{skill_content}

【REVIEW TO VERIFY】
{repaired}

Output ONLY the verified/fixed review text."""
    try:
        result = llm.chat(
            "You are a quality checker. Output ONLY the corrected review text.",
            verify_prompt, []
        ).strip()
        if result:
            repaired = result
    except Exception:
        pass

    return repaired


def _self_critique_review(topic: str, raw_review: str, provider_config: dict | None = None) -> str:
    """后生成通用自审：检查综述完备性、一致性和重复性，以及省略占位符。

    无论是否使用 Skill，生成后对综述进行四维修查：
    1. 是否覆盖了所有预期章节
    2. 是否引用了具体论文的方法/数据/指标
    3. 是否有明显重复段落
    4. 是否包含省略占位符（如「此处省略」「与上一版草稿相同」等）
    """
    llm = LLMClient(provider_config)

    # ━━━ 第零步：正则快速检测省略占位符 ━━━
    import re as _re
    _omit_patterns = [
        r'[（(]此处省略[^）)]*[）)]',
        r'[（(]具体[^）)]*与上一版[^）)]*[）)]',
        r'[（(]详见[^）)]*[）)]',
        r'[（(]同上[^）)]*[）)]',
        r'[（(]略[）)]',
        r'\.\.\.\s*[（(]略[）)]',
        r'[（(]下同[）)]',
        r'[（(]见上文[^）)]*[）)]',
        r'[（(]参见[^）)]*[）)]',
        r'[（(]内容同[^）)]*[）)]',
    ]
    _has_omission = False
    for pattern in _omit_patterns:
        if _re.search(pattern, raw_review):
            _has_omission = True
            break

    critique_prompt = f"""你是严格的学术综述质检员。请检查以下综述草稿的质量。

研究主题：{topic}

【质量检查清单】
1. ✅ 是否包含了引言与背景 / 核心方法对比 / 实验结果分析 / 局限性与未来方向？
2. ✅ 核心方法对比部分是否引用了具体论文的方法名、模型名（不是空泛的"有研究提出"）？
3. ✅ 实验结果分析部分是否列出了具体数值指标（准确率、F1 等）？
4. ✅ 是否有明显的段落重复或内容冗余？
5. {"⚠️ 【重点】是否包含省略占位符？如「（此处省略...）」「（与上一版草稿相同）」「...（略）...」「（同上）」等 —— 如果有，必须将其替换为完整的正文内容！" if _has_omission else "✅ 是否包含省略占位符？如有，必须替换为完整正文。"}

【待检查综述】
{raw_review}

如果发现问题，在原文基础上**直接修复并输出完整综述**。
如果质量合格，**原样输出综述，不做任何修改**。

修复规则：
- 缺失章节：补充基本框架，标注"需进一步调研"
- 空泛引用：用已有笔记中的具体方法名/数据替代
- 重复段落：合并或删除
- {"⚠️ 省略占位符：**必须全部替换为完整的正文内容**。如果原始笔记中缺乏素材，基于已有信息进行合理推断和总结，用「根据现有资料」「初步分析表明」等措辞引导，绝对不允许保留任何省略标记" if _has_omission else "- 省略占位符：如有发现，替换为完整正文"}
- 不要添加额外解释，只输出最终综述"""
    try:
        result = llm.chat(
            "你是严格的学术综述质检员。直接输出质检后的完整综述，不做额外说明。",
            critique_prompt, []
        ).strip()
        if result and len(result) > 200:
            # 二次正则检查：确保修复后的结果没有残留省略占位符
            for pattern in _omit_patterns:
                if _re.search(pattern, result):
                    # 仍有残留，再做一次强制替换
                    result = _re.sub(r'[（(]此处省略[^）)]*[）)]', '（基于现有资料整理如下）', result)
                    result = _re.sub(r'[（(]具体[^）)]*与上一版[^）)]*[）)]', '（详见下文分析）', result)
                    result = _re.sub(r'\.\.\.\s*[（(]略[）)]', '...', result)
                    result = _re.sub(r'[（(]详见[^）)]*[）)]', '', result)
                    result = _re.sub(r'[（(]同上[）)]', '', result)
                    result = _re.sub(r'[（(]略[）)]', '', result)
                    result = _re.sub(r'[（(]下同[）)]', '', result)
                    result = _re.sub(r'[（(]见上文[^）)]*[）)]', '', result)
                    result = _re.sub(r'[（(]参见[^）)]*[）)]', '', result)
                    result = _re.sub(r'[（(]内容同[^）)]*[）)]', '', result)
            return result
    except Exception:
        pass
    return raw_review


def _append_analysis_context(notes_content: str, analysis_context: str = "") -> str:
    """Append optional cross-paper analysis as extra writing evidence."""
    analysis_context = (analysis_context or "").strip()
    if not analysis_context:
        return notes_content
    if len(analysis_context) > 12000:
        analysis_context = analysis_context[:12000] + "\n\n...[analysis context truncated]..."
    return (
        f"{notes_content}\n\n---\n\n"
        "## Cross-paper analysis insights for writing\n\n"
        "Use this synthesis when writing method comparisons, research lineage, "
        "limitations, and future directions.\n\n"
        f"{analysis_context}"
    )


def _build_evidence_catalog(
    notes_content: str,
    papers_list: list[dict] | None = None,
    repository_sources: list[dict] | None = None,
) -> tuple[str, list[dict]]:
    """Build stable citation IDs and compact evidence excerpts for the writer."""
    sources: list[dict] = []
    for index, paper in enumerate(papers_list or [], start=1):
        title = str(paper.get("title") or paper.get("paper_id") or f"论文 {index}").strip()
        paper_notes = str(paper.get("notes") or paper.get("abstract") or "").strip()
        sources.append({
            "id": f"P{index}",
            "kind": "paper",
            "title": title,
            "authors": str(paper.get("authors") or "").strip(),
            "year": str(paper.get("year") or paper.get("published") or "").strip()[:4],
            "identifier": str(paper.get("doi") or paper.get("paper_id") or "").strip(),
            "url": str(paper.get("url") or paper.get("pdf_url") or "").strip(),
            "excerpt": paper_notes[:5000],
        })

    # Legacy projects may only contain a Markdown notes document.  Preserve
    # citation support by treating its top-level paper sections as evidence.
    if not sources and notes_content.strip():
        sections = re.split(r"(?m)^##\s+", notes_content)
        for index, section in enumerate(sections[1:9], start=1):
            lines = section.strip().splitlines()
            if not lines:
                continue
            sources.append({
                "id": f"P{index}", "kind": "paper", "title": lines[0].strip(),
                "authors": "", "year": "", "identifier": "", "url": "",
                "excerpt": "\n".join(lines[1:])[:5000],
            })

    for index, repo in enumerate(repository_sources or [], start=1):
        sources.append({
            "id": f"R{index}",
            "kind": "repository",
            "title": str(repo.get("full_name") or repo.get("name") or f"Repository {index}"),
            "authors": str(repo.get("owner") or ""),
            "year": "",
            "identifier": str(repo.get("default_branch") or ""),
            "url": str(repo.get("html_url") or repo.get("url") or ""),
            "excerpt": str(repo.get("report") or repo.get("summary") or repo.get("readme") or "")[:6000],
        })

    blocks = []
    for source in sources:
        meta = " · ".join(filter(None, [source["authors"], source["year"], source["identifier"]]))
        blocks.append(
            f"### [{source['id']}] {source['title']}\n"
            f"类型：{'论文' if source['kind'] == 'paper' else 'GitHub 仓库'}"
            f"{('；元数据：' + meta) if meta else ''}\n"
            f"链接：{source['url'] or '未提供'}\n\n"
            f"{source['excerpt'] or '当前材料仅包含元数据，不能据此推断研究结果。'}"
        )
    return "\n\n---\n\n".join(blocks), sources


def _append_verified_references(review: str, sources: list[dict]) -> str:
    """Replace model-written references with a deterministic source list."""
    cleaned = re.sub(r"(?ms)\n##\s+参考来源\s*.*$", "", review).rstrip()
    if not sources:
        return cleaned
    lines = ["## 参考来源", ""]
    for source in sources:
        detail = ". ".join(filter(None, [source.get("authors", ""), source.get("year", "")]))
        identifier = source.get("identifier", "")
        suffix = "; ".join(filter(None, [detail, identifier, source.get("url", "")]))
        lines.append(f"- [{source['id']}] {source['title']}{(' — ' + suffix) if suffix else ''}")
    return cleaned + "\n\n" + "\n".join(lines) + "\n"


def assess_review_quality(review: str, sources: list[dict]) -> dict:
    """Return a transparent, non-LLM quality gate for the generated review."""
    valid_ids = {source["id"] for source in sources}
    cited_ids = set(re.findall(r"\[([PR]\d+)\]", review))
    invalid_ids = sorted(cited_ids - valid_ids)
    used_ids = sorted(cited_ids & valid_ids)
    required_sections = ["摘要", "研究范围", "主题", "方法", "局限", "结论", "参考来源"]
    headings = re.findall(r"(?m)^##\s+(.+)$", review)
    section_hits = sum(1 for name in required_sections if any(name in heading for heading in headings))
    omission = bool(re.search(r"此处省略|同上|详见上文|与上一版.*相同|\.\.\.\s*[（(]略", review))
    citation_coverage = round(len(used_ids) / max(1, len(valid_ids)), 2)
    score = max(0, min(100, int(section_hits / len(required_sections) * 35 + citation_coverage * 50 + (15 if not omission and not invalid_ids else 0))))
    return {
        "score": score,
        "source_count": len(valid_ids),
        "cited_source_count": len(used_ids),
        "citation_coverage": citation_coverage,
        "invalid_citations": invalid_ids,
        "section_coverage": round(section_hits / len(required_sections), 2),
        "has_omission_markers": omission,
        "status": "passed" if score >= 75 and not invalid_ids and not omission else "needs_review",
    }


def _verify_review_against_evidence(
    topic: str,
    review: str,
    evidence_catalog: str,
    provider_config: dict | None = None,
) -> str:
    """Final evidence-grounding pass that may delete, but never invent, claims."""
    if not evidence_catalog.strip():
        return review
    prompt = f"""你是学术综述的证据审计员。请直接修订全文，使其满足以下要求：
1. 具体方法、样本、数据、指标、数值与归因判断后必须使用证据目录中的 `[P#]` 或 `[R#]`。
2. 删除不存在于证据目录中的引用编号；不得创造新的来源、数字、作者、年份、DOI、页码或文件路径。
3. 证据不足的判断改写为“现有材料不足以判断”。
4. 保留跨来源综合、共识、分歧与局限分析，避免退化为逐篇摘要。
5. 输出完整 Markdown 正文，不输出解释，不自行撰写参考文献列表。

研究主题：{topic}

【唯一可引用的证据目录】
{evidence_catalog}

【待审计综述】
{review}
"""
    try:
        verified = LLMClient(provider_config).chat(
            "你是严格的证据审计员，只保留可由给定材料支持的学术陈述。", prompt, []
        ).strip()
        return verified or review
    except Exception:
        return review


def compose_review_from_notes(
    topic: str,
    notes_content: str,
    write_skill_content: str = "",
    analysis_context: str = "",
    provider_config: dict | None = None,
    papers_list: list[dict] | None = None,
    repository_sources: list[dict] | None = None,
) -> tuple[str, str, dict]:
    llm = LLMClient(provider_config)
    writing_source = _append_analysis_context(notes_content, analysis_context)
    evidence_catalog, evidence_sources = _build_evidence_catalog(
        writing_source, papers_list=papers_list, repository_sources=repository_sources
    )
    if evidence_catalog:
        writing_source = (
            f"{writing_source}\n\n---\n\n## 可引用证据目录（引用编号不可更改）\n\n"
            f"{evidence_catalog}"
        )
    notes_content = writing_source
    effective_skill = write_skill_content or DEFAULT_REVIEW_SKILL

    # 双通道：大纲 + 逐节正文
    # 修复：body 已包含完整 ## 标题，不再在前面重复 prepend outline
    outline = _build_writer_outline(llm, topic, writing_source, effective_skill)
    body = _compose_review_by_sections(llm, topic, writing_source, outline, effective_skill)
    # outline 作为前置目录，使用引用格式（>）避免与 body 中的 ## 标题重复
    review = f"> **综述大纲**（由 AI 规划，仅供参考）\n>\n" + "\n".join(f"> {line}" for line in outline.split("\n")) + f"\n\n---\n\n{body}"

    # 自我修复：当有 Skill 时，调用 LLM 检查并修复综述格式和结构
    review = _self_repair_review(review, effective_skill, provider_config)

    # ━━━ 通用自审 (Self-Critique)：检查完备性与一致性 ━━━
    review = _self_critique_review(topic, review, provider_config)

    review = _verify_review_against_evidence(topic, review, evidence_catalog, provider_config)
    review = _append_verified_references(review, evidence_sources)
    quality = assess_review_quality(review, evidence_sources)

    return outline, review, quality


def _build_fallback_notes_from_traces(topic: str, traces: list[dict]) -> str:
    """当 Agent 未写入草稿时，从 traces 中提取最低可用笔记，避免整次任务直接失败。"""
    if not traces:
        return ""

    high_signal_markers = [
        "title:",
        "doi:",
        "abstract:",
        "summary:",
        "标题：",
        "摘要：",
        "论文标题：",
    ]

    def _is_high_signal_observation(text: str) -> bool:
        lowered = text.lower()
        return any(marker in lowered for marker in high_signal_markers)

    observations = []
    for step in traces:
        if not isinstance(step, dict):
            continue
        action = str(step.get("action", ""))
        obs = str(step.get("observation", "")).strip()
        if not obs:
            continue
        if action in {
            "arxiv_search",
            "arxiv_fetch",
            "semantic_scholar_search",
            "semantic_scholar_fetch",
            "arxiv_pdf_reader",
            "crossref_search",
            "crossref_fetch_doi",
        } and _is_high_signal_observation(obs):
            observations.append((action, obs))

    if not observations:
        return ""

    snippets = []
    for idx, (action, obs) in enumerate(observations[:6], start=1):
        normalized = re.sub(r"\n{3,}", "\n\n", obs)
        snippets.append(f"### 线索 {idx}（{action}）\n{normalized[:1600]}")

    header = (
        f"# 自动兜底笔记\n\n"
        f"主题：{topic}\n\n"
        "说明：本次运行中 Agent 未正常执行 append_note。"
        "以下内容由系统从执行轨迹自动提取，用于保障后续 Writer 阶段可继续。\n\n"
    )
    return header + "\n\n".join(snippets) + "\n"

def run_agent_pipeline(user_topic: str, max_loops: int = 20, agent_callback=None, provider_config: dict | None = None):
    """
    暴露给后端和CLI共享的核心全链路逻辑
    """
    load_dotenv(find_dotenv(usecwd=True))

    # 动态构建本轮运行的独立目录
    import re as m_re
    safe_topic = m_re.sub(r'[/\:*?"<>|]', '_', user_topic)
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    folder_name = f"{safe_topic}_{timestamp}"
    work_dir = os.path.join(os.path.dirname(__file__), 'documents', folder_name)
    papers_dir = os.path.join(work_dir, 'papers')
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(papers_dir, exist_ok=True)

    planner_llm = LLMClient(provider_config)
    initial_plan = _build_initial_plan(planner_llm, user_topic)
    with open(os.path.join(work_dir, "plan.md"), "w", encoding="utf-8") as f:
        f.write(initial_plan)

    # ━━━ 从工具注册中心加载已启用的工具 ━━━
    tool_config_path = os.path.join(os.path.dirname(__file__), "config", "tools.json")
    registry = get_registry(tool_config_path)
    enabled_meta = registry.get_enabled()
    enabled_names = {m.name for m in enabled_meta}

    # 工具名 → 实例的工厂映射
    _tool_factories = {
        "arxiv_search": ArxivSearchTool,
        "arxiv_fetch": ArxivFetchTool,
        "arxiv_pdf_reader": lambda: ArxivPdfReaderTool(papers_dir=papers_dir),
        "arxiv_download_pdf": lambda: ArxivDownloadPdfTool(papers_dir=papers_dir),
        "semantic_scholar_search": SemanticScholarSearchTool,
        "semantic_scholar_fetch": SemanticScholarFetchTool,
        "crossref_search": CrossrefSearchTool,
        "crossref_fetch_doi": CrossrefFetchByDoiTool,
        "openalex_search": OpenAlexSearchTool,
        "clear_notes": lambda: ClearNoteTool(work_dir=work_dir),
        "append_note": lambda: AppendNoteTool(work_dir=work_dir),
    }

    active_tools = []
    for name in enabled_names:
        factory = _tool_factories.get(name)
        if factory:
            active_tools.append(factory())

    researcher_agent = BaseAgent(tools=active_tools, max_loops=max_loops, provider_config=provider_config)
    if agent_callback:
        agent_callback(researcher_agent, work_dir)

    research_query = (
        f"## 🎯 研究目标\n"
        f"对《{user_topic}》进行深度学术文献调研，自主搜索、阅读、记录至少 3 篇高质量前沿论文的详细笔记。\n\n"
        "## 📋 硬性完成标准（不满足不得 FINISH）\n"
        "1. 必须至少成功调用 append_note 记录了 3 篇不同论文的详细笔记（每篇包含：标题、作者、DOI、核心方法、关键发现、与你研究主题的关联、**以及必须注明 arXiv ID 或者是 PDF 下载链接**）。\n"
        "2. 必须至少使用了两个不同的学术数据库（arXiv + OpenAlex/Semantic Scholar (根据研究领域进行选择)；可辅以 Crossref 补充元数据）。\n"
        "3. 对每一篇你记录笔记的论文，必须尽力获取摘要。\n\n"
        "## 🧠 自主规划要求\n"
        "你是一个具备自主决策能力的研究员，不是死板的脚本执行器。请你：\n"
        "- **先规划，再执行**：在第一轮，用你的 thought 字段分析主题、拆分关键词策略（中→英学术关键词提取）、决定先用哪个数据库、预计搜索几轮。\n"
        "- **数据库选择优先级**：CS/AI/理工科优先使用 arxiv_search（arXiv限流较松）；医学/社科/综述性话题优先使用 openalex_search 补充；Semantic Scholar 检索能力强但限流极严，只在大规模检索或补充时使用。\n"
        "- **动态调整策略**：如果某个关键词没搜到好结果，自行换同义词/上位词/下位词重试，或切换数据库。不要死磕同一个查询。同一个数据库连续失败 2 次后必须换另一个数据库。\n"
        "- **429 错误处理**：如果某个数据库返回 HTTP 429（限流），说明该数据库暂时不可用，应立即切换到另一个数据库，不要反复重试同一个数据库。\n"
        "- **禁止中文关键词搜索**：arxiv / OpenAlex / Semantic Scholar 完全不支持中文。你的第一条搜索必须且只能用英文关键词。英文搜索零结果只能换英文同义词/近义词重试，绝不能降级为中文。直接用中文搜索 100% 零结果！\n"
        "- **自主决定笔记时机**：你可以在拿到足够的论文信息后随时写笔记，不必等所有搜索完成。\n"
        "- **允许搜索枯竭退出**：如果经过 5 轮以上搜索仍未找到任何相关论文，可以 FINISH 并告知用户该主题可能过于小众，需要更换主题词或主题。不要强行收录不相关的论文充数。\n"
        "- **遇到困难时**：如果某篇论文拿不到全文，自主决定是换一篇还是用摘要写简略笔记；如果某个数据库持续失败，果断换另一个。\n\n"
        "## 🛠 可用工具速览\n"
        "- clear_notes / append_note：管理研究草稿\n"
        "- arxiv_search：arXiv 搜索（已自带标题+作者+摘要，拿到即可直接写笔记）\n"
        "- arxiv_fetch：按 arXiv ID 补全单篇论文信息（仅 arxiv_search 信息不足时用）\n"
        "- arxiv_download_pdf：下载论文 PDF 到本地 papers/ 目录（纯下载，速度快，每篇笔记存完后都应调一次！）\n"
        "- arxiv_pdf_reader：下载 PDF 并提取正文文本（可获取论文详细内容，用于深度阅读）\n"
        "- semantic_scholar_search / semantic_scholar_fetch：Semantic Scholar 检索与详情\n"
        "- openalex_search：OpenAlex 跨学科综合学术搜索（推荐在人文社科、医学领域优先使用）\n"
        "- crossref_search / crossref_fetch_doi：Crossref 补全 DOI 与期刊元数据\n\n"
        "## ⚠️ 关键经验（前人的试错教训，请内化为你的行动准则）\n"
        "- arxiv_search 返回结果已包含标题+作者+摘要，拿到后可以先 append_note 再下载 PDF，不必额外调 arxiv_fetch。\n"
        "- **每写完一篇 append_note 后，立即用 arxiv_download_pdf 下载该论文 PDF，确保前端可查看。传入 arXiv ID 或者是包含 .pdf 的 URL。**\n"
        "- arxiv_download_pdf 接受 arXiv ID（如 2308.11432）或 http 开头的 PDF 短链。如果 paper_id 带版本号（如 v3），工具会自动去掉。\n"
        "- 中文主题必须在 thought 中自行翻译为英文关键词后再搜索。\n"
        "- crossref_search 传入论文标题/作者名，不要直接扔 arXiv ID。\n"
        "- 如果某个数据库返回 HTTP 429（限流），立即换另一个数据库，不要反复重试。\n"
        "- 不要调用不存在的工具（如 translate、none、wait）。所有可用工具已在上面列出。"
        "## 🧭 初始计划草案（供参考，可在 thought 中修订）\n"
        f"{initial_plan}\n\n"
        "现在请开始你的自主研究。先用 thought 制定/修订你的检索计划，然后执行。"
    )

    final_answer = researcher_agent.run(research_query)

    # ━━━ 自动兜底下载：扫描所有轨迹中的 arXiv ID，批量下载 PDF ━━━
    print(f"\n📥 [PDF 自动下载] 扫描轨迹中发现的论文 ID 并下载...")
    scanned_ids = set()
    download_results = []
    for step in researcher_agent.traces:
        if not isinstance(step, dict):
            continue
        obs = str(step.get("observation", ""))
        inp = str(step.get("input", ""))
        action_input = step.get("action_input", {})
        content = f"{obs} {inp} {json.dumps(action_input, ensure_ascii=False)}"
        # 匹配 arXiv ID 模式
        found_ids = re.findall(r'\b(\d{4}\.\d{4,5})(?:v\d+)?\b', content)
        scanned_ids.update(found_ids)
        # 也匹配 Semantic Scholar PaperID
        ss_ids = re.findall(r'(?:PaperID|paperId)[:\s]*([a-zA-Z0-9]{8,})', content)
        scanned_ids.update(ss_ids)
    
    download_tool = ArxivDownloadPdfTool(papers_dir=papers_dir)
    for pid in sorted(scanned_ids):
        if pid in [r.get("id") for r in download_results]:
            continue
        result = download_tool.execute(paper_id=pid)
        download_results.append({"id": pid, "result": result})
        print(f"  {'✅' if '成功' in result else '❌'} {pid}: {result[:80]}")
    
    # 将下载结果保存到元数据文件，供前端参考
    dl_meta_path = os.path.join(papers_dir, "_download_log.json")
    try:
        with open(dl_meta_path, "w", encoding="utf-8") as f:
            json.dump(download_results, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    print(f"📥 [PDF 自动下载] 完成，扫描到 {len(scanned_ids)} 个 ID，成功下载 {sum(1 for r in download_results if '成功' in r['result'])} 个 PDF 至 {papers_dir}")

    note_path = os.path.join(work_dir, 'research_notes.md')
    if not os.path.exists(note_path):
        fallback_notes = _build_fallback_notes_from_traces(user_topic, list(researcher_agent.traces))
        if fallback_notes:
            with open(note_path, 'w', encoding='utf-8') as f:
                f.write(fallback_notes)
        else:
            raise Exception('未能检索到与该主题相关的有效学术文献并生成笔记。这可能是因为该主题过于小众，或者应该尝试更通用的学术关键词（推荐使用英文）。请尝试更换研究主题或关键词后重试！')

    with open(note_path, 'r', encoding='utf-8') as f:
        notes_content = f.read()

    outline, final_review, review_quality = compose_review_from_notes(
        user_topic, notes_content, provider_config=provider_config
    )

    file_path = os.path.join(work_dir, 'final_review.md')

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(f'# 文献调研综述：{user_topic}\n\n')
        f.write(f'> **生产时间**：{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n\n')
        f.write("<!-- writer-stage: outline_then_sections -->\n\n")
        f.write(f"<!-- outline -->\n{outline}\n\n")
        f.write(final_review)

    # 收集已下载的论文列表
    downloaded_papers = []
    if os.path.exists(papers_dir):
        for fname in sorted(os.listdir(papers_dir)):
            if fname.endswith(".pdf"):
                downloaded_papers.append(fname)
    
    return {
        "researcher_result": notes_content,
        "writer_result": final_review,
        "traces": researcher_agent.traces,
        "output_file": folder_name,
        "papers": downloaded_papers,
        "review_quality": review_quality,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Session-aware: 分阶段执行函数（支持断点/继续）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _extract_keywords_from_plan(plan_text: str, provider_config: dict | None = None) -> list[dict]:
    """用 LLM 从规划文本中智能提取关键词三元组（中文→英文→同义词）"""
    llm = LLMClient(provider_config)
    extract_prompt = f"""从以下研究规划中，提取真正用于学术搜索的关键词。

规则：
1. 只提取搜索关键词本身（如"Table Data Extraction"），不要提取步骤描述、数据源名、策略说明
2. 每个关键词拆分为：original（中文原词）、english（英文学术关键词）、synonyms（替换同义词）
3. 提取 2~5 组最核心的关键词即可

【研究规划】
{plan_text}

请直接输出 JSON 数组（不要 markdown 标记）：
[{{"original": "中文", "english": "English term", "synonyms": "syn1, syn2"}}, ...]
"""
    try:
        response = llm.chat("你是关键词提取专家。只输出 JSON。", extract_prompt, [])
        # 提取 JSON 数组
        match = re.search(r'\[[\s\S]*\]', response)
        if match:
            import json as _json
            keywords = _json.loads(match.group())
            if isinstance(keywords, list) and len(keywords) > 0:
                return keywords
    except Exception:
        pass

    # 兜底：正则提取关键词区域
    # 找到"关键词拆分"部分中的行
    kw_section_start = re.search(r'(?:关键词拆分|关键词).*?(?:中英对照)?', plan_text)
    if kw_section_start:
        section = plan_text[kw_section_start.start():]
        # 取后面约 500 字符
        section = section[:500]
        # 提取中英文关键词对：中文 / 英文 / 同义词
        pairs = re.findall(
            r'[\u4e00-\u9fff\w][\u4e00-\u9fff\w\s\-+]{2,40}\s*/\s*[\w\s\-+]{2,40}(?:\s*/\s*[\u4e00-\u9fff\w\s,\-+]+)?',
            section
        )
        keywords = []
        for p in pairs[:5]:
            parts = re.split(r'\s*/\s*', p)
            keywords.append({
                "original": parts[0].strip() if len(parts) > 0 else p.strip(),
                "english": parts[1].strip() if len(parts) > 1 else "",
                "synonyms": parts[2].strip() if len(parts) > 2 else "",
            })
        if keywords:
            return keywords

    return []


def run_plan_only(user_topic: str, provider_config: dict | None = None) -> dict:
    """
    【阶段 1：仅规划】生成初始规划并提取关键词候选项。
    在此断点暂停，将关键词返回给用户确认。
    """
    load_dotenv(find_dotenv(usecwd=True))
    planner_llm = LLMClient(provider_config)
    initial_plan = _build_initial_plan(planner_llm, user_topic)
    keywords = _extract_keywords_from_plan(initial_plan, provider_config)

    return {
        "phase": "plan",
        "initial_plan": initial_plan,
        "keywords": keywords,
        "traces": [{
            "thought": f"[规划阶段] 为主题「{user_topic}」生成初始关键词方案",
            "action": "PLAN",
            "input": {"topic": user_topic},
            "observation": f"已生成 {len(keywords)} 个关键词候选项",
            "error_type": "",
        }],
    }


def _build_research_query(
    topic: str,
    initial_plan: str,
    confirmed_keywords: list[dict] = None,
    existing_papers: list[dict] | None = None,
    target_new_papers: int = 3,
    search_mode: str = "initial",
    available_tool_names: list[str] | None = None,
) -> str:
    """构建 Researcher Agent 的研究查询，支持用户确认的关键词"""
    keyword_hint = ""
    if confirmed_keywords:
        kw_lines = []
        for kw in confirmed_keywords:
            parts = [kw.get("original", "")]
            if kw.get("english"):
                parts.append(f"(EN: {kw['english']})")
            if kw.get("synonyms"):
                parts.append(f"[同义词: {kw['synonyms']}]")
            kw_lines.append("  - " + " ".join(parts))
        if kw_lines:
            keyword_hint = (
                "\n## ✅ 用户确认的关键词（请优先使用这些关键词搜索）\n"
                + "\n".join(kw_lines) + "\n"
            )

    target_new_papers = max(1, int(target_new_papers or 3))
    available_tool_names = available_tool_names or [
        "arxiv_search", "arxiv_fetch", "paper_register",
        "openalex_search", "crossref_search", "crossref_fetch_doi",
        "semantic_scholar_search", "semantic_scholar_fetch",
    ]
    search_tool_names = [name for name in available_tool_names if "search" in name]
    source_target = 2 if len(search_tool_names) >= 2 else 1
    tool_hint = "\n".join(f"- {name}" for name in available_tool_names)
    existing_papers = existing_papers or []
    existing_lines = []
    for paper in existing_papers[:40]:
        existing_lines.append(
            f"- {paper.get('paper_id', 'unknown')} | {paper.get('title', '')[:120]}"
        )
    incremental_hint = ""
    if existing_lines:
        incremental_hint = (
            "\n## ♻️ 增量检索约束\n"
            f"本轮必须实际新增 {target_new_papers} 篇论文。以下论文已经存在，禁止重复登记：\n"
            + "\n".join(existing_lines)
            + "\n请改用同义词、相邻主题、引用链或数据库后续分页扩展覆盖范围；"
              "如果 paper_register 返回‘已存在，未新增’，该论文不计入本轮成果。\n"
        )

    return (
        f"## 🎯 研究目标\n"
        f"对《{topic}》进行学术文献调研。你的任务是**搜索并新增收集**至少 {target_new_papers} 篇高质量论文的标题、作者、摘要。\n\n"
        "## 📋 硬性完成标准\n"
        f"1. 必须实际新增至少 {target_new_papers} 篇相关论文，并获得标题+作者+摘要。\n"
        f"2. 本轮已启用 {len(search_tool_names)} 个检索工具；应使用至少 {source_target} 个不同数据库工具。\n"
        f"3. **本轮新增够 {target_new_papers} 篇高质量论文后必须立即 FINISH，不要无谓重复搜索！**\n\n"
        "## ⛔ 严禁行为（违反直接判定失败）\n"
        "- **禁止用中文关键词搜索任何学术数据库**：所有数据库都只支持英文！必须先将中文翻译为英文！\n"
        "- **禁止调用不存在的工具（wait/sleep/manual/none 等）**：遇到 429 限流直接换数据库，不要等待！\n"
        "- **禁止用同一关键词反复搜索同一个数据库**：最多 2 次，之后必须换关键词或换数据库。\n"
        "- **禁止连续 3 轮用相同参数调用同一个工具**：观察返回是否相同，若是则立即换策略。\n"
        "- **禁止搜索到好论文后还继续搜同一篇**：搜到元数据后换新关键词找下一篇。\n"
        "- 搜索结果一次返回多篇候选时，先逐一处理其中尚未登记的相关论文，再发起新搜索；禁止每次只登记第一篇。\n"
        "- 增量检索时不要只重复数据库第一页；使用工具提供的 start、offset 或 page 参数继续翻页。\n"
        "- **禁止反复尝试搜索结果里的 PDF 链接**：全文交付由 paper_register 处理。\n\n"
        "## 🧠 自主规划要求\n"
        "你是一个具备自主决策能力的调研员。你的唯一任务是搜索和收集论文元数据，PDF 下载由系统在后台自动完成。\n"
        "- **先规划，再执行**：在第一轮，用你的 thought 字段分析主题、拆分关键词策略（中→英学术关键词提取）、决定先用哪个数据库、预计搜索几轮。\n"
        f"- **工具边界**：只能从本轮真实启用的工具 {available_tool_names} 中选择。规划和执行都不得调用未列出的数据库。\n"
        "- **疑似论文标题的主题**：如果用户主题像一篇完整英文标题，先用完整标题和核心短语做精确检索，再扩展同义词；不要一开始就退化成过于宽泛的 Data Mining 等词。\n"
        "- **动态调整策略**：如果某个关键词没搜到好结果，换同义词/上位词/下位词重试，或切换数据库。同一个数据库连续失败 2 次后换另一个数据库。\n"
        "- **429 错误处理**：返回 HTTP 429（限流），立即切换到另一个数据库，不要反复重试。\n"
        "- **arXiv 优先**：如果候选来自 arXiv，直接使用 arXiv ID 登记；不要为了换成 DOI 再查一次 Crossref。论文同时有 DOI 与 arXiv ID 时，把 arxiv_id 一并传给 paper_register。\n"
        "- **不要尝试下载 PDF**：arxiv_download_pdf 只接受 arXiv ID，而 Crossref 等返回的是 DOI，强行传入 DOI 只会失败。系统会在你收集完元数据后自动下载。\n"
        "- **遇到困难时**：如果某篇论文搜不到详细信息，换更泛化的关键词；如果某个数据库持续失败，果断换另一个。\n\n"
        "## 🛠 本轮真实可用工具（唯一允许列表）\n"
        f"{tool_hint}\n\n"
        "## ⚠️ 关键经验\n"
        "- 搜索结果获得 ID、标题、作者、摘要后，必须调用 paper_register(paper_id, title, authors, abstract, arxiv_id?, pdf_url?)；abstract 缺失会拒绝登记。\n"
        "- abstract 必须逐字来自搜索/详情工具的 Abstract 或 Summary，严禁根据标题自行编造摘要。\n"
        "- 数据源返回 OpenAccessPDF/pdf_url 时原样传入 pdf_url；没有时留空，严禁臆造下载地址。\n"
        "- paper_register 支持 arXiv ID 和 DOI 两种格式，OpenAlex 返回的 doi 可以直接使用。\n"
        "- **🔴 遇到 HTTP 429（限流）时，立即换另一个数据库搜索，不要等待、不要重试、不要调用不存在的工具（wait/sleep/manual 都不存在）！**\n"
        "- 🔴 所有学术数据库都只支持英文关键词！中文关键词搜不到任何结果！必须在 thought 中将中文翻译为英文后再搜索。\n"
        "- HTTP 429 立即换数据库。\n"
        + keyword_hint + incremental_hint +
        "## 🧭 初始计划草案（供参考，可在 thought 中修订）\n"
        f"{initial_plan}\n\n"
        "现在请开始你的调研。先用 thought 制定检索计划，然后执行。"
    )


def run_search_only(
    user_topic: str,
    initial_plan: str,
    confirmed_keywords: list[dict] = None,
    max_loops: int = 20,
    session_papers_dir: str = None,
    session_notes_path: str = None,
    agent_callback=None,
    provider_config: dict | None = None,
    existing_papers: list[dict] | None = None,
    target_new_papers: int = 3,
    search_mode: str = "initial",
) -> dict:
    """
    【阶段 2：仅搜索】使用确认后的关键词执行论文搜索和笔记记录。
    在此断点暂停，将论文列表和笔记返回给用户审核。
    """
    load_dotenv(find_dotenv(usecwd=True))

    # 使用 Session 目录或动态创建
    if session_papers_dir:
        papers_dir = session_papers_dir
        os.makedirs(papers_dir, exist_ok=True)
        # work_dir = sessions/{id}/，只取 papers 的父目录一次！！
        work_dir = os.path.dirname(papers_dir)  # sessions/{id}/
    else:
        import re as m_re
        safe_topic = m_re.sub(r'[/\:*?"<>|]', '_', user_topic)
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        folder_name = f"{safe_topic}_{timestamp}"
        work_dir = os.path.join(os.path.dirname(__file__), 'documents', folder_name)
        papers_dir = os.path.join(work_dir, 'papers')
        os.makedirs(work_dir, exist_ok=True)

    os.makedirs(papers_dir, exist_ok=True)

    # ━━━ 从工具注册中心加载已启用的工具 ━━━
    tool_config_path = os.path.join(os.path.dirname(__file__), "config", "tools.json")
    registry = get_registry(tool_config_path)
    enabled_names = {m.name for m in registry.get_enabled()}

    _tool_factories = {
        "arxiv_search": ArxivSearchTool,
        "arxiv_fetch": ArxivFetchTool,
        "semantic_scholar_search": SemanticScholarSearchTool,
        "semantic_scholar_fetch": SemanticScholarFetchTool,
        "crossref_search": CrossrefSearchTool,
        "crossref_fetch_doi": CrossrefFetchByDoiTool,
        "openalex_search": OpenAlexSearchTool,
    }

    active_tools = []
    for name in enabled_names:
        factory = _tool_factories.get(name)
        if factory:
            active_tools.append(factory())

    # paper_register 始终添加（不通过工具注册中心管理）
    session_id = os.path.basename(work_dir) if work_dir else ""
    from tools.paper_register import PaperRegisterTool
    active_tools.append(PaperRegisterTool(
        session_id=session_id,
        papers_dir=papers_dir,
        provider_config=provider_config,
        sessions_root=os.path.join(os.path.dirname(__file__), "sessions") if session_papers_dir else "",
    ))

    paper_progress_getter = None
    if session_papers_dir and session_id:
        from backend.session_manager import SessionManager, papers_match
        progress_manager = SessionManager(os.path.join(os.path.dirname(__file__), "sessions"))
        baseline_papers = list(existing_papers or [])

        def _registered_progress() -> int:
            current_papers = progress_manager.get_papers(session_id)
            return sum(
                1 for paper in current_papers
                if not any(papers_match(paper, old) for old in baseline_papers)
            )

        paper_progress_getter = _registered_progress

    researcher_agent = BaseAgent(
        tools=active_tools,
        max_loops=max_loops,
        provider_config=provider_config,
        min_new_papers=target_new_papers,
        paper_progress_getter=paper_progress_getter,
    )
    if agent_callback:
        agent_callback(researcher_agent, work_dir)

    research_query = _build_research_query(
        user_topic,
        initial_plan,
        confirmed_keywords,
        existing_papers=existing_papers,
        target_new_papers=target_new_papers,
        search_mode=search_mode,
        available_tool_names=list(researcher_agent.tools.keys()),
    )

    # ━━━ 双通道 Skill 注入：搜索阶段 ━━━
    if session_id:
        skills = _get_skills_for_session(session_id)
        search_skill_id = skills.get("search")
        skill_info = _load_skill_info(skill_id=search_skill_id)
        researcher_agent.traces.append(_build_skill_trace("search", skill_info))
        skill_content = skill_info.get("content", "")
        if skill_content:
            # 通道 A：Skill 优先 — 用 Skill 内容替换默认搜索策略，
            # 仅保留最小核心约束（工具列表 + JSON 格式 + 质量门禁）
            _MIN_SEARCH_RULES = (
                "## 核心硬约束（必须遵守，不可绕过）\n"
                "1. 必须严格按照 JSON 格式输出 thought/action/action_input。\n"
                "2. 只能调用上面列出的可用工具，不能调用不存在的工具。\n"
                "3. 完成搜索后，必须以 action: finish 结束。\n"
                "4. 遇到 HTTP 429 立即换数据库，不要反复重试同一目标。\n"
            )
            research_query = (
                "## 用户自定义搜索策略（请严格遵循以下策略进行文献搜索）\n\n"
                f"{skill_content}\n\n"
                "---\n\n"
                f"{_MIN_SEARCH_RULES}\n"
                f"\n研究主题：{user_topic}\n\n"
                + _build_research_query(
                    user_topic,
                    "按用户自定义搜索策略执行。",
                    confirmed_keywords,
                    existing_papers=existing_papers,
                    target_new_papers=target_new_papers,
                    search_mode=search_mode,
                    available_tool_names=list(researcher_agent.tools.keys()),
                )
            )
            print(f"[Skill] Injected search skill: {search_skill_id}")

    final_answer = researcher_agent.run(research_query)

    # PDF 兜底下载：只处理本轮真正新增且尚无文件的 arXiv 论文。
    # paper_register 已负责首选下载，不能再从所有搜索 observation 扫描候选 ID。
    scanned_ids = set()
    download_results = []
    for step in researcher_agent.traces:
        if not isinstance(step, dict):
            continue
        if step.get("action") != "paper_register" or "论文新增成功" not in str(step.get("observation", "")):
            continue
        action_input = step.get("input", {}) or {}
        paper_id = str(action_input.get("paper_id", ""))
        match = re.search(r'\b(\d{4}\.\d{4,5})(?:v\d+)?\b', paper_id)
        if match:
            scanned_ids.add(match.group(1))

    download_tool = ArxivDownloadPdfTool(papers_dir=papers_dir)
    for pid in sorted(scanned_ids):
        if os.path.exists(os.path.join(papers_dir, f"{pid}.pdf")):
            continue
        result = download_tool.execute(paper_id=pid)
        download_results.append({"id": pid, "result": result})

    dl_meta_path = os.path.join(papers_dir, "_download_log.json")
    try:
        with open(dl_meta_path, "w", encoding="utf-8") as f:
            json.dump(download_results, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    notes_content = ""

    # ━━━ 从 Session 已有的 papers_list 和 Agent 登记的论文汇总 ━━━
    papers_list = []
    if session_id:
        try:
            from backend.session_manager import SessionManager
            sessions_root = (
                os.path.join(os.path.dirname(__file__), "sessions")
                if session_papers_dir
                else os.path.join(os.path.dirname(os.path.dirname(papers_dir)))
            )
            mgr = SessionManager(sessions_root)
            papers_list = mgr.get_papers(session_id) or []
        except Exception:
            pass

    return {
        "phase": "search",
        "notes": notes_content,
        "papers": papers_list,
        "traces": researcher_agent.traces,
        "papers_dir": str(papers_dir),
    }


def run_write_from_notes(
    user_topic: str,
    notes_content: str,
    previous_review: str = "",
    user_feedback: str = "",
    rewrite_count: int = 0,
    max_rewrites: int = 100,
    session_id: str = None,
    analysis_context: str = "",
    provider_config: dict | None = None,
    papers_list: list[dict] | None = None,
    repository_sources: list[dict] | None = None,
) -> dict:
    """
    【阶段 3：撰写综述】基于笔记内容生成/重写综述初稿。

    Args:
        user_topic: 研究主题
        notes_content: 当前笔记内容
        previous_draft: 上一版草稿（重写时传入）
        user_feedback: 用户反馈意见（重写时传入）
        rewrite_count: 当前重写次数
        max_rewrites: 最大重写次数
        session_id: Session ID（用于加载 write Skill）
    """
    load_dotenv(find_dotenv(usecwd=True))

    if rewrite_count >= max_rewrites:
        return {
            "phase": "write",
            "review": previous_review or "已达到最大修改次数限制，请创建新会话或手动编辑。",
            "rewrite_count": rewrite_count,
            "max_rewrites": max_rewrites,
            "can_rewrite": False,
        }

    llm = LLMClient(provider_config)
    writing_source = _append_analysis_context(notes_content, analysis_context)
    notes_content = writing_source

    # ━━━ Skill 注入：加载 write 类型的自定义提示词 ━━━
    write_skill_content = ""
    skill_trace = None
    if session_id:
        skills_config = _get_skills_for_session(session_id)
        write_skill_id = skills_config.get("write")
        write_skill_info = _load_skill_info(skill_id=write_skill_id)
        skill_trace = _build_skill_trace("write", write_skill_info)
        write_skill_content = write_skill_info.get("content", "")
        if write_skill_content:
            print(f"[Skill] Injected write skill: {write_skill_id}")

    if user_feedback and previous_review:
        # 带反馈的重写 — 双通道：有 Skill 时替换默认要求
        if write_skill_content:
            feedback_prompt = f"""你是学术综述修改专家。请根据用户反馈修改综述。

{write_skill_content}

【用户反馈】
{user_feedback}

【上一版草稿】
{previous_review}

【调研笔记（参考）】
{notes_content}

请直接输出完整的修改后综述（Markdown格式）。"""
        else:
            feedback_prompt = f"""你是学术综述修改专家。请根据用户反馈修改综述。

【用户反馈】
{user_feedback}

【上一版草稿】
{previous_review}

【调研笔记（参考）】
{notes_content}

要求：
1. 认真采纳用户反馈中的建议
2. 保持学术严谨性
3. 直接输出完整的修改后综述（Markdown格式）
"""
        new_review = llm.chat("你是严谨的学术综述修改专家。", feedback_prompt, []).strip()
        if not new_review:
            new_review = previous_review
    else:
        # 首次撰写
        outline, review, quality = compose_review_from_notes(
            topic=user_topic,
            notes_content=notes_content,
            write_skill_content=write_skill_content,
            analysis_context=analysis_context,
            provider_config=provider_config,
            papers_list=papers_list,
            repository_sources=repository_sources,
        )
        new_review = review

    if user_feedback and previous_review:
        evidence_catalog, evidence_sources = _build_evidence_catalog(
            notes_content, papers_list=papers_list, repository_sources=repository_sources
        )
        new_review = _verify_review_against_evidence(
            user_topic, new_review, evidence_catalog, provider_config
        )
        new_review = _append_verified_references(new_review, evidence_sources)
        quality = assess_review_quality(new_review, evidence_sources)

    return {
        "phase": "write",
        "review": new_review,
        "traces": [skill_trace] if skill_trace else [],
        "analysis_used": bool((analysis_context or "").strip()),
        "quality": quality,
        "rewrite_count": rewrite_count + 1,
        "max_rewrites": max_rewrites,
        "can_rewrite": (rewrite_count + 1) < max_rewrites,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Session-aware: 整合的 Session-aware Pipeline
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_agent_pipeline_session(
    session_id: str = None,
    user_topic: str = "",
    start_phase: str = "plan",
    user_keywords: list[dict] = None,
    max_loops: int = 20,
    agent_callback=None,
    provider_config: dict | None = None,
    existing_papers: list[dict] | None = None,
    target_new_papers: int = 3,
    search_mode: str = "initial",
) -> dict:
    """
    Session-aware 流水线，支持从指定断点继续执行。

    Args:
        session_id: Session ID
        user_topic: 研究主题
        start_phase: 起始阶段 (plan / search / write)
        user_keywords: 用户确认的关键词（start_phase=search 时需要）
        max_loops: Agent 最大循环次数
        agent_callback: 可选回调

    Returns:
        dict: 当前阶段的执行结果
    """
    load_dotenv(find_dotenv(usecwd=True))

    if start_phase == "plan":
        # 阶段 1：仅规划
        result = run_plan_only(user_topic, provider_config=provider_config)
        result["session_id"] = session_id
        return result

    elif start_phase == "search":
        # 阶段 2：搜索（需要已知 initial_plan 和 keywords）
        if not user_keywords:
            raise ValueError("start_phase='search' 需要提供 user_keywords")

        # 重建 initial_plan（用于 Agent 上下文）
        planner_llm = LLMClient(provider_config)
        initial_plan = _build_initial_plan(planner_llm, user_topic)

        # 使用 Session 目录
        base_dir = os.path.dirname(__file__)
        from backend.tenant import tenant_path
        sessions_root = tenant_path(os.path.join(base_dir, "sessions"))
        session_papers_dir = str(sessions_root / session_id / "papers") if session_id else None
        session_notes_path = str(sessions_root / session_id / "notes" / "draft_notes.md") if session_id else None

        result = run_search_only(
            user_topic=user_topic,
            initial_plan=initial_plan,
            confirmed_keywords=user_keywords,
            max_loops=max_loops,
            session_papers_dir=session_papers_dir,
            session_notes_path=session_notes_path,
            agent_callback=agent_callback,
            provider_config=provider_config,
            existing_papers=existing_papers,
            target_new_papers=target_new_papers,
            search_mode=search_mode,
        )
        result["session_id"] = session_id
        return result

    elif start_phase == "write":
        # 阶段 3：撰写（需要已知 notes）
        if not user_topic:
            raise ValueError("start_phase='write' 需要提供 user_topic")

        # 从 Session 加载笔记
        notes_content = ""
        if session_id:
            base_dir = os.path.dirname(__file__)
            from backend.tenant import tenant_path
            notes_path = tenant_path(os.path.join(base_dir, "sessions")) / session_id / "notes" / "draft_notes.md"
            if os.path.exists(notes_path):
                with open(notes_path, 'r', encoding='utf-8') as f:
                    notes_content = f.read()

        result = run_write_from_notes(
            user_topic=user_topic,
            notes_content=notes_content,
            session_id=session_id,
            provider_config=provider_config,
        )
        result["session_id"] = session_id
        return result

    else:
        raise ValueError(f"未知的 start_phase: {start_phase}，可选值: plan / search / write")


if __name__ == '__main__':
    print('====== 🚀 AI Agent 双阶段管线：调研(Researcher) + 撰写(Writer) ======\n')

    # 动态获取用户想要调研的主题
    user_topic = input("请输入您想要调研的学术主题（直接回车默认'LLM Agent Memory机制'）：").strip()
    if not user_topic:
        user_topic = "LLM Agent Memory（内存框架/机制）"
    print(f"\n>>> [任务目标] 开始对《{user_topic}》进行深度检索与综述撰写...\n")

    print('==================================================')
    print('--> [阶段一] 启动 Researcher Agent (纯学术资料搜集与笔记分析)')
    print('--> [阶段二] 启动 Writer Agent (无 JSON 工具束缚的纯文本深加工)')
    print('==================================================')
    
    try:
        result = run_agent_pipeline(user_topic, max_loops=20)
        
        print('\n\n' + '='*50)
        print('✅ [Researcher 阶段达成]')
        print('='*50)
        print(result["researcher_result"])
        
        print(f'\n🎉 [大获成功]\n无视 ReAct 限制，极大扩充了文本长度。万字级全文综述已生成至：\n👉 {result["output_file"]}')
        
    except Exception as e:
        print(f'\n❌ Pipeline运行崩溃了：{str(e)}')

