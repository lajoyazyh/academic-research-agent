"""
Deep analysis tools：文献对比、研究脉络、空白发现

在 Write 阶段之后，基于已有笔记和论文元数据，让 LLM 产出三种深度分析报告。
"""
import json
from llms.client import LLMClient


def _parse_papers_from_notes(notes_content: str, papers_list: list[dict] = None) -> list[dict]:
    """从笔记内容和论文列表中提取结构化信息"""
    papers = []
    if papers_list:
        for p in papers_list:
            papers.append({
                "title": p.get("title") or p.get("paper_id", "Unknown"),
                "authors": p.get("authors", ""),
                "year": p.get("year", ""),
                "abstract": p.get("abstract", "")[:500],
                "source": p.get("source", ""),
            })
    
    # 如果笔记中有更多细节，也尝试提取
    if notes_content and len(papers) < 2:
        blocks = notes_content.split("\n论文id:")
        for block in blocks[1:]:
            lines = block.strip().split("\n")
            title = lines[0] if lines else "Unknown"
            papers.append({"title": title.strip(), "authors": "", "year": "", "abstract": block[:300]})
    
    return papers


def _build_paper_summary(papers: list[dict], language: str = "zh-CN") -> str:
    """构建论文摘要文本"""
    lines = []
    for i, p in enumerate(papers, 1):
        lines.append(f"{i}. {p.get('title', 'Unknown')}")
        if p.get('authors'):
            lines.append(f"   {'Authors' if language == 'en' else '作者'}: {p['authors']}")
        if p.get('year'):
            lines.append(f"   {'Year' if language == 'en' else '年份'}: {p['year']}")
        if p.get('abstract'):
            lines.append(f"   {'Abstract' if language == 'en' else '摘要'}: {p['abstract'][:200]}")
    return "\n".join(lines)


def compare_papers(topic: str, notes_content: str, papers_list: list[dict] = None, provider_config: dict | None = None) -> str:
    """精确文献对比：对多篇论文进行横向对比分析
    
    产出：方法对比表格 + 优缺点矩阵 + 适用场景分析
    """
    llm = LLMClient(provider_config)
    papers = _parse_papers_from_notes(notes_content, papers_list)
    paper_summary = _build_paper_summary(papers, llm.language)
    if llm.language == "en":
        prompt = f"""Compare the following papers about “{topic}” with precision. Return English Markdown with:

## Core Method Comparison
| Paper | Method or model | Core contribution | Experimental setup | Key metrics |
|---|---|---|---|---|

## Strengths and Limitations Matrix
| Paper | Strengths | Limitations | Suitable settings |
|---|---|---|---|

## Cross-paper Synthesis
- Shared assumptions and important differences
- Which settings each approach suits
- Complementary or composable ideas

Paper list:
{paper_summary}

Research notes:
{notes_content[:6000]}

Use only supplied evidence. Return at most 1,000 English words."""
        result = llm.chat("You are a rigorous academic comparison analyst.", prompt, []).strip()
        return result or "Comparison analysis could not be generated; verify that the paper notes are complete."
    
    prompt = f"""你是资深学术研究员。请对以下关于「{topic}」的论文进行精确对比分析。

要求输出 Markdown 格式，包含三个部分：

## 一、核心方法对比
| 论文 | 方法/模型 | 核心创新 | 实验设置 | 关键指标 |
|------|----------|---------|---------|---------|
（每篇论文一行，从笔记内容中提取关键信息）

## 二、优缺点矩阵
| 论文 | 优势 | 不足 | 适用场景 |
|------|------|------|---------|
（客观分析每篇论文的优劣）

## 三、综合对比总结
- 这些方法的共性和差异
- 最适用于什么场景
- 可组合/互补的点

【论文列表】
{paper_summary}

【研究笔记（含更多细节）】
{notes_content[:6000]}

请直接输出 Markdown，控制在 800 字以内。"""
    
    result = llm.chat("你是严谨的学术对比分析师。", prompt, []).strip()
    return result or "对比分析生成失败，请检查论文笔记是否完整。"


