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
    this.els.detailTitle = document.getElementById("detailHeader");
    this.els.detailMeta = document.getElementById("detailMeta");
    this.els.detailContent = document.getElementById("detailContent");
    this.els.viewSummary = document.getElementById("viewSummary");
    this.els.viewReport = document.getElementById("viewReport");
    this.els.viewReview = document.getElementById("viewReview");
    this.els.viewTrace = document.getElementById("viewTrace");
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
    this.els.themeToggle = document.getElementById("themeToggle");
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

    // 深色模式切换按钮
    if (this.els.themeToggle) {
      this.els.themeToggle.addEventListener("click", () => this.toggleTheme());
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

    if (!this.els.homeRail) return;
    this.els.homeRail.innerHTML = "";

    // Always show a Create card first (NotebookLM style)
    const createCard = document.createElement("article");
    createCard.className = "home-card home-card--create";
    createCard.innerHTML = `
      <div class="home-card-inner">
        <span class="home-card-icon"><i class="fa-solid fa-plus"></i></span>
        <span class="home-card-label">新建综述</span>
      </div>
    `;
    createCard.setAttribute('role', 'button');
    createCard.setAttribute('tabindex', '0');
    createCard.addEventListener('click', () => this.openTopicModal());
    createCard.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); this.openTopicModal(); } });
    this.els.homeRail.appendChild(createCard);

    // Render recent sessions as cards
    const visible = sessions.slice(0, 7);
    visible.forEach((session) => {
      const card = document.createElement("article");
      card.className = "home-card";
      const title = this.escapeHtml(session.topic || "未命名综述");
      const time = this.formatDate(session.updated_at || session.created_at);
      const paperCount = session.paper_count || 0;
      const noteFlag = session.note_size && session.note_size > 0 ? '有笔记' : '无笔记';

      card.innerHTML = `
        <div>
          <h3 title="${title}">${title}</h3>
          <small>${time}</small>
        </div>
        <div class="home-card-meta">
          <span class="badge">${paperCount} 个来源</span>
          <span class="badge">${noteFlag}</span>
        </div>
      `;

      card.addEventListener('click', () => {
        window.location.href = `/app/console?sessionId=${encodeURIComponent(session.session_id)}`;
      });

      const deleteBtn = document.createElement("button");
      deleteBtn.className = "home-card-delete";
      deleteBtn.title = "删除";
      deleteBtn.innerHTML = '<i class="fa-solid fa-trash"></i>';
      deleteBtn.addEventListener("click", async (event) => {
        event.stopPropagation();
        event.preventDefault();
        await this.deleteHomeSession(session.session_id);
      });
      card.appendChild(deleteBtn);

      this.els.homeRail.appendChild(card);
    });

    // "更多" link if sessions > 7
    if (sessions.length > 7) {
      const moreCard = document.createElement('article');
      moreCard.className = 'home-card home-card--ghost';
      moreCard.innerHTML = `
        <div class="home-card-inner">
          <span class="home-card-icon"><i class="fa-solid fa-ellipsis"></i></span>
          <span class="home-card-label">更多历史 · ${sessions.length - 7} 个</span>
        </div>
      `;
      moreCard.addEventListener('click', () => window.location.href = '/app/history');
      this.els.homeRail.appendChild(moreCard);
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
    // Try backend AI extraction first
    const seed = (this.els.keywordInput?.value || "").trim();
    this.renderHomeKeywordPlan([]);
    const loading = document.createElement("div");
    loading.className = "keyword-plan-loading";
    loading.textContent = "正在调用 AI 生成关键词...";
    this.els.homeKeywordList.appendChild(loading);

    fetch('/api/keywords/extract', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ topic, seed }),
    }).then(async (res) => {
      if (!res.ok) throw new Error((await res.json()).detail || '后端返回错误');
      return res.json();
    }).then((data) => {
      const kws = Array.isArray(data.keywords) ? data.keywords.slice() : [];
      // 如果前端有 seed 关键词，把它们追加为原始关键词
      if (seed) {
        const lines = seed.replace(/[，；\n]/g, ',').split(',').map(s => s.trim()).filter(Boolean);
        lines.forEach((s) => kws.push({ original: s, english: '', synonyms: '' }));
      }
      if (kws.length === 0) {
        // fallback to local dictionary pairing
        const plan = this.inferKeywordPlan(topic, seed || '');
        this.renderHomeKeywordPlan(plan);
      } else {
        // normalize each keyword object to expected shape
        const normalized = kws.slice(0, 6).map((k) => ({
          original: k.original || k.chinese || k.text || '',
          english: k.english || k.en || '',
          synonyms: k.synonyms || k.syn || k.aliases || '',
        }));
        this.renderHomeKeywordPlan(normalized);
      }
    }).catch((err) => {
      console.warn('AI 关键词生成失败，使用本地规则回退：', err);
      const plan = this.inferKeywordPlan(topic, seed || '');
      this.renderHomeKeywordPlan(plan);
    }).finally(() => {
      loading.remove();
    });
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
    this.els.notesBtn?.addEventListener("click", () => this.generateNotesAction());
    this.els.reviewBtn?.addEventListener("click", () => this.generateReviewAction());
    this.els.viewSummary?.addEventListener("click", () => this.switchViewMode("summary"));
    this.els.viewReport?.addEventListener("click", () => this.switchViewMode("report"));
    this.els.viewReview?.addEventListener("click", () => this.switchViewMode("review"));
    this.els.viewTrace?.addEventListener("click", () => this.switchViewMode("trace"));
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

    // 深色模式切换按钮
    if (this.els.themeToggle) {
      this.els.themeToggle.addEventListener("click", () => this.toggleTheme());
    }
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
    const draft = this.state.currentSession?.draft || "";

    // 更新论文计数
    const countChip = document.getElementById("paperCountChip");
    if (countChip) {
      const acceptedCount = papers.filter(p => p.status === "accepted").length;
      const hasNotesCount = papers.filter(p => p.has_notes).length;
      countChip.innerHTML = acceptedCount > 0
        ? `<i class="fa-solid fa-check"></i> ${papers.length} 篇（${acceptedCount} 已选，${hasNotesCount} 有笔记）`
        : `<i class="fa-solid fa-check"></i> ${papers.length} 篇（${hasNotesCount} 有笔记）`;
    }

    if (!papers.length) {
      this.els.paperList.innerHTML = '<div class="empty-state">点击「AI 检索论文」或「添加论文」开始构建来源库。</div>';
      return;
    }

    this.els.paperList.innerHTML = "";
    papers.forEach((paper) => {
      // 直接使用后端 per-paper 字段
      paper._hasNotes = paper.has_notes === true || Boolean((paper.notes || "").trim());
      paper._hasReview = Boolean(draft.trim());

      const row = document.createElement("article");
      row.className = `paper-row ${paper.paper_id === this.state.currentPaperId ? "active" : ""}`;
      row.addEventListener("click", () => {
        this.state.currentPaperId = paper.paper_id;
        this.renderPaperList();
        this.renderDetailPanel();
        this.renderChatContext();
        this.renderViewButtons();
      });

      const title = paper.title || paper.paper_id || "未命名论文";
      const authorLine = paper.authors || paper.source_type || paper.source || "来源未标记";
      const abstractPreview = (paper.abstract || "").slice(0, 80) + (paper.abstract && paper.abstract.length > 80 ? "..." : "");
      
      const statusIcon = paper._hasNotes
        ? '<span class="chip ok" title="已生成笔记"><i class="fa-solid fa-check-circle"></i> 有笔记</span>'
        : '<span class="chip warn" title="未生成笔记"><i class="fa-regular fa-circle"></i> 无笔记</span>';
      const reviewIcon = paper._hasReview
        ? '<span class="chip ok" title="已纳入综述"><i class="fa-solid fa-check-circle"></i> 已纳入综述</span>'
        : '';
      const selectedClass = paper.status === "accepted" ? "accepted" : "";

      row.innerHTML = `
        <div class="paper-main">
          <h4>${this.escapeHtml(title)}</h4>
          <p>${this.escapeHtml(abstractPreview || authorLine)}</p>
          <div class="paper-meta">
            <span class="chip"><i class="fa-regular fa-circle-dot"></i> ${this.escapeHtml(paper.source || "agent_search")}</span>
            ${statusIcon}
            ${reviewIcon}
            ${paper.added_at ? `<span class="chip"><i class="fa-regular fa-clock"></i> ${this.formatDate(paper.added_at)}</span>` : ""}
          </div>
        </div>
        <div class="paper-actions">
          <button class="mini-btn remove" title="移除论文" data-action="remove"><i class="fa-solid fa-xmark"></i></button>
          <button class="mini-btn ${selectedClass}" title="${paper.status === 'accepted' ? '取消选中' : '选中论文'}" data-action="accept"><i class="fa-solid fa-check"></i></button>
        </div>
      `;

      row.querySelector('[data-action="remove"]')?.addEventListener("click", async (event) => {
        event.stopPropagation();
        await this.removePaper(paper.paper_id);
      });

      row.querySelector('[data-action="accept"]')?.addEventListener("click", async (event) => {
        event.stopPropagation();
        await this.setPaperStatus(paper.paper_id, paper.status === "accepted" ? "pending" : "accepted");
      });

      this.els.paperList.appendChild(row);
    });
  },

  renderNotesBlock() {
    // notesBlock 已从 HTML 中移除，笔记在右侧报告/综述视图中展示
    return;
  },

  renderReviewBlock() {
    if (!this.els.reviewBlock) return;
    const draft = this.state.currentSession?.draft || "";
    const hasDraft = Boolean(draft.trim());
    const topic = this.state.currentSession?.topic || "综述";

    if (hasDraft) {
      // 有综述 → 只显示标题，点击跳转到右侧综述视图
      this.els.reviewBlock.innerHTML = `
        <div class="panel-block-head">
          <strong>📝 综述</strong>
          <span class="chip ok"><i class="fa-solid fa-check-circle"></i> 已生成</span>
        </div>
        <div class="review-title-link" id="reviewTitleLink" style="cursor:pointer;padding:10px 0;border:1px solid var(--line);border-radius:12px;padding:14px;">
          <h4 style="margin:0;font-size:0.95rem;color:var(--accent);">${this.escapeHtml(topic)}</h4>
          <span style="font-size:0.82rem;color:var(--subtle);">点击查看完整综述 →</span>
        </div>
      `;
      const link = document.getElementById("reviewTitleLink");
      if (link) {
        link.addEventListener("click", () => {
          this.state.currentViewMode = "review";
          this.renderDetailPanel();
          this.renderViewButtons();
          this.renderChatContext();
        });
      }
    } else {
      this.els.reviewBlock.innerHTML = `
        <div class="panel-block-head">
          <strong>📝 综述</strong>
          <span class="chip"><i class="fa-regular fa-pen-to-square"></i> 未生成</span>
        </div>
        <div class="empty-state">还没有综述草稿。选中论文并生成笔记后，点击「生成综述」按钮生成。</div>
      `;
    }
  },

  renderDetailPanel() {
    if (!this.state.currentSession || !this.els.detailContent) return;

    const session = this.state.currentSession;
    const paper = this.getCurrentPaper();
    const paperCount = session.papers?.length || 0;
    const isPerSession = this.state.currentViewMode === "review" || this.state.currentViewMode === "trace";
    const selectedLabel = isPerSession
      ? (session.topic || "未命名主题")
      : (paper ? paper.title || paper.paper_id : "未选择论文");

    if (this.els.detailTitle) {
      this.els.detailTitle.textContent = selectedLabel;
    }
    if (this.els.detailMeta) {
      const modeLabel = this.viewModeLabel(this.state.currentViewMode);
      if (isPerSession) {
        this.els.detailMeta.textContent = `${paperCount} 个来源 · ${modeLabel} · ${session.state_label || session.state}`;
      } else {
        this.els.detailMeta.textContent = `${paperCount} 个来源 · ${modeLabel} · ${session.state_label || session.state}`;
      }
    }

    let html = "";
    if (this.state.currentViewMode === "summary") {
      html = this.renderPaperSummary(paper, session);
    } else if (this.state.currentViewMode === "report") {
      html = this.renderPaperReport(paper, session);
    } else if (this.state.currentViewMode === "trace") {
      html = this.renderTraceView(session);
    } else {
      html = this.renderReviewView(session);
    }

    this.els.detailContent.innerHTML = html;
  },

  renderPaperSummary(paper, session) {
    if (!paper) {
      return '<div class="empty-state">请先在左侧选择一篇论文。</div>';
    }

    const abstract = paper.abstract || paper.summary || paper.description || "";
    return `
      <div class="detail-hero">
        <span class="topic-badge"><i class="fa-regular fa-note-sticky"></i> 摘要</span>
        <h3>${this.escapeHtml(paper.title || paper.paper_id || "未命名论文")}</h3>
        <div class="lead">${this.escapeHtml(paper.authors || paper.source || "该论文已加入当前综述主题")}</div>
      </div>
      <div class="detail-blocks" style="margin-top:16px;">
        <div class="panel-block">
          <div class="panel-block-head"><strong>论文摘要</strong><span class="chip">只读</span></div>
          <div class="plain-text">${this.escapeHtml(abstract || "当前没有可用摘要，建议继续检索或添加 PDF 以补全信息。")}</div>
        </div>
        <div class="panel-block">
          <div class="panel-block-head"><strong>来源信息</strong><span class="chip">${this.escapeHtml(paper.status || "pending")}</span></div>
          <div class="plain-text">来源：${this.escapeHtml(paper.source || "agent_search")} · 来源类型：${this.escapeHtml(paper.source_type || "n/a")} · 添加时间：${this.escapeHtml(this.formatDate(paper.added_at))}</div>
        </div>
      </div>
    `;
  },

  renderPaperReport(paper, session) {
    const notes = paper.notes || session.notes || "";
    const hasPaperNotes = paper._hasNotes;
    return `
      <div class="detail-hero">
        <span class="topic-badge"><i class="fa-solid fa-chart-line"></i> 报告</span>
        <h3>${this.escapeHtml(paper?.title || paper?.paper_id || session.topic || "综合报告")}</h3>
        <div class="lead">${hasPaperNotes ? '这是该论文的研究笔记，由 AI 自动生成。' : '该论文尚未生成笔记，请选中后点击左侧「生成笔记」。'}</div>
      </div>
      <div class="panel-block" style="margin-top:16px;">
        <div class="panel-block-head"><strong>${hasPaperNotes ? '研究笔记' : '报告内容'}</strong><span class="chip">${hasPaperNotes ? 'AI生成' : '待生成'}</span></div>
        <div class="markdown">${notes.trim() ? marked.parse(notes) : '<div class="empty-state">该论文还没有研究笔记。请选中该论文后点击左侧「生成笔记」按钮。</div>'}</div>
      </div>
    `;
  },

  renderReviewView(session) {
    let draft = session?.draft || session?.notes || "";
    // 去除大纲的 markdown 代码块包裹 — 两种情形：
    // 1. 有闭合围栏：```markdown ... ```
    // 2. 无闭合围栏：```markdown ...（到文末或 --- 分隔符）
    draft = draft.replace(/```markdown\s*\n([\s\S]*?)```/g, '$1');
    draft = draft.replace(/```markdown\s*\n([\s\S]*?)(\n---|\n## (?!##)|$)/, '$1$2');
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
      trace: this.els.viewTrace,
    };
    const paper = this.getCurrentPaper();
    const hasNotes = paper ? paper._hasNotes : false;
    const hasDraft = Boolean((this.state.currentSession?.draft || "").trim());
    const acceptedPapers = (this.state.currentSession?.papers || []).filter(p => p.status === "accepted");
    const anyHasNotes = acceptedPapers.some(p => p._hasNotes) || paper?._hasNotes;
    
    Object.entries(map).forEach(([mode, el]) => {
      if (!el) return;
      el.classList.toggle("active", this.state.currentViewMode === mode);
      
      // 动态禁用逻辑：
      // - "摘要" 和 "轨迹" 始终可用
      // - "笔记"（报告）：当前论文有笔记时才可用
      // - "综述"：有综述草稿时才可用
      if (mode === "summary" || mode === "trace") {
        el.disabled = false;
      } else if (mode === "report") {
        el.disabled = !hasNotes;
      } else if (mode === "review") {
        el.disabled = !hasDraft;
      }
    });
  },

  renderTraceView(session) {
    const traces = session?.traces || [];
    const topic = session?.topic || "当前会话";

    let html = `
      <div class="detail-hero">
        <span class="topic-badge"><i class="fa-solid fa-route"></i> 执行轨迹</span>
        <h3>${this.escapeHtml(topic)}</h3>
        <div class="lead">共 ${traces.length} 步 · 当前状态：${session.state_label || session.state || "未知"}</div>
      </div>
      <div class="detail-blocks" style="margin-top:16px;">
    `;

    if (!traces || traces.length === 0) {
      html += `
        <div class="panel-block">
          <div class="panel-block-head"><strong>暂无轨迹</strong></div>
          <div class="empty-state">Agent 尚未执行，或轨迹尚未生成。请先执行规划或检索。</div>
        </div>
      `;
    } else {
      traces.forEach((step, idx) => {
        const action = step.action || "执行";
        const thought = step.thought || "";
        const observation = step.observation || "";
        const errorType = step.error_type || "";
        const inputObj = step.input || step.action_input || {};
        const inputStr = typeof inputObj === "string" ? inputObj : JSON.stringify(inputObj, null, 2);

        let statusChip = "";
        if (errorType) {
          statusChip = `<span class="chip err" title="错误类型: ${this.escapeHtml(errorType)}"><i class="fa-solid fa-triangle-exclamation"></i> 失败</span>`;
        } else {
          statusChip = `<span class="chip ok"><i class="fa-solid fa-circle-check"></i> 成功</span>`;
        }

        html += `
          <div class="panel-block trace-step">
            <div class="panel-block-head">
              <strong>第 ${idx + 1} 轮 · ${this.escapeHtml(action)}</strong>
              ${statusChip}
            </div>
            <div class="trace-body">
        `;

        if (thought) {
          html += `
              <div class="trace-section">
                <div class="trace-label">💭 思考</div>
                <div class="trace-text">${this.escapeHtml(thought)}</div>
              </div>
          `;
        }

        if (inputStr && inputStr !== "{}" && inputStr !== "null") {
          html += `
              <div class="trace-section">
                <div class="trace-label">📥 参数</div>
                <pre class="trace-pre">${this.escapeHtml(inputStr)}</pre>
              </div>
          `;
        }

        if (observation) {
          // 截断过长的 observation
          const truncated = observation.length > 2000
            ? observation.slice(0, 2000) + "\n\n... (观察内容过长，已截断)"
            : observation;
          html += `
              <div class="trace-section">
                <div class="trace-label">👁 观察</div>
                <pre class="trace-pre">${this.escapeHtml(truncated)}</pre>
              </div>
          `;
        }

        html += `
            </div>
          </div>
        `;
      });
    }

    html += `</div>`;
    return html;
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

    const papers = session.papers || [];
    const hasPapers = papers.length > 0;
    const hasDraft = Boolean((session.draft || "").trim());
    const acceptedPapers = papers.filter(p => p.status === "accepted");
    const effectivePapers = acceptedPapers.length > 0 ? acceptedPapers : papers;

    // 计数：有效选中论文中，有笔记的 / 没笔记的
    const withNotes = effectivePapers.filter(p => p._hasNotes).length;
    const withoutNotes = effectivePapers.length - withNotes;
    const allHaveNotes = effectivePapers.length > 0 && withoutNotes === 0;
    const anyNeedNotes = withoutNotes > 0;
    const notesGenerated = effectivePapers.length > 0 && allHaveNotes;

    // AI检索论文 按钮
    if (this.els.searchBtn) {
      if (!session.keywords || !session.keywords.length || session.state === "planning") {
        this.els.searchBtn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> 生成关键词';
        this.els.searchBtn.disabled = false;
      } else if (session.state === "plan_confirmed") {
        this.els.searchBtn.innerHTML = '<i class="fa-solid fa-magnifying-glass"></i> AI检索论文';
        this.els.searchBtn.disabled = false;
      } else if (session.state === "searching") {
        this.els.searchBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 检索中...';
        this.els.searchBtn.disabled = true;
      } else {
        this.els.searchBtn.innerHTML = '<i class="fa-solid fa-magnifying-glass"></i> 重新检索';
        this.els.searchBtn.disabled = false;
      }
    }

    // 添加论文 按钮
    if (this.els.addPaperBtn) {
      this.els.addPaperBtn.disabled = false;
    }

    // 生成笔记 按钮
    // 规则：有效选中论文中，有未生成笔记的 → 亮；全都有 → 灰（不能重新生成）
    if (this.els.notesBtn) {
      if (!effectivePapers.length || !hasPapers) {
        this.els.notesBtn.disabled = true;
        this.els.notesBtn.innerHTML = '<i class="fa-regular fa-file-lines"></i> 生成笔记';
        this.els.notesBtn.classList.remove("active");
      } else if (anyNeedNotes) {
        this.els.notesBtn.disabled = false;
        this.els.notesBtn.innerHTML = '<i class="fa-regular fa-file-lines"></i> 生成笔记';
        this.els.notesBtn.classList.add("active");
      } else {
        this.els.notesBtn.disabled = true;
        this.els.notesBtn.innerHTML = '<i class="fa-solid fa-check"></i> 笔记已生成';
        this.els.notesBtn.classList.remove("active");
      }
    }

    // 生成综述 按钮
    // 规则：所选全部有笔记 + 无草稿 → 亮；已有草稿 → 灰
    if (this.els.reviewBtn) {
      if (!notesGenerated) {
        this.els.reviewBtn.disabled = true;
        this.els.reviewBtn.innerHTML = '<i class="fa-regular fa-pen-to-square"></i> 生成综述';
        this.els.reviewBtn.classList.remove("active");
      } else if (hasDraft) {
        this.els.reviewBtn.disabled = true;
        this.els.reviewBtn.innerHTML = '<i class="fa-solid fa-check"></i> 综述已生成';
        this.els.reviewBtn.classList.remove("active");
      } else {
        this.els.reviewBtn.disabled = false;
        this.els.reviewBtn.innerHTML = '<i class="fa-regular fa-pen-to-square"></i> 生成综述';
        this.els.reviewBtn.classList.add("active");
      }
    }

    // 更新状态提示
    const hint = document.getElementById("statusHint");
    if (hint) {
      if (session.state === "planning") {
        hint.innerHTML = '<i class="status-dot warn"></i>请先确认关键词规划';
      } else if (session.state === "plan_confirmed") {
        hint.innerHTML = '<i class="status-dot live"></i>关键词已确认，点击「AI检索论文」开始搜索';
      } else if (session.state === "searching") {
        hint.innerHTML = '<i class="status-dot live"></i>正在检索论文并同步笔记...';
      } else if (hasDraft) {
        hint.innerHTML = '<i class="status-dot ok"></i>综述已生成，可在右侧查看与提问';
      } else if (notesGenerated) {
        hint.innerHTML = '<i class="status-dot ok"></i>选中论文笔记已全部生成，点击「生成综述」撰写初稿';
      } else if (anyNeedNotes) {
        hint.innerHTML = `<i class="status-dot live"></i>${withoutNotes} 篇选中论文未生成笔记，点击「生成笔记」`;
      } else if (hasPapers) {
        hint.innerHTML = '<i class="status-dot live"></i>请选中论文（✓），然后生成笔记';
      } else {
        hint.innerHTML = '<i class="status-dot live"></i>请先检索论文，再生成笔记与综述';
      }
    }
  },

  viewModeLabel(mode) {
    return {
      summary: "摘要",
      report: "报告",
      review: "综述",
      trace: "轨迹",
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

  async generateNotesAction() {
    const session = this.state.currentSession;
    if (!session || !this.state.currentSessionId) return;

    const papers = session.papers || [];
    const acceptedPapers = papers.filter(p => p.status === "accepted");
    const effectivePapers = acceptedPapers.length > 0 ? acceptedPapers : papers;
    // 只处理未生成笔记的论文
    const needNotes = effectivePapers.filter(p => !p._hasNotes);
    
    if (needNotes.length === 0) {
      alert("所有选中论文已生成笔记，无需重复生成。");
      return;
    }

    const paperIds = needNotes.map(p => p.paper_id);
    
    try {
      this.setConsoleStatus("writing", `正在为 ${paperIds.length} 篇论文生成笔记...`);
      const response = await fetch(`/api/sessions/${encodeURIComponent(this.state.currentSessionId)}/run/notes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic: session.topic, paper_ids: paperIds }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "生成笔记失败");
      }

      await this.reloadCurrentSession();
      // 自动选中刚生成笔记的论文
      for (const pid of paperIds) {
        try {
          await fetch(`/api/sessions/${encodeURIComponent(this.state.currentSessionId)}/papers/${encodeURIComponent(pid)}/status`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ status: "accepted" }),
          });
        } catch (e) { /* ignore */ }
      }
      await this.reloadCurrentSession();
      this.switchViewMode("report");
      this.setConsoleStatus("search_complete", `${data.count || paperIds.length} 篇论文笔记已生成`);
    } catch (error) {
      this.setConsoleStatus("error", `生成笔记失败：${error.message}`);
    }
  },

  async generateReviewAction() {
    await this.runWritePhase();
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
      this.setConsoleStatus("searching", "论文搜索中");
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

  async sendChatMessage() {
    if (!this.els.chatInput) return;
    const message = this.els.chatInput.value.trim();
    if (!message) return;

    this.appendChatMessage("user", message, this.state.currentViewMode);
    this.els.chatInput.value = "";

    // show a temporary loading indicator
    this.appendChatMessage("agent", "正在生成回复...", this.state.currentViewMode, "");
    // await AI reply
    const reply = await this.generateChatReply(message);

    // replace the last agent message with the real reply
    const msgs = Array.from(this.els.chatList.querySelectorAll('.chat-msg'));
    const lastMsg = msgs[msgs.length - 1];
    if (lastMsg) {
      lastMsg.innerHTML = `<span class="chat-role">AI</span><span>${this.escapeHtml(reply.text || '')}</span>`;
    }

    this.state.lastReviewFeedback = this.state.currentViewMode === "review" ? message : this.state.lastReviewFeedback;
    this.renderChatContext();
  },

  async generateChatReply(message) {
    const paper = this.getCurrentPaper();
    const session = this.state.currentSession || {};
    const mode = this.state.currentViewMode;

    // Show a temporary loading reply while waiting for backend
    try {
      const payload = { message, mode };
      if (paper && paper.paper_id) payload.paper_id = paper.paper_id;

      const res = await fetch(`/api/sessions/${encodeURIComponent(this.state.currentSessionId)}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      const data = await res.json();
      if (!res.ok) {
        console.warn('后端聊天接口返回错误，使用本地简短回复：', data);
        return { text: data.detail || 'AI 回复失败，请稍后重试。', note: '' };
      }

      return { text: data.reply || '（空回复）', note: '' };
    } catch (e) {
      console.warn('调用后端聊天接口失败：', e);
      return { text: 'AI 服务不可用，无法生成智能回复。', note: '' };
    }
  },

  appendChatMessage(role, text, mode, note = "") {
    if (!this.els.chatList) return;
    const msg = document.createElement("div");
    msg.className = "chat-msg";
    const roleLabel = role === "user" ? "你" : "AI";
    const noteHtml = note ? `<span style="font-size:11px;color:var(--subtle);display:block">${this.escapeHtml(note)}</span>` : "";
    msg.innerHTML = `<span class="chat-role">${roleLabel}</span><span>${noteHtml}${this.escapeHtml(text)}</span>`;
    this.els.chatList.appendChild(msg);
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

    const applyBtn = this.els.chatApply;
    try {
      // Disable button immediately to prevent duplicate submissions
      if (applyBtn) {
        applyBtn.disabled = true;
        applyBtn.setAttribute('aria-disabled', 'true');
        applyBtn.title = '已提交修订，正在生成中...';
      }

      const res = await fetch(`/api/sessions/${encodeURIComponent(this.state.currentSessionId)}/feedback`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ feedback }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || '提交失败');
      }

      await this.runWritePhase();

      // Keep the button disabled after successful submission to indicate it's been used
      if (applyBtn) {
        applyBtn.disabled = true;
        applyBtn.setAttribute('aria-disabled', 'true');
        applyBtn.textContent = '已提交修订';
      }
    } catch (error) {
      // Re-enable button on error to allow retry
      if (applyBtn) {
        applyBtn.disabled = false;
        applyBtn.setAttribute('aria-disabled', 'false');
        applyBtn.title = '生成修订版';
      }
      alert(`应用修改失败：${error.message}`);
    }
  },

  loadThemePreference() {
    const theme = localStorage.getItem("notebooklm:theme");
    if (theme === "dark") {
      document.body.dataset.theme = "dark";
    }
    this.updateThemeIcon();
  },

  toggleTheme() {
    const isDark = document.body.dataset.theme === "dark";
    document.body.dataset.theme = isDark ? "" : "dark";
    localStorage.setItem("notebooklm:theme", isDark ? "light" : "dark");
    this.updateThemeIcon();
  },

  updateThemeIcon() {
    const isDark = document.body.dataset.theme === "dark";
    const btn = document.getElementById("themeToggle");
    if (btn) {
      btn.innerHTML = isDark ? '<i class="fa-solid fa-sun"></i>' : '<i class="fa-solid fa-moon"></i>';
      btn.title = isDark ? "切换浅色模式" : "切换深色模式";
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