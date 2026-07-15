const notebooklm = {
  state: {
    sessions: [],
    currentSessionId: null,
    currentSession: null,
    currentPaperId: null,
    currentViewMode: "summary",
    chatMode: "normal",
    pendingRevision: null,
    chatMessages: [],
    currentConvId: null,
    conversations: [],
    pollTimer: null,
    pendingSeedKeywords: "",
    lastReviewFeedback: "",
    isEditingReport: false,
    reportEditText: "",
    isEditingReview: false,
    reviewEditText: "",
    editingAnalysisSection: "",
    analysisEditText: "",
    _autoRunning: false,
    _autoPollTimer: null,
    _searchLoopCustomized: false,
    lastAction: "",
    provider: {
      provider_id: "zhipu",
      api_key: "",
      base_url: "https://open.bigmodel.cn/api/paas/v4/",
      model: "glm-4-flash",
      chat_model: "glm-4-flash",
      embedding_model: "embedding-3",
      save_local: false,
      server_available: false,
    },
  },

  els: {},

  init() {
    this.bindCommonElements();
    this.loadThemePreference();
    this.loadProviderConfig();
    window.addEventListener("academic-auth-changed", () => this.loadProviderConfig());

    // 为所有页面绑定主题切换按钮
    this.els.themeToggle = document.getElementById("themeToggle");
    if (this.els.themeToggle) {
      this.els.themeToggle.addEventListener("click", () => this.toggleTheme());
    }

    const page = document.body.dataset.page || "home";
    if (page === "home") {
      this.initHome();
    } else if (page === "console") {
      this.initConsole();
    } else if (page === "skills") {
      this.initSkills();
    }
    // help 页面只需主题切换，不需要额外初始化
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
    this.els.homeContinueProject = document.getElementById("homeContinueProject");
    this.els.homeProviderStep = document.getElementById("homeProviderStep");
    this.els.homeProviderStepStatus = document.getElementById("homeProviderStepStatus");
    this.els.homeOnboardingProgress = document.getElementById("homeOnboardingProgress");
    this.els.historyCount = document.getElementById("historyCount");

    this.els.consoleTopic = document.getElementById("consoleTopic");
    this.els.consoleState = document.getElementById("consoleState");
    this.els.consoleStateDot = document.getElementById("consoleStateDot");
    this.els.searchBtn = document.getElementById("searchPaperBtn");
    this.els.searchTargetInput = document.getElementById("searchTargetInput");
    this.els.searchLoopLimitInput = document.getElementById("searchLoopLimitInput");
    this.els.searchBudgetHelp = document.getElementById("searchBudgetHelp");
    this.els.addPaperBtn = document.getElementById("addPaperBtn");
    this.els.pdfFileInput = document.getElementById("pdfFileInput");
    this.els.notesBtn = document.getElementById("generateNotesBtn");
    this.els.reviewBtn = document.getElementById("generateReviewBtn");
    this.els.selectedPaperCount = document.getElementById("selectedPaperCount");
    this.els.selectionActionHint = document.getElementById("selectionActionHint");
    this.els.paperList = document.getElementById("paperList");
    this.els.paperScrollTrack = document.getElementById("paperScrollTrack");
    this.els.paperScrollThumb = document.getElementById("paperScrollThumb");
    this.els.notesBlock = document.getElementById("notesBlock");
    this.els.reviewBlock = document.getElementById("reviewBlock");
    this.els.detailHeader = document.getElementById("detailHeader");
    this.els.detailTitle = document.getElementById("detailHeader");
    this.els.detailMeta = document.getElementById("detailMeta");
    this.els.detailContent = document.getElementById("detailContent");
    this.els.viewSummary = document.getElementById("viewSummary");
    this.els.viewReport = document.getElementById("viewReport");
    this.els.viewReview = document.getElementById("viewReview");
    this.els.viewPDF = document.getElementById("viewPDF");
    this.els.viewTrace = document.getElementById("viewTrace");
    this.els.viewAnalysis = document.getElementById("viewAnalysis");
    this.els.chatList = document.getElementById("chatList");
    this.els.chatInput = document.getElementById("chatInput");
    this.els.chatSend = document.getElementById("chatSend");
    this.els.chatModeToggle = document.getElementById("chatModeToggle");
    this.els.chatContext = document.getElementById("chatContext");
    this.els.keywordModal = document.getElementById("keywordModal");
    this.els.keywordTopic = document.getElementById("keywordTopic");
    this.els.keywordList = document.getElementById("keywordList");
    this.els.keywordAdd = document.getElementById("keywordAdd");
    this.els.keywordConfirm = document.getElementById("keywordConfirm");
    this.els.keywordCancel = document.getElementById("keywordCancel");
    this.els.themeToggle = document.getElementById("themeToggle");
    this.els.cancelSearchBtn = document.getElementById("cancelSearchBtn");
    this.els.autoRunBtn = document.getElementById("autoRunBtn");
    // 工具管理
    this.els.toolManagerBtn = document.getElementById("toolManagerBtn");
    this.els.toolManagerModal = document.getElementById("toolManagerModal");
    this.els.toolManagerList = document.getElementById("toolManagerList");
    this.els.toolManagerClose = document.getElementById("toolManagerClose");
    this.els.toolManagerClose2 = document.getElementById("toolManagerClose2");
    this.els.toolManagerSave = document.getElementById("toolManagerSave");
    this.els.toolResetBtn = document.getElementById("toolResetBtn");
    this.els.toolEnabledCount = document.getElementById("toolEnabledCount");
    this.els.toolDisabledCount = document.getElementById("toolDisabledCount");
    this.els.apiConfigBtn = document.getElementById("apiConfigBtn");
    this.els.apiConfigModal = document.getElementById("apiConfigModal");
    this.els.apiConfigClose = document.getElementById("apiConfigClose");
    this.els.apiConfigSave = document.getElementById("apiConfigSave");
    this.els.apiConfigClear = document.getElementById("apiConfigClear");
    this.els.providerApiKey = document.getElementById("providerApiKey");
    this.els.providerBaseUrl = document.getElementById("providerBaseUrl");
    this.els.providerModel = document.getElementById("providerModel");
    this.els.providerSaveLocal = document.getElementById("providerSaveLocal");
    this.els.providerStatusHint = document.getElementById("providerStatusHint");
    this.els.providerTopStatus = document.getElementById("providerTopStatus");
    this.els.researchStages = document.getElementById("researchStages");
    this.els.statusRetry = document.getElementById("statusRetry");
    this.els.exportArtifactsBtn = document.getElementById("exportArtifactsBtn");
    this.els.exportModal = document.getElementById("exportModal");
    this.els.exportModalClose = document.getElementById("exportModalClose");
    this.els.exportMessage = document.getElementById("exportMessage");
    this.els.githubExportRepo = document.getElementById("githubExportRepo");
    this.els.githubExportSubmit = document.getElementById("githubExportSubmit");
    this.els.researchRepoBtn = document.getElementById("researchRepoBtn");
    this.els.repositoryResearchModal = document.getElementById("repositoryResearchModal");
    this.els.repositoryResearchResult = document.getElementById("repositoryResearchResult");
    this.els.repositoryList = document.getElementById("repositoryList");
  },

  loadProviderConfig() {
    const defaults = {
      provider_id: "zhipu",
      api_key: "",
      base_url: "https://open.bigmodel.cn/api/paas/v4/",
      model: "glm-4-flash",
      chat_model: "glm-4-flash",
      embedding_model: "embedding-3",
      save_local: false,
      server_available: false,
    };
    try {
      const localSaved = JSON.parse(localStorage.getItem(this.providerStorageKey()) || "{}");
      const sessionSaved = JSON.parse(sessionStorage.getItem(this.providerStorageKey()) || "{}");
      const saved = Object.keys(sessionSaved).length ? sessionSaved : localSaved;
      this.state.provider = { ...defaults, ...saved, save_local: !!saved.save_local };
    } catch (error) {
      this.state.provider = defaults;
    }
    fetch("/api/provider/status")
      .then((res) => res.json())
      .then((status) => {
        this.state.provider.server_available = !!status.server_provider_available;
        this.state.provider.base_url = this.state.provider.base_url || status.default_base_url || defaults.base_url;
        this.state.provider.model = this.state.provider.model || status.default_model || defaults.model;
        this.refreshProviderStatus();
      })
      .catch(() => this.refreshProviderStatus());
  },

  providerStorageKey() {
    const userId = window.academicAuthUserId || "local";
    return `academic-agent:provider:${userId}`;
  },

  getProviderPayload() {
    const provider = this.state.provider || {};
    const payload = {
      provider_id: String(provider.provider_id || "zhipu").trim(),
      api_key: String(provider.api_key || "").trim(),
      base_url: String(provider.base_url || "https://open.bigmodel.cn/api/paas/v4/").trim(),
      model: String(provider.chat_model || provider.model || "glm-4-flash").trim(),
      chat_model: String(provider.chat_model || provider.model || "glm-4-flash").trim(),
      embedding_model: String(provider.embedding_model || "").trim(),
    };
    if (!payload.api_key) delete payload.api_key;
    return payload;
  },

  withProvider(body = {}) {
    return { ...body, provider: this.getProviderPayload() };
  },

  refreshProviderStatus() {
    const hasLocalKey = !!String(this.state.provider?.api_key || "").trim();
    const hasServerKey = !!this.state.provider?.server_available;
    if (this.els.providerStatusHint) {
      this.els.providerStatusHint.className = `provider-status ${hasLocalKey || hasServerKey ? "ok" : "warn"}`;
      this.els.providerStatusHint.textContent = hasLocalKey
        ? "模型已连接。"
        : hasServerKey
          ? "模型已连接。"
          : "需要配置模型后才能使用 AI 功能。";
    }
    if (this.els.providerTopStatus) {
      this.els.providerTopStatus.textContent = hasLocalKey || hasServerKey ? "模型已连接" : "需要配置";
      this.els.apiConfigBtn?.classList.toggle("connected", hasLocalKey || hasServerKey);
    }
    this.refreshHomeOnboarding();
  },

  refreshHomeOnboarding() {
    if (!this.els.homeProviderStep) return;
    const hasProvider = !!String(this.state.provider?.api_key || "").trim() || !!this.state.provider?.server_available;
    const hasProject = (this.state.sessions || []).length > 0;
    const hasSearch = (this.state.sessions || []).some((session) => Number(session.paper_count || 0) > 0);
    this.els.homeProviderStep.classList.toggle("complete", hasProvider);
    if (this.els.homeProviderStepStatus) this.els.homeProviderStepStatus.textContent = hasProvider ? "已连接" : "需要配置";
    document.getElementById("homeTopicStep")?.classList.toggle("complete", hasProject);
    document.getElementById("homeSearchStep")?.classList.toggle("complete", hasSearch);
    if (this.els.homeOnboardingProgress) {
      const completed = [hasProvider, hasProject, hasSearch].filter(Boolean).length;
      this.els.homeOnboardingProgress.textContent = `${completed} / 3`;
    }
  },

  openApiConfigModal() {
    if (!this.els.apiConfigModal) return;
    this.els.providerApiKey.value = this.state.provider.api_key || "";
    this.els.providerBaseUrl.value = this.state.provider.base_url || "https://open.bigmodel.cn/api/paas/v4/";
    this.els.providerModel.value = this.state.provider.model || "glm-4-flash";
    this.els.providerSaveLocal.checked = this.state.provider.save_local !== false;
    this.refreshProviderStatus();
    this.els.apiConfigModal.style.display = "";
    this.els.apiConfigModal.classList.add("active");
  },

  closeApiConfigModal() {
    this.els.apiConfigModal?.classList.remove("active");
  },

  saveApiConfig() {
    this.state.provider.api_key = this.els.providerApiKey?.value?.trim() || "";
    this.state.provider.base_url = this.els.providerBaseUrl?.value?.trim() || "https://open.bigmodel.cn/api/paas/v4/";
    this.state.provider.model = this.els.providerModel?.value?.trim() || "glm-4-flash";
    this.state.provider.save_local = this.els.providerSaveLocal?.checked !== false;
    if (this.state.provider.save_local) {
      localStorage.setItem(this.providerStorageKey(), JSON.stringify({
        provider_id: this.state.provider.provider_id,
        api_key: this.state.provider.api_key,
        base_url: this.state.provider.base_url,
        model: this.state.provider.model,
        chat_model: this.state.provider.chat_model || this.state.provider.model,
        embedding_model: this.state.provider.embedding_model,
        save_local: true,
      }));
      sessionStorage.removeItem(this.providerStorageKey());
    } else {
      localStorage.removeItem(this.providerStorageKey());
      sessionStorage.setItem(this.providerStorageKey(), JSON.stringify({
        provider_id: this.state.provider.provider_id,
        api_key: this.state.provider.api_key,
        base_url: this.state.provider.base_url,
        model: this.state.provider.model,
        chat_model: this.state.provider.chat_model || this.state.provider.model,
        embedding_model: this.state.provider.embedding_model,
        save_local: false,
      }));
    }
    this.refreshProviderStatus();
    this.closeApiConfigModal();
  },

  clearApiConfig() {
    this.state.provider.api_key = "";
    this.state.provider.base_url = "https://open.bigmodel.cn/api/paas/v4/";
    this.state.provider.model = "glm-4-flash";
    localStorage.removeItem(this.providerStorageKey());
    sessionStorage.removeItem(this.providerStorageKey());
    this.openApiConfigModal();
  },

  async initHome() {
    const openCreateTopic = document.getElementById("openCreateTopic");
    if (openCreateTopic) {
      openCreateTopic.addEventListener("click", () => this.openTopicModal());
    }
    document.getElementById("openCreateTopicInline")?.addEventListener("click", () => this.openTopicModal());
    if (this.els.topicSubmit) {
      this.els.topicSubmit.addEventListener("click", () => this.createTopicFromModal());
    }
    if (this.els.topicCancel) {
      this.els.topicCancel.addEventListener("click", () => this.closeTopicModal());
    }
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && this.els.topicModal?.classList.contains("active")) this.closeTopicModal();
    });
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
    await this.loadHomeStats();
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
      this.els.homeRail.innerHTML = '<div class="empty-state">暂时无法加载最近项目，请刷新页面重试。</div>';
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

    const latest = sessions[0];
    if (this.els.homeContinueProject) {
      this.els.homeContinueProject.hidden = !latest;
      if (latest) this.els.homeContinueProject.href = `/app/console?sessionId=${encodeURIComponent(latest.session_id)}`;
    }
    this.refreshHomeOnboarding();

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
      const moreCard = document.createElement('div');
      moreCard.className = 'home-card home-card--ghost';
      const extraCount = sessions.length - 7;
      const renderMoreLabel = (expanded) => expanded
        ? `<div class="home-card-inner"><span class="home-card-icon"><i class="fa-solid fa-angle-up"></i></span><span class="home-card-label">收起</span></div>`
        : `<div class="home-card-inner"><span class="home-card-icon"><i class="fa-solid fa-ellipsis"></i></span><span class="home-card-label">更多历史 · ${extraCount} 个</span></div>`;

      moreCard.innerHTML = renderMoreLabel(false);
      moreCard.setAttribute('role', 'button');
      moreCard.setAttribute('tabindex', '0');
      moreCard.addEventListener('click', () => {
        const parent = moreCard.parentElement;
        if (!parent) return;
        const expanded = moreCard.dataset.expanded === 'true';
        if (expanded) {
          // collapse: remove dynamically added extra cards
          const extras = Array.from(parent.querySelectorAll('.home-card--extra'));
          extras.forEach((el) => el.remove());
          moreCard.dataset.expanded = 'false';
          moreCard.innerHTML = renderMoreLabel(false);
        } else {
          // expand: insert remaining cards before the moreCard and mark them as extra
          try {
            if (typeof sessions !== 'undefined' && sessions.length > 7) {
              for (let i = 7; i < sessions.length; i++) {
                const sess = sessions[i];
                const card = document.createElement('article');
                card.className = 'home-card home-card--extra';
                const title = this.escapeHtml(sess.topic || "未命名综述");
                const time = this.formatDate(sess.updated_at || sess.created_at);
                const paperCount = sess.paper_count || 0;
                const noteFlag = sess.note_size && sess.note_size > 0 ? '有笔记' : '无笔记';

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
                  window.location.href = `/app/console?sessionId=${encodeURIComponent(sess.session_id)}`;
                });

                const deleteBtn = document.createElement('button');
                deleteBtn.className = 'home-card-delete';
                deleteBtn.title = '删除';
                deleteBtn.innerHTML = '<i class="fa-solid fa-trash"></i>';
                deleteBtn.addEventListener('click', async (event) => {
                  event.stopPropagation();
                  event.preventDefault();
                  await this.deleteHomeSession(sess.session_id);
                });
                card.appendChild(deleteBtn);

                parent.insertBefore(card, moreCard);
              }
            }
                moreCard.dataset.expanded = 'true';
                moreCard.innerHTML = renderMoreLabel(true);
          } catch (e) {
            console.warn('无法展开更多历史：', e);
          }
        }
      });
          moreCard.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              moreCard.click();
            }
          });
      this.els.homeRail.appendChild(moreCard);
    }
  },

  async loadHomeStats() {
    const statsGrid = document.getElementById("statsGrid");
    if (!statsGrid) return;

    statsGrid.innerHTML = '<div class="stats-loading">加载中...</div>';
    try {
      const response = await fetch("/api/stats");
      if (!response.ok) throw new Error("API error");
      const stats = await response.json();
      this.renderHomeStats(stats);
    } catch (error) {
      statsGrid.innerHTML = '<div class="stats-loading">暂时无法加载工作台概览。</div>';
      const timelineBox = document.getElementById("timelineBox");
      if (timelineBox) timelineBox.innerHTML = '<div class="timeline-empty">暂时无法加载最近活动。</div>';
    }
  },

  renderHomeStats(stats) {
    const statsGrid = document.getElementById("statsGrid");
    if (!statsGrid) return;

    const stateBreakdown = stats.state_breakdown || {};
    const stateColors = {
      "规划中": "var(--muted)",
      "关键词已确认": "var(--muted)",
      "搜索中": "var(--warning)",
      "搜索完成": "var(--warning)",
      "笔记审核中": "var(--accent)",
      "撰写中": "var(--accent)",
      "初稿评审中": "var(--accent)",
      "已完成": "var(--success)",
    };

    // 生成状态标签
    let breakdownTags = "";
    for (const [label, count] of Object.entries(stateBreakdown)) {
      const color = stateColors[label] || "var(--muted)";
      breakdownTags += `<span class="stats-tag"><span class="stats-tag-dot" style="background:${color}"></span>${this.escapeHtml(label)} ${count}</span>`;
    }

    // 最近活动
    let recentHtml = "";
    if (stats.recent_activity) {
      const ra = stats.recent_activity;
      const timeAgo = this.timeAgo(ra.time);
      recentHtml = `
        <div class="stats-recent">
          <i class="fa-solid fa-clock"></i>
          <span>最近活跃 · ${this.escapeHtml(ra.topic || "未命名")} · ${timeAgo}</span>
          <span class="stats-recent-link" onclick="window.location.href='/app/console?sessionId=${encodeURIComponent(ra.session_id || '')}'">进入 <i class="fa-solid fa-arrow-right"></i></span>
        </div>`;
    }

    statsGrid.innerHTML = `
      <div class="stats-card">
        <span class="stats-card-icon"><i class="fa-solid fa-file-lines"></i></span>
        <span class="stats-card-value">${stats.total_sessions || 0}</span>
        <span class="stats-card-label">综述项目</span>
      </div>
      <div class="stats-card">
        <span class="stats-card-icon"><i class="fa-solid fa-book-open"></i></span>
        <span class="stats-card-value">${stats.total_papers || 0}</span>
        <span class="stats-card-label">收录论文</span>
      </div>
      <div class="stats-card">
        <span class="stats-card-icon"><i class="fa-solid fa-note-sticky"></i></span>
        <span class="stats-card-value">${stats.total_notes || 0}</span>
        <span class="stats-card-label">撰写笔记</span>
      </div>
      <div class="stats-card">
        <span class="stats-card-icon"><i class="fa-solid fa-pen-to-square"></i></span>
        <span class="stats-card-value">${stats.total_reviews || 0}</span>
        <span class="stats-card-label">完成综述</span>
      </div>
      <div class="stats-breakdown">
        <div class="stats-breakdown-title">状态分布</div>
        <div class="stats-breakdown-tags">
          ${breakdownTags || '<span class="stats-tag">暂无数据</span>'}
        </div>
      </div>
      ${recentHtml}
    `;

    this.renderHomeTimeline(stats);
  },

  renderHomeTimeline(stats) {
    const timelineBox = document.getElementById("timelineBox");
    if (!timelineBox) return;

    const activities = stats.recent_activities || [];
    if (activities.length === 0) {
      timelineBox.innerHTML = '<div class="timeline-empty">暂无活动记录</div>';
      return;
    }

    const stateDisplay = {
      "planning": { label: "规划中", icon: "fa-lightbulb" },
      "plan_confirmed": { label: "关键词已确认", icon: "fa-check-circle" },
      "searching": { label: "搜索中", icon: "fa-magnifying-glass" },
      "search_complete": { label: "搜索完成", icon: "fa-check-double" },
      "search_partial": { label: "检索部分完成", icon: "fa-triangle-exclamation" },
      "search_failed": { label: "检索失败", icon: "fa-circle-xmark" },
      "reviewing_notes": { label: "笔记审核", icon: "fa-clipboard-check" },
      "writing": { label: "撰写中", icon: "fa-pen-fancy" },
      "reviewing_draft": { label: "评审中", icon: "fa-comments" },
      "complete": { label: "已完成", icon: "fa-circle-check" },
    };

    let itemsHtml = "";
    for (const act of activities) {
      const disp = stateDisplay[act.state] || { label: act.state_label || act.state, icon: "fa-circle" };
      const timeAgo = this.timeAgo(act.time);
      const topic = this.escapeHtml(act.topic || "未命名综述");
      const pc = act.paper_count || 0;
      const sid = encodeURIComponent(act.session_id || "");

      itemsHtml += `
        <div class="timeline-item" onclick="window.location.href='/app/console?sessionId=${sid}'" role="button" tabindex="0">
          <span class="timeline-dot ${act.state}"></span>
          <div class="timeline-body">
            <span class="timeline-topic" title="${topic}">${topic}</span>
            <span class="timeline-meta">
              <span class="timeline-badge"><i class="fa-solid ${disp.icon}"></i> ${disp.label}</span>
              <span class="timeline-papers">${pc} 篇论文</span>
              <span>· ${timeAgo}</span>
            </span>
          </div>
        </div>`;
    }

    timelineBox.innerHTML = `
      <div class="timeline-title">最近活动</div>
      <div class="timeline-list">${itemsHtml}</div>
    `;
  },

  timeAgo(dateStr) {
    if (!dateStr) return "";
    const now = new Date();
    const then = new Date(dateStr);
    const diffMs = now - then;
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return "刚刚";
    if (diffMin < 60) return `${diffMin} 分钟前`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr} 小时前`;
    const diffDay = Math.floor(diffHr / 24);
    if (diffDay < 30) return `${diffDay} 天前`;
    const diffMon = Math.floor(diffDay / 30);
    return `${diffMon} 月前`;
  },

  openTopicModal() {
    if (!this.els.topicModal) return;
    this._topicModalReturnFocus = document.activeElement;
    this.els.topicModal.classList.add("active");
    this.els.topicModal.setAttribute("aria-hidden", "false");
    if (this.els.topicInput) {
      this.els.topicInput.value = "";
      this.els.topicInput.focus();
    }
    if (this.els.keywordInput) {
      // 仅隐藏，不删除：该字段仍被会话创建、规划回填和历史兼容链路使用，直接移除容易引发连锁回归。
      this.els.keywordInput.value = "";
    }
    this.renderHomeKeywordPlan([]);
    this.syncKeywordPlanHint();
    const advanced = document.getElementById("createAdvancedSettings");
    if (advanced) advanced.open = false;
    // 加载 Skills 选择器选项
    this.loadHomeSkillSelectors();
  },

  closeTopicModal() {
    if (this.els.topicModal) {
      this.els.topicModal.classList.remove("active");
      this.els.topicModal.setAttribute("aria-hidden", "true");
    }
    if (this._topicModalReturnFocus && typeof this._topicModalReturnFocus.focus === "function") this._topicModalReturnFocus.focus();
  },

  async createTopicFromModal() {
    const topic = (this.els.topicInput?.value || "").trim();
    const keywords = this.collectHomeKeywords();
    const skills = this.collectSelectedSkills ? this.collectSelectedSkills() : {};
    if (!topic) {
      alert("请输入主题");
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
        body: JSON.stringify({ topic, keywords, skills }),
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

      this.trackProductEvent("project_created");

      window.location.href = `/app/console?sessionId=${encodeURIComponent(data.session_id)}`;
    } catch (error) {
      alert(`创建失败：${error.message}`);
    } finally {
      const createBtn = this.els.topicSubmit;
      if (createBtn) {
        createBtn.disabled = false;
        createBtn.innerHTML = '<i class="fa-solid fa-arrow-right"></i> 创建研究';
      }
    }
  },

  trackProductEvent(name) {
    const safeEvents = new Set(["project_created", "first_search_completed", "first_review_generated", "provider_test_succeeded"]);
    if (!safeEvents.has(name)) return;
    if (window.va && typeof window.va.track === "function") window.va.track(name);
    window.dispatchEvent(new CustomEvent("academic-product-event", { detail: { name } }));
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

  async generateHomeKeywordPlan() {
    const topic = (this.els.topicInput?.value || "").trim();
    if (!topic) {
      alert("请先输入主题");
      return;
    }
    const seed = this.els.keywordInput?.value || "";
    const generateBtn = this.els.keywordPlanGenerate;
    const originalBtnHtml = generateBtn?.innerHTML || "";
    try {
      if (generateBtn) {
        generateBtn.disabled = true;
        generateBtn.textContent = "关键词生成中...";
      }
      const res = await fetch("/api/keywords/extract", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(this.withProvider({ topic })),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "提取失败");
      const keywords = Array.isArray(data.keywords) ? data.keywords : [];
      // 如果用户在种子输入框中也提供了词，追加到 AI 返回的结果后面
      if (seed.trim()) {
        const seeds = seed.split(/[，,;\n]/).map(s => s.trim()).filter(Boolean);
        seeds.forEach(s => keywords.push({ original: s, english: "", synonyms: "" }));
      }
      this.renderHomeKeywordPlan(keywords);
    } catch (e) {
      alert("关键词生成失败：" + e.message);
    } finally {
      if (generateBtn) {
        generateBtn.disabled = false;
        generateBtn.innerHTML = originalBtnHtml || '<i class="fa-solid fa-wand-magic-sparkles"></i> 生成规划';
      }
    }
  },

  syncKeywordPlanHint() {
    if (!this.els.homeKeywordList) return;
    const hasRows = this.els.homeKeywordList.querySelectorAll(".keyword-plan-row").length > 0;
    if (hasRows) return;
    const topic = (this.els.topicInput?.value || "").trim();
    const seeds = this.normalizeSeedKeywords(this.els.keywordInput?.value || "");
    if (topic && seeds.length) {
      // 自动触发关键词提取
      this.generateHomeKeywordPlan();
    }
  },

  async initConsole() {
    this.bindConsoleActions();
    this.setMobileWorkspacePanel("sources");
    this.updateChatPlaceholder();
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
    this.els.searchTargetInput?.addEventListener("input", (event) => {
      const value = Number(event.target.value);
      const valid = Number.isInteger(value) && value >= 1 && value <= 15;
      event.target.setCustomValidity(valid ? "" : "请输入 1 到 15 之间的整数");
      if (valid) this.updateSearchLoopRecommendation(!this.state._searchLoopCustomized);
    });
    this.els.searchLoopLimitInput?.addEventListener("input", (event) => {
      this.state._searchLoopCustomized = true;
      const value = Number(event.target.value);
      const valid = Number.isInteger(value) && value >= 1 && value <= 80;
      event.target.setCustomValidity(valid ? "" : "请输入 1 到 80 之间的整数");
      this.updateSearchLoopRecommendation(false);
    });
    this.els.cancelSearchBtn?.addEventListener("click", () => this.cancelSearch());
    this.els.autoRunBtn?.addEventListener("click", () => this.startAutoRun());
    this.els.apiConfigBtn?.addEventListener("click", () => { window.location.href = "/app/profile#api"; });
    this.els.apiConfigClose?.addEventListener("click", () => this.closeApiConfigModal());
    this.els.apiConfigSave?.addEventListener("click", () => this.saveApiConfig());
    this.els.apiConfigClear?.addEventListener("click", () => this.clearApiConfig());
    this.els.addPaperBtn?.addEventListener("click", () => this.openAddPaperModal());
    this.els.pdfFileInput?.addEventListener("change", (e) => this.handleDropZoneFile(e.target.files[0]));
    this.els.notesBtn?.addEventListener("click", () => this.generateNotesAction());
    this.els.reviewBtn?.addEventListener("click", () => this.generateReviewAction());
    this.els.viewSummary?.addEventListener("click", () => this.switchViewMode("summary"));
    this.els.viewReport?.addEventListener("click", () => this.switchViewMode("report"));
    this.els.viewReview?.addEventListener("click", () => this.switchViewMode("review"));
    this.els.viewPDF?.addEventListener("click", () => this.switchViewMode("pdf"));
    this.els.viewAnalysis?.addEventListener("click", () => this.switchViewMode("analysis"));
    this.els.viewTrace?.addEventListener("click", () => this.switchViewMode("trace"));
    this.els.chatSend?.addEventListener("click", () => this.sendChatMessage());
    this.els.chatModeToggle?.addEventListener("click", () => this.toggleChatMode());
    this.els.chatInput?.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        this.sendChatMessage();
      }
    });
    document.querySelectorAll("[data-mobile-panel]").forEach((button) => {
      button.addEventListener("click", () => this.setMobileWorkspacePanel(button.dataset.mobilePanel));
    });
    this.updateSearchLoopRecommendation(true);
    this.els.statusRetry?.addEventListener("click", () => this.retryLastAction());
    this.els.exportArtifactsBtn?.addEventListener("click", () => this.openExportModal());
    this.els.exportModalClose?.addEventListener("click", () => this.closeExportModal());
    document.querySelectorAll("[data-export-format]").forEach((button) => {
      button.addEventListener("click", () => this.downloadArtifact(button.dataset.exportFormat));
    });
    this.els.githubExportSubmit?.addEventListener("click", () => this.exportArtifactToGitHub());
    this.els.researchRepoBtn?.addEventListener("click", () => this.openRepositoryResearch());
    document.getElementById("repositoryModalClose")?.addEventListener("click", () => this.closeRepositoryResearch());
    document.getElementById("repositoryModalCancel")?.addEventListener("click", () => this.closeRepositoryResearch());
    document.getElementById("repositoryResearchSubmit")?.addEventListener("click", () => this.runRepositoryResearch());
    document.querySelectorAll("[data-repo-mode]").forEach((button) => {
      button.addEventListener("click", () => this.setRepositoryMode(button.dataset.repoMode));
    });
    this.initPaperListScroll();

    this.els.keywordConfirm?.addEventListener("click", () => this.confirmKeywords());
    this.els.keywordCancel?.addEventListener("click", () => this.closeKeywordModal());
    this.els.keywordAdd?.addEventListener("click", () => this.addKeywordRow());

    // 工具管理
    this.els.toolManagerBtn?.addEventListener("click", () => this.openToolManager());
    this.els.toolManagerClose?.addEventListener("click", () => this.closeToolManager());
    this.els.toolManagerClose2?.addEventListener("click", () => this.closeToolManager());
    this.els.toolManagerSave?.addEventListener("click", () => this.saveToolConfig());
    this.els.toolResetBtn?.addEventListener("click", () => this.resetToolConfig());

    // 初始化对话助手拖拽缩放
    this.initChatResize();
  },

  initPaperListScroll() {
    const list = this.els.paperList;
    const track = this.els.paperScrollTrack;
    const thumb = this.els.paperScrollThumb;
    if (!list || !track || !thumb) return;

    list.addEventListener("scroll", () => this.updatePaperScrollbar(), { passive: true });
    track.addEventListener("pointerdown", (event) => {
      if (event.target !== track) return;
      const rect = track.getBoundingClientRect();
      const thumbHeight = thumb.getBoundingClientRect().height;
      const travel = Math.max(1, rect.height - thumbHeight);
      const ratio = Math.max(0, Math.min(1, (event.clientY - rect.top - thumbHeight / 2) / travel));
      list.scrollTop = ratio * Math.max(0, list.scrollHeight - list.clientHeight);
    });
    thumb.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      event.stopPropagation();
      this._paperScrollDrag = { startY: event.clientY, startScrollTop: list.scrollTop };
      thumb.classList.add("dragging");
      thumb.setPointerCapture(event.pointerId);
    });
    thumb.addEventListener("pointermove", (event) => {
      if (!this._paperScrollDrag) return;
      const maxScroll = Math.max(0, list.scrollHeight - list.clientHeight);
      const travel = Math.max(1, track.clientHeight - thumb.clientHeight);
      list.scrollTop = this._paperScrollDrag.startScrollTop + (event.clientY - this._paperScrollDrag.startY) * maxScroll / travel;
    });
    const stopDragging = (event) => {
      if (!this._paperScrollDrag) return;
      this._paperScrollDrag = null;
      thumb.classList.remove("dragging");
      if (thumb.hasPointerCapture(event.pointerId)) thumb.releasePointerCapture(event.pointerId);
    };
    thumb.addEventListener("pointerup", stopDragging);
    thumb.addEventListener("pointercancel", stopDragging);
    if (window.ResizeObserver) {
      this._paperListResizeObserver = new ResizeObserver(() => this.updatePaperScrollbar());
      this._paperListResizeObserver.observe(list);
    }
    this.updatePaperScrollbar();
  },

  updatePaperScrollbar() {
    const list = this.els.paperList;
    const track = this.els.paperScrollTrack;
    const thumb = this.els.paperScrollThumb;
    if (!list || !track || !thumb) return;
    const maxScroll = Math.max(0, list.scrollHeight - list.clientHeight);
    track.hidden = maxScroll <= 1;
    if (track.hidden) return;
    const trackHeight = track.clientHeight;
    const thumbHeight = Math.max(44, Math.round(trackHeight * list.clientHeight / list.scrollHeight));
    const travel = Math.max(0, trackHeight - thumbHeight);
    const offset = maxScroll ? Math.round(travel * list.scrollTop / maxScroll) : 0;
    thumb.style.height = `${thumbHeight}px`;
    thumb.style.transform = `translateY(${offset}px)`;
  },

  setMobileWorkspacePanel(panel) {
    const safePanel = ["sources", "content", "chat"].includes(panel) ? panel : "sources";
    document.body.dataset.mobileView = safePanel;
    document.querySelectorAll("[data-mobile-panel]").forEach((button) => {
      const active = button.dataset.mobilePanel === safePanel;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  },

  retryLastAction() {
    const action = this.state.lastAction;
    if (action === "auto") return this.startAutoRun();
    if (action === "notes") return this.generateNotesAction();
    if (action === "review") return this.generateReviewAction();
    return this.runSearchPhase();
  },

  initChatResize() {
    const resizeHandle = document.getElementById("resizeHandle");
    const chatDock = document.querySelector(".chat-dock");
    if (!resizeHandle || !chatDock) return;

    let isResizing = false;
    let startY = 0;
    let startHeight = 0;

    resizeHandle.addEventListener("mousedown", (e) => {
      isResizing = true;
      startY = e.clientY;
      startHeight = chatDock.getBoundingClientRect().height;
      resizeHandle.classList.add("active");
      document.body.style.cursor = "row-resize";
      e.preventDefault();
    });

    document.addEventListener("mousemove", (e) => {
      if (!isResizing) return;
      const dy = startY - e.clientY;
      const newHeight = startHeight + dy;
      if (newHeight >= 160 && newHeight <= window.innerHeight * 0.8) {
        chatDock.style.height = `${newHeight}px`;
      }
    });

    document.addEventListener("mouseup", () => {
      if (isResizing) {
        isResizing = false;
        resizeHandle.classList.remove("active");
        document.body.style.cursor = "";
      }
    });
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
      
      // 初始化多会话聊天
      this.state.conversations = session.conversations || [];
      // 如果没有会话则自动创建一个默认的
      if (!this.state.conversations.length) {
        await this.createConversation("默认对话");
      }
      // 恢复或设置当前会话
      if (!this.state.currentConvId || !this.state.conversations.find(c => c.conv_id === this.state.currentConvId)) {
        this.state.currentConvId = this.state.conversations[0]?.conv_id || null;
      }
      // 加载当前会话的聊天历史
      await this.loadCurrentConversation();

      // Preserve the currentPaperId if it still exists in the refreshed session's papers
      const prevPaperId = this.state.currentPaperId;
      const paperExists = prevPaperId && session.papers?.some(p => p.paper_id === prevPaperId);
      this.state.currentPaperId = paperExists ? prevPaperId : (session.papers?.[0]?.paper_id || null);

      // 首次加载时渲染 tabs（含用量条），后续轮询通过 updateContextMeter 静默更新
      this.renderChatTabs();
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
      this.els.detailContent.innerHTML = '<div class="empty-state empty-state--action"><i class="fa-solid fa-lightbulb"></i><strong>从一个研究问题开始</strong><span>创建项目后，这里会显示论文摘要、笔记和 PDF 原文。</span><a class="primary-btn" href="/app">返回工作台新建研究</a></div>';
    }
    if (this.els.paperList) {
      this.els.paperList.innerHTML = '<div class="empty-state">还没有打开研究项目。</div>';
    }
    [this.els.searchBtn, this.els.addPaperBtn, this.els.autoRunBtn, this.els.notesBtn, this.els.reviewBtn, this.els.chatInput, this.els.chatSend, this.els.researchRepoBtn, this.els.exportArtifactsBtn].forEach((element) => {
      if (element) element.disabled = true;
    });
  },

  renderConsoleSession() {
    const session = this.state.currentSession;
    if (!session) return;

    if (this.els.consoleTopic) {
      this.els.consoleTopic.textContent = session.topic || "未命名主题";
    }

    const statusLabel = session.state === "searching"
      ? `正在检索论文 · 已发现 ${(session.papers || []).length} 篇`
      : (session.state_label || session.state || "就绪");
    this.setConsoleStatus(session.state, statusLabel);
    this.updateResearchStage(session);
    this.renderPaperList();
    this.renderNotesBlock();
    this.renderReviewBlock();
    this.renderRepositorySources();
    this.renderDetailPanel();
    this.renderChatContext();
    this.updateChatPlaceholder();
    this.updateActionButtons();
    this.renderViewButtons();
    // 静默更新用量条（不重建 DOM）
    this.updateContextMeter();
  },

  updateResearchStage(session) {
    if (!this.els.researchStages || !session) return;
    const papers = session.papers || [];
    const hasPapers = papers.length > 0;
    const hasAccepted = papers.some((paper) => paper.status === "accepted");
    const hasNotes = papers.some((paper) => paper.has_notes || String(paper.notes || "").trim());
    const hasAnalysis = !!(session.analysis && Object.keys(session.analysis).length);
    const hasReview = !!String(session.draft || "").trim();
    const order = ["question", "search", "screen", "read", "analysis", "review"];
    let activeIndex = 0;
    if (session.state === "searching") activeIndex = 1;
    else if (hasPapers) activeIndex = 2;
    if (hasAccepted || hasNotes) activeIndex = 3;
    if (hasAnalysis || ["analysis", "writing", "reviewing_draft", "complete"].includes(session.state)) activeIndex = 4;
    if (hasReview || session.state === "complete") activeIndex = 5;
    this.els.researchStages.querySelectorAll("[data-stage]").forEach((item) => {
      const index = order.indexOf(item.dataset.stage);
      item.classList.toggle("active", index === activeIndex);
      item.classList.toggle("complete", index < activeIndex || (index === 5 && hasReview));
      if (index === activeIndex) item.setAttribute("aria-current", "step");
      else item.removeAttribute("aria-current");
    });
  },

  displaySource(value, sourceType) {
    const key = String(value || sourceType || "").toLowerCase();
    const labels = {
      agent_search: "AI 检索",
      arxiv: "arXiv",
      pdf: "上传 PDF",
      paper: "学术论文",
      manual: "手动添加",
      semantic_scholar: "Semantic Scholar",
      openalex: "OpenAlex",
    };
    return labels[key] || value || sourceType || "来源待确认";
  },

  displayPaperStatus(status) {
    const labels = { accepted: "已纳入", rejected: "已排除", pending: "等待判断" };
    return labels[String(status || "pending").toLowerCase()] || "等待判断";
  },

  displayResearchState(state, label) {
    const labels = {
      planning: "准备研究问题",
      plan_confirmed: "检索词已确认",
      searching: "正在检索论文",
      search_complete: "等待筛选论文",
      search_partial: "检索部分完成，可继续检索",
      search_failed: "本轮未新增论文，请重试",
      reviewing_notes: "正在整理笔记",
      analysis: "正在综合分析",
      writing: "正在生成综述",
      reviewing_draft: "综述初稿已生成",
      complete: "研究已完成",
      failed: "任务失败",
      error: "发生错误",
    };
    return label && label !== state ? label : (labels[state] || "就绪");
  },

  setConsoleStatus(state, label) {
    const displayLabel = this.displayResearchState(state, label);
    if (this.els.consoleState) {
      this.els.consoleState.textContent = displayLabel;
    }
    const statusHint = document.getElementById("statusHint");
    if (statusHint && displayLabel) statusHint.textContent = displayLabel;
    if (this.els.statusRetry) this.els.statusRetry.hidden = !["error", "failed", "search_partial", "search_failed"].includes(state);
    if (this.state.currentSession) this.updateResearchStage({ ...this.state.currentSession, state });
    if (!this.els.consoleStateDot) return;

    const map = {
      planning: "warn",
      plan_confirmed: "live",
      searching: "live",
      search_complete: "ok",
      search_partial: "warn",
      search_failed: "err",
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
        ? `<i class="fa-solid fa-check"></i> ${papers.length} 篇（${acceptedCount} 已纳入，${hasNotesCount} 有笔记）`
        : `<i class="fa-solid fa-check"></i> ${papers.length} 篇（${hasNotesCount} 有笔记）`;
    }

    if (!papers.length) {
      this.els.paperList.innerHTML = '<div class="empty-state">点击「搜索相关论文」或「添加论文」开始构建来源库。</div>';
      requestAnimationFrame(() => this.updatePaperScrollbar());
      return;
    }

    this.els.paperList.innerHTML = "";
    papers.forEach((paper) => {
      // 直接使用后端 per-paper 字段
      paper._hasNotes = paper.has_notes === true || Boolean((paper.notes || "").trim());
      var sessionRef = this.state.currentSession || {};
      var referencedPapers = sessionRef.review_referenced_papers || [];
      paper._hasReview = referencedPapers.indexOf(paper.paper_id) >= 0;

      const row = document.createElement("article");
      const isUpdating = this.state._updatingPaperId === paper.paper_id;
      row.setAttribute("role", "listitem");
      row.dataset.paperId = paper.paper_id;
      row.className = `paper-row ${paper.paper_id === this.state.currentPaperId ? "active" : ""} ${isUpdating ? "is-updating" : ""}`;
      row.addEventListener("click", () => {
        this.state.currentPaperId = paper.paper_id;
        this.renderPaperList();
        this.renderDetailPanel();
        this.renderChatContext();
        this.renderViewButtons();
        this.setMobileWorkspacePanel("content");
      });

      const title = paper.title || paper.paper_id || "未命名论文";
      const sourceLabel = this.displaySource(paper.source, paper.source_type);
      const authorLine = paper.authors || sourceLabel;
      const abstractPreview = (paper.abstract || "").slice(0, 80) + (paper.abstract && paper.abstract.length > 80 ? "..." : "");
      
      const statusIcon = paper._hasNotes
        ? '<span class="chip ok" title="已生成笔记"><i class="fa-solid fa-check-circle"></i> 有笔记</span>'
        : '<span class="chip warn" title="未生成笔记"><i class="fa-regular fa-circle"></i> 无笔记</span>';
      const reviewIcon = paper._hasReview
        ? '<span class="chip ok" title="已纳入综述"><i class="fa-solid fa-check-circle"></i> 已纳入综述</span>'
        : '';
      const decisionIcon = paper.status === "rejected"
        ? '<span class="chip" title="已标记为不纳入"><i class="fa-solid fa-ban"></i> 已排除</span>'
        : '';
      const selectedClass = paper.status === "accepted" ? "accepted" : "";

      row.innerHTML = `
        <div class="paper-main">
          <h4>${this.escapeHtml(title)}</h4>
          <p>${this.escapeHtml(abstractPreview || authorLine)}</p>
          <div class="paper-meta">
            <span class="chip"><i class="fa-regular fa-circle-dot"></i> ${this.escapeHtml(sourceLabel)}</span>
            ${statusIcon}
            ${reviewIcon}
            ${decisionIcon}
            ${paper.added_at ? `<span class="chip"><i class="fa-regular fa-clock"></i> ${this.formatDate(paper.added_at)}</span>` : ""}
          </div>
        </div>
        <div class="paper-actions">
          <button class="paper-include-btn ${selectedClass}" data-action="accept" ${isUpdating ? "disabled" : ""} aria-pressed="${paper.status === 'accepted'}" aria-label="${paper.status === 'accepted' ? '从综述中移除' : '纳入综述'}">${isUpdating ? '<i class="fa-solid fa-circle-notch fa-spin"></i><span>保存中</span>' : `<i class="fa-solid fa-check"></i><span>${paper.status === 'accepted' ? '已纳入' : '纳入综述'}</span>`}</button>
          <details class="paper-more-menu">
            <summary class="mini-btn" aria-label="打开论文操作菜单"><i class="fa-solid fa-ellipsis-vertical"></i></summary>
            <div>
              <button type="button" data-action="reject"><i class="fa-solid fa-ban"></i> 标记为不纳入</button>
              <button type="button" class="danger" data-action="remove"><i class="fa-solid fa-trash"></i> 从项目移除</button>
            </div>
          </details>
        </div>
      `;

      row.querySelector(".paper-more-menu")?.addEventListener("click", (event) => event.stopPropagation());

      row.querySelector('[data-action="remove"]')?.addEventListener("click", async (event) => {
        event.stopPropagation();
        await this.removePaper(paper.paper_id);
      });

      row.querySelector('[data-action="accept"]')?.addEventListener("click", async (event) => {
        event.stopPropagation();
        await this.setPaperStatus(paper.paper_id, paper.status === "accepted" ? "pending" : "accepted");
      });

      row.querySelector('[data-action="reject"]')?.addEventListener("click", async (event) => {
        event.stopPropagation();
        await this.setPaperStatus(paper.paper_id, "rejected");
      });

      this.els.paperList.appendChild(row);
    });
    requestAnimationFrame(() => this.updatePaperScrollbar());
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
    const quality = this.state.currentSession?.review_quality || {};

    if (hasDraft) {
      const outputFile = this.state.currentSessionId;
      // 有综述 → 显示标题 + 收藏按钮
      this.els.reviewBlock.innerHTML = `
        <div class="panel-block-head">
          <strong>📝 综述</strong>
          <span class="chip ok"><i class="fa-solid fa-check-circle"></i> 已生成</span>
        </div>
        <div class="review-title-link" id="reviewTitleLink" style="cursor:pointer;padding:10px 0;border:1px solid var(--line);border-radius:12px;padding:14px;">
          <h4 style="margin:0;font-size:0.95rem;color:var(--accent);">${this.escapeHtml(topic)}</h4>
          <span style="font-size:0.82rem;color:var(--subtle);">点击查看完整综述 →</span>
        </div>
        <div style="margin-top:8px;" id="favBtnArea"></div>
        ${quality.score !== undefined ? `<div class="review-quality"><i class="fa-solid fa-shield-halved"></i><span class="quality-score">证据质量 ${this.escapeHtml(String(quality.score))}/100</span><span>引用覆盖 ${this.escapeHtml(String(Math.round((quality.citation_coverage || 0) * 100)))}%</span></div>` : ""}
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
    const isPerSession = this.state.currentViewMode === "review" || this.state.currentViewMode === "trace" || this.state.currentViewMode === "analysis";
    const selectedLabel = isPerSession
      ? (session.topic || "未命名主题")
      : (paper ? paper.title || paper.paper_id : "未选择论文");

    if (this.els.detailTitle) {
      this.els.detailTitle.textContent = selectedLabel;
    }
    if (this.els.detailMeta) {
      const modeLabel = this.viewModeLabel(this.state.currentViewMode);
      if (isPerSession) {
        this.els.detailMeta.textContent = `${paperCount} 个来源 · ${modeLabel} · ${this.displayResearchState(session.state, session.state_label)}`;
      } else {
        this.els.detailMeta.textContent = `${paperCount} 个来源 · ${modeLabel} · ${this.displayResearchState(session.state, session.state_label)}`;
      }
    }

    let html = "";
    if (this.state.currentViewMode === "summary") {
      html = this.renderPaperSummary(paper, session);
    } else if (this.state.currentViewMode === "report") {
      html = this.renderPaperReport(paper, session);
    } else if (this.state.currentViewMode === "trace") {
      html = this.renderTraceView(session);
    } else if (this.state.currentViewMode === "pdf") {
      html = this.renderPDFView(paper, session);
    } else if (this.state.currentViewMode === "analysis") {
      html = this.renderAnalysisView(session);
    } else {
      html = this.renderReviewView(session);
    }

    this.els.detailContent.classList.toggle("pdf-mode", this.state.currentViewMode === "pdf");
    if (this.state.currentViewMode !== "pdf") {
      this.releasePDFObjectUrl();
    }
    this.els.detailContent.innerHTML = html;
    if (this.state.currentViewMode === "pdf" && paper) {
      this.loadPDFPreview(paper, session);
    }
  },

  renderPaperSummary(paper, session) {
    if (!paper) {
      return '<div class="empty-state">请先在左侧选择一篇论文。</div>';
    }

    const pid = paper.paper_id || "";
    const sessionNotes = session.notes || "";

    // 从 session.notes（draft_notes.md）中用论文 id 提取对应的整段 Markdown
    let sectionMd = String(paper.notes || "").trim();
    if (!sectionMd && pid && sessionNotes) {
      // 按「论文id:」分割，找到匹配 pid 的那一段
      const blocks = sessionNotes.split(/\n(?=论文id:)/);
      for (const block of blocks) {
        if (block.includes(`论文id: ${pid}`)) {
          // 去掉开头的「论文id: xxx」行，保留其余结构
          sectionMd = block.replace(/^论文id:\s*\S+\s*\n?/, '').trim();
          break;
        }
      }
    }

    const hasSection = Boolean(sectionMd);

    return `
      <div class="detail-hero">
        <span class="topic-badge"><i class="fa-regular fa-note-sticky"></i> 摘要</span>
        <h3>${this.escapeHtml(paper.title || paper.paper_id || "未命名论文")}</h3>
        <div class="lead">${this.escapeHtml(paper.authors || this.displaySource(paper.source, paper.source_type) || "该论文已加入当前研究项目")}</div>
      </div>
      <div class="detail-blocks" style="margin-top:16px;">
        <div class="panel-block">
          <div class="panel-block-head"><strong>调研笔记</strong><span class="chip">${hasSection ? '已整理' : '尚未生成'}</span></div>
          ${hasSection
            ? `<div class="markdown">${marked.parse(sectionMd)}</div>`
            : `<div class="plain-text">${this.escapeHtml(paper.abstract || "当前没有可用摘要。")}</div>`}
        </div>
        <div class="panel-block">
          <div class="panel-block-head"><strong>来源信息</strong><span class="chip">${this.displayPaperStatus(paper.status)}</span></div>
          <div class="plain-text">来源：${this.escapeHtml(this.displaySource(paper.source, paper.source_type))} · 添加时间：${this.escapeHtml(this.formatDate(paper.added_at))}</div>
        </div>
      </div>
    `;
  },

  renderPaperReport(paper, session) {
    const rawNotes = paper?.notes || session?.notes || "";
    const notes = typeof this.state.reportEditText === "string" && this.state.isEditingReport ? this.state.reportEditText : rawNotes;
    const hasPaperNotes = paper?._hasNotes;
    
    let contentHtml = "";
    if (this.state.isEditingReport) {
      contentHtml = `
        <div id="reportEditArea" style="display:none;">${this.escapeHtml(notes)}</div>
        <div style="display: flex; gap: 8px; justify-content: flex-end; margin-top: 8px;">
          <button class="secondary-btn" onclick="notebooklm.cancelEditReport()">取消</button>
          <button class="primary-btn" onclick="notebooklm.saveEditReport()">保存</button>
        </div>
      `;
    } else {
      contentHtml = notes.trim() ? `<div class="markdown">${marked.parse(notes)}</div>` : '<div class="empty-state">该论文还没有研究笔记。请选中该论文后点击左侧「生成笔记」按钮。</div>';
    }

    const editBtnHtml = hasPaperNotes && !this.state.isEditingReport ? `<button class="secondary-btn" title="编辑笔记" onclick="notebooklm.startEditReport()"><i class="fa-solid fa-pen" style="margin-right:4px;"></i>编辑笔记</button>` : "";

    return `
      <div class="detail-hero">
        <span class="topic-badge"><i class="fa-solid fa-note-sticky"></i> 调研笔记</span>
        <h3>${this.escapeHtml(paper?.title || paper?.paper_id || session?.topic || "调研笔记")}</h3>
        <div class="lead">${hasPaperNotes ? '这是该论文的研究笔记，由 AI 自动生成。' : '该论文尚未生成笔记，请选中后点击左侧「生成笔记」。'}</div>
      </div>
      <div class="panel-block" style="margin-top:16px;">
        <div class="panel-block-head">
          <div style="display:flex; align-items:center; gap:8px;">
            <strong>${hasPaperNotes ? '研究笔记' : '报告内容'}</strong>
            <span class="chip">${hasPaperNotes ? 'AI生成' : '待生成'}</span>
          </div>
          ${editBtnHtml}
        </div>
        ${contentHtml}
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
    
    // 如果处于编辑态，则使用编辑中的内容
    const editContent = typeof this.state.reviewEditText === "string" && this.state.isEditingReview ? this.state.reviewEditText : draft;
    const acceptedCount = (session?.papers || []).filter((paper) => paper.status === "accepted").length;
    const hasDraft = Boolean(draft.trim());

    let contentHtml = "";
    if (this.state.isEditingReview) {
      contentHtml = `
        <div id="reviewEditArea" style="display:none;">${this.escapeHtml(editContent)}</div>
        <div style="display: flex; gap: 8px; justify-content: flex-end; margin-top: 8px;">
          <button class="secondary-btn" onclick="notebooklm.cancelEditReview()">取消</button>
          <button class="primary-btn" onclick="notebooklm.saveEditReview()">保存</button>
        </div>
      `;
    } else {
      contentHtml = editContent.trim() ? `<div class="markdown">${marked.parse(editContent)}</div>` : '<div class="empty-state">还没有综述草稿。</div>';
    }

    const editBtnHtml = hasDraft && !this.state.isEditingReview ? `<button class="secondary-btn" title="编辑综述" onclick="notebooklm.startEditReview()"><i class="fa-solid fa-pen" style="margin-right:4px;"></i>编辑综述</button>` : "";

    return `
      <div class="detail-hero">
        <span class="topic-badge"><i class="fa-solid fa-layer-group"></i> 综述</span>
        <h3>${this.escapeHtml(session.topic || "综合综述")}</h3>
        <div class="lead">该视图会结合已选论文和综述草稿给出回答，并允许你通过底部对话区提交修改意见，或者手动修改。</div>
      </div>
      <div class="detail-blocks" style="margin-top:16px;">
        <div class="panel-block">
          <div class="panel-block-head">
            <div style="display:flex; align-items:center; gap:8px;">
              <strong>综述草稿</strong>
              <span class="chip">${acceptedCount} 篇已选论文</span>
            </div>
            ${editBtnHtml}
          </div>
          ${contentHtml}
        </div>
      </div>
    `;
  },

  startEditReport() {
    const paper = this.getCurrentPaper();
    const session = this.state.currentSession;
    const rawNotes = paper?.notes || session?.notes || "";

    this.state.isEditingReport = true;
    this.state.reportEditText = rawNotes;
    this.renderDetailPanel();

    // 延迟初始化 Vditor（等 DOM 渲染完）
    setTimeout(() => this._initVditor("reportEditArea", rawNotes, "saveEditReport"), 50);
  },

  cancelEditReport() {
    this._destroyVditor("reportEditArea");
    this.state.isEditingReport = false;
    this.state.reportEditText = "";
    this.renderDetailPanel();
  },

  async saveEditReport() {
    const vditor = this._vditors?.reportEditArea;
    const newNotes = vditor ? vditor.getValue() : "";
    const sessionId = this.state.currentSessionId;
    const paperId = this.state.currentPaperId;
    if (!sessionId) return;

    this.els.detailContent.innerHTML = '<div class="loading-state">保存中...</div>';

    try {
      const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/notes`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: newNotes, version_note: "User manual edit", paper_id: paperId }),
      });
      if (!response.ok) throw new Error("保存失败");

      this._destroyVditor("reportEditArea");
      await this.reloadCurrentSession();
      this.state.isEditingReport = false;
      this.state.reportEditText = "";
      this.renderDetailPanel();
    } catch (error) {
      alert(error.message);
      this.renderDetailPanel();
    }
  },

  startEditReview() {
    const session = this.state.currentSession;
    let draft = session?.draft || session?.notes || "";
    draft = draft.replace(/```markdown\s*\n([\s\S]*?)```/g, '$1');
    draft = draft.replace(/```markdown\s*\n([\s\S]*?)(\n---|\n## (?!##)|$)/, '$1$2');

    this.state.isEditingReview = true;
    this.state.reviewEditText = draft;
    this.renderDetailPanel();

    setTimeout(() => this._initVditor("reviewEditArea", draft, "saveEditReview"), 50);
  },

  cancelEditReview() {
    this._destroyVditor("reviewEditArea");
    this.state.isEditingReview = false;
    this.state.reviewEditText = "";
    this.renderDetailPanel();
  },

  async saveEditReview() {
    const vditor = this._vditors?.reviewEditArea;
    const newDraft = vditor ? vditor.getValue() : "";
    const sessionId = this.state.currentSessionId;
    if (!sessionId) return;

    this.els.detailContent.innerHTML = '<div class="loading-state">保存中...</div>';

    try {
      const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/draft`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: newDraft }),
      });
      if (!response.ok) throw new Error("保存失败");

      this._destroyVditor("reviewEditArea");
      await this.reloadCurrentSession();
      this.state.isEditingReview = false;
      this.state.reviewEditText = "";
      this.renderDetailPanel();
    } catch (error) {
      alert(error.message);
      this.renderDetailPanel();
    }
  },

  // ━━━ Vditor 初始化/销毁 ━━━
  _vditors: {},

  _initVditor(id, content, saveAction = "saveEditReport") {
    if (typeof Vditor === "undefined") return;
    this._destroyVditor(id);

    const el = document.getElementById(id);
    if (!el) return;
    el.style.display = "none";

    const wrapper = document.createElement("div");
    wrapper.className = "editor-container";
    wrapper.id = id + "_vditor";
    el.parentNode.insertBefore(wrapper, el);

    const isDark = document.body.dataset.theme === "dark";

    this._vditors[id] = new Vditor(wrapper, {
      height: Math.max(400, window.innerHeight * 0.45),
      mode: "ir",
      value: content,
      placeholder: "开始编辑...",
      theme: isDark ? "dark" : "classic",
      cdn: "https://cdn.jsdelivr.net/npm/vditor@3.10.6",
      toolbar: [
        "headings", "bold", "italic", "strike", "|",
        "list", "ordered-list", "check", "|",
        "quote", "code", "inline-code", "|",
        "undo", "redo", "|",
        { name: "save", tip: "保存 (Ctrl+S)", className: "right", icon: '<i class="fa-solid fa-floppy-disk"></i>', click: () => this[saveAction]?.() },
      ],
      cache: { enable: false },
      after: () => {
        wrapper.querySelector(".vditor-reset")?.setAttribute("spellcheck", "false");
        if (document.body.dataset.theme === "dark") {
          const irEl = wrapper.querySelector(".vditor-ir");
          if (irEl) irEl.style.color = "var(--text, #e8e8e8)";
        }
      },
    });
  },

  _destroyVditor(id) {
    if (this._vditors[id]) {
      try { this._vditors[id].destroy(); } catch(e) {}
      delete this._vditors[id];
    }
    const wrapper = document.getElementById(id + "_vditor");
    if (wrapper) wrapper.remove();
    const el = document.getElementById(id);
    if (el) el.style.display = "";
  },

  switchViewMode(mode) {
    // 切换视图前销毁编辑器
    this._destroyVditor("reportEditArea");
    this._destroyVditor("reviewEditArea");
    this.state.isEditingReport = false;
    this.state.isEditingReview = false;
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
      pdf: this.els.viewPDF,
      analysis: this.els.viewAnalysis,
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
      // - "PDF"：选中论文且有 paper_id 时才可用
      if (mode === "summary" || mode === "trace") {
        el.disabled = false;
      } else if (mode === "report") {
        el.disabled = !hasNotes;
      } else if (mode === "review") {
        el.disabled = !hasDraft;
      } else if (mode === "pdf") {
        el.disabled = !(paper && paper.paper_id);
      } else if (mode === "analysis") {
        el.disabled = false;
      }
    });
  },

  renderPDFView(paper, session) {
    if (!paper) {
      return `
        <div class="detail-hero">
          <span class="topic-badge"><i class="fa-solid fa-file-pdf"></i> PDF</span>
          <h3>PDF 预览</h3>
          <div class="lead">请先从左侧选择一篇论文查看其 PDF。</div>
        </div>
      `;
    }

    const paperId = paper.paper_id || "";
    return `
      <div class="detail-hero">
        <span class="topic-badge"><i class="fa-solid fa-file-pdf"></i> PDF</span>
        <h3>${this.escapeHtml(paper.title || paperId)}</h3>
        <div class="lead">${this.escapeHtml(paper.authors || "")}</div>
      </div>
      <div class="pdf-preview-shell panel-block">
        <div class="pdf-preview-state" id="pdfPreviewMount">
          <i class="fa-solid fa-circle-notch fa-spin"></i>
          <strong>正在安全加载 PDF…</strong>
          <span>正在从你的私有研究工作区读取文件</span>
        </div>
      </div>
      <div class="pdf-preview-actions">
        <span><i class="fa-solid fa-shield-halved"></i> PDF 通过登录凭证安全读取，不会公开文件地址。</span>
        <div>
          <button class="secondary-btn" id="pdfDownloadButton" type="button" disabled><i class="fa-solid fa-download"></i> 下载</button>
          <button class="secondary-btn" id="pdfOpenButton" type="button" disabled><i class="fa-solid fa-up-right-from-square"></i> 新窗口打开</button>
        </div>
      </div>
    `;
  },

  renderRepositorySources() {
    const section = document.getElementById("repositorySourcesSection");
    const list = this.els.repositoryList;
    if (!section || !list) return;
    const repositories = this.state.currentSession?.repositories || [];
    section.hidden = repositories.length === 0;
    const count = document.getElementById("repositoryCountChip");
    if (count) count.textContent = `${repositories.length} 个`;
    list.innerHTML = repositories.map((repo) => `
      <article class="repository-card">
        <a href="${this.escapeHtml(repo.html_url || "#")}" target="_blank" rel="noopener noreferrer"><i class="fa-brands fa-github"></i> ${this.escapeHtml(repo.full_name || "GitHub repository")}</a>
        <p>${this.escapeHtml(repo.description || "已作为研究证据加入当前项目")}</p>
      </article>
    `).join("");
  },

  pdfUrlForPaper(paper, session) {
    const paperId = String(paper?.paper_id || "");
    const sessionId = String(session?.session_id || "");
    const pdfFilename = String(paper?.pdf_filename || `${paperId}.pdf`);
    return sessionId
      ? `/api/agent/document/${encodeURIComponent(sessionId)}/papers/${encodeURIComponent(pdfFilename)}`
      : `/api/agent/document/${encodeURIComponent(paperId)}/papers/${encodeURIComponent(pdfFilename)}`;
  },

  releasePDFObjectUrl() {
    if (this._pdfObjectUrl) {
      URL.revokeObjectURL(this._pdfObjectUrl);
      this._pdfObjectUrl = null;
    }
  },

  async loadPDFPreview(paper, session) {
    const mount = document.getElementById("pdfPreviewMount");
    if (!mount) return;

    this.releasePDFObjectUrl();
    const loadToken = (this._pdfLoadToken || 0) + 1;
    this._pdfLoadToken = loadToken;
    const pdfUrl = this.pdfUrlForPaper(paper, session);
    try {
      const response = await fetch(pdfUrl);
      if (!response.ok) {
        let detail = "";
        try { detail = (await response.json()).detail || ""; } catch (_error) {}
        throw new Error(response.status === 404 ? "PDF 文件尚未下载或已经丢失。" : (detail || `PDF 请求失败（${response.status}）`));
      }
      const sourceBlob = await response.blob();
      if (!sourceBlob.size) throw new Error("PDF 文件为空。 ");
      const pdfBlob = sourceBlob.type === "application/pdf"
        ? sourceBlob
        : new Blob([sourceBlob], { type: "application/pdf" });
      const objectUrl = URL.createObjectURL(pdfBlob);

      if (this._pdfLoadToken !== loadToken || this.state.currentViewMode !== "pdf" || !mount.isConnected) {
        URL.revokeObjectURL(objectUrl);
        return;
      }
      this._pdfObjectUrl = objectUrl;
      const title = this.escapeHtml(paper.title || paper.paper_id || "论文 PDF");
      mount.className = "pdf-preview-state loaded";
      mount.innerHTML = `<iframe src="${objectUrl}" title="${title}" class="pdf-preview-frame"></iframe>`;

      const openButton = document.getElementById("pdfOpenButton");
      const downloadButton = document.getElementById("pdfDownloadButton");
      if (openButton) {
        openButton.disabled = false;
        openButton.addEventListener("click", () => window.open(objectUrl, "_blank", "noopener,noreferrer"));
      }
      if (downloadButton) {
        downloadButton.disabled = false;
        downloadButton.addEventListener("click", () => {
          const link = document.createElement("a");
          link.href = objectUrl;
          link.download = `${String(paper.title || paper.paper_id || "paper").replace(/[\\/:*?\"<>|]+/g, "_")}.pdf`;
          document.body.appendChild(link);
          link.click();
          link.remove();
        });
      }
    } catch (error) {
      if (this._pdfLoadToken !== loadToken || !mount.isConnected) return;
      mount.className = "pdf-preview-state error";
      mount.innerHTML = `
        <i class="fa-solid fa-file-circle-xmark"></i>
        <strong>无法显示这份 PDF</strong>
        <span>${this.escapeHtml(paper?.pdf_error || error?.message || "PDF 加载失败，请稍后重试。")}</span>
        <button class="secondary-btn" id="pdfRetryButton" type="button"><i class="fa-solid fa-cloud-arrow-down"></i> 重新获取 PDF</button>
      `;
      document.getElementById("pdfRetryButton")?.addEventListener("click", () => this.retryPaperPDF(paper, session));
    }
  },

  async retryPaperPDF(paper, session) {
    const mount = document.getElementById("pdfPreviewMount");
    const sessionId = String(session?.session_id || "");
    const paperId = String(paper?.paper_id || "");
    if (!mount || !sessionId || !paperId) return;
    mount.className = "pdf-preview-state";
    mount.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i><strong>正在重新寻找开放全文…</strong><span>依次检查 arXiv 与开放获取来源</span>';
    try {
      const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/papers/${encodeURIComponent(paperId)}/pdf/retry`, { method: "POST" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "重新获取 PDF 失败");
      if (!data.ok) throw new Error(data.message || "没有找到可合法下载的开放全文");
      if (data.paper) Object.assign(paper, data.paper);
      await this.loadPDFPreview(paper, session);
    } catch (error) {
      mount.className = "pdf-preview-state error";
      mount.innerHTML = `
        <i class="fa-solid fa-file-circle-xmark"></i>
        <strong>仍未找到开放全文</strong>
        <span>${this.escapeHtml(error?.message || "请稍后重试或手动上传 PDF。")}</span>
        <button class="secondary-btn" id="pdfRetryButton" type="button"><i class="fa-solid fa-rotate-right"></i> 再试一次</button>
      `;
      document.getElementById("pdfRetryButton")?.addEventListener("click", () => this.retryPaperPDF(paper, session));
    }
  },

  renderTraceView(session) {
    const traces = session?.traces || [];
    const topic = session?.topic || "当前会话";

    // 收集 SECTION markers 做目录
    const sections = [];
    traces.forEach((step, idx) => {
      if (step.action === "SECTION") {
        sections.push({ idx, label: (step.observation || "").replace(/^##\s*📌\s*/, "") });
      }
    });

    let html = `
      <div class="detail-hero">
        <span class="topic-badge"><i class="fa-solid fa-route"></i> 执行轨迹</span>
        <h3>${this.escapeHtml(topic)}</h3>
        <div class="lead">共 ${traces.length} 步 · ${sections.length > 0 ? sections.length + ' 个调研阶段 · ' : ''}当前状态：${session.state_label || session.state || "未知"}</div>
      </div>
    `;

    // 目录导航
    if (sections.length > 0) {
      html += `<div class="trace-toc"><strong>📑 调研目录：</strong>`;
      sections.forEach((sec) => {
        html += `<a class="toc-link" href="#" onclick="document.getElementById('trace-step-${sec.idx}').scrollIntoView({behavior:'smooth'});return false;">${this.escapeHtml(sec.label)}</a>`;
      });
      html += `</div>`;
    }

    html += `<div class="detail-blocks" style="margin-top:16px;">`;

    if (!traces || traces.length === 0) {
      html += `
        <div class="panel-block">
          <div class="panel-block-head"><strong>暂无轨迹</strong></div>
          <div class="empty-state">Agent 尚未执行，或轨迹尚未生成。请先执行规划或检索。</div>
        </div>
      `;
    } else {
      traces.forEach((step, idx) => {
        // SECTION 条目特殊渲染
        if (step.action === "SECTION") {
          html += `
            <div class="trace-section-header" id="trace-step-${idx}">
              <i class="fa-solid fa-bookmark"></i> ${this.escapeHtml(step.observation || "").replace(/^##\s*📌\s*/, "📌 ")}
            </div>
          `;
          return;
        }

        const action = step.action || "执行";
        const thought = step.thought || "";
        const observation = step.observation || "";
        const errorType = step.error_type || "";
        const inputObj = step.input || step.action_input || {};
        const inputStr = typeof inputObj === "string" ? inputObj : JSON.stringify(inputObj, null, 2);

        // 时间戳
        const ts = step.timestamp || "";
        const timeStr = ts ? new Date(ts).toLocaleTimeString("zh-CN") : "";

        let statusChip = "";
        if (errorType && errorType !== "section") {
          statusChip = `<span class="chip err" title="错误类型: ${this.escapeHtml(errorType)}"><i class="fa-solid fa-triangle-exclamation"></i> 失败</span>`;
        } else if (action === "FINISH_BLOCKED") {
          statusChip = `<span class="chip warn"><i class="fa-solid fa-lock"></i> 拦截</span>`;
        } else {
          statusChip = `<span class="chip ok"><i class="fa-solid fa-circle-check"></i> 成功</span>`;
        }

        html += `
          <div class="panel-block trace-step" id="trace-step-${idx}">
            <div class="panel-block-head">
              <strong>第 ${idx + 1} 轮 · ${this.escapeHtml(action)}</strong>
              ${timeStr ? `<span class="chip" style="font-size:10px;"><i class="fa-regular fa-clock"></i> ${timeStr}</span>` : ""}
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

    const modeLabel = this.state.chatMode === "agent" ? "Agent 模式" : "对话模式";
    const modeIcon = this.state.chatMode === "agent" ? "fa-wand-magic-sparkles" : "fa-comment-dots";

    this.els.chatContext.innerHTML = `
      <span class="chip chat-mode-chip" title="${this.state.chatMode === "agent" ? "切换到对话模式" : "切换到 Agent 模式"}"><i class="fa-solid ${modeIcon}"></i> ${modeLabel}</span>
      <span class="chip"><i class="fa-solid fa-sparkles"></i> ${this.escapeHtml(label)}</span>
    `;

    // 让模式 chip 可点击切换
    const modeChip = this.els.chatContext.querySelector(".chat-mode-chip");
    if (modeChip) {
      modeChip.addEventListener("click", () => this.toggleChatMode());
    }

    // 更新上下文用量条
    this.updateContextMeter();
  },

  async updateContextMeter() {
    const fill = document.getElementById("contextMeterFill");
    const stats = document.getElementById("contextStats");
    const compressBtn = document.getElementById("contextCompressBtn");
    if (!fill || !stats) return;

    const sessionId = this.state.currentSessionId;
    if (!sessionId) { fill.style.width = "0%"; stats.textContent = ""; return; }

    try {
      const convId = this.state.currentConvId || "default";
      const resp = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/context/stats?conv_id=${encodeURIComponent(convId)}`);
      const data = resp.ok ? await resp.json() : null;

      if (data) {
        const pct = Math.max(data.usage_percent || 0, 0.5);
        fill.style.width = pct + "%";
        // 内联背景色：>80% 红色，>60% 黄色，否则默认蓝色
        if (pct > 80) fill.style.background = "var(--danger)";
        else if (pct > 60) fill.style.background = "var(--warning, #f59e0b)";
        else fill.style.background = "var(--accent)";
        stats.textContent = `${data.estimated_tokens || 0} / ${data.max_tokens || 40000} tokens · ${data.round_count || 0} 轮`;
        if (compressBtn) {
          compressBtn.style.display = data.round_count >= 6 ? "" : "none";
          compressBtn.onclick = () => this.compressContext();
        }
      } else {
        fill.style.width = "0%";
        stats.textContent = "统计暂不可用";
        if (compressBtn) compressBtn.style.display = "none";
      }
    } catch (e) {
      fill.style.width = "0%";
      stats.textContent = "统计暂不可用";
      if (compressBtn) compressBtn.style.display = "none";
    }
  },

  async compressContext() {
    const sessionId = this.state.currentSessionId;
    if (!sessionId) return;
    const compressBtn = document.getElementById("contextCompressBtn");
    if (compressBtn) { compressBtn.disabled = true; compressBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 压缩中...'; }

    try {
      const convId = this.state.currentConvId || "default";
      const resp = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/context/compress?conv_id=${encodeURIComponent(convId)}`, { method: "POST" });
      const data = await resp.json();
      if (data.status === "compressed") {
        // 刷新聊天记录
        if (typeof this.loadConversationMessages === "function") {
          await this.loadConversationMessages(convId);
        }
      }
      await this.updateContextMeter();
    } catch (e) {
      console.warn("压缩失败：", e);
    } finally {
      if (compressBtn) { compressBtn.disabled = false; compressBtn.innerHTML = '<i class="fa-solid fa-compress"></i> 压缩'; }
    }
  },

  toggleChatMode(forceMode = null) {
    const nextMode = forceMode || (this.state.chatMode === "agent" ? "normal" : "agent");
    this.state.chatMode = nextMode;
    this.updateChatPlaceholder();
    this.renderChatContext();
  },

  updateChatPlaceholder() {
    if (!this.els.chatInput) return;
    this.els.chatInput.placeholder = this.state.chatMode === "agent"
      ? "输入问题；或使用 /修订 修改意见 来修订笔记/综述"
      : "输入问题，按回车发送";
  },

  // ━━━ 多会话聊天管理 ━━━

  async loadCurrentConversation() {
    if (!this.state.currentSessionId || !this.state.currentConvId) return;
    try {
      const response = await fetch(
        `/api/sessions/${encodeURIComponent(this.state.currentSessionId)}/conversations/${encodeURIComponent(this.state.currentConvId)}/messages`
      );
      if (!response.ok) return;
      const data = await response.json();
      this.state.chatMessages = data.messages || [];
      this.renderChatMessages();
    } catch (e) {
      this.renderChatMessages();
    }
  },

  renderChatTabs() {
    const tabsEl = document.getElementById("chatTabs");
    if (!tabsEl) return;
    
    const convs = this.state.conversations;

    // 先保存用量条 DOM（在 innerHTML 清空前），避免检索期间闪烁
    const existingMeter = document.getElementById("chatContextBar");
    const meterHTML = existingMeter ? existingMeter.outerHTML : null;

    tabsEl.innerHTML = "";

    convs.forEach((conv) => {
      const tab = document.createElement("span");
      tab.className = `chat-tab${conv.conv_id === this.state.currentConvId ? " active" : ""}`;
      tab.title = conv.title || conv.conv_id;

      const label = document.createElement("span");
      label.textContent = conv.title || conv.conv_id;
      label.addEventListener("click", () => this.switchConversation(conv.conv_id));
      tab.appendChild(label);

      // 删除按钮（至少保留一个）
      if (convs.length > 1) {
        const close = document.createElement("span");
        close.className = "tab-close";
        close.innerHTML = '<i class="fa-solid fa-xmark"></i>';
        close.addEventListener("click", (e) => {
          e.stopPropagation();
          this.deleteConversation(conv.conv_id);
        });
        tab.appendChild(close);
      }

      tabsEl.appendChild(tab);
    });

    // + 新建按钮
    const addBtn = document.createElement("span");
    addBtn.className = "chat-tab-add";
    addBtn.title = "新建对话";
    addBtn.innerHTML = '<i class="fa-solid fa-plus"></i>';
    addBtn.addEventListener("click", () => this.createConversation());
    tabsEl.appendChild(addBtn);

    // 用量条 — 如果之前存在则恢复 HTML 并只更新数据，避免检索期间闪烁
    if (meterHTML) {
      tabsEl.insertAdjacentHTML("beforeend", meterHTML);
      this.updateContextMeter();
      return;
    }

    const meter = document.createElement("div");
    meter.id = "chatContextBar";
    meter.style.cssText = "display:flex;align-items:center;gap:8px;margin-left:auto;padding:2px 8px;flex-shrink:0;";
    meter.innerHTML = `
      <span style="font-size:11px;color:var(--subtle);white-space:nowrap;">上下文</span>
      <div id="contextMeterOuter" style="width:120px;height:8px;background:var(--line);border-radius:4px;overflow:hidden;flex-shrink:0;">
        <div id="contextMeterFill" style="display:block;width:0%;height:8px;background:var(--accent);border-radius:4px;transition:width .3s,background .3s;"></div>
      </div>
      <span id="contextStats" style="font-size:11px;color:var(--muted);white-space:nowrap;">加载中...</span>
      <button id="contextCompressBtn" title="压缩早期对话为摘要"
        style="display:none;font-size:11px;padding:3px 10px;border-radius:12px;white-space:nowrap;border:1px solid var(--line);background:var(--panel);color:var(--text);cursor:pointer;">
        <i class="fa-solid fa-compress"></i> 压缩
      </button>
    `;
    tabsEl.appendChild(meter);

    // 更新用量条数据
    setTimeout(() => this.updateContextMeter(), 100);
  },

  async switchConversation(convId) {
    if (convId === this.state.currentConvId) return;
    this.state.currentConvId = convId;
    this.renderChatTabs();
    await this.loadCurrentConversation();
  },

  async createConversation(title = "") {
    if (!this.state.currentSessionId) return;
    try {
      const response = await fetch(
        `/api/sessions/${encodeURIComponent(this.state.currentSessionId)}/conversations`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: title || `对话 ${new Date().toLocaleTimeString()}` }),
        }
      );
      if (!response.ok) return;
      const conv = await response.json();
      this.state.conversations.push(conv);
      this.state.currentConvId = conv.conv_id;
      this.state.chatMessages = [];
      this.renderChatTabs();
      this.renderChatMessages();
    } catch (e) { /* ignore */ }
  },

  async deleteConversation(convId) {
    if (!this.state.currentSessionId) return;
    if (this.state.conversations.length <= 1) {
      alert("至少保留一个聊天会话");
      return;
    }
    try {
      const response = await fetch(
        `/api/sessions/${encodeURIComponent(this.state.currentSessionId)}/conversations/${encodeURIComponent(convId)}`,
        { method: "DELETE" }
      );
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        alert(data.detail || "删除失败");
        return;
      }
      this.state.conversations = this.state.conversations.filter(c => c.conv_id !== convId);
      if (this.state.currentConvId === convId) {
        this.state.currentConvId = this.state.conversations[0]?.conv_id || null;
        await this.loadCurrentConversation();
      }
      this.renderChatTabs();
    } catch (e) {
      alert("删除失败：" + e.message);
    }
  },

  renderChatMessages() {
    if (!this.els.chatList) return;
    this.els.chatList.innerHTML = "";

    const messages = this.state.chatMessages;
    if (!messages || messages.length === 0) {
      this.els.chatList.innerHTML = `
        <div class="chat-msg">
          <span class="chat-role">AI</span>
          <span>点击左侧论文进入对应界面后可在下方提问，笔记无需勾选，综述模式需要勾选对应的论文。笔记模式和综述模式下可请求修改。</span>
        </div>`;
      return;
    }

    messages.forEach((msg) => {
      this._renderChatMsgDOM(
        msg.role,
        msg.text || "",
        msg.view_mode || "",
        msg.note || "",
        [],
      );
    });
  },

  updateActionButtons() {
    const session = this.state.currentSession;
    if (!session) return;

    const papers = session.papers || [];
    const hasPapers = papers.length > 0;
    const hasDraft = Boolean((session.draft || "").trim());
    const acceptedPapers = papers.filter(p => p.status === "accepted");
    const effectivePapers = acceptedPapers;

    // 计数：有效选中论文中，有笔记的 / 没笔记的
    const withNotes = effectivePapers.filter(p => p._hasNotes).length;
    const withoutNotes = effectivePapers.length - withNotes;
    const allHaveNotes = effectivePapers.length > 0 && withoutNotes === 0;
    const anyNeedNotes = withoutNotes > 0;
    const notesGenerated = effectivePapers.length > 0 && allHaveNotes;

    // AI检索论文 / 停止检索 按钮切换
    if (this.els.searchBtn) {
      if (!session.keywords || !session.keywords.length || session.state === "planning") {
        this.els.searchBtn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> 生成关键词';
        this.els.searchBtn.disabled = false;
        this.els.searchBtn.style.display = "";
        if (this.els.cancelSearchBtn) this.els.cancelSearchBtn.style.display = "none";
      } else if (session.state === "plan_confirmed") {
        this.els.searchBtn.innerHTML = '<i class="fa-solid fa-magnifying-glass"></i> AI检索论文';
        this.els.searchBtn.disabled = false;
        this.els.searchBtn.style.display = "";
        if (this.els.cancelSearchBtn) this.els.cancelSearchBtn.style.display = "none";
      } else if (session.state === "searching") {
        // 隐藏主按钮，显示红色取消按钮
        this.els.searchBtn.style.display = "none";
        if (this.els.cancelSearchBtn) {
          this.els.cancelSearchBtn.style.display = "";
          this.els.cancelSearchBtn.disabled = false;
        }
      } else {
        this.els.searchBtn.innerHTML = '<i class="fa-solid fa-magnifying-glass-plus"></i> 继续检索';
        this.els.searchBtn.disabled = false;
        this.els.searchBtn.style.display = "";
        if (this.els.cancelSearchBtn) this.els.cancelSearchBtn.style.display = "none";
      }
    }
    if (this.els.searchTargetInput) {
      this.els.searchTargetInput.disabled = session.state === "searching";
    }
    if (this.els.searchLoopLimitInput) {
      this.els.searchLoopLimitInput.disabled = session.state === "searching";
    }

    // 添加论文 按钮
    if (this.els.addPaperBtn) {
      this.els.addPaperBtn.disabled = false;
    }

    // 「自动进行」按钮
    // 规则：以 _autoRunning 标志为唯一运行中判断依据，不依赖 session.state
    if (this.els.autoRunBtn) {
      if (this.state._autoRunning) {
        this.els.autoRunBtn.disabled = true;
        this.els.autoRunBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 自动进行中...';
        this.els.autoRunBtn.style.display = "";
      } else if (session.state === "complete") {
        this.els.autoRunBtn.disabled = true;
        this.els.autoRunBtn.innerHTML = '<i class="fa-solid fa-check-circle"></i> 已完成';
        this.els.autoRunBtn.style.display = "";
      } else {
        this.els.autoRunBtn.disabled = false;
        this.els.autoRunBtn.innerHTML = '<i class="fa-solid fa-forward-step"></i> 自动进行';
        this.els.autoRunBtn.style.display = "";
      }
    }

    if (this.els.selectedPaperCount) {
      this.els.selectedPaperCount.textContent = acceptedPapers.length
        ? `已纳入 ${acceptedPapers.length} / ${papers.length} 篇`
        : "尚未纳入论文";
    }
    if (this.els.selectionActionHint) {
      if (!acceptedPapers.length) {
        this.els.selectionActionHint.textContent = "请先选择“纳入综述”";
      } else if (withoutNotes > 0) {
        this.els.selectionActionHint.textContent = `${withoutNotes} 篇尚无笔记`;
      } else if (hasDraft && session.review_is_stale) {
        this.els.selectionActionHint.textContent = "论文选择已变化，建议更新综述";
      } else if (hasDraft) {
        this.els.selectionActionHint.textContent = `当前综述基于 ${acceptedPapers.length} 篇论文`;
      } else {
        this.els.selectionActionHint.textContent = "已具备综述生成条件";
      }
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
    // 规则：只基于明确纳入的论文；已有草稿时允许生成更新版本
    if (this.els.reviewBtn) {
      if (!notesGenerated) {
        this.els.reviewBtn.disabled = true;
        this.els.reviewBtn.innerHTML = '<i class="fa-regular fa-pen-to-square"></i> 生成综述';
        this.els.reviewBtn.classList.remove("active");
      } else if (hasDraft) {
        this.els.reviewBtn.disabled = false;
        this.els.reviewBtn.innerHTML = `<i class="fa-solid fa-rotate"></i> 更新综述 · ${acceptedPapers.length}篇`;
        this.els.reviewBtn.classList.add("active");
      } else {
        this.els.reviewBtn.disabled = false;
        this.els.reviewBtn.innerHTML = `<i class="fa-regular fa-pen-to-square"></i> 生成综述 · ${acceptedPapers.length}篇`;
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
      } else if (session.state === "search_failed") {
        hint.innerHTML = '<i class="status-dot err"></i>本轮没有成功新增论文，请调整关键词或检查数据源后重试';
      } else if (session.state === "search_partial") {
        const latestRun = (session.search_runs || []).at(-1) || {};
        hint.innerHTML = `<i class="status-dot warn"></i>本轮新增 ${latestRun.new_count || 0}/${latestRun.target_new_papers || "?"} 篇，尚未达到目标，可继续检索`;
      } else if (hasDraft && session.review_is_stale) {
        hint.innerHTML = '<i class="status-dot warn"></i>论文选择已变化，请更新笔记或综述';
      } else if (hasDraft) {
        hint.innerHTML = '<i class="status-dot ok"></i>综述已生成，可继续更新或查看';
      } else if (notesGenerated) {
        hint.innerHTML = '<i class="status-dot ok"></i>选中论文笔记已全部生成，点击「生成综述」撰写初稿';
      } else if (anyNeedNotes) {
        hint.innerHTML = `<i class="status-dot live"></i>${withoutNotes} 篇选中论文未生成笔记，点击「生成笔记」`;
      } else if (hasPapers) {
        hint.innerHTML = '<i class="status-dot live"></i>请先将论文纳入综述，然后生成笔记';
      } else {
        hint.innerHTML = '<i class="status-dot live"></i>请先检索论文，再生成笔记与综述';
      }
    }
  },

  viewModeLabel(mode) {
    return {
      summary: "摘要",
      report: "笔记",
      review: "综述",
      trace: "轨迹",
      analysis: "分析",
      pdf: "PDF",
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

  async cancelSearch() {
    // 同时取消自动模式
    if (this.state._autoRunning) {
      this.state._autoRunning = false;
      if (this.state._autoPollTimer) {
        clearInterval(this.state._autoPollTimer);
        this.state._autoPollTimer = null;
      }
    }

    if (!this.state.currentSessionId) return;
    try {
      const response = await fetch(`/api/sessions/${encodeURIComponent(this.state.currentSessionId)}/run/cancel`, {
        method: "POST",
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "取消失败");

      await this.reloadCurrentSession();
      this._setSearchButtons("idle");
      this.setConsoleStatus("search_complete", "检索已被手动终止");
    } catch (error) {
      alert("取消检索失败：" + error.message);
    }
  },

  async startAutoRun() {
    const session = this.state.currentSession;
    this.state.lastAction = "auto";
    const sessionId = this.state.currentSessionId;
    if (!session || !sessionId) {
      alert("当前没有活跃的会话");
      return;
    }

    const topic = session.topic || "";
    if (!topic.trim()) {
      alert("主题不能为空");
      return;
    }
    const targetNewPapers = this.getSearchTarget();
    if (targetNewPapers === null) return;
    const maxSearchLoops = this.getSearchLoopLimit(targetNewPapers);
    if (maxSearchLoops === null) return;
    if (!confirm(`“自动进行”将尝试新增至少 ${targetNewPapers} 篇论文，最多执行 ${maxSearchLoops} 轮，再依次生成笔记、分析和综述。若先达到轮数上限，流程会保留已有结果并停止，是否继续？`)) return;

    // 如果还在 planning 阶段且无关键词，先自动生成关键词再启动
    if (!session.keywords || !session.keywords.length || session.state === "planning") {
      this.setConsoleStatus("planning", "正在生成关键词规划...");
      try {
        const planResp = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/run/plan`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(this.withProvider({ topic, start_phase: "plan" })),
        });
        const planData = await planResp.json();
        if (!planResp.ok) throw new Error(planData.detail || "规划失败");

        // 收集关键词并确认
        const seed = sessionStorage.getItem(`notebooklm:seedKeywords:${sessionId}`) || "";
        sessionStorage.removeItem(`notebooklm:seedKeywords:${sessionId}`);
        let keywords = Array.isArray(planData.keywords) ? planData.keywords.slice() : [];
        if (seed) {
          const lines = seed.split(/[，,\n;]/).map((item) => item.trim()).filter(Boolean);
          lines.forEach((line) => keywords.push({ original: line, english: "", synonyms: "" }));
        }

        // 保存关键词并确认
        await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/keywords`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ keywords }),
        });
        await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/state`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ state: "plan_confirmed" }),
        });
      } catch (error) {
        this.setConsoleStatus("error", `自动规划失败：${error.message}`);
        return;
      }
    }

    // 启动自动流水线
    this.state._autoRunning = true;
    this.setConsoleStatus("searching", "🚀 自动模式已启动，正在全自动执行...");
    this.updateActionButtons();

    try {
      const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/run/auto`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(this.withProvider({
          topic,
          max_loops: maxSearchLoops,
          min_papers: targetNewPapers,
        })),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "启动失败");
    } catch (error) {
      this.state._autoRunning = false;
      this.setConsoleStatus("error", `自动模式启动失败：${error.message}`);
      this.updateActionButtons();
      return;
    }

    // 轮询进度
    if (this.state._autoPollTimer) {
      clearInterval(this.state._autoPollTimer);
    }

    this.state._autoPollTimer = setInterval(async () => {
      try {
        // 获取运行状态（优先使用 RUNS 内存状态，它更实时）
        const statusResp = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/run/status`);
        const status = await statusResp.json();

        const phase = status.phase || "unknown";
        const runStatus = status.status || "unknown";
        const message = status.message || "";

        // 只在自动模式下不调用 reloadCurrentSession，避免磁盘状态覆盖 RUNS 实时状态
        // 改为手动更新必要的 UI 部分
        const sessionResp = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}`);
        const session = await sessionResp.json();
        if (sessionResp.ok) {
          // 将 RUNS 中的实时 traces 注入 session，确保轨迹视图能实时更新
          if (status.traces && status.traces.length > 0) {
            session.traces = status.traces;
          }
          if (status.analysis) {
            session._analysis = {
              compare: status.analysis.compare || "",
              lineage: status.analysis.lineage || "",
              gaps: status.analysis.gaps || "",
              document: status.analysis.document || "",
            };
          }
          this.state.currentSession = session;
          if (session.papers?.length && !this.state.currentPaperId) {
            this.state.currentPaperId = session.papers[0].paper_id;
          }
          // 只更新内容面板，不更新状态栏（状态栏由 RUNS 驱动）
          this.renderPaperList();
          this.renderNotesBlock();
          this.renderReviewBlock();
          this.renderDetailPanel();
          this.renderChatContext();
          this.renderViewButtons();
        }

        // 更新顶部状态（以 RUNS 内存状态为准，避免与磁盘状态冲突导致闪烁）
        if (message) {
          this.setConsoleStatus(phase, message);
        } else {
          // 无 message 时用 phase 自身作为标签
          const phaseLabels = {
            planning: "正在规划关键词...",
            searching: "正在检索论文...",
            search_complete: "搜索完成，即将生成笔记...",
            search_partial: "检索部分完成，尚未达到目标",
            search_failed: "检索失败，本轮未新增论文",
            reviewing_notes: "正在生成笔记...",
            analysis: "正在生成深度分析报告...",
            writing: "正在撰写综述草稿...",
            reviewing_draft: "正在评审草稿...",
            complete: "流程完成",
            failed: "流程出错",
          };
          this.setConsoleStatus(phase, phaseLabels[phase] || phase);
        }

        // 根据阶段切换视图
        if (["search_complete", "search_partial", "search_failed"].includes(phase)) {
          this.switchViewMode("summary");
        } else if (phase === "reviewing_notes" || phase === "analysis" || phase === "writing") {
          // 保持当前视图
        } else if (phase === "complete" && runStatus === "done") {
          this.switchViewMode("review");
        }

        // 更新按钮状态
        this.updateActionButtons();

        // 检查是否完成
        if (["done", "partial", "error", "cancelled"].includes(runStatus)) {
          clearInterval(this.state._autoPollTimer);
          this.state._autoPollTimer = null;
          this.state._autoRunning = false;

          // 先刷新 session 再更新按钮，确保 session.state 已同步为最新
          await this.reloadCurrentSession();

          if (runStatus === "done") {
            this.setConsoleStatus("complete", "🎉 自动流程全部完成！");
            this.trackProductEvent("first_review_generated");
          } else if (runStatus === "partial") {
            this.setConsoleStatus("search_partial", status.message || "检索部分完成，尚未达到目标，请继续检索");
          } else if (runStatus === "error") {
            this.setConsoleStatus(status.phase === "search_failed" ? "search_failed" : "error", status.message || `自动流程失败：${status.error || "未知错误"}`);
          }
          this.updateActionButtons();
        }
      } catch (error) {
        // 轮询出错不中断，继续尝试
        console.warn("自动模式轮询出错：", error);
      }
    }, 2500);
  },

  _setSearchButtons(state) {
    // 已集成到 updateActionButtons 中，此函数保留用于显式切换
    if (this.els.searchBtn) {
      if (state === "searching") {
        this.els.searchBtn.style.display = "none";
      } else {
        this.els.searchBtn.style.display = "";
      }
    }
    if (this.els.cancelSearchBtn) {
      this.els.cancelSearchBtn.style.display = state === "searching" ? "" : "none";
    }
    if (this.els.searchTargetInput) {
      this.els.searchTargetInput.disabled = state === "searching";
    }
    if (this.els.searchLoopLimitInput) {
      this.els.searchLoopLimitInput.disabled = state === "searching";
    }
  },

  getSearchTarget() {
    const input = this.els.searchTargetInput;
    if (!input) return 3;
    const value = Number(input.value);
    const valid = Number.isInteger(value) && value >= 1 && value <= 15;
    input.setCustomValidity(valid ? "" : "请输入 1 到 15 之间的整数");
    if (!valid) {
      input.reportValidity();
      input.focus();
      return null;
    }
    return value;
  },

  recommendedSearchLoops(targetNewPapers) {
    const target = Math.max(1, Math.min(15, Number(targetNewPapers) || 3));
    return Math.min(80, Math.max(20, target * 5 + 10));
  },

  updateSearchLoopRecommendation(syncValue = false) {
    const target = Number(this.els.searchTargetInput?.value);
    if (!Number.isInteger(target) || target < 1 || target > 15) return;
    const recommended = this.recommendedSearchLoops(target);
    const input = this.els.searchLoopLimitInput;
    if (input && syncValue) input.value = String(recommended);
    const configured = Number(input?.value);
    if (!this.els.searchBudgetHelp) return;
    this.els.searchBudgetHelp.textContent = Number.isInteger(configured) && configured < recommended
      ? `推荐 ${recommended} 轮；当前上限较低，可能在达到 ${target} 篇前结束。`
      : `推荐 ${recommended} 轮；系统不会超过你设置的上限。`;
  },

  getSearchLoopLimit(targetNewPapers = 3) {
    const input = this.els.searchLoopLimitInput;
    if (!input) return this.recommendedSearchLoops(targetNewPapers);
    const value = Number(input.value);
    const valid = Number.isInteger(value) && value >= 1 && value <= 80;
    input.setCustomValidity(valid ? "" : "请输入 1 到 80 之间的整数");
    if (!valid) {
      input.reportValidity();
      input.focus();
      return null;
    }
    return value;
  },

  async generateNotesAction() {
    this.state.lastAction = "notes";
    const session = this.state.currentSession;
    if (!session || !this.state.currentSessionId) return;

    const papers = session.papers || [];
    const acceptedPapers = papers.filter(p => p.status === "accepted");
    const effectivePapers = acceptedPapers;
    if (!effectivePapers.length) {
      alert("请先至少纳入一篇论文，再生成笔记。");
      return;
    }
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
        body: JSON.stringify(this.withProvider({ topic: session.topic, paper_ids: paperIds })),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "生成笔记失败");
      }

      await this.reloadCurrentSession();
      this.switchViewMode("report");
      this.setConsoleStatus("search_complete", `${data.count || paperIds.length} 篇论文笔记已生成`);
    } catch (error) {
      this.setConsoleStatus("error", `生成笔记失败：${error.message}`);
    }
  },

  async generateAnalysisAction() {
    const session = this.state.currentSession;
    if (!session || !this.state.currentSessionId) return;
    const paperIds = (session.papers || [])
      .filter((paper) => paper.status === "accepted")
      .map((paper) => paper.paper_id);
    if (!paperIds.length) {
      alert("请先至少纳入一篇论文，再生成分析报告。");
      return;
    }

    try {
      this.setConsoleStatus("writing", "正在生成深度分析报告...");
      const response = await fetch(`/api/sessions/${encodeURIComponent(this.state.currentSessionId)}/run/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(this.withProvider({ topic: session.topic, analysis_type: "all", paper_ids: paperIds })),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "分析失败");
      }

      if (!this.state.currentSession._analysis) this.state.currentSession._analysis = {};
      if (data.compare) this.state.currentSession._analysis.compare = data.compare;
      if (data.lineage) this.state.currentSession._analysis.lineage = data.lineage;
      if (data.gaps) this.state.currentSession._analysis.gaps = data.gaps;
      this.state.currentSession._analysis.document = this.analysisToMarkdown(this.state.currentSession._analysis, session.topic || "当前主题");

      this.switchViewMode("analysis");
      this.setConsoleStatus("complete", "深度分析报告已生成");
    } catch (error) {
      this.setConsoleStatus("error", `分析失败：${error.message}`);
    }
  },

  renderAnalysisView(session) {
    const analysis = this.normalizeAnalysisSections(session?._analysis || session?.analysis || {}, session?.topic || "当前主题");
    const hasData = analysis.compare || analysis.lineage || analysis.gaps;

    if (!hasData) {
      return `
        <div class="detail-hero">
          <span class="topic-badge"><i class="fa-solid fa-magnifying-glass-chart"></i> 深度分析</span>
          <h3>${this.escapeHtml(session?.topic || "当前主题")}</h3>
          <div class="lead">基于已有笔记和论文，生成文献对比、研究脉络和空白发现三份深度分析报告。</div>
        </div>
        <div class="detail-blocks" style="margin-top:16px;">
          <div class="panel-block" style="text-align:center;padding:40px;">
            <div class="empty-state" style="margin-bottom:16px;">尚未生成分析报告</div>
            <button class="primary-btn" onclick="notebooklm.generateAnalysisAction()" style="font-size:14px;">
              <i class="fa-solid fa-wand-magic-sparkles"></i> 生成深度分析报告
            </button>
          </div>
        </div>
      `;
    }

    return `
      <div class="detail-hero">
        <span class="topic-badge"><i class="fa-solid fa-magnifying-glass-chart"></i> 深度分析</span>
        <h3>${this.escapeHtml(session?.topic || "当前主题")}</h3>
        <div class="lead">文献对比 · 研究脉络 · 空白发现。每个分析卡片都可单独编辑 Markdown 内容。</div>
      </div>
      <div class="detail-blocks" style="margin-top:16px;">
        ${this.renderAnalysisCard("compare", "文献对比分析", "fa-table-columns", analysis.compare)}
        ${this.renderAnalysisCard("lineage", "研究脉络梳理", "fa-timeline", analysis.lineage)}
        ${this.renderAnalysisCard("gaps", "研究空白发现", "fa-lightbulb", analysis.gaps)}
        <div class="panel-block" style="text-align:center;padding:12px;">
          <button class="secondary-btn" onclick="notebooklm.generateAnalysisAction()" style="font-size:13px;">
            <i class="fa-solid fa-rotate"></i> 重新生成分析报告
          </button>
        </div>
      </div>
    `;
  },

  renderAnalysisCard(section, title, icon, content) {
    const safeContent = String(content || "").trim();
    const isEditing = this.state.editingAnalysisSection === section;
    const editAreaId = `analysisEditArea_${section}`;
    const bodyHtml = isEditing
      ? `
        <div id="${editAreaId}" style="display:none;">${this.escapeHtml(this.state.analysisEditText || safeContent)}</div>
        <div style="display: flex; gap: 8px; justify-content: flex-end; margin-top: 8px;">
          <button class="secondary-btn" onclick="notebooklm.cancelEditAnalysis()">取消</button>
          <button class="primary-btn" onclick="notebooklm.saveEditAnalysis()">保存</button>
        </div>
      `
      : (safeContent ? `<div class="markdown">${marked.parse(this.stripMarkdownFence(safeContent))}</div>` : '<div class="empty-state">暂无内容。</div>');

    return `
      <div class="panel-block">
        <div class="panel-block-head">
          <div style="display:flex; align-items:center; gap:8px;">
            <strong><i class="fa-solid ${icon}"></i> ${title}</strong>
            <span class="chip">Markdown</span>
          </div>
          ${!isEditing ? `<button class="secondary-btn" title="编辑${title}" onclick="notebooklm.startEditAnalysis('${section}')"><i class="fa-solid fa-pen" style="margin-right:4px;"></i>编辑</button>` : ""}
        </div>
        ${bodyHtml}
      </div>
    `;
  },

  analysisToMarkdown(analysis, topic = "当前主题") {
    if (!analysis) return "";
    const normalized = this.normalizeAnalysisSections(analysis, topic);
    const sections = [];
    const compare = String(normalized.compare || "").trim();
    const lineage = String(normalized.lineage || "").trim();
    const gaps = String(normalized.gaps || "").trim();
    if (compare) sections.push(`## 文献对比分析\n\n${compare}`);
    if (lineage) sections.push(`## 研究脉络梳理\n\n${lineage}`);
    if (gaps) sections.push(`## 研究空白发现\n\n${gaps}`);
    if (!sections.length) return "";
    return `# 深度分析：${topic}\n\n${sections.join("\n\n---\n\n")}`;
  },

  normalizeAnalysisSections(analysis, topic = "当前主题") {
    const normalized = {
      compare: String(analysis?.compare || "").trim(),
      lineage: String(analysis?.lineage || "").trim(),
      gaps: String(analysis?.gaps || "").trim(),
    };

    if ((normalized.compare || normalized.lineage || normalized.gaps) || !analysis?.document) {
      return normalized;
    }

    const documentText = this.stripMarkdownFence(analysis.document);
    const sectionPatterns = [
      ["compare", /##\s*文献对比分析\s*\n+([\s\S]*?)(?=\n---\n|\n##\s*研究脉络梳理|\n##\s*研究空白发现|$)/],
      ["lineage", /##\s*研究脉络梳理\s*\n+([\s\S]*?)(?=\n---\n|\n##\s*文献对比分析|\n##\s*研究空白发现|$)/],
      ["gaps", /##\s*研究空白发现\s*\n+([\s\S]*?)(?=\n---\n|\n##\s*文献对比分析|\n##\s*研究脉络梳理|$)/],
    ];
    sectionPatterns.forEach(([key, pattern]) => {
      const match = documentText.match(pattern);
      if (match) normalized[key] = match[1].trim();
    });

    if (!normalized.compare && !normalized.lineage && !normalized.gaps && documentText) {
      normalized.compare = documentText.replace(/^#\s*深度分析[:：]?.*?\n+/s, "").trim();
    }
    return normalized;
  },

  stripMarkdownFence(text) {
    return String(text || "")
      .replace(/```markdown\s*\n([\s\S]*?)```/g, '$1')
      .replace(/```markdown\s*\n([\s\S]*?)(\n---|\n## (?!##)|$)/, '$1$2')
      .trim();
  },

  startEditAnalysis(section) {
    const session = this.state.currentSession;
    const analysis = this.normalizeAnalysisSections(session?._analysis || session?.analysis || {}, session?.topic || "当前主题");
    const rawAnalysis = String(analysis[section] || "").trim();
    const editAreaId = `analysisEditArea_${section}`;

    this.state.editingAnalysisSection = section;
    this.state.analysisEditText = rawAnalysis;
    this.renderDetailPanel();

    setTimeout(() => this._initVditor(editAreaId, rawAnalysis, "saveEditAnalysis"), 50);
  },

  cancelEditAnalysis() {
    const section = this.state.editingAnalysisSection;
    if (section) this._destroyVditor(`analysisEditArea_${section}`);
    this.state.editingAnalysisSection = "";
    this.state.analysisEditText = "";
    this.renderDetailPanel();
  },

  async saveEditAnalysis() {
    const section = this.state.editingAnalysisSection;
    if (!section) return;
    const editAreaId = `analysisEditArea_${section}`;
    const vditor = this._vditors?.[editAreaId];
    const newAnalysis = vditor ? vditor.getValue() : "";
    const sessionId = this.state.currentSessionId;
    if (!sessionId) return;

    this.els.detailContent.innerHTML = '<div class="loading-state">保存中...</div>';

    try {
      const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/analysis`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ section, content: newAnalysis }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "保存失败");

      this._destroyVditor(editAreaId);
      await this.reloadCurrentSession();
      this.state.editingAnalysisSection = "";
      this.state.analysisEditText = "";
      this.renderDetailPanel();
    } catch (error) {
      alert(error.message);
      this.renderDetailPanel();
    }
  },

  async generateReviewAction() {
    this.state.lastAction = "review";
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
        body: JSON.stringify(this.withProvider({ topic: session.topic, start_phase: "plan" })),
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
    this.state.lastAction = "search";
    const session = this.state.currentSession;
    if (!session || !this.state.currentSessionId) return;

    if (!session.keywords || !session.keywords.length) {
      this.openKeywordModal(session.topic, session.keywords || []);
      return;
    }

    const targetNewPapers = this.getSearchTarget();
    if (targetNewPapers === null) return;
    const maxSearchLoops = this.getSearchLoopLimit(targetNewPapers);
    if (maxSearchLoops === null) return;

    try {
      const existingIds = (session.papers || []).map((paper) => paper.paper_id);
      const incremental = existingIds.length > 0;
      this.state._searchStartPaperIds = existingIds.slice();
      this.setConsoleStatus(
        "searching",
        incremental
          ? `正在扩展检索，目标新增 ${targetNewPapers} 篇，最多 ${maxSearchLoops} 轮，并自动排除已有论文...`
          : `正在检索论文，本轮目标 ${targetNewPapers} 篇，最多 ${maxSearchLoops} 轮...`,
      );
      this._setSearchButtons("searching");
      const response = await fetch(`/api/sessions/${encodeURIComponent(this.state.currentSessionId)}/run/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(this.withProvider({
          topic: session.topic,
          start_phase: "search",
          keywords: session.keywords || [],
          search_mode: incremental ? "incremental" : "initial",
          target_new_papers: targetNewPapers,
          exclude_ids: existingIds,
          max_loops: maxSearchLoops,
        })),
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

          // 同时获取 RUNS 内存中的实时 traces（搜索进行中时磁盘尚未写入）
          try {
            const runStatusResp = await fetch(`/api/sessions/${encodeURIComponent(this.state.currentSessionId)}/run/status`);
            const runStatus = await runStatusResp.json();
            if (runStatus.traces && runStatus.traces.length > 0) {
              polled.traces = runStatus.traces;
            }
          } catch (e) { /* 忽略，使用磁盘数据兜底 */ }

          this.state.currentSession = polled;
          this.renderConsoleSession();

          if (["search_complete", "search_partial", "search_failed"].includes(polled.state)) {
            clearInterval(this.state.pollTimer);
            this.state.pollTimer = null;
            this._setSearchButtons("idle");
            this.switchViewMode("summary");
            const beforeIds = new Set(this.state._searchStartPaperIds || []);
            const fallbackCount = (polled.papers || []).filter((paper) => !beforeIds.has(paper.paper_id)).length;
            const latestRun = (polled.search_runs || []).at(-1) || {};
            const newCount = Number.isInteger(latestRun.new_count) ? latestRun.new_count : fallbackCount;
            const target = latestRun.target_new_papers || targetNewPapers;
            const outcomeMessage = latestRun.message || (
              polled.state === "search_complete"
                ? `检索完成：本轮实际新增 ${newCount}/${target} 篇论文。`
                : polled.state === "search_partial"
                  ? `检索部分完成：本轮实际新增 ${newCount}/${target} 篇，可继续检索。`
                  : `检索失败：本轮实际新增 0/${target} 篇，请调整关键词或检查数据源后重试。`
            );
            this.setConsoleStatus(polled.state, outcomeMessage);
            this.state._searchStartPaperIds = [];
            if (polled.state === "search_complete") this.trackProductEvent("first_search_completed");
          }
        } catch (error) {
          clearInterval(this.state.pollTimer);
          this.state.pollTimer = null;
          this._setSearchButtons("idle");
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
    const paperIds = (session.papers || [])
      .filter((paper) => paper.status === "accepted")
      .map((paper) => paper.paper_id);
    if (!paperIds.length && !(session.repositories || []).length) {
      alert("请先至少纳入一篇论文，再生成综述。");
      return;
    }
    const actionLabel = (session.draft || "").trim() ? "更新综述" : "生成综述";
    if (!confirm(`${actionLabel}将严格使用当前纳入的 ${paperIds.length} 篇论文，并保存为新版本。是否继续？`)) return;

    try {
      this.setConsoleStatus("writing", "正在生成综述草稿...");
      const response = await fetch(`/api/sessions/${encodeURIComponent(this.state.currentSessionId)}/run/write`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(this.withProvider({ topic: session.topic, start_phase: "write", paper_ids: paperIds })),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "写作失败");
      }

      await this.reloadCurrentSession();
      this.switchViewMode("review");
      this.setConsoleStatus("reviewing_draft", "综述已生成，可以继续提问或提交修改建议");
      this.trackProductEvent("first_review_generated");
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

  // ━━━ 统一的「添加论文」弹窗（arXiv ID + 拖拽上传）━━━
  _dropZoneFile: null,

  openAddPaperModal() {
    const sessionId = this.state.currentSessionId;
    if (!sessionId) {
      alert("当前没有活跃的会话，请先创建会话！");
      return;
    }

    // 延迟获取弹窗元素
    this.els.addPaperModal = document.getElementById("addPaperModal");
    this.els.addPaperArxivInput = document.getElementById("addPaperArxivInput");
    this.els.addPaperSubmitBtn = document.getElementById("addPaperSubmitBtn");
    this.els.addPaperCancel = document.getElementById("addPaperCancel");
    this.els.addPaperClose = document.getElementById("addPaperClose");
    this.els.dropZoneClear = document.getElementById("dropZoneClear");

    // 重置状态
    this._dropZoneFile = null;
    if (this.els.addPaperArxivInput) this.els.addPaperArxivInput.value = "";
    this._setDropZonePreview(null);

    // 显示弹窗
    if (this.els.addPaperModal) this.els.addPaperModal.classList.add("active");

    // 首次打开时绑定事件
    this._bindAddPaperModalEvents();
  },

  _bindAddPaperModalEvents() {
    if (this._addPaperModalBound) return;
    this._addPaperModalBound = true;

    const close = () => {
      if (this.els.addPaperModal) this.els.addPaperModal.classList.remove("active");
    };

    // × 和取消按钮关闭
    this.els.addPaperCancel?.addEventListener("click", close);
    this.els.addPaperClose?.addEventListener("click", close);
    // 点击遮罩关闭
    this.els.addPaperModal?.addEventListener("click", (e) => {
      if (e.target === this.els.addPaperModal) close();
    });

    // 统一的「添加」按钮
    this.els.addPaperSubmitBtn?.addEventListener("click", () => this._submitAddPaper());

    // 回车提交 arXiv 输入
    this.els.addPaperArxivInput?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") this._submitAddPaper();
    });

    // 拖拽上传区域
    this._setupDropZone();

    // 清除已选文件
    this.els.dropZoneClear?.addEventListener("click", (e) => {
      e.stopPropagation();
      this._dropZoneFile = null;
      this._setDropZonePreview(null);
    });
  },

  _setupDropZone() {
    const zone = document.getElementById("addPaperDropZone");
    if (!zone) return;

    // 点击选择文件
    zone.addEventListener("click", () => {
      if (this._dropZoneFile) return;
      this.els.pdfFileInput?.click();
    });

    // 拖拽悬停
    zone.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.stopPropagation();
      zone.classList.add("drop-zone-active");
    });
    zone.addEventListener("dragleave", (e) => {
      e.preventDefault();
      e.stopPropagation();
      zone.classList.remove("drop-zone-active");
    });

    // 拖拽放下 → 仅预览，不自动提交
    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      e.stopPropagation();
      zone.classList.remove("drop-zone-active");

      const files = e.dataTransfer?.files;
      if (files && files.length > 0) {
        const file = files[0];
        if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
          alert("仅支持 PDF 文件");
          return;
        }
        this._dropZoneFile = file;
        this._setDropZonePreview(file);
      }
    });
  },

  _setDropZonePreview(file) {
    const content = document.querySelector("#addPaperDropZone .drop-zone-content");
    const preview = document.getElementById("dropZonePreview");
    const fileName = document.getElementById("dropZoneFileName");
    const zone = document.getElementById("addPaperDropZone");

    if (file) {
      if (content) content.style.display = "none";
      if (preview) preview.style.display = "flex";
      if (fileName) fileName.textContent = file.name;
      if (zone) zone.classList.add("has-file");
    } else {
      if (content) content.style.display = "";
      if (preview) preview.style.display = "none";
      if (fileName) fileName.textContent = "";
      if (zone) zone.classList.remove("has-file");
    }
  },

  // 文件选择器回调（点击拖拽区触发）→ 仅预览
  handleDropZoneFile(file) {
    if (!file) return;
    this._dropZoneFile = file;
    this._setDropZonePreview(file);
    if (this.els.pdfFileInput) this.els.pdfFileInput.value = "";
  },

  // 统一的提交入口：优先处理 arXiv 输入，其次处理拖拽文件
  async _submitAddPaper() {
    const arxivVal = this.els.addPaperArxivInput?.value?.trim();

    if (arxivVal) {
      // 有 arXiv ID → 走 arXiv 通道
      await this._doAddPaper("arxiv", arxivVal);
      if (this.els.addPaperArxivInput) this.els.addPaperArxivInput.value = "";
    } else if (this._dropZoneFile) {
      // 有拖拽文件 → 走上传通道
      await this._doAddPaper("upload", this._dropZoneFile);
      this._dropZoneFile = null;
      this._setDropZonePreview(null);
    } else {
      alert("请输入 arXiv ID 或拖拽上传 PDF 文件");
    }
  },

  async _doAddPaper(type, payload) {
    const sessionId = this.state.currentSessionId;
    if (!sessionId) return;

    // 禁用提交按钮防止重复点击
    const btn = this.els.addPaperSubmitBtn;
    const origHTML = btn?.innerHTML;
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 添加中...';
    }

    try {
      this.setConsoleStatus("searching", type === "arxiv" ? "正在下载并解析论文..." : "正在解析并上传论文...");

      let response;
      if (type === "arxiv") {
        response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/papers/custom`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ paper_id: payload }),
        });
      } else {
        const formData = new FormData();
        formData.append("file", payload);
        response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/papers/upload`, {
          method: "POST",
          body: formData,
        });
      }

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "添加论文失败");
      }

      await this.reloadCurrentSession();
      const sessionPapers = this.state.currentSession?.papers || [];
      const uploadedId = data.paper_id;
      if (uploadedId) {
        this.state.currentPaperId = uploadedId;
      } else if (sessionPapers.length > 0) {
        this.state.currentPaperId = sessionPapers[sessionPapers.length - 1].paper_id;
      }
      this.switchViewMode("summary");

      const msg = data.exists ? "论文已存在，已刷新来源列表" : "论文已添加并同步笔记";
      this.setConsoleStatus("search_complete", msg);

      // 关闭弹窗
      if (this.els.addPaperModal) this.els.addPaperModal.classList.remove("active");
    } catch (error) {
      alert(`添加失败：${error.message}`);
      this.setConsoleStatus("search_complete", "添加失败");
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = origHTML || '<i class="fa-solid fa-plus"></i> 添加';
      }
    }
  },

  async removePaper(paperId) {
    if (!this.state.currentSessionId) return;
    if (!confirm("确定移除这篇论文吗？（同时删除 PDF 和元数据）")) return;

    try {
      const response = await fetch(`/api/sessions/${encodeURIComponent(this.state.currentSessionId)}/papers/${encodeURIComponent(paperId)}`, {
        method: "DELETE",
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || `删除失败 (HTTP ${response.status})`);
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
    const paper = (this.state.currentSession?.papers || []).find((item) => item.paper_id === paperId);
    if (!paper) {
      this.setConsoleStatus("error", "找不到这篇论文，请刷新项目后重试。");
      return;
    }
    const previousStatus = paper.status || "pending";
    this.state._updatingPaperId = paperId;
    paper.status = status;
    this.renderPaperList();
    this.updateActionButtons();
    this.updateResearchStage(this.state.currentSession);
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
      this.state.currentSession = data;
      this.state._updatingPaperId = null;
      this.renderConsoleSession();
      const actionLabel = status === "accepted" ? "已纳入综述" : status === "rejected" ? "已排除" : "已移出综述";
      this.setConsoleStatus(data.state, actionLabel);
    } catch (error) {
      paper.status = previousStatus;
      this.state._updatingPaperId = null;
      this.renderPaperList();
      this.updateActionButtons();
      this.setConsoleStatus("error", `状态更新失败：${error.message}`);
    }
  },

  async sendChatMessage() {
    if (!this.els.chatInput) return;
    const message = this.els.chatInput.value.trim();
    if (!message) return;

    // 自动展开聊天区（如果太小则拉起来）
    const dock = document.querySelector(".chat-dock");
    if (dock && dock.getBoundingClientRect().height < 200) {
      dock.style.height = "320px";
    }

    this.appendChatMessage("user", message, this.state.currentViewMode);
    this.els.chatInput.value = "";

    // 显示"处理中"状态
    const loadingMsg = this.appendChatMessage("system", "AI 正在处理你的请求...", "", "⏳ 请稍候");
    let loadingEl = loadingMsg;

    try {
      if (!this.state.currentSessionId) {
        throw new Error("当前没有活跃会话");
      }

      const response = await fetch(`/api/sessions/${encodeURIComponent(this.state.currentSessionId)}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(this.withProvider({
          message,
          view_mode: this.state.currentViewMode,
          chat_mode: this.state.chatMode,
          current_paper_id: this.state.currentPaperId,
          conv_id: this.state.currentConvId,
        })),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || data.message || "发送失败");
      }

      if (data.confirmation_required) {
        this.state.pendingRevision = data.pending_revision || null;
        this.appendChatMessage(
          "agent",
          data.reply || "我判断你这条消息像是要修改内容，请确认后再执行。",
          this.state.currentViewMode,
          data.note || "",
          [
            { label: "确认", variant: "primary", onClick: () => this.confirmPendingRevision() },
            { label: "取消", variant: "secondary", onClick: () => this.cancelPendingRevision() },
          ],
        );
        this.renderChatContext();
        return;
      }

      this.state.pendingRevision = null;

      // 移除"处理中"消息
      if (loadingEl && loadingEl.parentNode) loadingEl.remove();

      this.appendChatMessage("agent", data.reply || "已收到。", this.state.currentViewMode, data.note || "");

      // 展示 RAG 检索状态
      if (data.rag_status === "used") {
        this.appendChatMessage("system", "已检索 " + (data.rag_count || 0) + " 个相关段落", "", "📚 基于论文原文生成本次回答");
      } else if (data.rag_status === "no_results") {
        this.appendChatMessage("system", "未找到与问题相关的原文段落", "", "📝 回答基于已有笔记和摘要");
      } else if (data.rag_status === "not_attempted") {
        // 静默，不显示
      }

      if (data.action_taken) {
        await this.reloadCurrentSession();
        if (data.session_state) {
          this.setConsoleStatus(data.session_state, data.session_state_label || data.session_state);
        }
      }
      this.renderChatContext();
      this.updateContextMeter();
    } catch (error) {
      if (loadingEl && loadingEl.parentNode) loadingEl.remove();
      this.appendChatMessage("agent", `操作失败：${error.message}`, this.state.currentViewMode, "请检查当前会话和模式设置。");
      this.setConsoleStatus("error", `聊天发送失败：${error.message}`);
    }
  },

  async confirmPendingRevision() {
    const pending = this.state.pendingRevision;
    if (!pending) return;
    // 更新确认/取消按钮为执行中状态
    this.renderChatContext();
    await this.executeConfirmedRevision(pending.target, pending.feedback);
  },

  cancelPendingRevision() {
    this.state.pendingRevision = null;
    this.appendChatMessage("agent", "已取消本次修改请求。", this.state.currentViewMode, "你可以继续提问，或重新发起修改。");
    this.renderChatContext();
    // 延迟刷新按钮
    setTimeout(() => this.renderChatContext(), 100);
  },

  async executeConfirmedRevision(target, feedback) {
    if (!feedback || !this.state.currentSessionId) {
      return;
    }

    try {
      this.setConsoleStatus("writing", target === "review" ? "正在修订综述..." : "正在修订笔记...");
      const response = await fetch(`/api/sessions/${encodeURIComponent(this.state.currentSessionId)}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(this.withProvider({
          message: "确认修改",
          view_mode: this.state.currentViewMode,
          chat_mode: "agent",
          current_paper_id: this.state.currentPaperId,
          conv_id: this.state.currentConvId,
          confirmed_revision: true,
          revision_target: target,
          revision_feedback: feedback,
        })),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || data.message || "执行修改失败");
      }

      this.state.pendingRevision = null;
      this.appendChatMessage("agent", data.reply || "修订已完成。", this.state.currentViewMode, data.note || "");
      if (data.action_taken) {
        await this.reloadCurrentSession();
        if (data.session_state) {
          this.setConsoleStatus(data.session_state, data.session_state_label || data.session_state);
        }
      }
      this.renderChatContext();
    } catch (error) {
      this.appendChatMessage("agent", `执行修改失败：${error.message}`, this.state.currentViewMode, "请稍后重试。");
      this.setConsoleStatus("error", `修改执行失败：${error.message}`);
    }
  },

  appendChatMessage(role, text, mode, note = "", actions = []) {
    if (!this.els.chatList) return null;

    // 存入 chatMessages 数组以持久化
    if (role !== "system") {
      this.state.chatMessages.push({
        role, text, view_mode: mode, note,
        timestamp: new Date().toISOString(),
      });
    }

    return this._renderChatMsgDOM(role, text, mode, note, actions);
  },

  _renderChatMsgDOM(role, text, mode, note = "", actions = []) {
    if (!this.els.chatList) return null;
    const msg = document.createElement("div");
    msg.className = "chat-msg";
    if (role === "system") msg.style.opacity = "0.7";
    const roleLabel = role === "user" ? "你" : role === "system" ? "" : "AI";
    const noteHtml = note ? `<span style="font-size:11px;color:var(--subtle);display:block">${this.escapeHtml(note)}</span>` : "";
    const body = document.createElement("span");
    body.className = "markdown";
    body.innerHTML = `${noteHtml}${marked.parse(text)}`;
    msg.innerHTML = `<span class="chat-role">${roleLabel}</span>`;
    msg.appendChild(body);

    if (Array.isArray(actions) && actions.length > 0) {
      const actionRow = document.createElement("div");
      actionRow.style.cssText = "display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;";
      actions.forEach((action) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `tiny-btn ${action.variant === "primary" ? "is-active" : ""}`.trim();
        button.textContent = action.label;
        button.addEventListener("click", function() {
          const allBtns = this.parentNode.querySelectorAll("button");
          allBtns.forEach(b => { b.disabled = true; b.style.opacity = "0.4"; b.style.pointerEvents = "none"; });
          action.onClick();
        });
        actionRow.appendChild(button);
      });
      msg.appendChild(actionRow);
    }

    this.els.chatList.appendChild(msg);
    this.els.chatList.scrollTop = this.els.chatList.scrollHeight;
    return msg;
  },

  async applyReviewFeedback() {
    const feedback = this.state.pendingRevision?.feedback || this.state.lastReviewFeedback || this.els.chatInput?.value.trim() || "";
    if (!feedback) {
      alert("请先输入一条修改建议");
      return;
    }

    const target = this.state.pendingRevision?.target || (this.state.currentViewMode === "review" ? "review" : "report");
    await this.executeConfirmedRevision(target, feedback);
  },

  githubHeaders(extra = {}) {
    const tokenHeaders = window.academicGitHubHeaders ? window.academicGitHubHeaders() : {};
    return { ...extra, ...tokenHeaders };
  },

  showExportMessage(text, type = "success") {
    if (!this.els.exportMessage) return;
    this.els.exportMessage.textContent = text || "";
    this.els.exportMessage.className = `form-message${text ? ` visible ${type}` : ""}`;
  },

  async openExportModal() {
    if (!this.state.currentSessionId || !this.els.exportModal) return;
    this.els.exportModal.style.display = "flex";
    this.showExportMessage("");
    await this.loadGitHubRepositoriesForExport();
  },

  closeExportModal() {
    if (this.els.exportModal) this.els.exportModal.style.display = "none";
  },

  async downloadArtifact(format) {
    const sessionId = this.state.currentSessionId;
    if (!sessionId) return;
    const includeAll = document.getElementById("exportIncludeAll")?.checked !== false;
    this.showExportMessage(`正在生成 ${String(format).toUpperCase()} 文件…`);
    try {
      const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/export?format=${encodeURIComponent(format)}&include_all=${includeAll}`);
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || "导出失败");
      }
      const blob = await response.blob();
      const contentDisposition = response.headers.get("Content-Disposition") || "";
      const match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
      const fallback = `${this.state.currentSession?.topic || "research-output"}.${format}`;
      const filename = match ? decodeURIComponent(match[1]) : fallback;
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      this.showExportMessage(`${filename} 已生成。`, "success");
    } catch (error) {
      this.showExportMessage(error.message || "导出失败，请稍后重试。", "error");
    }
  },

  async loadGitHubRepositoriesForExport() {
    const select = this.els.githubExportRepo;
    const status = document.getElementById("githubExportStatus");
    const token = window.academicGitHubToken ? window.academicGitHubToken() : "";
    if (!select || !status) return;
    if (!token) {
      select.innerHTML = '<option value="">请先在个人中心连接 GitHub</option>';
      status.textContent = "需要连接";
      status.className = "chip warn";
      this.els.githubExportSubmit.disabled = true;
      return;
    }
    try {
      const response = await fetch("/api/github/repositories", { headers: this.githubHeaders() });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "无法读取仓库");
      select.innerHTML = (data.repositories || []).map((repo) => `<option value="${this.escapeHtml(repo.full_name)}">${this.escapeHtml(repo.full_name)}${repo.private ? " · 私有" : ""}</option>`).join("");
      status.textContent = `${(data.repositories || []).length} 个可用仓库`;
      status.className = "chip ok";
      this.els.githubExportSubmit.disabled = !(data.repositories || []).length;
    } catch (error) {
      status.textContent = "连接失效";
      status.className = "chip warn";
      this.els.githubExportSubmit.disabled = true;
      this.showExportMessage(error.message, "error");
    }
  },

  async exportArtifactToGitHub() {
    const repository = this.els.githubExportRepo?.value || "";
    if (!repository || !this.state.currentSessionId) return;
    const path = document.getElementById("githubExportPath")?.value.trim() || "research/review.md";
    const branch = document.getElementById("githubExportBranch")?.value.trim() || null;
    const includeAll = document.getElementById("exportIncludeAll")?.checked !== false;
    this.els.githubExportSubmit.disabled = true;
    this.showExportMessage("正在向 GitHub 提交研究产物…");
    try {
      const response = await fetch(`/api/sessions/${encodeURIComponent(this.state.currentSessionId)}/export/github`, {
        method: "POST",
        headers: this.githubHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ repository, path, branch, format: "md", include_all: includeAll }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "GitHub 导出失败");
      this.showExportMessage(`已提交到 ${data.repository}/${data.path}`, "success");
      if (data.content_url) window.open(data.content_url, "_blank", "noopener,noreferrer");
    } catch (error) {
      this.showExportMessage(error.message, "error");
    } finally {
      this.els.githubExportSubmit.disabled = false;
    }
  },

  openRepositoryResearch() {
    if (!this.els.repositoryResearchModal) return;
    this.els.repositoryResearchModal.style.display = "flex";
    this.setRepositoryMode("specified");
    if (this.els.repositoryResearchResult) this.els.repositoryResearchResult.innerHTML = "";
    document.getElementById("repositoryTarget")?.focus();
  },

  closeRepositoryResearch() {
    if (this.els.repositoryResearchModal) this.els.repositoryResearchModal.style.display = "none";
  },

  setRepositoryMode(mode) {
    this.state.repositoryMode = mode === "discovery" ? "discovery" : "specified";
    document.querySelectorAll("[data-repo-mode]").forEach((button) => {
      const active = button.dataset.repoMode === this.state.repositoryMode;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", String(active));
    });
    const input = document.getElementById("repositoryTarget");
    const label = document.getElementById("repositoryTargetLabel");
    if (input) input.placeholder = this.state.repositoryMode === "discovery" ? "例如 RAG evaluation framework" : "例如 openai/openai-python";
    if (label) label.textContent = this.state.repositoryMode === "discovery" ? "希望检索的仓库主题" : "仓库地址或 owner/repo";
  },

  async runRepositoryResearch() {
    const target = document.getElementById("repositoryTarget")?.value.trim() || "";
    const question = document.getElementById("repositoryQuestion")?.value.trim() || "";
    const resultBox = this.els.repositoryResearchResult;
    const submit = document.getElementById("repositoryResearchSubmit");
    if (!target) {
      resultBox.innerHTML = '<div class="form-message visible error">请填写仓库或检索主题。</div>';
      return;
    }
    submit.disabled = true;
    resultBox.innerHTML = '<div class="loading-state"><i class="fa-solid fa-circle-notch fa-spin"></i> 正在读取仓库结构、README 和关键代码文件…</div>';
    try {
      const body = this.withProvider({
        repository: this.state.repositoryMode === "specified" ? target : null,
        query: this.state.repositoryMode === "discovery" ? target : null,
        question,
        session_id: this.state.currentSessionId,
      });
      const response = await fetch("/api/github/research", {
        method: "POST",
        headers: this.githubHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(body),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "仓库调研失败");
      resultBox.innerHTML = `<div class="markdown-body">${marked.parse(data.report || "调研完成")}</div>`;
      await this.reloadCurrentSession();
      this.renderRepositorySources();
    } catch (error) {
      resultBox.innerHTML = `<div class="form-message visible error">${this.escapeHtml(error.message)}</div>`;
    } finally {
      submit.disabled = false;
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
    this._syncVditorTheme();
  },

  _syncVditorTheme() {
    const isDark = document.body.dataset.theme === "dark";
    Object.values(this._vditors || {}).forEach(vd => {
      try { vd.setTheme(isDark ? "dark" : "classic"); } catch(e) {}
    });
    // 补丁：深色模式下 IR 编辑区文字颜色
    document.querySelectorAll(".vditor-ir").forEach(ir => {
      ir.style.color = isDark ? "var(--text, #e8e8e8)" : "";
    });
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

  // ═══════════════════════════════════════════
  //  工具管理
  // ═══════════════════════════════════════════

  async openToolManager() {
    if (!this.els.toolManagerModal) return;
    this.els.toolManagerModal.style.display = "flex";
    await this.loadToolList();
  },

  closeToolManager() {
    if (this.els.toolManagerModal) {
      this.els.toolManagerModal.style.display = "none";
    }
  },

  async loadToolList() {
    if (!this.els.toolManagerList) return;
    this.els.toolManagerList.innerHTML = '<div class="empty-state">加载中...</div>';
    try {
      const response = await fetch("/api/tools");
      const data = await response.json();
      if (!response.ok) throw new Error("加载失败");
      this._toolData = data.tools;
      this._renderToolList(data.tools);
      if (this.els.toolEnabledCount) {
        this.els.toolEnabledCount.textContent = "已启用: " + data.enabled_count;
      }
      if (this.els.toolDisabledCount) {
        this.els.toolDisabledCount.textContent = "已禁用: " + (data.total_count - data.enabled_count);
      }
    } catch (error) {
      this.els.toolManagerList.innerHTML = '<div class="empty-state">加载失败: ' + error.message + '</div>';
    }
  },

  _renderToolList(tools) {
    if (!this.els.toolManagerList) return;
    var categoryLabels = { search: "学术搜索", pdf: "PDF 处理", file: "文件操作", chat: "对话检索", notes: "笔记生成", register: "收录管理" };
    var categoryIcons = { search: "fa-magnifying-glass", pdf: "fa-file-pdf", file: "fa-file-lines", chat: "fa-comments", notes: "fa-pen-fancy", register: "fa-clipboard-check" };
    var categoryIconClass = { search: "tool-icon-search", pdf: "tool-icon-pdf", file: "tool-icon-file", chat: "tool-icon-chat", notes: "tool-icon-notes", register: "tool-icon-register" };

    var html = "";
    for (var i = 0; i < tools.length; i++) {
      var tool = tools[i];
      var cat = tool.category || "search";
      var icon = categoryIcons[cat] || "fa-wrench";
      var iconCls = categoryIconClass[cat] || "tool-icon-search";
      var catLabel = categoryLabels[cat] || cat;
      var checkedAttr = tool.enabled ? " checked" : "";
      var pipelineTag = tool.pipeline ? '<span class="tool-pipeline">⏱ ' + this.escapeHtml(tool.pipeline) + '</span>' : '';
      html += '<div class="tool-manager-item">' +
        '<div class="tool-icon ' + iconCls + '"><i class="fa-solid ' + icon + '"></i></div>' +
        '<div class="tool-info">' +
          '<div class="tool-name">' + this.escapeHtml(tool.name) + '</div>' +
          '<div class="tool-desc">' + this.escapeHtml(tool.description) + '</div>' +
          '<div class="tool-category">' + catLabel + pipelineTag + '</div>' +
        '</div>' +
        '<label class="tool-toggle">' +
          '<input type="checkbox" data-tool="' + tool.name + '"' + checkedAttr + ' onchange="notebooklm._onToolToggle(this)">' +
          '<span class="slider"></span>' +
        '</label>' +
      '</div>';
    }
    this.els.toolManagerList.innerHTML = html;
  },

  _onToolToggle(checkbox) {
    var toolName = checkbox.dataset.tool;
    if (this._toolData) {
      for (var i = 0; i < this._toolData.length; i++) {
        if (this._toolData[i].name === toolName) {
          this._toolData[i].enabled = checkbox.checked;
          break;
        }
      }
    }
    if (this._toolData && this.els.toolEnabledCount && this.els.toolDisabledCount) {
      var enabled = 0;
      for (var j = 0; j < this._toolData.length; j++) {
        if (this._toolData[j].enabled) enabled++;
      }
      this.els.toolEnabledCount.textContent = "已启用: " + enabled;
      this.els.toolDisabledCount.textContent = "已禁用: " + (this._toolData.length - enabled);
    }
  },

  async saveToolConfig() {
    if (!this._toolData) return;
    var toolsMap = {};
    for (var i = 0; i < this._toolData.length; i++) {
      toolsMap[this._toolData[i].name] = this._toolData[i].enabled;
    }
    try {
      var response = await fetch("/api/tools/batch-toggle", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tools: toolsMap }),
      });
      if (!response.ok) throw new Error("保存失败");
      this.closeToolManager();
      this.setConsoleStatus("search_complete", "工具配置已保存，下次调研将使用新配置");
    } catch (error) {
      alert("保存工具配置失败: " + error.message);
    }
  },

  async resetToolConfig() {
    if (!confirm("确定恢复所有工具为默认配置吗？")) return;
    try {
      var response = await fetch("/api/tools/reset", { method: "POST" });
      if (!response.ok) throw new Error("重置失败");
      var data = await response.json();
      this._toolData = data.tools;
      this._renderToolList(data.tools);
      if (this.els.toolEnabledCount) {
        var en = 0;
        for (var i = 0; i < data.tools.length; i++) { if (data.tools[i].enabled) en++; }
        this.els.toolEnabledCount.textContent = "已启用: " + en;
      }
      if (this.els.toolDisabledCount) {
        this.els.toolDisabledCount.textContent = "已禁用: " + (data.tools.length - en);
      }
      this.setConsoleStatus("search_complete", "工具配置已恢复默认");
    } catch (error) {
      alert("重置失败: " + error.message);
    }
  },

  // ════════════ Skills 页面逻辑 ════════════
  _skillsState: {
    currentSkillId: null,
    skills: [],
    _skillVditor: null,
    _defaultSkills: null,
    _presets: {},
  },

  async initSkills() {
    // 弹窗按钮绑定
    document.getElementById("skillCancelBtn")?.addEventListener("click", () => this.closeSkillModal());
    document.getElementById("skillSaveBtn")?.addEventListener("click", () => this.saveSkill());
    document.getElementById("skillDeleteCancelBtn")?.addEventListener("click", () => this.closeSkillDeleteModal());
    document.getElementById("skillDeleteConfirmBtn")?.addEventListener("click", () => this.confirmDeleteSkill());
    document.getElementById("skillShowDefaultBtn")?.addEventListener("click", () => this.showSkillDefault());
    document.getElementById("skillDefaultCloseBtn")?.addEventListener("click", () => this.closeSkillDefaultModal());
    document.getElementById("skillDefaultUseBtn")?.addEventListener("click", () => this.useSkillDefault());
    document.getElementById("skillDeleteBtn")?.addEventListener("click", () => {
      this.openSkillDeleteConfirm(this._skillsState.currentSkillId);
    });
    this._initSkillCharCounter();
    await this.loadAllSkills();
    // 预加载默认 skill 内容，完成后重新渲染以显示默认卡片
    await this._loadDefaultSkills();
    this.renderSkillsByType("search");
    this.renderSkillsByType("notes");
    this.renderSkillsByType("write");
  },

  async _loadDefaultSkills() {
    try {
      const resp = await fetch("/api/skills/defaults");
      const data = await resp.json();
      this._skillsState._defaultSkills = data.defaults || {};
      const presetResp = await fetch("/api/skills/presets");
      const presetData = await presetResp.json();
      this._skillsState._presets = presetData.presets || {};
    } catch (e) {
      this._skillsState._defaultSkills = {};
      this._skillsState._presets = {};
    }
  },

  async loadAllSkills() {
    try {
      const resp = await fetch("/api/skills");
      const data = await resp.json();
      this._skillsState.skills = data.skills || [];
    } catch (e) {
      this._skillsState.skills = [];
    }
    this.renderSkillsByType("search");
    this.renderSkillsByType("notes");
    this.renderSkillsByType("write");
  },

  renderSkillsByType(type) {
    const grid = document.getElementById("skillsGrid" + type.charAt(0).toUpperCase() + type.slice(1));
    if (!grid) return;
    const skills = this._skillsState.skills.filter(function(s) { return s.type === type; });
    grid.innerHTML = "";

    var labels = { search: "AI 检索论文", notes: "笔记生成", write: "综述生成" };
    var iconMap = { search: "fa-magnifying-glass", notes: "fa-note-sticky", write: "fa-pen-to-square" };
    var self = this;

    // ━━━ 始终显示默认 Skill 卡片（系统内置，不可编辑）━━━
    var defaults = this._skillsState._defaultSkills;
    var def = (defaults && defaults[type]) ? defaults[type] : null;
    var defCard = document.createElement("article");
    defCard.className = "skill-card skill-card-default";
    var defPreview = def ? (def.content || "").replace(/^#+\s*/gm, "").replace(/\n/g, " ").trim().slice(0, 60) : "";
    defCard.innerHTML =
      '<div class="skill-card-icon ' + type + ' default-icon"><i class="fa-solid ' + (iconMap[type] || 'fa-file') + '"></i></div>' +
      '<div class="skill-card-body">' +
        '<h4 title="' + self.escapeHtml(def ? def.title : "默认策略") + '">' +
          '<i class="fa-solid fa-shield-halved" style="font-size:10px;color:var(--accent);margin-right:4px;" title="系统内置"></i>' +
          self.escapeHtml(def ? def.title : "默认策略") +
        '</h4>' +
        '<div class="skill-card-meta"><span class="skill-default-badge">系统内置</span></div>' +
        (defPreview ? '<div class="skill-card-preview">' + self.escapeHtml(defPreview) + '</div>' : '') +
      '</div>';
    defCard.addEventListener("click", function() { self.showSkillDefaultForType(type); });
    defCard.title = "查看系统默认策略（不可编辑）";
    grid.appendChild(defCard);

    if (type === "write") {
      Object.entries(this._skillsState._presets || {}).forEach(function(entry) {
        var presetId = entry[0];
        var preset = entry[1];
        var presetCard = document.createElement("article");
        presetCard.className = "skill-card skill-card-preset";
        presetCard.innerHTML =
          '<div class="skill-card-icon write"><i class="fa-solid fa-book-open"></i></div>' +
          '<div class="skill-card-body"><h4>' + self.escapeHtml(preset.title) + '</h4>' +
          '<div class="skill-card-meta"><span class="skill-preset-badge">写作预设</span></div>' +
          '<div class="skill-card-preview">' + self.escapeHtml(preset.description || "") + '</div></div>' +
          '<button class="skill-preset-copy" type="button" aria-label="复制为可编辑 Skill"><i class="fa-solid fa-copy"></i></button>';
        presetCard.querySelector("button").addEventListener("click", function(event) {
          event.stopPropagation();
          self.copySkillPreset(presetId);
        });
        presetCard.addEventListener("click", function() {
          self._skillsState._defaultViewType = "write";
          document.getElementById("skillDefaultTitle").textContent = preset.title;
          document.getElementById("skillDefaultContent").textContent = preset.content;
          document.getElementById("skillDefaultModal").classList.add("active");
        });
        grid.appendChild(presetCard);
      });
    }

    // ━━━ 用户自定义 Skill 卡片 ━━━
    skills.forEach(function(skill) {
      var card = document.createElement("article");
      card.className = "skill-card";
      var preview = (skill.content || "").replace(/^#+\s*/gm, "").replace(/\n/g, " ").trim().slice(0, 60);
      card.innerHTML =
        '<div class="skill-card-icon ' + type + '"><i class="fa-solid ' + (iconMap[type] || 'fa-file') + '"></i></div>' +
        '<div class="skill-card-body">' +
          '<h4 title="' + self.escapeHtml(skill.title) + '">' + self.escapeHtml(skill.title) + '</h4>' +
          '<div class="skill-card-meta"><span>' + self.formatDate(skill.updated_at || skill.created_at) + '</span></div>' +
          (preview ? '<div class="skill-card-preview">' + self.escapeHtml(preview) + '</div>' : '') +
        '</div>';
      card.addEventListener("click", function() { self.openEditSkillModal(skill.skill_id); });

      var delBtn = document.createElement("button");
      delBtn.className = "skill-card-delete";
      delBtn.title = "删除";
      delBtn.innerHTML = '<i class="fa-solid fa-trash"></i>';
      delBtn.addEventListener("click", function(e) {
        e.stopPropagation();
        e.preventDefault();
        self.openSkillDeleteConfirm(skill.skill_id);
      });
      card.appendChild(delBtn);
      grid.appendChild(card);
    });

    // 如果默认也未加载，显示加载占位
    if (!def && skills.length === 0) {
      var emptyEl = document.createElement("div");
      emptyEl.className = "skills-empty";
      emptyEl.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 加载中...';
      grid.appendChild(emptyEl);
    }
  },

  async copySkillPreset(presetId) {
    try {
      const response = await fetch(`/api/skills/presets/${encodeURIComponent(presetId)}/copy`, { method: "POST" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "复制失败");
      await this.loadAllSkills();
    } catch (error) {
      alert(error.message);
    }
  },

  openCreateModal: function(type) {
    this._skillsState.currentSkillId = null;
    document.getElementById("skillModalTitle").textContent = "创建 Skill";
    document.getElementById("skillModalDesc").textContent = "自定义提示词模板，控制 Agent 在特定阶段的行为策略。留空则使用系统默认策略。";
    document.getElementById("skillTypeSelect").value = type || "search";
    document.getElementById("skillTypeSelect").disabled = false;
    document.getElementById("skillTitleInput").value = "";
    document.getElementById("skillDeleteBtn").style.display = "none";
    document.getElementById("skillModal").classList.add("active");
    // 初始化 Vditor 编辑器
    this._initSkillVditor("");
    var self = this;
    setTimeout(function() { document.getElementById("skillTitleInput").focus(); }, 100);
  },

  openEditSkillModal: async function(skillId) {
    try {
      var resp = await fetch("/api/skills/" + encodeURIComponent(skillId));
      if (!resp.ok) throw new Error("Skill 不存在");
      var skill = await resp.json();
      this._skillsState.currentSkillId = skillId;
      document.getElementById("skillModalTitle").textContent = "编辑 Skill";
      document.getElementById("skillModalDesc").textContent = "修改后点击保存即可更新。";
      document.getElementById("skillTypeSelect").value = skill.type;
      document.getElementById("skillTypeSelect").disabled = true;
      document.getElementById("skillTitleInput").value = skill.title;
      document.getElementById("skillDeleteBtn").style.display = "inline-flex";
      document.getElementById("skillModal").classList.add("active");
      // 初始化 Vditor 编辑器并填充内容
      this._initSkillVditor(skill.content || "");
    } catch (e) {
      alert("加载 Skill 失败：" + e.message);
    }
  },

  closeSkillModal: function() {
    document.getElementById("skillModal").classList.remove("active");
    this._destroySkillVditor();
    this._skillsState.currentSkillId = null;
  },

  saveSkill: async function() {
    var type = document.getElementById("skillTypeSelect").value;
    var title = document.getElementById("skillTitleInput").value.trim();
    var content = this._getSkillVditorContent();

    if (!title) { alert("标题不能为空"); return; }
    if (!content) { alert("Skill 内容不能为空"); return; }
    if (content.length > 16384) { alert("内容不能超过 16384 字符"); return; }

    var skillId = this._skillsState.currentSkillId;
    var saveBtn = document.getElementById("skillSaveBtn");
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 保存中...';
    var self = this;

    try {
      if (skillId) {
        var resp1 = await fetch("/api/skills/" + encodeURIComponent(skillId), {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: title, content: content }),
        });
        if (!resp1.ok) {
          var err1 = await resp1.json();
          throw new Error(err1.detail || "更新失败");
        }
      } else {
        var resp2 = await fetch("/api/skills", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: title, type: type, content: content }),
        });
        if (!resp2.ok) {
          var err2 = await resp2.json();
          throw new Error(err2.detail || "创建失败");
        }
      }
      self.closeSkillModal();
      await self.loadAllSkills();
    } catch (e) {
      alert("保存失败：" + e.message);
    } finally {
      saveBtn.disabled = false;
      saveBtn.innerHTML = '<i class="fa-solid fa-check"></i> 保存';
    }
  },

  openSkillDeleteConfirm: async function(skillId) {
    this._skillsState._deleteTargetId = skillId;
    var usageEl = document.getElementById("skillDeleteUsage");
    usageEl.textContent = "加载中...";
    try {
      var resp = await fetch("/api/skills/" + encodeURIComponent(skillId) + "/usage");
      var data = await resp.json();
      if (data.count > 0) {
        usageEl.textContent = "该 Skill 被 " + data.count + " 个 Session 引用，删除后这些 Session 将回退到默认提示词。";
      } else {
        usageEl.textContent = "";
      }
    } catch (e) {
      usageEl.textContent = "";
    }
    document.getElementById("skillDeleteModal").classList.add("active");
  },

  closeSkillDeleteModal: function() {
    document.getElementById("skillDeleteModal").classList.remove("active");
    this._skillsState._deleteTargetId = null;
  },

  confirmDeleteSkill: async function() {
    var skillId = this._skillsState._deleteTargetId;
    if (!skillId) return;
    try {
      var resp = await fetch("/api/skills/" + encodeURIComponent(skillId), { method: "DELETE" });
      if (!resp.ok) throw new Error("删除失败");
      this.closeSkillDeleteModal();
      if (this._skillsState.currentSkillId === skillId) {
        this.closeSkillModal();
      }
      await this.loadAllSkills();
    } catch (e) {
      alert("删除失败：" + e.message);
    }
  },

  _initSkillCharCounter: function() {
    // Vditor 模式下通过轮询更新字符计数
    var self = this;
    var counter = document.getElementById("skillCharCount");
    if (counter) {
      this._skillsState._charPollTimer = setInterval(function() {
        var len = (self._getSkillVditorContent() || "").length;
        counter.textContent = len + " / 16384";
        counter.style.color = len > 16384 ? "var(--danger)" : "var(--muted)";
      }, 800);
    }
  },

  // ━━━ Vditor 编辑器（复用笔记编辑逻辑）━━━
  _initSkillVditor: function(content) {
    this._destroySkillVditor();
    if (typeof Vditor === "undefined") return;

    var container = document.getElementById("skillEditorContainer");
    if (!container) return;
    container.innerHTML = "";

    var isDark = document.body.dataset.theme === "dark";
    var self = this;

    this._skillsState._skillVditor = new Vditor(container, {
      height: Math.max(360, window.innerHeight * 0.4),
      mode: "ir",
      value: content || "",
      placeholder: "在此编辑 Skill 内容，支持 Markdown 格式...",
      theme: isDark ? "dark" : "classic",
      cdn: "https://cdn.jsdelivr.net/npm/vditor@3.10.6",
      toolbar: [
        "headings", "bold", "italic", "strike", "|",
        "list", "ordered-list", "check", "|",
        "quote", "code", "inline-code", "|",
        "undo", "redo",
      ],
      cache: { enable: false },
      after: function() {
        var reset = container.querySelector(".vditor-reset");
        if (reset) reset.setAttribute("spellcheck", "false");
      },
    });
  },

  _destroySkillVditor: function() {
    if (this._skillsState._skillVditor) {
      try { this._skillsState._skillVditor.destroy(); } catch(e) {}
      this._skillsState._skillVditor = null;
    }
    if (this._skillsState._charPollTimer) {
      clearInterval(this._skillsState._charPollTimer);
      this._skillsState._charPollTimer = null;
    }
    var container = document.getElementById("skillEditorContainer");
    if (container) container.innerHTML = "";
  },

  _getSkillVditorContent: function() {
    var vd = this._skillsState._skillVditor;
    if (vd) return vd.getValue();
    return "";
  },

  // ━━━ 查看默认 Skill ━━━
  showSkillDefault: async function() {
    var type = document.getElementById("skillTypeSelect").value;
    await this._showDefaultForType(type);
  },

  showSkillDefaultForType: async function(type) {
    await this._showDefaultForType(type);
  },

  _showDefaultForType: async function(type) {
    var defaults = this._skillsState._defaultSkills;

    if (!defaults || Object.keys(defaults).length === 0) {
      await this._loadDefaultSkills();
      defaults = this._skillsState._defaultSkills;
    }

    if (!defaults || Object.keys(defaults).length === 0) {
      alert("无法加载默认策略，请检查网络连接后重试。");
      return;
    }

    var def = defaults[type];
    if (!def || !def.content) {
      alert("该类型暂无默认策略。");
      return;
    }

    document.getElementById("skillDefaultTitle").textContent = def.title || type;
    document.getElementById("skillDefaultContent").textContent = def.content;
    // 查看模式下隐藏"使用此内容"按钮（从卡片点击查看默认时不需要）
    var useBtn = document.getElementById("skillDefaultUseBtn");
    if (useBtn) useBtn.style.display = "";
    document.getElementById("skillDefaultModal").classList.add("active");
  },

  showSkillDefault: async function() {
    var type = document.getElementById("skillTypeSelect").value;
    await this._showDefaultForType(type);
  },

  closeSkillDefaultModal: function() {
    document.getElementById("skillDefaultModal").classList.remove("active");
  },

  useSkillDefault: function() {
    var content = document.getElementById("skillDefaultContent").textContent || "";
    if (content) {
      this._initSkillVditor(content);
    }
    this.closeSkillDefaultModal();
  },

  loadHomeSkillSelectors: async function() {
    try {
      var resp = await fetch("/api/skills");
      var data = await resp.json();
      var skills = data.skills || [];
      var types = ["search", "notes", "write"];
      types.forEach(function(type) {
        var select = document.getElementById("skillSelect" + type.charAt(0).toUpperCase() + type.slice(1));
        if (!select) return;
        select.innerHTML = '<option value="">— 默认提示词 —</option>';
        skills.filter(function(s) { return s.type === type; }).forEach(function(s) {
          var opt = document.createElement("option");
          opt.value = s.skill_id;
          opt.textContent = s.title;
          select.appendChild(opt);
        });
      });
    } catch (e) {
      // ignore
    }
  },

  collectSelectedSkills: function() {
    var skills = {};
    var types = ["search", "notes", "write"];
    types.forEach(function(type) {
      var select = document.getElementById("skillSelect" + type.charAt(0).toUpperCase() + type.slice(1));
      skills[type] = select && select.value ? select.value : null;
    });
    return skills;
  },

};

