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
        "1. 必须至少成功调用 append_note 记录了 3 篇不同论文的详细笔记（每篇包含：标题、作者、DOI、核心方法、关键发现、与你研究主题的关联、**以及必须注明 arXiv ID 或者是 PDF 下载链接**）。\n"
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

    return {
        "researcher_result": notes_content,
        "writer_result": final_review,
        "traces": researcher_agent.traces,
        "output_file": folder_name
    }


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