def trace_lineage(topic: str, notes_content: str, papers_list: list[dict] = None, provider_config: dict | None = None) -> str:
    """研究脉络梳理：按时间线/逻辑线梳理研究发展路径
    
    产出：时间线图 + 关键转折点 + 技术演进路径
    """
    llm = LLMClient(provider_config)
    papers = _parse_papers_from_notes(notes_content, papers_list)
    paper_summary = _build_paper_summary(papers, llm.language)
    if llm.language == "en":
        prompt = f"""Trace the development of research on “{topic}” from the supplied papers. Return English Markdown with:

## Research Timeline
Order the papers by time and identify foundational, incremental, review, or application work.

## Technical Evolution
Explain major changes in methods, representative contributions, and branches or convergences in the field.

## Textual Lineage Map
Use a compact arrow-based map connecting the works by identifier and year.

Paper list:
{paper_summary}

Research notes:
{notes_content[:6000]}

Do not invent chronology or relationships absent from the evidence. Return at most 1,000 English words."""
        result = llm.chat("You are a rigorous research-lineage analyst.", prompt, []).strip()
        return result or "Research lineage could not be generated; verify that the paper notes are complete."
    
    prompt = f"""你是学术研究脉络分析师。请基于以下关于「{topic}」的论文，梳理该领域的研究发展脉络。

要求输出 Markdown 格式，包含三个部分：

## 一、研究时间线
按时间排序，标注每篇论文在该领域的定位（开创性工作 / 改进工作 / 综述 / 应用拓展）

## 二、关键技术演进
- 从早期到当前，研究方法/思路发生了哪些关键变化
- 每个阶段的代表性工作和核心贡献
- 技术路线的分叉与融合

## 三、发展脉络图（文字版）
```
[早期工作 A (年份)] → [改进 B (年份)] → [当前 SOTA C (年份)]
                  ↘ [旁支 D (年份)] → [融合 E (年份)]
```

【论文列表】
{paper_summary}

【研究笔记】
{notes_content[:6000]}

请直接输出 Markdown，控制在 800 字以内。"""
    
    result = llm.chat("你是专业的学术脉络分析师。", prompt, []).strip()
    return result or "脉络分析生成失败，请检查论文笔记是否完整。"


def find_gaps(topic: str, notes_content: str, papers_list: list[dict] = None, provider_config: dict | None = None) -> str:
    """研究空白发现：识别当前研究中未被覆盖的子领域和开放问题
    
    产出：空白领域列表 + 开放问题 + 未来方向建议
    """
    llm = LLMClient(provider_config)
    papers = _parse_papers_from_notes(notes_content, papers_list)
    paper_summary = _build_paper_summary(papers, llm.language)
    if llm.language == "en":
        prompt = f"""Identify research gaps and future directions for “{topic}” using only the supplied papers. Return English Markdown with:

## Areas Covered by Current Evidence
Map each paper to the subtopics it actually addresses.

## Underexplored Directions
Assess methodological, dataset/evaluation, application, and interdisciplinary gaps. Clearly distinguish a demonstrated gap from an absence in this limited evidence set.

## Prioritized Future Research
For each short- or long-term direction, explain its value, a plausible entry point, and expected challenges.

Paper list:
{paper_summary}

Research notes:
{notes_content[:6000]}

Never claim the entire field lacks something merely because these papers omit it. Return at most 1,000 English words."""
        result = llm.chat("You are a rigorous research-gap analyst.", prompt, []).strip()
        return result or "Research gaps could not be generated; verify that the paper notes are complete."
    
    prompt = f"""你是学术前沿洞察专家。请基于以下关于「{topic}」的论文，分析当前研究中的空白和未来方向。

要求输出 Markdown 格式，包含三个部分：

## 一、已覆盖的研究子领域
列出当前论文已涉及的方向，标注每篇论文的覆盖范围

## 二、未充分探索的方向（Research Gaps）
- 方法论上的空白（哪些方法尚未被尝试）
- 数据集/评测上的空白（缺少基准或评测标准）
- 应用场景的空白（哪些实际场景未被覆盖）
- 跨领域的空白（哪些相关领域的方法可以引入但尚未引入）

## 三、未来研究方向建议
按优先级排序（短期可做 / 中长期方向），每个方向说明：
- 为什么值得研究
- 可能的切入思路
- 预计挑战

【论文列表】
{paper_summary}

【研究笔记】
{notes_content[:6000]}

请直接输出 Markdown，控制在 800 字以内。"""
    
    result = llm.chat("你是学术前沿洞察专家。", prompt, []).strip()
    return result or "研究空白分析生成失败，请检查论文笔记是否完整。"


def run_full_analysis(topic: str, notes_content: str, papers_list: list[dict] = None, provider_config: dict | None = None) -> dict:
    """运行全部三种分析，返回字典 {compare, lineage, gaps}"""
    return {
        "compare": compare_papers(topic, notes_content, papers_list, provider_config),
        "lineage": trace_lineage(topic, notes_content, papers_list, provider_config),
        "gaps": find_gaps(topic, notes_content, papers_list, provider_config),
    }
