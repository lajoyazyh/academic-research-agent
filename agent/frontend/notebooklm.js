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
    pollTimer: null,
    pendingSeedKeywords: "",
    lastReviewFeedback: "",
    isEditingReport: false,
    reportEditText: "",
    isEditingReview: false,
    reviewEditText: "",
    _autoRunning: false,
    _autoPollTimer: null,
  },

  els: {},

  init() {
    this.bindCommonElements();
    this.loadThemePreference();

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
    this.els.historyCount = document.getElementById("historyCount");

    this.els.consoleTopic = document.getElementById("consoleTopic");
    this.els.consoleState = document.getElementById("consoleState");
    this.els.consoleStateDot = document.getElementById("consoleStateDot");
    this.els.searchBtn = document.getElementById("searchPaperBtn");
    this.els.addPaperBtn = document.getElementById("addPaperBtn");
    this.els.pdfFileInput = document.getElementById("pdfFileInput");
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
    this.els.viewPDF = document.getElementById("viewPDF");
    this.els.viewTrace = document.getElementById("viewTrace");
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
      statsGrid.innerHTML = `<div class="stats-loading">统计加载失败：${this.escapeHtml(error.message)}</div>`;
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
    this.els.topicModal.classList.add("active");
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
        body: JSON.stringify({ topic }),
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
    this.els.cancelSearchBtn?.addEventListener("click", () => this.cancelSearch());
    this.els.autoRunBtn?.addEventListener("click", () => this.startAutoRun());
    this.els.addPaperBtn?.addEventListener("click", () => this.openAddPaperModal());
    this.els.pdfFileInput?.addEventListener("change", (e) => this.handleDropZoneFile(e.target.files[0]));
    this.els.notesBtn?.addEventListener("click", () => this.generateNotesAction());
    this.els.reviewBtn?.addEventListener("click", () => this.generateReviewAction());
    this.els.viewSummary?.addEventListener("click", () => this.switchViewMode("summary"));
    this.els.viewReport?.addEventListener("click", () => this.switchViewMode("report"));
    this.els.viewReview?.addEventListener("click", () => this.switchViewMode("review"));
    this.els.viewPDF?.addEventListener("click", () => this.switchViewMode("pdf"));
    this.els.viewTrace?.addEventListener("click", () => this.switchViewMode("trace"));
    this.els.chatSend?.addEventListener("click", () => this.sendChatMessage());
    this.els.chatModeToggle?.addEventListener("click", () => this.toggleChatMode());
    this.els.chatInput?.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        this.sendChatMessage();
      }
    });

    this.els.keywordConfirm?.addEventListener("click", () => this.confirmKeywords());
    this.els.keywordCancel?.addEventListener("click", () => this.closeKeywordModal());
    this.els.keywordAdd?.addEventListener("click", () => this.addKeywordRow());

    // 初始化对话助手拖拽缩放
    this.initChatResize();
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
      
      // Preserve the currentPaperId if it still exists in the refreshed session's papers
      const prevPaperId = this.state.currentPaperId;
      const paperExists = prevPaperId && session.papers?.some(p => p.paper_id === prevPaperId);
      this.state.currentPaperId = paperExists ? prevPaperId : (session.papers?.[0]?.paper_id || null);

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
    this.updateChatPlaceholder();
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
    } else if (this.state.currentViewMode === "pdf") {
      html = this.renderPDFView(paper, session);
    } else {
      html = this.renderReviewView(session);
    }

    this.els.detailContent.innerHTML = html;
  },

  renderPaperSummary(paper, session) {
    if (!paper) {
      return '<div class="empty-state">请先在左侧选择一篇论文。</div>';
    }

    const pid = paper.paper_id || "";
    const sessionNotes = session.notes || "";

    // 从 session.notes（draft_notes.md）中用论文 id 提取对应的整段 Markdown
    let sectionMd = "";
    if (pid && sessionNotes) {
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
        <div class="lead">${this.escapeHtml(paper.authors || paper.source || "该论文已加入当前综述主题")}</div>
      </div>
      <div class="detail-blocks" style="margin-top:16px;">
        <div class="panel-block">
          <div class="panel-block-head"><strong>调研笔记（draft_notes）</strong><span class="chip">${hasSection ? '自动提取' : '无'}</span></div>
          ${hasSection
            ? `<div class="markdown">${marked.parse(sectionMd)}</div>`
            : `<div class="plain-text">${this.escapeHtml(paper.abstract || "当前没有可用摘要。")}</div>`}
        </div>
        <div class="panel-block">
          <div class="panel-block-head"><strong>来源信息</strong><span class="chip">${this.escapeHtml(paper.status || "pending")}</span></div>
          <div class="plain-text">来源：${this.escapeHtml(paper.source || "agent_search")} · 来源类型：${this.escapeHtml(paper.source_type || "n/a")} · 添加时间：${this.escapeHtml(this.formatDate(paper.added_at))}</div>
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
        <span class="topic-badge"><i class="fa-solid fa-chart-line"></i> 报告</span>
        <h3>${this.escapeHtml(paper?.title || paper?.paper_id || session?.topic || "综合报告")}</h3>
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
    setTimeout(() => this._initVditor("reportEditArea", rawNotes), 50);
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

    setTimeout(() => this._initVditor("reviewEditArea", draft), 50);
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

  _initVditor(id, content) {
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
        { name: "save", tip: "保存 (Ctrl+S)", className: "right", icon: '<i class="fa-solid fa-floppy-disk"></i>', click: () => this.saveEditReport() },
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
    const sessionId = session?.session_id || "";
    const pdfUrl = sessionId
      ? `/api/agent/document/${encodeURIComponent(sessionId)}/papers/${encodeURIComponent(paperId)}.pdf`
      : `/api/agent/document/${encodeURIComponent(paperId)}/papers/${encodeURIComponent(paperId)}.pdf`;

    return `
      <div class="detail-hero">
        <span class="topic-badge"><i class="fa-solid fa-file-pdf"></i> PDF</span>
        <h3>${this.escapeHtml(paper.title || paperId)}</h3>
        <div class="lead">${this.escapeHtml(paper.authors || "")}</div>
      </div>
      <div class="panel-block" style="margin-top:16px; height: calc(100vh - 260px); min-height: 500px;">
        <embed
          src="${pdfUrl}"
          type="application/pdf"
          style="width: 100%; height: 100%; border: none; border-radius: 8px;"
        ></embed>
      </div>
      <div style="margin-top: 8px; text-align: center; font-size: 12px; color: var(--subtle);">
        <i class="fa-solid fa-circle-info"></i> 如果 PDF 无法显示，该论文可能尚未下载。请先执行检索阶段。
        &nbsp;<a href="${pdfUrl}" target="_blank" style="color: var(--accent);">在新窗口打开</a>
      </div>
    `;
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
        this.els.searchBtn.innerHTML = '<i class="fa-solid fa-magnifying-glass"></i> 重新检索';
        this.els.searchBtn.disabled = false;
        this.els.searchBtn.style.display = "";
        if (this.els.cancelSearchBtn) this.els.cancelSearchBtn.style.display = "none";
      }
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

    // 如果还在 planning 阶段且无关键词，先自动生成关键词再启动
    if (!session.keywords || !session.keywords.length || session.state === "planning") {
      this.setConsoleStatus("planning", "正在生成关键词规划...");
      try {
        const planResp = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/run/plan`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ topic, start_phase: "plan" }),
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
        body: JSON.stringify({ topic, max_loops: 20, min_papers: 3 }),
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
            reviewing_notes: "正在生成笔记...",
            writing: "正在撰写综述草稿...",
            reviewing_draft: "正在评审草稿...",
            complete: "流程完成",
            failed: "流程出错",
          };
          this.setConsoleStatus(phase, phaseLabels[phase] || phase);
        }

        // 根据阶段切换视图
        if (phase === "search_complete") {
          this.switchViewMode("summary");
        } else if (phase === "reviewing_notes" || phase === "writing") {
          // 保持当前视图
        } else if (phase === "complete" && runStatus === "done") {
          this.switchViewMode("review");
        }

        // 更新按钮状态
        this.updateActionButtons();

        // 检查是否完成
        if (runStatus === "done" || runStatus === "error" || runStatus === "cancelled") {
          clearInterval(this.state._autoPollTimer);
          this.state._autoPollTimer = null;
          this.state._autoRunning = false;

          // 先刷新 session 再更新按钮，确保 session.state 已同步为最新
          await this.reloadCurrentSession();

          if (runStatus === "done") {
            this.setConsoleStatus("complete", "🎉 自动流程全部完成！");
          } else if (runStatus === "error") {
            this.setConsoleStatus("error", `自动流程失败：${status.error || "未知错误"}`);
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
      this._setSearchButtons("searching");
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
            this._setSearchButtons("idle");
            this.switchViewMode("summary");
            this.setConsoleStatus("search_complete", "论文检索完成，可以生成综述");
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
        body: JSON.stringify({
          message,
          view_mode: this.state.currentViewMode,
          chat_mode: this.state.chatMode,
          current_paper_id: this.state.currentPaperId,
        }),
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
        body: JSON.stringify({
          message: "确认修改",
          view_mode: this.state.currentViewMode,
          chat_mode: "agent",
          current_paper_id: this.state.currentPaperId,
          confirmed_revision: true,
          revision_target: target,
          revision_feedback: feedback,
        }),
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
    const msg = document.createElement("div");
    msg.className = "chat-msg";
    if (role === "system") msg.style.opacity = "0.7";
    const roleLabel = role === "user" ? "你" : role === "system" ? "" : "AI";
    const noteHtml = note ? `<span style="font-size:11px;color:var(--subtle);display:block">${this.escapeHtml(note)}</span>` : "";
    const body = document.createElement("span");
    body.innerHTML = `${noteHtml}${this.escapeHtml(text)}`;
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
          // 点任何一个按钮后，整行全部变灰禁用
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
    return msg;  // 返回 DOM 元素以便调用方移除
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
};

document.addEventListener("DOMContentLoaded", () => {
  notebooklm.init();
});

window.notebooklm = notebooklm;


