(function () {
  "use strict";

  var STORAGE_KEY = "academic-agent:language";
  var language = localStorage.getItem(STORAGE_KEY) === "en" ? "en" : "zh-CN";

  var exact = {
    "智能学术综述助手": "Academic Research Assistant",
    "智能学术综述助手首页": "Academic Research Assistant home",
    "登录 · 智能学术综述助手": "Sign in · Academic Research Assistant",
    "个人中心 · 智能学术综述助手": "Profile · Academic Research Assistant",
    "使用指南 - 智能学术综述助手": "User Guide - Academic Research Assistant",
    "历史记录与收藏 - 智能学术助手": "History and Favorites - Academic Research Assistant",
    "Skills — 智能学术综述助手": "Skills — Academic Research Assistant",
    "AI 对话助手 - 智能学术助手": "AI Research Assistant - Academic Research Assistant",
    "主导航": "Main navigation",
    "工作流程": "Workflow",
    "数据安全": "Data security",
    "登录": "Sign in",
    "注册": "Sign up",
    "免费开始": "Start free",
    "面向个人研究者的文献工作台": "A literature workspace for independent researchers",
    "从一个研究问题，走到一篇有依据的综述初稿。": "Turn one research question into an evidence-grounded review draft.",
    "在同一条工作流中搜索论文、判断是否纳入、阅读原文、记录证据并生成综述。每一步都保留来源，方便你核查和继续修改。": "Search papers, screen them, read the full text, capture evidence, and draft a review in one workflow. Every step retains its sources for verification and revision.",
    "开始第一次研究": "Start your first research project",
    "看看如何工作": "See how it works",
    "产品特点": "Product highlights",
    "论文来源可追溯": "Traceable paper sources",
    "用户自带模型密钥": "Bring your own model key",
    "项目独立保存": "Projects saved separately",
    "研究工作台预览": "Research workspace preview",
    "多智能体协作记忆机制": "Collaborative memory for multi-agent systems",
    "候选论文": "Candidate papers",
    "次引用": "citations",
    "已纳入": "Included",
    "等待判断": "Awaiting decision",
    "论文证据": "Paper evidence",
    "核心结论": "Key finding",
    "结构化共享记忆能够减少代理之间的重复检索，并提高长任务中的协作一致性。": "Structured shared memory can reduce duplicated retrieval among agents and improve consistency in long-running collaborative tasks.",
    "查看原文依据 · 第 6 页": "View source evidence · page 6",
    "加入调研笔记": "Add to research notes",
    "完整但不复杂": "Complete without being complicated",
    "把文献综述拆成清楚的三个动作": "A clear three-step literature-review workflow",
    "系统处理重复劳动，你保留研究判断。": "The system handles repetitive work while you retain research judgment.",
    "描述研究问题": "Describe the research question",
    "用自然语言输入主题，系统生成可编辑的关键词并搜索相关论文。": "Describe a topic in natural language; the system suggests editable keywords and searches for relevant papers.",
    "筛选和核查证据": "Screen and verify evidence",
    "在摘要、方法和 PDF 原文之间切换，决定哪些论文真正进入综述。": "Move between abstracts, methods, and PDF evidence to decide which papers belong in the review.",
    "形成综述初稿": "Build the review draft",
    "基于已纳入论文生成笔记、分析和带引用的初稿，再继续对话修改。": "Generate notes, analysis, and a cited draft from included papers, then revise it through conversation.",
    "BYOK 数据边界": "BYOK data boundaries",
    "模型由你选择，密钥由你掌握。": "Choose the model and keep control of the key.",
    "API Key 只在调用模型时通过 HTTPS 发送，不写入研究项目、分析事件或服务端日志。默认只保留到当前浏览器会话结束。": "Your API key is sent over HTTPS only when the model is called. It is not written to projects, analytics, or server logs, and is kept only for the current browser session by default.",
    "密钥与研究数据分离": "Keys are separated from research data",
    "项目数据库不会保存模型密钥。": "The project database never stores model keys.",
    "独立研究空间": "Isolated research workspace",
    "登录用户的项目和文件彼此隔离。": "Each signed-in user's projects and files are isolated.",
    "结果保留来源": "Results retain their sources",
    "生成内容能够回到论文和 PDF 继续核查。": "Generated content links back to papers and PDF evidence for verification.",
    "从下一次文献检索开始": "Start with your next literature search",
    "少一些工具切换，多一些研究判断。": "Spend less time switching tools and more time making research judgments.",
    "创建研究空间": "Create a research workspace",
    "AI 生成内容可能存在错误，请始终核查论文原文。": "AI-generated content may contain errors. Always verify it against the original papers.",
    "把检索、阅读与综述写作放进同一个工作流。": "Bring search, reading, and review writing into one workflow.",
    "登录后，你的研究项目会与其他用户隔离保存。模型 API 由你自行配置，密钥只保留在当前浏览器。": "After signing in, your research projects are stored in an isolated workspace. You configure the model API, and its key remains in this browser.",
    "集中管理论文、笔记、研究会话与生成结果": "Manage papers, notes, research sessions, and generated artifacts in one place",
    "每位用户拥有独立工作区与独立模型配置": "Each user has an isolated workspace and model configuration",
    "欢迎回来": "Welcome back",
    "账号操作": "Account actions",
    "登录后继续你的研究工作。": "Sign in to continue your research.",
    "邮箱": "Email",
    "密码": "Password",
    "显示密码": "Show password",
    "显示 API Key": "Show API key",
    "忘记密码？": "Forgot password?",
    "登录服务尚未配置，请联系站点管理员。": "Sign-in is not configured. Contact the site administrator.",
    "或": "or",
    "使用 GitHub 继续": "Continue with GitHub",
    "授权包含仓库读写权限，用于调研仓库及把产物导出到你选择的仓库；Token 不会写入项目数据库。": "Authorization includes repository access for repository research and exporting artifacts to a repository you choose. The token is never stored in the project database.",
    "+ 新建综述": "+ New review",
    "新建综述": "New review",
    "切换深色模式": "Switch to dark mode",
    "本轮目标新增论文数，1 到 15": "Target number of new papers for this run, 1 to 15",
    "本轮最大检索轮数，1 到 80": "Maximum search rounds for this run, 1 to 80",
    "论文列表": "Paper list",
    "返回工作台新建研究": "Return to the workspace to start a research project",
    "输入问题，按回车发送": "Enter a question and press Enter to send",
    "退出登录": "Sign out",
    "管理你的账号，以及当前浏览器使用的模型 API。": "Manage your account and the model API used in this browser.",
    "当前登录身份及账号操作。": "Current identity and account actions.",
    "正在加载…": "Loading…",
    "已安全登录": "Signed in securely",
    "前往 GitHub 完成标准 OAuth 授权后，可以调研公开或私有仓库，并把综述提交到你选择的仓库。": "Complete the standard GitHub OAuth flow to research public or private repositories and commit a review to a repository you choose.",
    "正在检查连接…": "Checking connection…",
    "尚未连接": "Not connected",
    "连接时会请求仓库读写权限，用于检索与导出。": "Repository access is requested for repository research and artifact export.",
    "已可调研仓库并导出研究产物。": "Repository research and artifact export are available.",
    "重新授权": "Authorize again",
    "授权需要更新": "Authorization needs to be renewed",
    "重新连接后即可继续使用仓库功能。": "Reconnect to continue using repository features.",
    "重新连接": "Reconnect",
    "Token 只保留在当前浏览器会话。": "The token is kept only for the current browser session.",
    "前往 GitHub 授权": "Authorize with GitHub",
    "模型 API": "Model API",
    "选择模型提供商并测试连接。密钥默认只保留到当前浏览器会话结束。": "Choose a model provider and test the connection. The key is kept only for the current browser session by default.",
    "正在检查配置…": "Checking configuration…",
    "模型提供商": "Model provider",
    "智谱 AI": "Zhipu AI",
    "当前项目默认支持，适合中文学术研究。": "The project’s default provider, with strong support for Chinese-language research.",
    "使用 OpenAI 官方 API。": "Use the official OpenAI API.",
    "高级选项；需要自行确认聊天和向量接口兼容性。": "Advanced option; confirm chat and embedding endpoint compatibility with your provider.",
    "请填写聊天模型": "Enter a chat model",
    "不启用向量模型（关键词检索）": "Disable embeddings (keyword retrieval)",
    "请输入 API Key。": "Enter an API key.",
    "请选择或填写聊天模型。": "Select or enter a chat model.",
    "Base URL 格式无效，请填写完整的 http:// 或 https:// 地址。": "The Base URL is invalid. Enter a complete http:// or https:// URL.",
    "模型配置已保存，请测试连接确认可用。": "Model configuration saved. Test the connection to verify it.",
    "需要配置模型后才能使用 AI 研究功能。": "Configure a model before using AI research features.",
    "隐藏 API Key": "Hide API key",
    "正在测试聊天和向量模型…": "Testing chat and embedding models…",
    "连接测试失败": "Connection test failed",
    "聊天与向量模型均可用": "Chat and embedding models are available",
    "聊天模型可用，向量模型未启用": "Chat model available; embeddings disabled",
    "连接测试成功。": "Connection test succeeded.",
    "模型连接需要检查": "Model connection needs attention",
    "连接失败，请检查配置。": "Connection failed. Check the configuration.",
    "聊天模型已连接，但向量请求失败。这不一定是模型名称错误，也可能是向量权限、账户额度或频率限制；请切换 embedding-3 / embedding-2，或暂时选择不启用向量模型。": "The chat model is connected, but the embedding request failed. The cause may be model access, account quota, or rate limits rather than the model name. Try embedding-3 or embedding-2, or temporarily disable embeddings.",
    "暂时无法完成连接测试": "Unable to complete the connection test",
    "研究服务暂时不可用，请稍后重试。": "The research service is temporarily unavailable. Try again later.",
    "配置已保存在此设备。": "Configuration saved on this device.",
    "配置仅在当前浏览器会话中有效。": "Configuration is active only for this browser session.",
    "配置已保存。现在可以返回工作台开始研究。": "Configuration saved. Return to the workspace to begin research.",
    "确定清除当前浏览器中的模型配置吗？": "Clear the model configuration from this browser?",
    "模型配置已清除。": "Model configuration cleared.",
    "已从当前浏览器清除 API Key。": "The API key was cleared from this browser.",
    "GitHub 授权未开始": "GitHub authorization did not start",
    "无法打开 GitHub 授权页，请检查网络后重试。": "The GitHub authorization page could not be opened. Check the network and retry.",
    "用户": "User",
    "自定义 OpenAI-compatible": "Custom OpenAI-compatible",
    "聊天模型": "Chat model",
    "向量模型": "Embedding model",
    "我们不会把密钥写入项目数据库或分析事件。": "The key is never written to the project database or analytics events.",
    "用于论文语义检索；不可用时系统将明确提示并降级。": "Used for semantic paper retrieval. If unavailable, the system reports it explicitly and uses a supported fallback path.",
    "高级连接设置": "Advanced connection settings",
    "调用模型时，API Key 会通过 HTTPS 随请求发送给研究服务，但不会写入项目数据库、研究文件、服务端配置或日志。使用公共设备后请清除配置并退出登录。": "When a model is called, the API key is sent to the research service over HTTPS. It is never written to the project database, research files, server configuration, or logs. Clear the configuration and sign out after using a shared device.",
    "记住在此设备": "Remember on this device",
    "不勾选时，关闭浏览器会话后自动清除。": "If unchecked, the key is cleared when the browser session ends.",
    "记住在此设备 不勾选时，关闭浏览器会话后自动清除。": "Remember on this device. If unchecked, the key is cleared when the browser session ends.",
    "完整操作流程": "Complete workflow",
    "📋 完整操作流程": "📋 Complete workflow",
    "数据来源": "Data sources",
    "🛠 数据来源": "🛠 Data sources",
    "常见问题": "Frequently asked questions",
    "❓ 常见问题": "❓ Frequently asked questions",
    "首页新建综述": "Create a review from the workspace",
    "在首页点击「+ 新建综述」卡片，只需要输入研究主题。关键词种子输入已隐藏但仍保留兼容链路，点击「生成规划」后系统会先显示“关键词生成中...”，再给出可编辑的关键词建议。": "Select “+ New review” in the workspace and enter only the research topic. The legacy seed-keyword input remains compatible but hidden. After you generate a plan, the system proposes editable search terms.",
    "进入控制台后，点击「AI检索论文」按钮。Agent 会自主调用 arXiv、OpenAlex、Crossref 等学术数据库，根据确认的关键词搜索相关论文，每篇论文自动提取标题、作者和摘要。": "In the console, select “AI paper search.” The agent searches enabled scholarly databases such as arXiv, OpenAlex, and Crossref using the confirmed keywords, then extracts each paper’s title, authors, and abstract.",
    "管理论文来源": "Manage paper sources",
    "检索完成后，左侧显示论文列表。你可以点击 ✓ 选中论文、✕ 移除不需要的论文，或通过「添加论文」手动上传 PDF/arXiv ID。每篇论文显示摘要预览和笔记/综述状态。": "After the search, papers appear in the source list. Include relevant papers, exclude unsuitable ones, or add a PDF or arXiv ID manually. Each paper shows an abstract preview and its notes/review status.",
    "选中需要深度分析的论文后，点击「生成笔记」。系统会为每篇选中的论文自动生成结构化学术笔记，包含核心方法、关键发现、与研究主题的关联分析。": "Include the papers to analyze, then select “Generate notes.” The system creates structured notes for every included paper, covering core methods, key findings, and relevance to the research question.",
    "所有选中论文的笔记生成完毕后，点击「生成综述」。AI Writer 会基于笔记内容撰写完整综述，包括引言与背景、核心方法对比、实验分析、局限性与未来方向四大章节。": "After notes have been generated, select “Generate review.” The writer synthesizes the evidence into a complete literature review with citations, comparisons, limitations, and future directions.",
    "点击论文可在右侧「摘要」视图查看基本信息，切换到「笔记」视图查看详细笔记，切换到「综述」视图阅读完整综述。对话区默认是普通问答；打开「Agent 模式」后，隐式修改请求会先由 AI 判断是否为修订意图，再在聊天中显示「确认 / 取消」按钮。若你想直接修订，也可以输入「/修订 + 修改意见」。": "Select a paper to inspect its summary and notes, or switch to Review to read the complete draft. Chat mode answers questions. Agent mode detects revision requests and asks for confirmation before editing. Use “/revise” followed by instructions to revise directly.",
    "CS/AI/理工科优先，包含标题+作者+摘要，限流较宽松": "Best for computer science, AI, and STEM; provides titles, authors, and abstracts with relatively permissive rate limits.",
    "跨学科综合学术搜索，人文社科/医学优先使用": "Cross-disciplinary scholarly search, useful for social sciences, humanities, and medicine.",
    "检索能力强但限流极严，仅作大规模补充检索": "Strong discovery coverage but strict rate limits; used as a supplementary source.",
    "补全 DOI 与期刊元数据，支持按标题/作者搜索": "Completes DOI and journal metadata and supports title or author search.",
    "提示：普通问题直接提问即可；需要修订时可先切换 Agent 模式，系统会先判定是否为修改意图并要求确认。也可直接输入 /修订 + 修改意见。": "Tip: ask ordinary questions directly. For revisions, switch to Agent mode and confirm the detected change, or use /revise followed by your instructions.",
    "Q: 为什么没有搜到论文？": "Q: Why were no papers found?",
    "A: 尝试使用英文关键词，或换用更通用的学术术语。系统会自动在多个数据库间切换，如果某数据库限流会自动切换到备选数据库。": "A: Try focused English keywords or broader scholarly terms. The system can switch among enabled databases when a provider is rate-limited.",
    "Q: 综述大纲显示异常怎么办？": "Q: What if the review outline is displayed incorrectly?",
    "A: 系统已自动处理 Markdown 围栏包裹问题。如果仍有问题，刷新页面即可。新生成的综述不会再有此问题。": "A: The system removes accidental Markdown code fences automatically. If an older draft still looks wrong, refresh the page and regenerate it if needed.",
    "Q: 可以修改生成的内容吗？": "Q: Can I revise generated content?",
    "A: 可以。现在普通对话和修订协同已经合并到同一个聊天区：Agent 模式下输入修改意见后，系统会先判断是否真的是修订请求，再在对话里确认后执行；也可以直接用 /修订 + 修改意见 明确触发。": "A: Yes. Chat and revision share one conversation area. Agent mode identifies a proposed edit and asks for confirmation, while /revise followed by instructions applies an explicit revision request.",
    "AI paper search 搜索阶段": "AI paper search · Search stage",
    "笔记生成": "Note generation",
    "综述生成": "Review generation",
    "搜索阶段": "Search stage",
    "笔记生成 笔记阶段": "Note generation · Notes stage",
    "笔记阶段": "Notes stage",
    "综述生成 综述阶段": "Review generation · Review stage",
    "综述阶段": "Review stage",
    "查看系统默认策略（不可编辑）": "View the system default strategy (read-only)",
    "默认搜索策略": "Default search strategy",
    "默认笔记生成策略": "Default note-generation strategy",
    "证据综合型综述策略": "Evidence-synthesis review strategy",
    "证据综合型叙述综述": "Evidence-synthesis narrative review",
    "证据综合型叙述综述写作预设适合大多数个人研究主题，强调跨论文主题综合、分歧解释与可核验引用。": "A narrative-review preset for most independent research topics, emphasizing cross-paper synthesis, explanation of disagreements, and verifiable citations.",
    "系统综述写作框架": "Systematic-review writing framework",
    "系统综述写作框架写作预设适合已经明确检索范围与筛选标准的项目；不会虚构 PRISMA 流程或检索数量。": "A writing preset for projects with a defined search scope and screening criteria. It never fabricates a PRISMA process or search counts.",
    "技术方法对比综述": "Technical method comparison review",
    "技术方法对比综述写作预设适合计算机、AI 与工程主题，强调任务定义、架构、数据集、指标、成本和复现条件。": "A preset for computing, AI, and engineering topics, emphasizing task definitions, architectures, datasets, metrics, cost, and reproducibility conditions.",
    "范围综述与研究地图": "Scoping review and research map",
    "范围综述与研究地图写作预设适合主题宽、概念尚未稳定的领域，侧重概念边界、研究类型分布和空白地图。": "A preset for broad fields with unsettled concepts, focused on conceptual boundaries, distributions of research types, and gap mapping.",
    "复制为可编辑 Skill": "Copy as an editable skill",
    "AI 学术助手": "AI research assistant",
    "输入你的问题...": "Enter your question...",
    "智能学术综述助手": "Academic Research Assistant",
    "Notebook 研究控制台": "Research Console",
    "Notebook 风格控制台 - 智能学术综述": "Research Console - Academic Review",
    "个人研究工作台": "Personal Research Workspace",
    "继续你的研究，或从一个新问题开始。": "Continue your research or start with a new question.",
    "搜索、筛选、阅读论文，并把可核查的证据整理成综述初稿。": "Search, screen, and read papers, then turn verifiable evidence into a review draft.",
    "新建研究": "New research",
    "继续最近项目": "Continue recent project",
    "首次使用": "First time here",
    "三步开始研究": "Start in three steps",
    "配置并测试模型": "Configure and test a model",
    "输入研究问题": "Enter a research question",
    "开始检索论文": "Start searching for papers",
    "在项目中完成": "Complete inside the project",
    "开始一项新研究": "Start a new research project",
    "一个必填项": "One required field",
    "先写下你真正想回答的问题。进入项目后，系统会给出可编辑的检索词建议。": "Write the question you actually want to answer. The system will suggest editable search terms after the project is created.",
    "研究问题": "Research question",
    "关键词种子（可选）": "Seed keywords (optional)",
    "提前规划检索词": "Plan search terms in advance",
    "可以跳过；进入项目后再生成和确认检索词。": "Optional; you can generate and confirm search terms inside the project.",
    "创建研究": "Create research",
    "取消": "Cancel",
    "最近研究": "Recent research",
    "暂无活动记录": "No recent activity",
    "继续你的研究": "Continue your research",
    "工作台概览": "Workspace overview",
    "综述项目": "Review projects",
    "收录论文": "Included papers",
    "撰写笔记": "Notes written",
    "完成综述": "Completed reviews",
    "状态分布": "Status distribution",
    "暂无数据": "No data yet",
    "快捷入口": "Quick access",
    "研究会话": "Research sessions",
    "新建会话": "New session",
    "历史记录与收藏夹": "History and favorites",
    "收藏的综述": "Saved reviews",
    "这里展示你收藏的综述报告和所有正在进行或已完成的研究会话。": "Saved reviews and all active or completed research sessions appear here.",
    "来源": "Sources",
    "目标新增": "Target new",
    "最大轮数": "Maximum rounds",
    "篇": "papers",
    "轮": "rounds",
    "推荐 25 轮；系统不会超过你设置的上限。": "Recommended: 25 rounds. The system will not exceed your limit.",
    "搜索相关论文": "Search papers",
    "AI 检索论文": "AI paper search",
    "AI检索论文": "AI paper search",
    "停止检索": "Stop search",
    "添加论文": "Add paper",
    "自动进行": "Run automatically",
    "检索到和添加的论文": "Searched and added papers",
    "点击「搜索相关论文」开始。": "Select “Search papers” to begin.",
    "尚未纳入论文": "No papers included",
    "请先在论文卡片中选择“纳入综述”": "Include papers from the paper cards first",
    "生成笔记": "Generate notes",
    "生成综述": "Generate review",
    "详情": "Details",
    "摘要": "Summary",
    "轨迹": "Trace",
    "笔记": "Notes",
    "分析": "Analysis",
    "综述": "Review",
    "内容": "Content",
    "问答": "Q&A",
    "研究进度": "Research progress",
    "检索": "Search",
    "筛选": "Screen",
    "阅读与笔记": "Read and take notes",
    "综合分析": "Synthesis",
    "综述完成": "Review complete",
    "需要配置": "Setup required",
    "模型已连接": "Model connected",
    "就绪": "Ready",
    "返回工作台": "Back to workspace",
    "更多": "More",
    "高级工具": "Advanced tools",
    "GitHub 仓库调研": "GitHub repository research",
    "导出成果": "Export artifacts",
    "导出研究成果": "Export research artifacts",
    "完整 ZIP": "Complete ZIP",
    "导出到 GitHub": "Export to GitHub",
    "提交 Markdown 到仓库": "Commit Markdown to repository",
    "请先连接 GitHub": "Connect GitHub first",
    "GitHub 仓库": "GitHub repository",
    "目标仓库": "Target repository",
    "仓库地址或 owner/repo": "Repository URL or owner/repo",
    "分支（可选）": "Branch (optional)",
    "文件路径": "File path",
    "调研 GitHub 仓库": "Research a GitHub repository",
    "指定仓库": "Specific repository",
    "自主检索仓库": "Discover repositories",
    "开始调研": "Start research",
    "关闭": "Close",
    "保存": "Save",
    "添加": "Add",
    "重试": "Retry",
    "加载中...": "Loading...",
    "暂无对话记录": "No conversation history",
    "暂无收藏": "No saved reviews",
    "暂无会话": "No research sessions",
    "新对话": "New conversation",
    "发送": "Send",
    "上下文": "Context",
    "当前上下文": "Current context",
    "随时向我提问研究相关的问题": "Ask a question about your research at any time",
    "请先从左侧选择一篇论文。": "Select a paper from the left first.",
    "全局 Copilot": "Global Copilot",
    "跨项目知识问答": "Cross-project knowledge Q&A",
    "基于所有 Session 的论文、笔记、综述回答": "Answer from papers, notes, and reviews across all sessions",
    "我目前有哪些研究项目？": "What research projects do I have?",
    "有哪些论文被多个项目引用？": "Which papers are cited by multiple projects?",
    "帮我总结一下所有项目的共同主题": "Summarize the themes shared across all projects",
    "模型配置": "Model configuration",
    "高级设置": "Advanced settings",
    "保存配置": "Save configuration",
    "恢复默认": "Restore defaults",
    "检查连接中": "Testing connection",
    "测试连接": "Test connection",
    "清除配置": "Clear configuration",
    "个人中心": "Profile",
    "账号": "Account",
    "返回首页": "Back to home",
    "返回主页": "Back to home",
    "工作台": "Workspace",
    "研究控制台": "Research console",
    "使用帮助": "Help",
    "使用指南": "User guide",
    "完整操作流程": "Complete workflow",
    "常见问题": "Frequently asked questions",
    "数据来源": "Data sources",
    "标题": "Title",
    "类型": "Type",
    "可选": "Optional",
    "确定": "Confirm",
    "创建": "Create",
    "删除": "Delete",
    "全选": "Select all",
    "展开": "Expand",
    "查看与修订": "View and revise",
    "使用此内容": "Use this content",
    "默认策略": "Default strategy",
    "使用默认策略": "Use default strategy",
    "自定义研究策略": "Custom research strategy",
    "Agent 工具管理": "Agent tool management",
    "Skills 管理": "Skills management",
    "创建 Skill": "Create skill",
    "删除 Skill": "Delete skill",
    "内容 (Markdown)": "Content (Markdown)",
    "添加关键词": "Add keyword",
    "确认关键词": "Confirm keywords",
    "确认并开始搜索": "Confirm and start search",
    "添加一行": "Add row",
    "拖拽 PDF 文件到此处": "Drop a PDF here",
    "或点击选择文件": "or select a file",
    "arXiv ID 或论文链接": "arXiv ID or paper URL",
    "生成论文笔记": "Generate paper notes",
    "生成文献综述": "Generate literature review",
    "论文": "Papers",
    "篇论文": "papers",
    "篇综述": "reviews",
    "个项目": "projects"
  };

  var mojibake = {
    "鏅鸿兘瀛︽湳缁艰堪鍔╂墜": "Academic Research Assistant",
    "鐧诲綍": "Sign in",
    "娉ㄥ唽": "Sign up",
    "娆㈣繋鍥炴潵": "Welcome back",
    "閭": "Email",
    "瀵嗙爜": "Password",
    "璐﹀彿": "Account",
    "涓汉涓績": "Profile",
    "宸ヤ綔娴佺▼": "Workflow",
    "鏁版嵁瀹夊叏": "Data security",
    "鐮旂┒闂": "Research question",
    "鍊欓€夎鏂?": "Candidate papers",
    "鏍稿績缁撹": "Key findings",
    "缁煎悎鍒嗘瀽": "Synthesis",
    "缁艰堪瀹屾垚": "Review complete",
    "鍓嶅線 GitHub 鎺堟潈": "Authorize with GitHub",
    "浣跨敤 GitHub 缁х画": "Continue with GitHub",
    "鑱婂ぉ妯″瀷": "Chat model",
    "鍚戦噺妯″瀷": "Embedding model",
    "娴嬭瘯杩炴帴": "Test connection",
    "淇濆瓨閰嶇疆": "Save configuration",
    "娓呴櫎閰嶇疆": "Clear configuration",
    "鑷畾涔?OpenAI-compatible": "Custom OpenAI-compatible",
    "鏅鸿氨 AI": "Zhipu AI"
  };

  var patterns = [
    [/写作预设适合大多数个人研究主题，强调跨论文主题综合、分歧解释与可核验引用。/, " writing preset for most independent research topics, emphasizing cross-paper synthesis, explanation of disagreements, and verifiable citations."],
    [/写作预设适合已经明确检索范围与筛选标准的项目；不会虚构 PRISMA 流程或检索数量。/, " writing preset for projects with a defined search scope and screening criteria; it never fabricates a PRISMA process or search counts."],
    [/写作预设适合计算机、AI 与工程主题，强调任务定义、架构、数据集、指标、成本和复现条件。/, " writing preset for computing, AI, and engineering topics, emphasizing task definitions, architectures, datasets, metrics, cost, and reproducibility conditions."],
    [/写作预设适合主题宽、概念尚未稳定的领域，侧重概念边界、研究类型分布和空白地图。/, " writing preset for broad fields with unsettled concepts, focused on conceptual boundaries, research-type distributions, and gap mapping."],
    [/证据综合型叙述综述写作预设适合大多数个人研究主题，强调跨论文主题综合、分歧解释与可核验引用。/, "Evidence-synthesis narrative review preset for most independent research topics, emphasizing cross-paper synthesis, explanation of disagreements, and verifiable citations."],
    [/系统综述写作框架写作预设适合已经明确检索范围与筛选标准的项目；不会虚构 PRISMA 流程或检索数量。/, "Systematic-review writing preset for projects with a defined search scope and screening criteria; it never fabricates a PRISMA process or search counts."],
    [/技术方法对比综述写作预设适合计算机、AI 与工程主题，强调任务定义、架构、数据集、指标、成本和复现条件。/, "Technical comparison review preset for computing, AI, and engineering topics, emphasizing task definitions, architectures, datasets, metrics, cost, and reproducibility conditions."],
    [/范围综述与研究地图写作预设适合主题宽、概念尚未稳定的领域，侧重概念边界、研究类型分布和空白地图。/, "Scoping-review preset for broad fields with unsettled concepts, focused on conceptual boundaries, research-type distributions, and gap mapping."],
    [/^推荐 (\d+) 轮；系统不会超过你设置的上限。$/, "Recommended: $1 rounds. The system will not exceed your limit."],
    [/^推荐 (\d+) 轮；当前上限较低，可能在达到 (\d+) 篇前结束。$/, "Recommended: $1 rounds. The current limit may stop before $2 papers are reached."],
    [/^共 (\d+) 步/, "$1 steps"],
    [/^(\d+) 篇$/, "$1 papers"],
    [/^(\d+) 个$/, "$1 items"],
    [/^已启用: (\d+)$/, "Enabled: $1"],
    [/^已禁用: (\d+)$/, "Disabled: $1"],
    [/^正在检索论文，本轮目标 (\d+) 篇，最多 (\d+) 轮\.\.\.$/, "Searching for papers: target $1, maximum $2 rounds..."],
    [/^正在扩展检索，目标新增 (\d+) 篇，最多 (\d+) 轮，并自动排除已有论文\.\.\.$/, "Expanding the search: target $1 new papers, maximum $2 rounds, excluding existing papers..."],
    [/^检索完成：本轮实际新增 (\d+)\/(\d+) 篇论文。/, "Search complete: $1/$2 papers added this run."],
    [/^检索部分完成：本轮实际新增 (\d+)\/(\d+) 篇/, "Search partially complete: $1/$2 papers added this run"],
    [/^正在安全加载 PDF…$/, "Loading PDF securely..."],
    [/^正在重新寻找开放全文…$/, "Searching again for an open full text..."],
    [/^无法显示这份 PDF$/, "Unable to display this PDF"],
    [/^仍未找到开放全文$/, "No open full text found yet"]
  ];

  function translate(value) {
    var raw = String(value || "");
    var trimmed = raw.trim();
    if (!trimmed) return raw;
    var translated = exact[trimmed] || mojibake[trimmed];
    if (!translated) {
      for (var i = 0; i < patterns.length; i += 1) {
        if (patterns[i][0].test(trimmed)) {
          translated = trimmed.replace(patterns[i][0], patterns[i][1]);
          break;
        }
      }
    }
    if (!translated) return raw;
    return raw.replace(trimmed, translated);
  }

  function translateNode(node) {
    if (!node || node.parentElement && node.parentElement.closest("[data-locale-skip]")) return;
    if (node.nodeType === Node.TEXT_NODE) {
      var next = translate(node.nodeValue);
      if (next !== node.nodeValue) node.nodeValue = next;
      return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    ["title", "placeholder", "aria-label", "data-empty-label"].forEach(function (name) {
      if (node.hasAttribute(name)) {
        var current = node.getAttribute(name);
        var next = translate(current);
        if (next !== current) node.setAttribute(name, next);
      }
    });
    Array.from(node.childNodes).forEach(translateNode);
  }

  function addToggle() {
    if (document.querySelector("[data-language-toggle]")) return;
    if (!document.getElementById("localeToggleStyles")) {
      var style = document.createElement("style");
      style.id = "localeToggleStyles";
      style.textContent = ".locale-toggle{display:inline-flex;align-items:center;justify-content:center;min-width:44px;min-height:36px;padding:6px 10px;border:1px solid rgba(99,115,129,.28);border-radius:9px;background:transparent;color:inherit;font:600 12px/1 inherit;cursor:pointer;white-space:nowrap}.locale-toggle:hover{background:rgba(80,100,130,.09)}.locale-toggle:focus-visible{outline:2px solid #4f7ee8;outline-offset:2px}@media(max-width:480px){.locale-toggle{min-width:40px;padding:5px 8px}}";
      document.head.appendChild(style);
    }
    var target = document.querySelector(".topbar-right, .account-header-actions, .market-nav-links, .account-header");
    if (!target) return;
    var button = document.createElement("button");
    button.type = "button";
    button.className = "locale-toggle";
    button.dataset.languageToggle = "true";
    button.dataset.localeSkip = "true";
    button.textContent = language === "en" ? "中文" : "EN";
    button.title = language === "en" ? "Switch to Chinese" : "Switch to English";
    button.setAttribute("aria-label", button.title);
    button.addEventListener("click", function () {
      localStorage.setItem(STORAGE_KEY, language === "en" ? "zh-CN" : "en");
      window.location.reload();
    });
    target.insertBefore(button, target.firstChild);
  }

  function start() {
    document.documentElement.lang = language;
    addToggle();
    if (language !== "en") return;
    translateNode(document.body);
    document.title = translate(document.title);
    var observer = new MutationObserver(function (mutations) {
      mutations.forEach(function (mutation) {
        if (mutation.type === "characterData") translateNode(mutation.target);
        if (mutation.type === "attributes") translateNode(mutation.target);
        mutation.addedNodes.forEach(translateNode);
      });
    });
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ["title", "placeholder", "aria-label", "data-empty-label"]
    });
  }

  window.academicLocale = {
    get: function () { return language; },
    isEnglish: function () { return language === "en"; },
    t: function (zh, en) { return language === "en" ? en : zh; },
    translate: translate
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
