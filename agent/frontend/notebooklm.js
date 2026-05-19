const notebooklm = {
  state: {
    sessions: [],
    currentSessionId: null,
    currentSession: null,
    currentPaperId: null,
    currentViewMode: "summary",
    chatMessages: [],
    pollTimer: null,
    pendingSeedKeywords: "",
    lastReviewFeedback: "",
  },

  els: {},

  init() {
    this.bindCommonElements();
    this.loadThemePreference();

    const page = document.body.dataset.page || "home";
    if (page === "home") {
      this.initHome();
    } else if (page === "console") {
      this.initConsole();
    }
  },

  bindCommonElements() {
    this.els.topicModal = document.getElementById("topicModal");
    this.els.topicInput = document.getElementById("topicInput");
    this.els.keywordInput = document.getElementById("keywordInput");
    this.els.keywordPlanGenerate = document.getElementById("keywordPlanGenerate");
    this.els.homeKeywordList = document.getElementById("homeKeywordList");
    this.els.topicSubmit = document.getElementById("topicSubmit");
    this.els.topicCancel = document.getElementById("topicCancel");
    this.els.keywordAddHome = document.getElementById("keywordAddHome");
    this.els.homeRail = document.getElementById("homeRail");
    this.els.historyCount = document.getElementById("historyCount");

    this.els.consoleTopic = document.getElementById("consoleTopic");
    this.els.consoleState = document.getElementById("consoleState");
    this.els.consoleStateDot = document.getElementById("consoleStateDot");
    this.els.searchBtn = document.getElementById("searchPaperBtn");
    this.els.addPaperBtn = document.getElementById("addPaperBtn");
    this.els.notesBtn = document.getElementById("generateNotesBtn");
    this.els.reviewBtn = document.getElementById("generateReviewBtn");
    this.els.paperList = document.getElementById("paperList");
    this.els.notesBlock = document.getElementById("notesBlock");
    this.els.reviewBlock = document.getElementById("reviewBlock");
    this.els.detailHeader = document.getElementById("detailHeader");
    this.els.detailTitle = document.getElementById("detailTitle");
    this.els.detailMeta = document.getElementById("detailMeta");
    this.els.detailContent = document.getElementById("detailContent");
    this.els.viewSummary = document.getElementById("viewSummary");
    this.els.viewReport = document.getElementById("viewReport");
    this.els.viewReview = document.getElementById("viewReview");
    this.els.chatList = document.getElementById("chatList");
    this.els.chatInput = document.getElementById("chatInput");
    this.els.chatSend = document.getElementById("chatSend");
    this.els.chatApply = document.getElementById("chatApply");
    this.els.chatContext = document.getElementById("chatContext");
    this.els.keywordModal = document.getElementById("keywordModal");
    this.els.keywordTopic = document.getElementById("keywordTopic");
    this.els.keywordList = document.getElementById("keywordList");
    this.els.keywordAdd = document.getElementById("keywordAdd");
    this.els.keywordConfirm = document.getElementById("keywordConfirm");
    this.els.keywordCancel = document.getElementById("keywordCancel");
  },

  async initHome() {
    const openCreateTopic = document.getElementById("openCreateTopic");
    if (openCreateTopic) {
      openCreateTopic.addEventListener("click", () => this.openTopicModal());
    }
    if (this.els.topicSubmit) {
      this.els.topicSubmit.addEventListener("click", () => this.createTopicFromModal());
    }
    if (this.els.topicCancel) {
      this.els.topicCancel.addEventListener("click", () => this.closeTopicModal());
    }
    if (this.els.keywordPlanGenerate) {
      this.els.keywordPlanGenerate.addEventListener("click", () => this.generateHomeKeywordPlan());
    }
    if (this.els.keywordAddHome) {
      this.els.keywordAddHome.addEventListener("click", () => this.addHomeKeywordRow({}, (this.els.homeKeywordList?.querySelectorAll(".keyword-plan-row").length || 0) + 1));
    }
    if (this.els.keywordInput) {
      this.els.keywordInput.addEventListener("input", () => this.syncKeywordPlanHint());
    }
    if (this.els.topicInput) {
      this.els.topicInput.addEventListener("input", () => this.syncKeywordPlanHint());
    }

    await this.loadHomeSessions();
  },

  async loadHomeSessions() {
    if (!this.els.homeRail) return;

    this.els.homeRail.innerHTML = '<div class="loading-state">正在加载历史综述...</div>';
    try {
      const response = await fetch("/api/sessions/list");
      const sessions = await response.json();
      this.state.sessions = Array.isArray(sessions) ? sessions : [];
      // Enrich sessions with quick metadata (paper/note sizes) by calling session summary endpoints in parallel (best-effort)
      const enriched = await Promise.all(this.state.sessions.slice(0,10).map(async (s) => {
        try {
          const res = await fetch(`/api/sessions/${encodeURIComponent(s.session_id)}`);
          if (!res.ok) return s;
          const detail = await res.json();
          s.paper_count = Array.isArray(detail.papers) ? detail.papers.length : (detail.papers || []).length || 0;
          s.note_size = detail.notes ? detail.notes.length : 0;
        } catch (e) {
          // ignore
        }
        return s;
      }));
      this.state.sessions = enriched.concat(this.state.sessions.slice(10));
      this.renderHomeSessions();
    } catch (error) {
      this.els.homeRail.innerHTML = `<div class="empty-state">加载失败：${this.escapeHtml(error.message)}</div>`;
    }
  },

  renderHomeSessions() {
    const sessions = [...(this.state.sessions || [])].sort((left, right) => {
      const leftTime = new Date(left.updated_at || left.created_at || 0).getTime();
      const rightTime = new Date(right.updated_at || right.created_at || 0).getTime();
      return rightTime - leftTime;
    });
    if (this.els.historyCount) {
      this.els.historyCount.textContent = `${sessions.length} 个综述`;
    }

    if (!this.els.homeRail) return;
    this.els.homeRail.innerHTML = "";

    // Always show a create card first (mirrors NotebookLM layout)
    const createCard = document.createElement("article");
    createCard.className = "topic-card create";
    createCard.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:center;flex-direction:column;gap:8px;">
        <div style="font-size:28px;color:var(--accent);"><i class="fa-solid fa-plus"></i></div>
        <div style="font-size:13px;color:var(--subtle);">新建综述</div>
      </div>
    `;
    createCard.setAttribute('role', 'button');
    createCard.setAttribute('tabindex', '0');
    createCard.style.cursor = 'pointer';
    createCard.addEventListener('click', () => this.openTopicModal());
    createCard.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); this.openTopicModal(); } });
    this.els.homeRail.appendChild(createCard);

    // Render up to 5 recent sessions as clickable cards
    const visible = sessions.slice(0, 5);
    visible.forEach((session) => {
      const card = document.createElement("article");
      card.className = "topic-card";

      const title = this.escapeHtml(session.topic || "未命名综述");
      const time = this.formatDate(session.updated_at || session.created_at);

      const paperCount = session.paper_count || 0;
      const noteFlag = session.note_size && session.note_size > 0 ? '有笔记' : '无笔记';

      card.innerHTML = `
        <div>
          <h3 title="${title}">${title}</h3>
          <small>更新时间 ${time}</small>
        </div>
        <div class="meta-row">
          <span class="badge">${paperCount} 个来源</span>
          <span class="badge">${noteFlag}</span>
        </div>
      `;

      card.addEventListener('click', () => {
        window.location.href = `/app/console?sessionId=${encodeURIComponent(session.session_id)}`;
      });

      const deleteBtn = document.createElement("button");
      deleteBtn.type = "button";
      deleteBtn.className = "tiny-btn card-delete";
      deleteBtn.title = "删除综述";
      deleteBtn.innerHTML = '<i class="fa-solid fa-trash"></i>';
      deleteBtn.addEventListener("click", async (event) => {
        event.stopPropagation();
        event.preventDefault();
        await this.deleteHomeSession(session.session_id);
      });

      const metaRow = card.querySelector(".meta-row");
      if (metaRow) {
        metaRow.appendChild(deleteBtn);
      }

      this.els.homeRail.appendChild(card);
    });

    // If there are more sessions, add a '更多' card
    if (sessions.length > 5) {
      const moreCard = document.createElement('article');
      moreCard.className = 'topic-card';
      moreCard.innerHTML = `
        <div>
          <h3>更多历史</h3>
          <small>查看全部历史会话</small>
        </div>
        <div class="meta-row">
          <button class="btn-text" id="viewAllSessions">查看全部</button>
        </div>
      `;
      this.els.homeRail.appendChild(moreCard);
      const viewAllBtn = document.getElementById('viewAllSessions');
      if (viewAllBtn) viewAllBtn.addEventListener('click', () => window.location.href = '/app/history');
    }
  },

  openTopicModal() {
    if (!this.els.topicModal) return;
    this.els.topicModal.classList.add("active");
    if (this.els.topicInput) {
      this.els.topicInput.value = localStorage.getItem("notebooklm:lastTopic") || "";
      this.els.topicInput.focus();
    }
    if (this.els.keywordInput) {
      this.els.keywordInput.value = localStorage.getItem("notebooklm:lastKeywords") || "";
    }
    this.renderHomeKeywordPlan([]);
    this.syncKeywordPlanHint();
  },

  closeTopicModal() {
    if (this.els.topicModal) {
      this.els.topicModal.classList.remove("active");
    }
  },

  async createTopicFromModal() {
    const topic = (this.els.topicInput?.value || "").trim();
    const keywords = this.collectHomeKeywords();
    if (!topic) {
      alert("请输入主题");
      return;
    }
    if (!keywords.length) {
      alert("请先生成并确认 AI 关键词规划");
      return;
    }

    try {
      localStorage.setItem("notebooklm:lastTopic", topic);
      localStorage.setItem("notebooklm:lastKeywords", (this.els.keywordInput?.value || "").trim());

      const createBtn = this.els.topicSubmit;
      if (createBtn) {
        createBtn.disabled = true;
        createBtn.textContent = "创建中...";
      }

      const response = await fetch("/api/sessions/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic, keywords }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "创建会话失败");
      }

      if (keywords.length) {
        const seedText = keywords
          .map((item) => item.original || item.english || item.synonyms || "")
          .filter(Boolean)
          .join(", ");
        sessionStorage.setItem(`notebooklm:seedKeywords:${data.session_id}`, seedText);
      }

      this.closeTopicModal();

      window.location.href = `/app/console?sessionId=${encodeURIComponent(data.session_id)}`;
    } catch (error) {
      alert(`创建失败：${error.message}`);
    } finally {
      const createBtn = this.els.topicSubmit;
      if (createBtn) {
        createBtn.disabled = false;
        createBtn.innerHTML = '<i class="fa-solid fa-arrow-right"></i> 进入控制台';
      }
    }
  },

  keywordPlanDictionary: {
    "多智能体": { english: "Multi-Agent", synonyms: "多智能体系统, 多智能体技术" },
    "协作": { english: "Collaboration", synonyms: "协同, 协作机制" },
    "记忆": { english: "Memory", synonyms: "记忆辅助, 记忆支持" },
    "机制": { english: "Mechanism", synonyms: "机制设计, 机制分析" },
    "检索": { english: "Retrieval", synonyms: "信息检索, 检索增强" },
    "规划": { english: "Planning", synonyms: "任务规划, 显式规划" },
    "综述": { english: "Review", synonyms: "文献综述, 研究综述" },
    "学术": { english: "Academic", synonyms: "学术研究, 学术论文" },
    "大模型": { english: "LLM", synonyms: "大语言模型, 语言模型" },
    "智能": { english: "Intelligent", synonyms: "智能系统, 智能化" },
    "知识": { english: "Knowledge", synonyms: "知识图谱, 知识增强" },
    "RAG": { english: "Retrieval-Augmented Generation", synonyms: "检索增强生成" },
  },

  normalizeSeedKeywords(seedText) {
    return (seedText || "")
      .replace(/[，；;\n]/g, ",")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  },

  inferKeywordPlan(topic, seedText) {
    const seeds = this.normalizeSeedKeywords(seedText);
    const bag = [];
    const text = `${topic || ""} ${seeds.join(" ")}`;
    Object.entries(this.keywordPlanDictionary).forEach(([token, mapped]) => {
      if (text.includes(token)) {
        bag.push({ original: token, english: mapped.english, synonyms: mapped.synonyms });
      }
    });

    seeds.forEach((seed) => {
      const matched = Object.keys(this.keywordPlanDictionary).find((token) => seed.includes(token));
      if (matched) {
        bag.push({ original: matched, english: this.keywordPlanDictionary[matched].english, synonyms: this.keywordPlanDictionary[matched].synonyms });
      } else {
        bag.push({ original: seed, english: "", synonyms: "" });
      }
    });

    if (topic && !bag.length) {
      const fragments = topic.split(/\s+/).filter(Boolean).slice(0, 4);
      fragments.forEach((fragment) => bag.push({ original: fragment, english: "", synonyms: "" }));
    }

    const seen = new Set();
    return bag.filter((item) => {
      const key = `${item.original}__${item.english}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    }).slice(0, 6);
  },

  renderHomeKeywordPlan(keywords) {
    if (!this.els.homeKeywordList) return;
    this.els.homeKeywordList.innerHTML = "";
    if (!keywords.length) {
      const empty = document.createElement("div");
      empty.className = "keyword-plan-empty";
      empty.textContent = "输入主题后点击“生成规划”，系统会先给出可编辑的关键词建议。";
      this.els.homeKeywordList.appendChild(empty);
      return;
    }
    keywords.forEach((keyword, index) => this.addHomeKeywordRow(keyword, index + 1));
  },

  addHomeKeywordRow(keyword = {}, index = 1) {
    if (!this.els.homeKeywordList) return;
    const row = document.createElement("div");
    row.className = "keyword-plan-row";
    row.innerHTML = `
      <div class="keyword-plan-index">关键词 ${index}</div>
      <input type="text" class="kw-original" placeholder="中文原词" value="${this.escapeHtml(keyword.original || "")}">
      <input type="text" class="kw-english" placeholder="英文学术词" value="${this.escapeHtml(keyword.english || "")}">
      <input type="text" class="kw-synonyms" placeholder="同义词（逗号分隔）" value="${this.escapeHtml(keyword.synonyms || "")}">
      <button class="tiny-btn kw-remove" type="button" title="删除"><i class="fa-solid fa-trash"></i></button>
    `;
    row.querySelector(".kw-remove")?.addEventListener("click", () => row.remove());
    this.els.homeKeywordList.appendChild(row);
  },

  async deleteHomeSession(sessionId) {
    if (!sessionId) return;
    if (!confirm("确定删除这个综述吗？删除后无法恢复。")) return;

    try {
      const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "删除失败");
      }

      this.state.sessions = (this.state.sessions || []).filter((session) => session.session_id !== sessionId);
      this.renderHomeSessions();
    } catch (error) {
      alert(`删除失败：${error.message}`);
    }
  },

  collectHomeKeywords() {
    const rows = Array.from(this.els.homeKeywordList?.querySelectorAll(".keyword-plan-row") || []);
    return rows.map((row) => ({
      original: row.querySelector(".kw-original")?.value?.trim() || "",
      english: row.querySelector(".kw-english")?.value?.trim() || "",
      synonyms: row.querySelector(".kw-synonyms")?.value?.trim() || "",
    })).filter((item) => item.original || item.english || item.synonyms);
  },

  generateHomeKeywordPlan() {
    const topic = (this.els.topicInput?.value || "").trim();
    if (!topic) {
      alert("请先输入主题");
      return;
    }
    const plan = this.inferKeywordPlan(topic, this.els.keywordInput?.value || "");
    this.renderHomeKeywordPlan(plan);
  },

  syncKeywordPlanHint() {
    if (!this.els.homeKeywordList) return;
    const hasRows = this.els.homeKeywordList.querySelectorAll(".keyword-plan-row").length > 0;
    if (hasRows) return;
    const topic = (this.els.topicInput?.value || "").trim();
    const seeds = this.normalizeSeedKeywords(this.els.keywordInput?.value || "");
    if (topic && seeds.length) {
      this.renderHomeKeywordPlan(this.inferKeywordPlan(topic, this.els.keywordInput?.value || ""));
    }
  },

  async initConsole() {
    this.bindConsoleActions();
    const params = new URLSearchParams(window.location.search);
    const sessionId = params.get("sessionId");
    if (!sessionId) {
      this.setConsoleEmptyState();
      return;
    }
    await this.loadSession(sessionId);
  },

  bindConsoleActions() {
    this.els.searchBtn?.addEventListener("click", () => this.primarySourceAction());
    this.els.addPaperBtn?.addEventListener("click", () => this.addPaperFromPrompt());
    this.els.notesBtn?.addEventListener("click", () => this.runSearchPhase());
    this.els.reviewBtn?.addEventListener("click", () => this.runWritePhase());
    this.els.viewSummary?.addEventListener("click", () => this.switchViewMode("summary"));
    this.els.viewReport?.addEventListener("click", () => this.switchViewMode("report"));
    this.els.viewReview?.addEventListener("click", () => this.switchViewMode("review"));
    this.els.chatSend?.addEventListener("click", () => this.sendChatMessage());
    this.els.chatApply?.addEventListener("click", () => this.applyReviewFeedback());
    this.els.chatInput?.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        this.sendChatMessage();
      }
    });

    this.els.keywordConfirm?.addEventListener("click", () => this.confirmKeywords());
    this.els.keywordCancel?.addEventListener("click", () => this.closeKeywordModal());
    this.els.keywordAdd?.addEventListener("click", () => this.addKeywordRow());
  },

  async loadSession(sessionId) {
    try {
      const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}`);
      const session = await response.json();
      if (!response.ok) {
        throw new Error(session.detail || "加载会话失败");
      }

      this.state.currentSessionId = sessionId;
      this.state.currentSession = session;
      this.state.currentPaperId = session.papers?.[0]?.paper_id || null;

      this.renderConsoleSession();

      if (session.state === "planning" && (!session.keywords || session.keywords.length === 0)) {
        await this.runPlanPhase();
        return;
      }

      if (session.state === "planning" && session.keywords && session.keywords.length > 0) {
        this.openKeywordModal(session.topic, session.keywords);
      }
    } catch (error) {
      this.setConsoleStatus("error", `加载失败：${error.message}`);
    }
  },

  setConsoleEmptyState() {
    if (this.els.detailContent) {
      this.els.detailContent.innerHTML = '<div class="empty-state">请先从首页新建综述并进入会话。</div>';
    }
    if (this.els.paperList) {
      this.els.paperList.innerHTML = '<div class="empty-state">暂无会话</div>';
    }
  },

  renderConsoleSession() {
    const session = this.state.currentSession;
    if (!session) return;

    if (this.els.consoleTopic) {
      this.els.consoleTopic.textContent = session.topic || "未命名主题";
    }

    this.setConsoleStatus(session.state, session.state_label || session.state || "就绪");
    this.renderPaperList();
    this.renderNotesBlock();
    this.renderReviewBlock();
    this.renderDetailPanel();
    this.renderChatContext();
    this.updateActionButtons();
    this.renderViewButtons();
  },

  setConsoleStatus(state, label) {
    if (this.els.consoleState) {
      this.els.consoleState.textContent = label;
    }
    if (!this.els.consoleStateDot) return;

    const map = {
      planning: "warn",
      plan_confirmed: "live",
      searching: "live",
      search_complete: "ok",
      reviewing_notes: "warn",
      writing: "live",
      reviewing_draft: "warn",
      complete: "ok",
      error: "err",
    };

    this.els.consoleStateDot.className = `status-dot ${map[state] || ""}`.trim();
  },

  renderPaperList() {
    if (!this.els.paperList) return;
    const papers = this.state.currentSession?.papers || [];

    if (!papers.length) {
      this.els.paperList.innerHTML = '<div class="empty-state">点击「AI 检索论文」或「添加论文」开始构建来源库。</div>';
      return;
    }

    this.els.paperList.innerHTML = "";
    papers.forEach((paper) => {
      const row = document.createElement("article");
      row.className = `paper-row ${paper.paper_id === this.state.currentPaperId ? "active" : ""}`;
      row.addEventListener("click", () => {
        this.state.currentPaperId = paper.paper_id;
        this.renderPaperList();
        this.renderDetailPanel();
        this.renderChatContext();
      });

      const title = paper.title || paper.paper_id || "未命名论文";
      const authorLine = paper.authors || paper.source_type || paper.source || "来源未标记";

      row.innerHTML = `
        <div class="paper-main">
          <h4>${this.escapeHtml(title)}</h4>
          <p>${this.escapeHtml(authorLine)}</p>
          <div class="paper-meta">
            <span class="chip"><i class="fa-regular fa-circle-dot"></i> ${this.escapeHtml(paper.source || "agent_search")}</span>
            <span class="chip"><i class="fa-regular fa-bookmark"></i> ${this.escapeHtml(paper.status || "pending")}</span>
            ${paper.added_at ? `<span class="chip"><i class="fa-regular fa-clock"></i> ${this.formatDate(paper.added_at)}</span>` : ""}
          </div>
        </div>
        <div class="paper-actions">
          <button class="mini-btn remove" title="移除论文" data-action="remove"><i class="fa-solid fa-xmark"></i></button>
          <button class="mini-btn ${paper.status === "accepted" ? "accepted" : ""}" title="选中论文" data-action="accept"><i class="fa-solid fa-check"></i></button>
        </div>
      `;

      row.querySelector('[data-action="remove"]').addEventListener("click", async (event) => {
        event.stopPropagation();
        await this.removePaper(paper.paper_id);
      });

      row.querySelector('[data-action="accept"]').addEventListener("click", async (event) => {
        event.stopPropagation();
        await this.setPaperStatus(paper.paper_id, paper.status === "accepted" ? "pending" : "accepted");
      });

      this.els.paperList.appendChild(row);
    });
  },

  renderNotesBlock() {
    if (!this.els.notesBlock) return;
    const notes = this.state.currentSession?.notes || "";
    const hasNotes = Boolean(notes.trim());
    this.els.notesBlock.innerHTML = `
      <div class="panel-block-head">
        <strong>生成笔记</strong>
        <span class="chip"><i class="fa-regular fa-file-lines"></i> ${hasNotes ? "已生成" : "未生成"}</span>
      </div>
      <div class="markdown">${hasNotes ? marked.parse(notes) : '<div class="empty-state">还没有研究笔记。点击下方按钮启动 AI 检索，系统会自动汇总成笔记。</div>'}</div>
    `;
  },

  renderReviewBlock() {
    if (!this.els.reviewBlock) return;
    const draft = this.state.currentSession?.draft || "";
    const hasDraft = Boolean(draft.trim());
    this.els.reviewBlock.innerHTML = `
      <div class="panel-block-head">
        <strong>生成综述</strong>
        <span class="chip"><i class="fa-regular fa-pen-to-square"></i> ${hasDraft ? `v${this.state.currentSession?.draft_version || 1}` : "未生成"}</span>
      </div>
      <div class="markdown">${hasDraft ? marked.parse(draft) : '<div class="empty-state">还没有综述草稿。完成笔记后，点击右上按钮生成综述。</div>'}</div>
    `;
  },

  renderDetailPanel() {
    if (!this.state.currentSession || !this.els.detailContent || !this.els.detailTitle) return;

    const session = this.state.currentSession;
    const paper = this.getCurrentPaper();
    const paperCount = session.papers?.length || 0;
    const selectedLabel = paper ? paper.title || paper.paper_id : "未选择论文";

    this.els.detailTitle.textContent = selectedLabel;
    if (this.els.detailMeta) {
      this.els.detailMeta.textContent = `${paperCount} 个来源 · ${this.viewModeLabel(this.state.currentViewMode)} · ${session.state_label || session.state}`;
    }

    let html = "";
    if (this.state.currentViewMode === "summary") {
      html = this.renderPaperSummary(paper, session);
    } else if (this.state.currentViewMode === "report") {
      html = this.renderPaperReport(paper, session);
    } else {
      html = this.renderReviewView(session);
    }

    this.els.detailContent.innerHTML = html;
  },

  renderPaperSummary(paper, session) {
    if (!paper) {
      return '<div class="empty-state">请先在左侧选择一篇论文。</div>';
    }

    const extracted = this.extractPaperSnippet(paper, session?.notes || "", 420);
    return `
      <div class="detail-hero">
        <span class="topic-badge"><i class="fa-regular fa-note-sticky"></i> 摘要</span>
        <h3>${this.escapeHtml(paper.title || paper.paper_id || "未命名论文")}</h3>
        <div class="lead">${this.escapeHtml(paper.authors || paper.source || "该论文已加入当前综述主题")}</div>
      </div>
      <div class="detail-blocks" style="margin-top:16px;">
        <div class="panel-block">
          <div class="panel-block-head"><strong>论文简介</strong><span class="chip">只读</span></div>
          <div class="plain-text">${this.escapeHtml(paper.abstract || paper.summary || paper.description || extracted || "当前没有可用摘要，建议继续检索或添加 PDF 以补全信息。")}</div>
        </div>
        <div class="panel-block">
          <div class="panel-block-head"><strong>来源信息</strong><span class="chip">${this.escapeHtml(paper.status || "pending")}</span></div>
          <div class="plain-text">来源：${this.escapeHtml(paper.source || "agent_search")} · 来源类型：${this.escapeHtml(paper.source_type || "n/a")} · 添加时间：${this.escapeHtml(this.formatDate(paper.added_at))}</div>
        </div>
      </div>
    `;
  },

  renderPaperReport(paper, session) {
    const notes = session?.notes || "";
    const reportText = this.extractPaperSnippet(paper, notes, 900) || notes || "暂无报告内容";
    return `
      <div class="detail-hero">
        <span class="topic-badge"><i class="fa-solid fa-chart-line"></i> 报告</span>
        <h3>${this.escapeHtml(paper?.title || paper?.paper_id || session.topic || "综合报告")}</h3>
        <div class="lead">报告视图默认只读，展示当前论文与会话笔记中的关联内容。</div>
      </div>
      <div class="panel-block" style="margin-top:16px;">
        <div class="panel-block-head"><strong>报告内容</strong><span class="chip">来自笔记 / 研究轨迹</span></div>
        <div class="markdown">${marked.parse(reportText)}</div>
      </div>
    `;
  },

  renderReviewView(session) {
    const draft = session?.draft || session?.notes || "";
    const acceptedCount = (session?.papers || []).filter((paper) => paper.status === "accepted").length;
    return `
      <div class="detail-hero">
        <span class="topic-badge"><i class="fa-solid fa-layer-group"></i> 综述</span>
        <h3>${this.escapeHtml(session.topic || "综合综述")}</h3>
        <div class="lead">该视图会结合已选论文和综述草稿给出回答，并允许你通过底部对话区提交修改意见。</div>
      </div>
      <div class="detail-blocks" style="margin-top:16px;">
        <div class="panel-block">
          <div class="panel-block-head"><strong>综述草稿</strong><span class="chip">${acceptedCount} 篇已选论文</span></div>
          <div class="markdown">${draft ? marked.parse(draft) : '<div class="empty-state">还没有综述草稿。</div>'}</div>
        </div>
      </div>
    `;
  },

  switchViewMode(mode) {
    this.state.currentViewMode = mode;
    this.renderDetailPanel();
    this.renderViewButtons();
    this.renderChatContext();
  },

  renderViewButtons() {
    const map = {
      summary: this.els.viewSummary,
      report: this.els.viewReport,
      review: this.els.viewReview,
    };
    Object.entries(map).forEach(([mode, el]) => {
      if (!el) return;
      el.classList.toggle("active", this.state.currentViewMode === mode);
    });
  },

  renderChatContext() {
    if (!this.els.chatContext) return;
    const paper = this.getCurrentPaper();
    const label = this.state.currentViewMode === "review"
      ? `综述修改 · ${this.state.currentSession?.papers?.filter((p) => p.status === "accepted").length || 0} 篇已选`
      : paper
        ? `${paper.title || paper.paper_id} · ${this.viewModeLabel(this.state.currentViewMode)}`
        : `${this.state.currentSession?.topic || "当前主题"} · ${this.viewModeLabel(this.state.currentViewMode)}`;

    this.els.chatContext.innerHTML = `<span class="chip"><i class="fa-solid fa-sparkles"></i> ${this.escapeHtml(label)}</span>`;
    if (this.els.chatApply) {
      this.els.chatApply.style.display = this.state.currentViewMode === "review" ? "inline-flex" : "none";
    }
  },

  updateActionButtons() {
    const session = this.state.currentSession;
    if (!session) return;

    const hasNotes = Boolean((session.notes || "").trim());
    const hasDraft = Boolean((session.draft || "").trim());
    const hasPapers = Boolean((session.papers || []).length);

    if (this.els.searchBtn) {
      if (!session.keywords || !session.keywords.length) {
        this.els.searchBtn.classList.add("active");
        this.els.searchBtn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> 生成关键词';
      } else if (session.state === "plan_confirmed" || session.state === "searching") {
        this.els.searchBtn.classList.add("active");
        this.els.searchBtn.innerHTML = '<i class="fa-solid fa-magnifying-glass"></i> AI检索论文';
      } else {
        this.els.searchBtn.classList.toggle("active", hasPapers && !hasNotes);
        this.els.searchBtn.innerHTML = '<i class="fa-solid fa-magnifying-glass"></i> AI检索论文';
      }
    }

    if (this.els.notesBtn) {
      this.els.notesBtn.classList.toggle("active", hasPapers && !hasNotes);
      this.els.notesBtn.innerHTML = hasNotes ? '<i class="fa-solid fa-rotate"></i> 重写笔记' : '<i class="fa-solid fa-file-lines"></i> 生成笔记';
    }

    if (this.els.reviewBtn) {
      this.els.reviewBtn.classList.toggle("active", hasNotes && !hasDraft);
      this.els.reviewBtn.innerHTML = hasDraft ? '<i class="fa-solid fa-rotate"></i> 重写综述' : '<i class="fa-solid fa-pen-nib"></i> 生成综述';
    }
  },

  viewModeLabel(mode) {
    return {
      summary: "摘要",
      report: "报告",
      review: "综述",
    }[mode] || "摘要";
  },

  getCurrentPaper() {
    const papers = this.state.currentSession?.papers || [];
    return papers.find((paper) => paper.paper_id === this.state.currentPaperId) || papers[0] || null;
  },

  extractPaperSnippet(paper, text, maxLength = 360) {
    if (!text) return "";
    const haystack = text || "";
    const candidates = [paper?.title, paper?.paper_id].filter(Boolean);
    for (const keyword of candidates) {
      const index = haystack.toLowerCase().indexOf(String(keyword).toLowerCase());
      if (index >= 0) {
        const start = Math.max(0, index - 140);
        return haystack.slice(start, Math.min(haystack.length, index + maxLength));
      }
    }
    return haystack.slice(0, maxLength);
  },

  async primarySourceAction() {
    const session = this.state.currentSession;
    if (!session) return;

    if (!session.keywords || !session.keywords.length || session.state === "planning") {
      await this.runPlanPhase();
      return;
    }
    await this.runSearchPhase();
  },

  async runPlanPhase() {
    const session = this.state.currentSession;
    if (!session || !this.state.currentSessionId) return;

    try {
      this.setConsoleStatus("planning", "正在生成关键词规划...");
      const response = await fetch(`/api/sessions/${encodeURIComponent(this.state.currentSessionId)}/run/plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic: session.topic, start_phase: "plan" }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "规划失败");
      }

      const seed = sessionStorage.getItem(`notebooklm:seedKeywords:${this.state.currentSessionId}`) || "";
      sessionStorage.removeItem(`notebooklm:seedKeywords:${this.state.currentSessionId}`);
      const keywords = Array.isArray(data.keywords) ? data.keywords.slice() : [];
      if (seed) {
        const lines = seed.split(/[，,\n;]/).map((item) => item.trim()).filter(Boolean);
        lines.forEach((line) => keywords.push({ original: line, english: "", synonyms: "" }));
      }

      this.openKeywordModal(session.topic, keywords);
      await this.reloadCurrentSession();
    } catch (error) {
      this.setConsoleStatus("error", `规划失败：${error.message}`);
    }
  },

  openKeywordModal(topic, keywords = []) {
    if (!this.els.keywordModal) return;
    if (this.els.keywordTopic) {
      if ("value" in this.els.keywordTopic) {
        this.els.keywordTopic.value = topic || "主题";
      } else {
        this.els.keywordTopic.textContent = topic || "主题";
      }
    }
    this.els.keywordList.innerHTML = "";
    if (keywords.length === 0) {
      this.addKeywordRow();
    } else {
      keywords.forEach((keyword) => this.addKeywordRow(keyword));
    }
    this.els.keywordModal.classList.add("active");
  },

  closeKeywordModal() {
    this.els.keywordModal?.classList.remove("active");
  },

  addKeywordRow(keyword = {}) {
    if (!this.els.keywordList) return;
    const row = document.createElement("div");
    row.className = "keyword-plan-row";
    row.innerHTML = `
      <div class="keyword-plan-index">关键词 ${this.els.keywordList.children.length + 1}</div>
      <input type="text" class="kw-original" placeholder="中文原词" value="${this.escapeHtml(keyword.original || "")}">
      <input type="text" class="kw-english" placeholder="英文学术词" value="${this.escapeHtml(keyword.english || "")}">
      <input type="text" class="kw-synonyms" placeholder="同义词（逗号分隔）" value="${this.escapeHtml(keyword.synonyms || "")}">
      <button class="tiny-btn kw-remove" type="button" title="删除"><i class="fa-solid fa-trash"></i></button>
    `;
    row.querySelector(".kw-remove")?.addEventListener("click", () => row.remove());
    this.els.keywordList.appendChild(row);
  },

  collectKeywords() {
    const rows = Array.from(this.els.keywordList?.children || []);
    return rows.map((row) => ({
      original: row.querySelector(".kw-original")?.value?.trim() || "",
      english: row.querySelector(".kw-english")?.value?.trim() || "",
      synonyms: row.querySelector(".kw-synonyms")?.value?.trim() || "",
    })).filter((item) => item.original || item.english || item.synonyms);
  },

  async confirmKeywords() {
    const sessionId = this.state.currentSessionId;
    if (!sessionId) return;
    const keywords = this.collectKeywords();
    if (!keywords.length) {
      alert("请至少保留一个关键词");
      return;
    }

    try {
      const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/keywords`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ keywords }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "关键词保存失败");
      }

      await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/state`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ state: "plan_confirmed" }),
      }).catch(() => {});

      this.closeKeywordModal();
      await this.reloadCurrentSession();
      this.setConsoleStatus("plan_confirmed", "关键词已确认，点击 AI检索论文 开始搜索");
    } catch (error) {
      alert(`保存失败：${error.message}`);
    }
  },

  async runSearchPhase() {
    const session = this.state.currentSession;
    if (!session || !this.state.currentSessionId) return;

    if (!session.keywords || !session.keywords.length) {
      this.openKeywordModal(session.topic, session.keywords || []);
      return;
    }

    try {
      this.setConsoleStatus("searching", "正在检索论文并同步笔记...");
      const response = await fetch(`/api/sessions/${encodeURIComponent(this.state.currentSessionId)}/run/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic: session.topic,
          start_phase: "search",
          keywords: session.keywords || [],
          max_loops: 20,
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "搜索失败");
      }

      if (this.state.pollTimer) {
        clearInterval(this.state.pollTimer);
      }

      this.state.pollTimer = setInterval(async () => {
        try {
          const pollResponse = await fetch(`/api/sessions/${encodeURIComponent(this.state.currentSessionId)}`);
          const polled = await pollResponse.json();
          if (!pollResponse.ok) {
            throw new Error(polled.detail || "状态查询失败");
          }

          this.state.currentSession = polled;
          this.renderConsoleSession();

          if (polled.state === "search_complete") {
            clearInterval(this.state.pollTimer);
            this.state.pollTimer = null;
            this.switchViewMode("summary");
            this.setConsoleStatus("search_complete", "论文检索完成，可以生成综述");
          }
        } catch (error) {
          clearInterval(this.state.pollTimer);
          this.state.pollTimer = null;
          this.setConsoleStatus("error", `搜索失败：${error.message}`);
        }
      }, 2200);

      await this.reloadCurrentSession();
    } catch (error) {
      this.setConsoleStatus("error", `搜索失败：${error.message}`);
    }
  },

  async runWritePhase() {
    const session = this.state.currentSession;
    if (!session || !this.state.currentSessionId) return;

    try {
      this.setConsoleStatus("writing", "正在生成综述草稿...");
      const response = await fetch(`/api/sessions/${encodeURIComponent(this.state.currentSessionId)}/run/write`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic: session.topic, start_phase: "write" }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "写作失败");
      }

      await this.reloadCurrentSession();
      this.switchViewMode("review");
      this.setConsoleStatus("reviewing_draft", "综述已生成，可以继续提问或提交修改建议");
    } catch (error) {
      this.setConsoleStatus("error", `写作失败：${error.message}`);
    }
  },

  async reloadCurrentSession() {
    if (!this.state.currentSessionId) return;
    const response = await fetch(`/api/sessions/${encodeURIComponent(this.state.currentSessionId)}`);
    const session = await response.json();
    if (!response.ok) {
      throw new Error(session.detail || "刷新失败");
    }
    this.state.currentSession = session;
    if (session.papers?.length && !this.state.currentPaperId) {
      this.state.currentPaperId = session.papers[0].paper_id;
    }
    this.renderConsoleSession();
  },

  async addPaperFromPrompt() {
    const sessionId = this.state.currentSessionId;
    if (!sessionId) return;

    const paperId = prompt("输入 arXiv ID、论文链接或可下载 PDF 链接：");
    if (!paperId || !paperId.trim()) return;

    try {
      const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/papers/custom`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ paper_id: paperId.trim() }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "添加论文失败");
      }

      await this.reloadCurrentSession();
      const latest = this.getCurrentPaper();
      if (latest) {
        this.state.currentPaperId = latest.paper_id;
      }
      this.switchViewMode("summary");
      this.setConsoleStatus("search_complete", data.exists ? "论文已存在，已刷新来源列表" : "论文已添加并同步笔记");
    } catch (error) {
      alert(`添加失败：${error.message}`);
    }
  },

  async removePaper(paperId) {
    if (!this.state.currentSessionId) return;
    if (!confirm("确定移除这篇论文吗？")) return;

    try {
      const response = await fetch(`/api/sessions/${encodeURIComponent(this.state.currentSessionId)}/papers/${encodeURIComponent(paperId)}`, {
        method: "DELETE",
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "删除失败");
      }

      if (this.state.currentPaperId === paperId) {
        this.state.currentPaperId = null;
      }
      await this.reloadCurrentSession();
    } catch (error) {
      alert(`删除失败：${error.message}`);
    }
  },

  async setPaperStatus(paperId, status) {
    if (!this.state.currentSessionId) return;
    try {
      const response = await fetch(`/api/sessions/${encodeURIComponent(this.state.currentSessionId)}/papers/${encodeURIComponent(paperId)}/status`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "状态更新失败");
      }

      this.state.currentPaperId = paperId;
      await this.reloadCurrentSession();
      this.switchViewMode("summary");
    } catch (error) {
      alert(`状态更新失败：${error.message}`);
    }
  },

  sendChatMessage() {
    if (!this.els.chatInput) return;
    const message = this.els.chatInput.value.trim();
    if (!message) return;

    this.appendChatMessage("user", message, this.state.currentViewMode);
    this.els.chatInput.value = "";

    const reply = this.generateChatReply(message);
    this.appendChatMessage("agent", reply.text, this.state.currentViewMode, reply.note);
    this.state.lastReviewFeedback = this.state.currentViewMode === "review" ? message : this.state.lastReviewFeedback;
    this.renderChatContext();
  },

  generateChatReply(message) {
    const paper = this.getCurrentPaper();
    const session = this.state.currentSession || {};
    const mode = this.state.currentViewMode;

    if (mode === "review") {
      return {
        text: `我会按当前综述与已选论文来回答。基于你刚才的问题「${message}」，我建议先明确要修改的章节，再把修改意见压成 3 到 5 条可执行建议。当前选中的论文有 ${session.papers?.filter((item) => item.status === "accepted").length || 0} 篇。`,
        note: "可点击「生成修订版」把这条建议写入反馈并重新生成综述。",
      };
    }

    const currentName = paper?.title || paper?.paper_id || session.topic || "当前论文";
    return {
      text: `针对「${currentName}」，我可以只基于摘要 / 报告内容来回答。关于「${message}」，当前可用信息显示该论文属于 ${paper?.source || "当前主题来源"}，你可以继续切换到报告视图查看更多上下文。`,
      note: "该模式仅回答当前论文内容，不会改写报告或综述。",
    };
  },

  appendChatMessage(role, text, mode, note = "") {
    if (!this.els.chatList) return;
    const message = document.createElement("div");
    message.className = "chat-message";
    const avatar = document.createElement("div");
    avatar.className = `chat-avatar ${role}`;
    avatar.innerHTML = role === "user" ? '<i class="fa-solid fa-user"></i>' : '<i class="fa-solid fa-robot"></i>';

    const bubble = document.createElement("div");
    bubble.className = `chat-bubble ${role}`;
    bubble.innerHTML = `${note ? `<small>${this.escapeHtml(note)}</small>` : ""}${this.escapeHtml(text)}`;

    message.appendChild(avatar);
    message.appendChild(bubble);
    this.els.chatList.appendChild(message);
    this.els.chatList.scrollTop = this.els.chatList.scrollHeight;
  },

  async applyReviewFeedback() {
    if (this.state.currentViewMode !== "review") {
      return;
    }
    if (!this.state.currentSessionId) return;

    const feedback = this.state.lastReviewFeedback || this.els.chatInput?.value.trim() || "";
    if (!feedback) {
      alert("请先输入一条综述修改建议");
      return;
    }

    try {
      await fetch(`/api/sessions/${encodeURIComponent(this.state.currentSessionId)}/feedback`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ feedback }),
      });
      await this.runWritePhase();
    } catch (error) {
      alert(`应用修改失败：${error.message}`);
    }
  },

  loadThemePreference() {
    const theme = localStorage.getItem("notebooklm:theme");
    if (theme === "dark") {
      document.body.dataset.theme = "dark";
    }
  },

  escapeHtml(text) {
    return String(text || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  },

  formatDate(value) {
    if (!value) return "未知时间";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" });
  },
};

document.addEventListener("DOMContentLoaded", () => {
  notebooklm.init();
});

window.notebooklm = notebooklm;