/* ═══════════════════════════════════════════
   全局 Copilot 侧边栏交互逻辑
   ═══════════════════════════════════════════ */

var GlobalCopilot = {
  _open: false,
  _loading: false,
  _messages: [],
  _currentSessionId: null,
  _sessions: [],
  _knowledgeSessions: [],
  _selectedKnowledgeSessionIds: [],
  _knowledgeSelectionInitialized: false,
  _els: {},

  _toolList: [],
  _selectedTools: [],

  init: function () {
    var self = this;
    // 缓存 DOM 元素
    this._els = {
      sidebar: document.getElementById("copilotSidebar"),
      toggle: document.getElementById("copilotToggle"),
      close: document.getElementById("copilotClose"),
      messages: document.getElementById("copilotMessages"),
      input: document.getElementById("copilotInput"),
      send: document.getElementById("copilotSend"),
      rebuild: document.getElementById("copilotRebuild"),
      newChat: document.getElementById("copilotNewChat"),
      sessionsList: document.getElementById("copilotSessionsList"),
      knowledgeList: document.getElementById("copilotKnowledgeList"),
      knowledgeSelectAll: document.getElementById("copilotKnowledgeSelectAll"),
      knowledgeHint: document.getElementById("copilotKnowledgeHint"),
      toolsSection: document.getElementById("copilotToolsSection"),
      toolsHead: document.getElementById("copilotToolsHead"),
      toolsList: document.getElementById("copilotToolsList"),
      toolsToggle: document.getElementById("copilotToolsToggle"),
      sessionCount: document.getElementById("copilotSessionCount"),
      paperCount: document.getElementById("copilotPaperCount"),
      draftCount: document.getElementById("copilotDraftCount"),
    };

    if (!this._els.sidebar) return; // 非首页不初始化

    // 绑定事件
    if (this._els.toggle) {
      this._els.toggle.addEventListener("click", function () { self.toggle(); });
    }
    if (this._els.close) {
      this._els.close.addEventListener("click", function () { self.close(); });
    }
    if (this._els.send) {
      this._els.send.addEventListener("click", function () { self.send(); });
    }
    if (this._els.input) {
      this._els.input.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          self.send();
        }
      });
      // 自动调整高度
      this._els.input.addEventListener("input", function () {
        this.style.height = "auto";
        this.style.height = Math.min(this.scrollHeight, 100) + "px";
      });
    }
    if (this._els.rebuild) {
      this._els.rebuild.addEventListener("click", function () { self.rebuildIndex(); });
    }
    if (this._els.knowledgeSelectAll) {
      this._els.knowledgeSelectAll.addEventListener("click", function () {
        self.selectAllKnowledgeSessions();
      });
    }

    // 绑定工具面板的展开/收起
    if (this._els.toolsHead) {
      this._els.toolsHead.addEventListener("click", function () {
        self.toggleTools();
      });
    }

    // 绑定新会话按钮
    if (this._els.newChat) {
      this._els.newChat.addEventListener("click", function () { self.createNewSession(); });
    }

    // 绑定建议问题点击
    var suggestions = document.querySelectorAll(".copilot-suggestion");
    for (var i = 0; i < suggestions.length; i++) {
      suggestions[i].addEventListener("click", function () {
        var query = this.getAttribute("data-query");
        if (query) {
          self._els.input.value = query;
          self.send();
        }
      });
    }

    // 点击遮罩关闭
    var overlay = document.getElementById("copilotOverlay");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.className = "copilot-overlay";
      overlay.id = "copilotOverlay";
      document.body.appendChild(overlay);
      overlay.addEventListener("click", function () { self.close(); });
    }

    // 加载统计信息
    this._loadStats();
    this.loadKnowledgeSessions();
  },

  toggle: function () {
    if (this._open) {
      this.close();
    } else {
      this.open();
    }
  },

  open: function () {
    this._open = true;
    this._els.sidebar.classList.add("open");
    this._els.sidebar.setAttribute("aria-hidden", "false");
    var overlay = document.getElementById("copilotOverlay");
    if (overlay) overlay.classList.add("active");
    this._loadStats();
    this.loadSessions();
    this.loadKnowledgeSessions();
    this.loadTools();
    // 聚焦输入框
    setTimeout(function () {
      var inp = document.getElementById("copilotInput");
      if (inp) inp.focus();
    }, 300);
  },

  close: function () {
    this._open = false;
    this._els.sidebar.classList.remove("open");
    this._els.sidebar.setAttribute("aria-hidden", "true");
    var overlay = document.getElementById("copilotOverlay");
    if (overlay) overlay.classList.remove("active");
  },

  _loadStats: function () {
    var self = this;
    fetch("/api/knowledge/stats")
      .then(function (r) { return r.json(); })
      .then(function (stats) {
        if (self._els.sessionCount) self._els.sessionCount.textContent = stats.session_count || 0;
        if (self._els.paperCount) self._els.paperCount.textContent = stats.total_papers || 0;
        if (self._els.draftCount) self._els.draftCount.textContent = stats.total_drafts || 0;
      })
      .catch(function () {
        // 静默失败
      });
  },

  send: function () {
    var self = this;
    var message = (this._els.input.value || "").trim();
    if (!message || this._loading) return;

    this._loading = true;
    this._els.input.value = "";
    this._els.input.style.height = "auto";
    this._els.send.disabled = true;

    // 添加用户消息
    this._addMessage("user", message);
    // 显示打字动画
    this._showTyping();

    var selectedSessionIds = this._getSelectedKnowledgeSessionIds();
    fetch("/api/knowledge/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(self.withProvider({
        message: message,
        copilot_session_id: self._currentSessionId || "",
        session_ids: selectedSessionIds,
      })),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        self._hideTyping();
        var reply = data.reply || "抱歉，无法生成回答。";
        var meta = "";
        if (data.has_rag) {
          var scopeCount = selectedSessionIds.length || 0;
          meta = "基于 " + data.search_count + " 条资料";
          if (scopeCount) meta += "，范围 " + scopeCount + " 个项目";
        }
        self._addMessage("agent", reply, meta);
        self._loading = false;
        self._els.send.disabled = false;
        self._els.input.focus();
        self._updateContextMeter();
      })
      .catch(function (err) {
        self._hideTyping();
        self._addMessage("agent", "抱歉，请求失败：" + err.message);
        self._loading = false;
        self._els.send.disabled = false;
      });
  },

  _addMessage: function (role, text, meta) {
    var msgDiv = document.createElement("div");
    msgDiv.className = "copilot-msg copilot-msg--" + role;
    msgDiv.textContent = text;

    if (meta) {
      var metaDiv = document.createElement("div");
      metaDiv.className = "copilot-msg-meta";
      var badge = document.createElement("span");
      badge.className = "copilot-msg-rag-badge";
      badge.textContent = "📚 " + meta;
      metaDiv.appendChild(badge);
      msgDiv.appendChild(metaDiv);
    }

    // 隐藏欢迎消息
    var welcome = this._els.messages.querySelector(".copilot-welcome");
    if (welcome) welcome.style.display = "none";

    this._els.messages.appendChild(msgDiv);
    this._els.messages.scrollTop = this._els.messages.scrollHeight;
  },

  _showTyping: function () {
    var typing = document.createElement("div");
    typing.className = "copilot-typing";
    typing.id = "copilotTyping";
    typing.innerHTML = "<span></span><span></span><span></span>";
    var welcome = this._els.messages.querySelector(".copilot-welcome");
    if (welcome) welcome.style.display = "none";
    this._els.messages.appendChild(typing);
    this._els.messages.scrollTop = this._els.messages.scrollHeight;
  },

  _hideTyping: function () {
    var typing = document.getElementById("copilotTyping");
    if (typing) typing.remove();
  },

  rebuildIndex: function () {
    var self = this;
    if (!confirm("确定要重建全局知识库索引吗？这可能需要几秒钟。")) return;
    var btn = this._els.rebuild;
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> 重建中...';
    fetch("/api/knowledge/rebuild", { method: "POST" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-arrows-rotate"></i> 刷新索引';
        self._loadStats();
        // 添加系统消息
        self._addMessage("agent", "✅ 知识库索引已重建完成。共索引 " + (data.stats && data.stats.session_count || "?") + " 个 Session。");
      })
      .catch(function (err) {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-arrows-rotate"></i> 刷新索引';
        self._addMessage("agent", "❌ 索引重建失败：" + err.message);
      });
  },

  loadKnowledgeSessions: function () {
    var self = this;
    fetch("/api/knowledge/sessions")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        self._knowledgeSessions = data.sessions || [];
        if (!self._knowledgeSelectionInitialized) {
          self._selectedKnowledgeSessionIds = self._knowledgeSessions.map(function (s) {
            return s.session_id;
          });
          self._knowledgeSelectionInitialized = true;
        } else {
          var existing = {};
          for (var i = 0; i < self._knowledgeSessions.length; i++) {
            existing[self._knowledgeSessions[i].session_id] = true;
          }
          self._selectedKnowledgeSessionIds = self._selectedKnowledgeSessionIds.filter(function (sid) {
            return existing[sid];
          });
        }
        self._renderKnowledgeSessions();
        self._updateKnowledgeHint();
      })
      .catch(function () {
        if (self._els.knowledgeList) {
          self._els.knowledgeList.innerHTML = '<div class="copilot-knowledge-empty">知识范围加载失败</div>';
        }
      });
  },

  selectAllKnowledgeSessions: function () {
    this._selectedKnowledgeSessionIds = (this._knowledgeSessions || []).map(function (s) {
      return s.session_id;
    });
    this._renderKnowledgeSessions();
    this._updateKnowledgeHint();
  },

  _getSelectedKnowledgeSessionIds: function () {
    if (!this._knowledgeSelectionInitialized && this._knowledgeSessions.length) {
      this._selectedKnowledgeSessionIds = this._knowledgeSessions.map(function (s) {
        return s.session_id;
      });
      this._knowledgeSelectionInitialized = true;
    }
    return this._selectedKnowledgeSessionIds.slice();
  },

  _renderKnowledgeSessions: function () {
    var self = this;
    if (!this._els.knowledgeList) return;
    var sessions = this._knowledgeSessions || [];
    if (sessions.length === 0) {
      this._els.knowledgeList.innerHTML = '<div class="copilot-knowledge-empty">暂无可用项目</div>';
      return;
    }

    var selected = {};
    for (var i = 0; i < this._selectedKnowledgeSessionIds.length; i++) {
      selected[this._selectedKnowledgeSessionIds[i]] = true;
    }

    this._els.knowledgeList.innerHTML = "";
    sessions.forEach(function (session) {
      var label = document.createElement("label");
      label.className = "copilot-knowledge-check";

      var checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = !!selected[session.session_id];
      checkbox.addEventListener("change", function () {
        if (checkbox.checked) {
          if (self._selectedKnowledgeSessionIds.indexOf(session.session_id) === -1) {
            self._selectedKnowledgeSessionIds.push(session.session_id);
          }
        } else {
          self._selectedKnowledgeSessionIds = self._selectedKnowledgeSessionIds.filter(function (sid) {
            return sid !== session.session_id;
          });
        }
        self._updateKnowledgeHint();
      });

      var title = document.createElement("span");
      title.className = "copilot-knowledge-title";
      title.textContent = session.topic || "未命名项目";

      var count = document.createElement("span");
      count.className = "copilot-knowledge-count";
      count.textContent = (session.paper_count || 0) + " 篇";

      label.appendChild(checkbox);
      label.appendChild(title);
      label.appendChild(count);
      this._els.knowledgeList.appendChild(label);
    }, this);
  },

  _updateKnowledgeHint: function () {
    if (!this._els.knowledgeHint) return;
    var total = (this._knowledgeSessions || []).length;
    var selected = this._selectedKnowledgeSessionIds.length;
    if (!total) {
      this._els.knowledgeHint.textContent = "暂无可检索的 Session 知识";
    } else if (selected === total) {
      this._els.knowledgeHint.textContent = "基于全部 " + total + " 个 Session 的论文、笔记、综述回答";
    } else if (selected > 0) {
      this._els.knowledgeHint.textContent = "基于选中的 " + selected + " / " + total + " 个 Session 回答";
    } else {
      this._els.knowledgeHint.textContent = "未选择知识范围，本次问答不会引用项目资料";
    }
  },

  // ═══════════════════════════════════════════
  //  会话管理
  // ═══════════════════════════════════════════

  loadSessions: function () {
    var self = this;
    fetch("/api/copilot/sessions")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        self._sessions = data.sessions || [];
        self._renderSessions();
        // 如果没有会话，自动创建一个默认的
        if (self._sessions.length === 0) {
          self.createNewSession();
        } else if (!self._currentSessionId) {
          // 有会话但未选中，自动选中第一个
          self.switchSession(self._sessions[0].session_id);
        }
      })
      .catch(function (err) {
        console.error("加载会话列表失败:", err);
      });
  },

  switchSession: function (sessionId) {
    var self = this;
    this._currentSessionId = sessionId;
    this._renderSessions();

    // 加载会话消息
    if (sessionId) {
      fetch("/api/copilot/sessions/" + sessionId + "/messages")
        .then(function (r) { return r.json(); })
        .then(function (data) {
          // 清空当前消息
          self._els.messages.innerHTML = '<div class="copilot-welcome"><div class="copilot-welcome-icon"><i class="fa-solid fa-lightbulb"></i></div><p>你好！我是全局 Copilot，可以基于你所有研究项目的论文、笔记和综述来回答问题。</p><p class="copilot-welcome-hint">试试问我：</p><div class="copilot-suggestions"><button class="copilot-suggestion" data-query="我目前有哪些研究项目？">我目前有哪些研究项目？</button><button class="copilot-suggestion" data-query="帮我总结一下所有项目的共同主题">帮我总结一下所有项目的共同主题</button><button class="copilot-suggestion" data-query="有哪些论文被多个项目引用？">有哪些论文被多个项目引用？</button></div></div>';
          // 重新绑定建议问题
          var suggestions = self._els.messages.querySelectorAll(".copilot-suggestion");
          for (var i = 0; i < suggestions.length; i++) {
            suggestions[i].addEventListener("click", function () {
              var query = this.getAttribute("data-query");
              if (query) {
                self._els.input.value = query;
                self.send();
              }
            });
          }
          // 添加历史消息
          if (data.messages && data.messages.length > 0) {
            var welcome = self._els.messages.querySelector(".copilot-welcome");
            if (welcome) welcome.style.display = "none";
            for (var j = 0; j < data.messages.length; j++) {
              var msg = data.messages[j];
              self._addMessage(msg.role, msg.content);
            }
          }
        })
        .catch(function (err) {
          console.error("加载会话消息失败:", err);
        });
    } else {
      // 清空消息显示欢迎
      self._els.messages.innerHTML = '<div class="copilot-welcome"><div class="copilot-welcome-icon"><i class="fa-solid fa-lightbulb"></i></div><p>你好！我是全局 Copilot，可以基于你所有研究项目的论文、笔记和综述来回答问题。</p><p class="copilot-welcome-hint">试试问我：</p><div class="copilot-suggestions"><button class="copilot-suggestion" data-query="我目前有哪些研究项目？">我目前有哪些研究项目？</button><button class="copilot-suggestion" data-query="帮我总结一下所有项目的共同主题">帮我总结一下所有项目的共同主题</button><button class="copilot-suggestion" data-query="有哪些论文被多个项目引用？">有哪些论文被多个项目引用？</button></div></div>';
      // 重新绑定建议问题
      var suggestions = self._els.messages.querySelectorAll(".copilot-suggestion");
      for (var i = 0; i < suggestions.length; i++) {
        suggestions[i].addEventListener("click", function () {
          var query = this.getAttribute("data-query");
          if (query) {
            self._els.input.value = query;
            self.send();
          }
        });
      }
    }
    self._updateContextMeter();
  },

  _updateContextMeter: function () {
    var bar = document.getElementById("copilotContextBar");
    var fill = document.getElementById("copilotContextFill");
    var stats = document.getElementById("copilotContextStats");
    if (!bar || !fill || !stats) return;
    if (!this._currentSessionId) { bar.style.display = "none"; return; }

    var self = this;
    fetch("/api/copilot/context/stats?copilot_session_id=" + encodeURIComponent(this._currentSessionId))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        bar.style.display = "flex";
        bar.style.cssText = "display:flex;align-items:center;gap:6px;padding:4px 0;";
        var pct = Math.max(data.usage_percent || 0, 0.5);
        fill.style.width = pct + "%";
        if (pct > 80) fill.style.background = "var(--danger)";
        else if (pct > 60) fill.style.background = "var(--warning, #f59e0b)";
        else fill.style.background = "var(--accent)";
        stats.textContent = (data.estimated_tokens || 0) + " / " + (data.max_tokens || 40000) + " tokens · " + (data.round_count || 0) + " 轮";
      })
      .catch(function () {
        bar.style.display = "none";
      });
  },

  createNewSession: function () {
    var self = this;
    var title = "新对话 " + new Date().toLocaleTimeString();
    fetch("/api/copilot/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: title })
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        self._sessions.push(data);
        self.switchSession(data.session_id);
        self._renderSessions();
      })
      .catch(function (err) {
        alert("创建会话失败：" + err.message);
      });
  },

  deleteSession: function (sessionId, event) {
    if (event) event.stopPropagation();
    var self = this;
    if (!confirm("确定删除这个对话吗？")) return;

    fetch("/api/copilot/sessions/" + sessionId, { method: "DELETE" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        self._sessions = self._sessions.filter(function (s) { return s.session_id !== sessionId; });
        if (self._currentSessionId === sessionId) {
          self._currentSessionId = null;
          self.switchSession(null);
        }
        self._renderSessions();
      })
      .catch(function (err) {
        alert("删除会话失败：" + err.message);
      });
  },

  _renderSessions: function () {
    var self = this;
    if (!this._els.sessionsList) return;
    
    var sessions = this._sessions || [];
    if (sessions.length === 0) {
      this._els.sessionsList.innerHTML = '<div class="copilot-sessions-empty">暂无对话记录</div>';
      return;
    }

    this._els.sessionsList.innerHTML = "";
    for (var i = 0; i < sessions.length; i++) {
      var session = sessions[i];
      var item = document.createElement("div");
      item.className = "copilot-session-item" + (session.session_id === this._currentSessionId ? " active" : "");
      item.innerHTML = '<span class="copilot-session-item-title">' + this._escapeHtml(session.title || "未命名") + '</span>';
      
      var deleteBtn = document.createElement("button");
      deleteBtn.className = "copilot-session-item-delete";
      deleteBtn.title = "删除";
      deleteBtn.innerHTML = '<i class="fa-solid fa-trash"></i>';
      deleteBtn.addEventListener("click", function (sid) {
        return function (e) { self.deleteSession(sid, e); };
      }(session.session_id));
      
      item.appendChild(deleteBtn);
      item.addEventListener("click", function (sid) {
        return function () { self.switchSession(sid); };
      }(session.session_id));
      
      this._els.sessionsList.appendChild(item);
    }
  },

  // ═══════════════════════════════════════════
  //  工具管理（Copilot 内集成的工具勾选）
  // ═══════════════════════════════════════════

  toggleTools: function () {
    var list = this._els.toolsList;
    var toggle = this._els.toolsToggle;
    if (!list) return;
    if (list.classList.contains("collapsed")) {
      list.classList.remove("collapsed");
      if (toggle) toggle.textContent = "收起";
    } else {
      list.classList.add("collapsed");
      if (toggle) toggle.textContent = "展开";
    }
  },

  loadTools: function () {
    var self = this;
    fetch("/api/tools")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        self._toolList = data.tools || [];
        // 如果 selectedTools 为空，默认选中所有
        if (!self._selectedTools || self._selectedTools.length === 0) {
          self._selectedTools = self._toolList.map(function (t) { return t.name; });
        }
        self._renderTools();
      })
      .catch(function (err) {
        console.error("加载工具列表失败:", err);
      });
  },

  _renderTools: function () {
    var self = this;
    if (!this._els.toolsList) return;

    var tools = this._toolList || [];
    if (tools.length === 0) {
      this._els.toolsList.innerHTML = '<div class="copilot-tools-empty">暂无可用工具</div>';
      return;
    }

    var catLabels = { search: "搜索", pdf: "PDF", file: "文件", chat: "对话", notes: "笔记", register: "收录" };

    this._els.toolsList.innerHTML = "";
    for (var i = 0; i < tools.length; i++) {
      var tool = tools[i];
      var checked = (this._selectedTools || []).indexOf(tool.name) >= 0;
      var cat = catLabels[tool.category] || tool.category;
      var pipeline = tool.pipeline || "";

      var row = document.createElement("label");
      row.className = "copilot-tool-check";

      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.dataset.tool = tool.name;
      cb.checked = checked;
      cb.addEventListener("change", function (toolName) {
        return function () {
          var idx = self._selectedTools.indexOf(toolName);
          if (idx >= 0) {
            self._selectedTools.splice(idx, 1);
          } else {
            self._selectedTools.push(toolName);
          }
        };
      }(tool.name));

      var label = document.createElement("span");
      label.className = "copilot-tool-check-label";
      label.textContent = tool.name;

      var pipelineSpan = document.createElement("span");
      pipelineSpan.className = "copilot-tool-check-pipeline";
      pipelineSpan.textContent = pipeline ? "⏱ " + pipeline : "";

      var catSpan = document.createElement("span");
      catSpan.className = "copilot-tool-check-cat";
      catSpan.textContent = cat;

      row.appendChild(cb);
      row.appendChild(label);
      row.appendChild(pipelineSpan);
      row.appendChild(catSpan);
      this._els.toolsList.appendChild(row);
    }
  },

  _escapeHtml: function (text) {
    if (typeof notebooklm !== "undefined" && notebooklm.escapeHtml) {
      return notebooklm.escapeHtml(text);
    }
    var s = String(text || "");
    s = s.split("&").join("&" + "amp;");
    s = s.split("<").join("&" + "lt;");
    s = s.split(">").join("&" + "gt;");
    s = s.split('"').join("&" + "quot;");
    s = s.split("'").join("&" + "#39;");
    return s;
  },
};

document.addEventListener("DOMContentLoaded", () => {
  notebooklm.init();
  GlobalCopilot.init();
});

window.notebooklm = notebooklm;
window.GlobalCopilot = GlobalCopilot;



