import json
import os
import datetime
import re
from dotenv import load_dotenv, find_dotenv
from core.agent import BaseAgent
from tools.arxiv_tools import ArxivSearchTool, ArxivFetchTool
from tools.semantic_scholar_tools import SemanticScholarSearchTool, SemanticScholarFetchTool
from tools.crossref_tools import CrossrefSearchTool, CrossrefFetchByDoiTool
from tools.openalex_tools import OpenAlexSearchTool
from tools.pdf_tools import ArxivPdfReaderTool, ArxivDownloadPdfTool
from tools.file_tools import ClearNoteTool, AppendNoteTool
from llms.client import LLMClient


WRITER_SECTION_TITLES = [
    "引言与背景",
    "核心论文方法对比",
    "实验结果与工程实践分析",
    "局限性与未来研究方向",
]


def _build_initial_plan(llm: LLMClient, topic: str) -> str:
    plan_prompt = f"""你是调研规划师。请为主题《{topic}》产出一个“可执行的检索计划”，仅用 Markdown 要点列出：
1) 关键词拆分（中英对照）
2) 数据源与调用顺序（必须明确说明优先级：医学/社科类及跨学科主题优先使用 openalex_search，CS/AI及理工科优先使用 arxiv_search。Semantic Scholar仅作严重缺失时的后备补充且要警惕限流）
3) 选取/排除标准（例如时间下限、核心概念匹配度）
4) 失败回退策略（0结果、限流、检索过泛时如何修改关键词）
5) 预期的3~5步行动序列（每步务必写明要调用的具体工具名，如 openalex_search, arxiv_search, append_note 等）
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
            "- 行动序列：arxiv_search -> arxiv_fetch/pdf_reader -> openalex_search/semantic_scholar_search -> crossref_fetch_doi -> append_note\n"
        )
    return plan


def _build_writer_outline(llm: LLMClient, topic: str, notes_content: str) -> str:
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


def _compose_review_by_sections(llm: LLMClient, topic: str, notes_content: str, outline: str) -> str:
    section_texts = []
    for idx, section_title in enumerate(WRITER_SECTION_TITLES, start=1):
        previous_text = "\n\n".join(section_texts)
        section_prompt = f"""你是学术综述写作者。请只撰写《{topic}》综述的第 {idx} 节：{section_title}。
写作要求：
1. 使用 Markdown 二级标题，标题必须是：## {section_title}。
2. 内容要具体引用笔记中的模型、方法、实验指标和对比结论，不要空话。
3. 与已完成章节保持衔接，但不要重复。
4. 输出只包含本节内容。

【整体大纲】
{outline}

【已完成章节】
{previous_text if previous_text else '（无）'}

【调研笔记】
{notes_content}
"""
        section = llm.chat("你是严谨、老练的学术综述作者。", section_prompt, []).strip()
        if not section.startswith("##"):
            section = f"## {section_title}\n\n{section}"
        section_texts.append(section)

    return "\n\n".join(section_texts)


def compose_review_from_notes(topic: str, notes_content: str) -> tuple[str, str]:
    llm = LLMClient()
    outline = _build_writer_outline(llm, topic, notes_content)
    body = _compose_review_by_sections(llm, topic, notes_content, outline)
    # 确保大纲不被 ```markdown 围栏包裹
    if outline.startswith("```markdown") and outline.endswith("```"):
        outline = outline[len("```markdown"):-3].strip()
    elif outline.startswith("```markdown"):
        outline = outline[len("```markdown"):].strip()
    elif outline.startswith("```") and outline.endswith("```"):
        outline = outline[3:-3].strip()
    review = f"## 综述大纲\n\n{outline}\n\n---\n\n{body}"
    return outline, review


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

def run_agent_pipeline(user_topic: str, max_loops: int = 20, agent_callback=None):
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

    planner_llm = LLMClient()
    initial_plan = _build_initial_plan(planner_llm, user_topic)
    with open(os.path.join(work_dir, "plan.md"), "w", encoding="utf-8") as f:
        f.write(initial_plan)

    t1, t2 = ArxivSearchTool(), ArxivFetchTool()
    t3, t4 = SemanticScholarSearchTool(), SemanticScholarFetchTool()
    t5, t6 = CrossrefSearchTool(), CrossrefFetchByDoiTool()
    t7 = ArxivPdfReaderTool(papers_dir=papers_dir)
    t8 = ArxivDownloadPdfTool(papers_dir=papers_dir)
    t9 = ClearNoteTool(work_dir=work_dir)
    t10 = AppendNoteTool(work_dir=work_dir)
    t11 = OpenAlexSearchTool()

    researcher_agent = BaseAgent(tools=[t1, t2, t3, t4, t5, t6, t7, t8, t9, t10, t11], max_loops=max_loops)
    if agent_callback:
        agent_callback(researcher_agent, work_dir)

    research_query = (
        f"## 🎯 研究目标\n"
        f"对《{user_topic}》进行深度学术文献调研，自主搜索、阅读、记录至少 3 篇高质量前沿论文的详细笔记。\n\n"
        "## 📋 硬性完成标准（不满足不得 FINISH）\n"
        "1. 必须至少成功调用 append_note 记录了 3 篇不同论文的详细笔记。**注意：每一篇笔记必须非常详尽（约 300-500 字）**，一定要提炼出关键发现、方法或指标，并包含：标题、作者、DOI、核心方法、具体实验/数据/发现、对研究主题的深度点评、**以及必须注明 arXiv ID 或者是 PDF 下载链接**。\n"
        "2. 必须至少使用了两个不同的学术数据库（arXiv + OpenAlex/Semantic Scholar (根据研究领域进行选择)；可辅以 Crossref 补充元数据）。\n"
        "3. 对每一篇你记录笔记的论文，必须尽力获取摘要。\n\n"
        "## 🧠 自主规划要求\n"
        "你是一个具备自主决策能力的研究员，不是死板的脚本执行器。请你：\n"
        "- **先规划，再执行**：在第一轮，用你的 thought 字段分析主题、拆分关键词策略（中→英学术关键词提取）、决定先用哪个数据库、预计搜索几轮。\n"
        "- **数据库选择优先级**：CS/AI/理工科优先使用 arxiv_search（arXiv限流较松）；医学/社科/综述性话题优先使用 openalex_search 补充；Semantic Scholar 检索能力强但限流极严，只在大规模检索或补充时使用。\n"
        "- **动态调整策略**：如果某个关键词没搜到好结果，自行换同义词/上位词/下位词重试，或切换数据库。不要死磕同一个查询。同一个数据库连续失败 2 次后必须换另一个数据库。\n"
        "- **429 错误处理**：如果某个数据库返回 HTTP 429（限流），说明该数据库暂时不可用，应立即切换到另一个数据库，不要反复重试同一个数据库。"
        "- **自主决定笔记时机**：你可以在拿到足够的论文信息后随时写笔记，不必等所有搜索完成。\n"
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

    outline, final_review = compose_review_from_notes(user_topic, notes_content)

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
        "papers": downloaded_papers
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  迭代三新增：分阶段执行函数（支持断点/继续）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _extract_keywords_from_plan(plan_text: str) -> list[dict]:
    """用 LLM 从规划文本中智能提取关键词三元组（中文→英文→同义词）"""
    llm = LLMClient()
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


def run_plan_only(user_topic: str) -> dict:
    """
    【阶段 1：仅规划】生成初始规划并提取关键词候选项。
    在此断点暂停，将关键词返回给用户确认。
    """
    load_dotenv(find_dotenv(usecwd=True))
    planner_llm = LLMClient()
    initial_plan = _build_initial_plan(planner_llm, user_topic)
    keywords = _extract_keywords_from_plan(initial_plan)

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


def _build_research_query(topic: str, initial_plan: str, confirmed_keywords: list[dict] = None) -> str:
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

    return (
        f"## 🎯 研究目标\n"
        f"对《{topic}》进行深度学术文献调研，自主搜索、阅读、记录至少 3 篇高质量前沿论文的详细笔记。\n\n"
        "## 📋 硬性完成标准（不满足不得 FINISH）\n"
        "1. 必须至少成功调用 append_note 记录了 3 篇不同论文的详细笔记。\n"
        "   **注意：每一篇笔记必须非常详尽（约 300-500 字）且高度结构化！**\n"
        "   强制要求在 append_note 中使用以下 Markdown 格式：\n"
        "   论文标题：... \n"
        "   作者：... \n"
        "   摘要：[详细的背景和摘要段落] \n"
        "   关键发现：[使用无序列表 列出至少3条具体的指标或发现] \n"
        "   方法：[详细描述核心模型或数据集等] \n"
        "   结论：[对研究主题的深度点评以及与用户研究主题的关联] \n"
        "   并必须注明 arXiv ID 或 PDF 下载链接。\n"
        "2. 必须至少使用了两个不同的学术数据库（arXiv + OpenAlex/Semantic Scholar (根据研究领域进行选择)；可辅以 Crossref 补充元数据）。\n"
        "3. 对每一篇你记录笔记的论文，必须尽力获取摘要。\n\n"
        "## 🧠 自主规划要求\n"
        "你是一个具备自主决策能力的研究员，不是死板的脚本执行器。请你：\n"
        "- **先规划，再执行**：在第一轮，用你的 thought 字段分析主题、拆分关键词策略（中→英学术关键词提取）、决定先用哪个数据库、预计搜索几轮。\n"
        "- **数据库选择优先级**：CS/AI/理工科优先使用 arxiv_search（arXiv限流较松）；医学/社科/综述性话题优先使用 openalex_search 补充；Semantic Scholar 检索能力强但限流极严，只在大规模检索或补充时使用。\n"
        "- **动态调整策略**：如果某个关键词没搜到好结果，自行换同义词/上位词/下位词重试，或切换数据库。不要死磕同一个查询。同一个数据库连续失败 2 次后必须换另一个数据库。\n"
        "- **429 错误处理**：如果某个数据库返回 HTTP 429（限流），说明该数据库暂时不可用，应立即切换到另一个数据库，不要反复重试同一个数据库。"
        "- **自主决定笔记时机**：你可以在拿到足够的论文信息后随时写笔记，不必等所有搜索完成。\n"
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
        "- 不要调用不存在的工具（如 translate、none、wait）。所有可用工具已在上面列出。\n"
        + keyword_hint +
        "## 🧭 初始计划草案（供参考，可在 thought 中修订）\n"
        f"{initial_plan}\n\n"
        "现在请开始你的自主研究。先用 thought 制定/修订你的检索计划，然后执行。"
    )


def run_search_only(
    user_topic: str,
    initial_plan: str,
    confirmed_keywords: list[dict] = None,
    max_loops: int = 20,
    session_papers_dir: str = None,
    session_notes_path: str = None,
    agent_callback=None,
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
        note_path = os.path.join(work_dir, 'research_notes.md')
        # 如果调用者提供了 session_notes_path（sessions/{id}/notes/draft_notes.md），优先使用它
        if session_notes_path and os.path.exists(session_notes_path):
            note_path = session_notes_path
    else:
        import re as m_re
        safe_topic = m_re.sub(r'[/\:*?"<>|]', '_', user_topic)
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        folder_name = f"{safe_topic}_{timestamp}"
        work_dir = os.path.join(os.path.dirname(__file__), 'documents', folder_name)
        papers_dir = os.path.join(work_dir, 'papers')
        note_path = os.path.join(work_dir, 'research_notes.md')
        os.makedirs(work_dir, exist_ok=True)

    os.makedirs(papers_dir, exist_ok=True)

    t1, t2 = ArxivSearchTool(), ArxivFetchTool()
    t3, t4 = SemanticScholarSearchTool(), SemanticScholarFetchTool()
    t5, t6 = CrossrefSearchTool(), CrossrefFetchByDoiTool()
    t7 = ArxivPdfReaderTool(papers_dir=papers_dir)
    t8 = ArxivDownloadPdfTool(papers_dir=papers_dir)
    t9 = ClearNoteTool(work_dir=work_dir)
    t10 = AppendNoteTool(work_dir=work_dir)
    t11 = OpenAlexSearchTool()

    researcher_agent = BaseAgent(tools=[t1, t2, t3, t4, t5, t6, t7, t8, t9, t10, t11], max_loops=max_loops)
    if agent_callback:
        agent_callback(researcher_agent, work_dir)

    research_query = _build_research_query(user_topic, initial_plan, confirmed_keywords)
    final_answer = researcher_agent.run(research_query)

    # PDF 自动下载
    scanned_ids = set()
    download_results = []
    for step in researcher_agent.traces:
        if not isinstance(step, dict):
            continue
        obs = str(step.get("observation", ""))
        inp = str(step.get("input", ""))
        action_input = step.get("action_input", {})
        content = f"{obs} {inp} {json.dumps(action_input, ensure_ascii=False)}"
        found_ids = re.findall(r'\b(\d{4}\.\d{4,5})(?:v\d+)?\b', content)
        scanned_ids.update(found_ids)

    download_tool = ArxivDownloadPdfTool(papers_dir=papers_dir)
    for pid in sorted(scanned_ids):
        result = download_tool.execute(paper_id=pid)
        download_results.append({"id": pid, "result": result})

    dl_meta_path = os.path.join(papers_dir, "_download_log.json")
    try:
        with open(dl_meta_path, "w", encoding="utf-8") as f:
            json.dump(download_results, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    # 笔记处理
    if not os.path.exists(note_path):
        fallback_notes = _build_fallback_notes_from_traces(user_topic, list(researcher_agent.traces))
        if fallback_notes:
            with open(note_path, 'w', encoding='utf-8') as f:
                f.write(fallback_notes)

    notes_content = ""
    if os.path.exists(note_path):
        with open(note_path, 'r', encoding='utf-8') as f:
            notes_content = f.read()
    
    # 同步到 sessions/{id}/notes/draft_notes.md（SessionManager 从这里读取）
    if session_papers_dir:
        notes_draft_path = os.path.join(work_dir, 'notes', 'draft_notes.md')
        if notes_content:
            os.makedirs(os.path.dirname(notes_draft_path), exist_ok=True)
            with open(notes_draft_path, 'w', encoding='utf-8') as f:
                f.write(notes_content)

    # 收集论文列表：优先根据 notes_content（如果提供的 Session 环境），解析每篇笔记块并匹配本地 PDF
    papers_list = []
    if os.path.exists(papers_dir):
        pdf_names = set()
        for fname in sorted(os.listdir(papers_dir)):
            if fname.endswith(".pdf"):
                pdf_names.add(fname.replace(".pdf", ""))

        # 如果存在 notes_content（Session 模式），优先解析 notes 中的每篇论文条目
        def _extract_blocks(text: str) -> list[str]:
            # 先把��能被转义的 "\\n" 恢复为真实换行，便于后续正则按���解析
            text = text.replace('\\n', '\n')
            # 使用等号/短横线分隔线，或连续两个及以上的空行作为分割段落
            parts = re.split(r"\n={2,}\n|\n-{2,}\n|\n{2,}", text)
            return [p.strip() for p in parts if p.strip()]

        def _first_nonempty(*args):
            for a in args:
                if a:
                    return a
            return ""


        matched_pids = set()

        if notes_content and notes_content.strip():
            blocks = _extract_blocks(notes_content)
            for blk in blocks:
                # ensure escaped newlines are normalized
                blk_proc = blk.replace('\\n', '\n')

                # 提取论文ID（优先），标题，摘要
                arxiv_ids = re.findall(r"\b(\d{4}\.\d{4,5})(?:v\d+)?\b", blk_proc)
                pid_found = None
                if arxiv_ids:
                    # prefer the first
                    pid_found = arxiv_ids[0]
                    # if pdf exists without version
                    if pid_found in pdf_names:
                        matched_pid = pid_found
                    else:
                        # try matching partial
                        for p in pdf_names:
                            if p.startswith(pid_found):
                                matched_pid = p
                                break
                        else:
                            matched_pid = pid_found

                    if matched_pid not in matched_pids:
                        # 抽取标题（单行）
                        title = re.search(r'论文标题[：:]\s*(.+?)(?:\n|$)', blk_proc) or re.search(r'标题[：:]\s*(.+?)(?:\n|$)', blk_proc)
                        # 抽取摘要：允许多行，直到下一个已知字段（作者/标题/DOI/PDF）或两个连续换行
                        abstract = re.search(r'摘要[：:]\s*(.+?)(?=\n(?:作者|标题|论文标题|DOI|PDF)|\n{2,}|$)', blk_proc, re.DOTALL)
                        abstract_text = abstract.group(1).strip() if abstract else ""
                        # 尝试抽取作者
                        authors = re.search(r'作者[：:]\s*(.+?)(?:\n|$)', blk_proc)
                        authors_text = authors.group(1).strip() if authors else ""

                        papers_list.append({
                            "paper_id": matched_pid,
                            "title": _first_nonempty(title.group(1).strip() if title else "", matched_pid),
                            "authors": authors_text,
                            "source": "agent_search",
                            "source_type": "arxiv",
                            "status": "pending",
                            "abstract": (abstract_text[:500] if abstract_text else ""),
                            "notes": "",
                            "has_notes": False,
                            "added_at": datetime.datetime.now().isoformat(),
                        })
                        matched_pids.add(matched_pid)
                    continue

                # 否则尝试提取标题并用模糊匹配匹配 PDF 名称或已知 papers_list.json
                title_m = re.search(r'论文标题[：:]\s*(.+?)(?:\n|$)', blk_proc) or re.search(r'标题[：:]\s*(.+?)(?:\n|$)', blk_proc)
                # 抽取摘要（多行）
                abstract_m = re.search(r'摘要[：:]\s*(.+?)(?=\n(?:作者|标题|论文标题|DOI|PDF)|\n{2,}|$)', blk_proc, re.DOTALL)
                title = title_m.group(1).strip() if title_m else ""
                abstract = abstract_m.group(1).strip()[:500] if abstract_m else ""

                # 尝试在 pdf_names 中找到包含 title 关键字的文件名
                found_any = False
                if title:
                    title_tokens = [t.lower() for t in re.findall(r"[\w\u4e00-\u9fff]+", title)[:6]]
                    for pid in pdf_names:
                        low = pid.lower()
                        if all(tok in low for tok in title_tokens if len(tok) > 1):
                            if pid not in matched_pids:
                                papers_list.append({
                                    "paper_id": pid,
                                    "title": title,
                                    "authors": "",
                                    "source": "agent_search",
                                    "source_type": "arxiv",
                                    "status": "pending",
                                    "abstract": abstract,
                                    "notes": "",
                                    "has_notes": False,
                                    "added_at": datetime.datetime.now().isoformat(),
                                })
                                matched_pids.add(pid)
                                found_any = True
                    # 如果没有通过 filename 匹配到，仍添加一条以标题为名的记录（paper_id 设为标题摘要hash）
                if not found_any:
                    pseudo_id = re.sub(r"\s+", "_", (title or abstract[:30]))
                    if pseudo_id and pseudo_id not in matched_pids:
                        papers_list.append({
                            "paper_id": pseudo_id,
                            "title": title or pseudo_id,
                            "authors": "",
                            "source": "agent_search",
                            "source_type": "arxiv",
                            "status": "pending",
                            "abstract": abstract,
                            "notes": "",
                            "has_notes": False,
                            "added_at": datetime.datetime.now().isoformat(),
                        })
                        matched_pids.add(pseudo_id)

        # 如果 notes_content 不存在或解析未命中任何 PDF，再回退到从 traces 提取（更宽松地匹配多篇）
        if not papers_list:
            # 从 traces 中提取论文元数据（允许为单次 append_note 生成多篇记录，将不再在发现第一个匹配后 break）
            for step in researcher_agent.traces:
                obs = str(step.get("observation", ""))
                action = str(step.get("action", ""))
                action_input = step.get("action_input", {}) if isinstance(step.get("action_input", {}), dict) else {}

                if action == "append_note":
                    content = str(action_input.get("content", "") or step.get("input", ""))
                    # 查找所有可能的标题/摘要对
                    title_matches = list(re.finditer(r'标题[：:]\s*(.+?)(?:\n|$)', content))
                    if not title_matches:
                        title_matches = list(re.finditer(r'论文标题[：:]\s*(.+?)(?:\n|$)', content))

                    # 如果没有标题，仍尝试抽取单个摘要
                    if title_matches:
                        for tm in title_matches:
                            paper_title = tm.group(1).strip()
                            # 尝试提取该标题附近的摘要
                            tail = content[tm.end():tm.end()+2000]
                            abstract_match = re.search(r'摘要[：:]\s*(.+?)(?:\n|作者|关联|DOI|PDF)', tail, re.DOTALL)
                            paper_abstract = abstract_match.group(1).strip()[:500] if abstract_match else ""
                            for pid in pdf_names:
                                if pid in content or (paper_title and any(w in content for w in paper_title.split()[:3])):
                                    if not any(p.get("paper_id") == pid for p in papers_list):
                                        papers_list.append({
                                            "paper_id": pid,
                                            "title": paper_title or pid,
                                            "authors": "",
                                            "source": "agent_search",
                                            "source_type": "arxiv",
                                            "status": "pending",
                                            "abstract": paper_abstract,
                                            "notes": "",
                                            "has_notes": False,
                                            "added_at": datetime.datetime.now().isoformat(),
                                        })
                    else:
                        # 没有标题，尝试抽取 arXiv id
                        arxiv_ids = re.findall(r'\b(\d{4}\.\d{4,5})(?:v\d+)?\b', content)
                        for aid in arxiv_ids:
                            for pid in pdf_names:
                                if pid.startswith(aid):
                                    if not any(p.get("paper_id") == pid for p in papers_list):
                                        papers_list.append({
                                            "paper_id": pid,
                                            "title": pid,
                                            "authors": "",
                                            "source": "agent_search",
                                            "source_type": "arxiv",
                                            "status": "pending",
                                            "abstract": "",
                                            "notes": "",
                                            "has_notes": False,
                                            "added_at": datetime.datetime.now().isoformat(),
                                        })

                # 也从搜索结果中收集论文信息
                if action in ("arxiv_search", "openalex_search", "crossref_search", "semantic_scholar_search"):
                    # 解析搜索结果中的标题
                    for title_m in re.finditer(r'(?:Title|标题)[：:]\s*(.+?)(?:\n|$)', obs, re.IGNORECASE):
                        t = title_m.group(1).strip()
                        abs_m = re.search(r'(?:Summary|Abstract|摘要)[：:]\s*(.+?)(?=\n(?:ID|Title|Authors|DOI|$))', obs, re.IGNORECASE | re.DOTALL)
                        abstract = abs_m.group(1).strip()[:500] if abs_m else ""
                        # 找匹配的PDF，允许多匹配
                        for pid in pdf_names:
                            clean_pid = pid.replace("paper_", "").replace("_", "")
                            if clean_pid[:6] in obs or any(w.lower() in obs.lower() for w in t.split()[:3]):
                                if not any(p.get("paper_id") == pid for p in papers_list):
                                    papers_list.append({
                                        "paper_id": pid,
                                        "title": t,
                                        "authors": "",
                                        "source": "agent_search",
                                        "source_type": "arxiv",
                                        "status": "pending",
                                        "abstract": abstract,
                                        "notes": "",
                                        "has_notes": False,
                                        "added_at": datetime.datetime.now().isoformat(),
                                    })

        # 补漏：任何未匹配的 PDF
        for pid in pdf_names:
            if not any(p.get("paper_id") == pid for p in papers_list):
                papers_list.append({
                    "paper_id": pid,
                    "title": pid,
                    "authors": "",
                    "source": "agent_search",
                    "source_type": "arxiv",
                    "status": "pending",
                    "abstract": "",
                    "notes": "",
                    "has_notes": False,
                    "added_at": datetime.datetime.now().isoformat(),
                })

        # 如果处于 session 模式，持久化 papers_list 到 sessions/{id}/papers/papers_list.json，方便前端/SessionManager 读取
        try:
            if session_papers_dir:
                papers_list_path = os.path.join(papers_dir, 'papers_list.json')
                with open(papers_list_path, 'w', encoding='utf-8') as f:
                    json.dump(papers_list, f, ensure_ascii=False, indent=2)
        except Exception:
            # 忽略写入错误，返回结果仍然包含 papers
            pass

    return {
        "phase": "search",
        "notes": notes_content,
        "papers": papers_list,
        "traces": researcher_agent.traces,
        "papers_dir": str(papers_dir),
        "note_path": str(note_path),
    }


def run_write_from_notes(
    user_topic: str,
    notes_content: str,
    previous_draft: str = "",
    user_feedback: str = "",
    rewrite_count: int = 0,
    max_rewrites: int = 100,
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
    """
    load_dotenv(find_dotenv(usecwd=True))

    if rewrite_count >= max_rewrites:
        return {
            "phase": "write",
            "draft": previous_draft or "已达到最大修改次数限制，请创建新会话或手动编辑。",
            "rewrite_count": rewrite_count,
            "max_rewrites": max_rewrites,
            "can_rewrite": False,
        }

    llm = LLMClient()

    if user_feedback and previous_draft:
        # 带反馈的重写
        feedback_prompt = f"""你是学术综述修改专家。请根据用户反馈修改综述。

【用户反馈】
{user_feedback}

【上一版草稿】
{previous_draft}

【调研笔记（参考）】
{notes_content}

要求：
1. 认真采纳用户反馈中的建议
2. 保持学术严谨性
3. 直接输出完整的修改后综述（Markdown格式）
"""
        new_draft = llm.chat("你是严谨的学术综述修改专家。", feedback_prompt, []).strip()
        if not new_draft:
            new_draft = previous_draft
    else:
        # 首次撰写
        outline, review = compose_review_from_notes(user_topic, notes_content)
        new_draft = review

    return {
        "phase": "write",
        "draft": new_draft,
        "rewrite_count": rewrite_count + 1,
        "max_rewrites": max_rewrites,
        "can_rewrite": (rewrite_count + 1) < max_rewrites,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  迭代三新增：整合的 Session-aware Pipeline
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_agent_pipeline_session(
    session_id: str = None,
    user_topic: str = "",
    start_phase: str = "plan",
    user_keywords: list[dict] = None,
    max_loops: int = 20,
    agent_callback=None,
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
        result = run_plan_only(user_topic)
        result["session_id"] = session_id
        return result

    elif start_phase == "search":
        # 阶段 2：搜索（需要已知 initial_plan 和 keywords）
        if not user_keywords:
            raise ValueError("start_phase='search' 需要提供 user_keywords")

        # 重建 initial_plan（用于 Agent 上下文）
        planner_llm = LLMClient()
        initial_plan = _build_initial_plan(planner_llm, user_topic)

        # 使用 Session 目录
        base_dir = os.path.dirname(__file__)
        session_papers_dir = os.path.join(base_dir, "sessions", session_id, "papers") if session_id else None
        session_notes_path = os.path.join(base_dir, "sessions", session_id, "notes", "draft_notes.md") if session_id else None

        result = run_search_only(
            user_topic=user_topic,
            initial_plan=initial_plan,
            confirmed_keywords=user_keywords,
            max_loops=max_loops,
            session_papers_dir=session_papers_dir,
            session_notes_path=session_notes_path,
            agent_callback=agent_callback,
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
            notes_path = os.path.join(base_dir, "sessions", session_id, "notes", "draft_notes.md")
            if os.path.exists(notes_path):
                with open(notes_path, 'r', encoding='utf-8') as f:
                    notes_content = f.read()

        result = run_write_from_notes(
            user_topic=user_topic,
            notes_content=notes_content,
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
