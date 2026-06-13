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
    // 加载 Skills 选择器选项
    this.loadHomeSkillSelectors();
  },

  closeTopicModal() {
    if (this.els.topicModal) {
      this.els.topicModal.classList.remove("active");
    }
  },

  async createTopicFromModal() {
    const topic = (this.els.topicInput?.value || "").trim();
    const keywords = this.collectHomeKeywords();
    const skills = this.collectSelectedSkills ? this.collectSelectedSkills() : {};
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

      this.renderConsoleSession();
      // 确保用量条在首次加载时更新
      setTimeout(() => this.updateContextMeter(), 300);

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
    this.renderChatTabs();
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
      var sessionRef = this.state.currentSession || {};
      var referencedPapers = sessionRef.review_referenced_papers || [];
      paper._hasReview = referencedPapers.indexOf(paper.paper_id) >= 0;

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
    } else if (this.state.currentViewMode === "analysis") {
      html = this.renderAnalysisView(session);
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

    // 用量条（与标签同一行右侧）— 使用内联样式确保高度不被覆盖
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
          <span>选择论文后可在下方提问。笔记模式和综述模式下可请求修改。</span>
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
      analysis: "分析",
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
          // 将 RUNS 中的实时 traces 注入 session，确保轨迹视图能实时更新
          if (status.traces && status.traces.length > 0) {
            session.traces = status.traces;
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

  async generateAnalysisAction() {
    const session = this.state.currentSession;
    if (!session || !this.state.currentSessionId) return;

    try {
      this.setConsoleStatus("writing", "正在生成深度分析报告...");
      const response = await fetch(`/api/sessions/${encodeURIComponent(this.state.currentSessionId)}/run/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic: session.topic, analysis_type: "all" }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "分析失败");
      }

      if (!this.state.currentSession._analysis) this.state.currentSession._analysis = {};
      if (data.compare) this.state.currentSession._analysis.compare = data.compare;
      if (data.lineage) this.state.currentSession._analysis.lineage = data.lineage;
      if (data.gaps) this.state.currentSession._analysis.gaps = data.gaps;

      this.switchViewMode("analysis");
      this.setConsoleStatus("complete", "深度分析报告已生成");
    } catch (error) {
      this.setConsoleStatus("error", `分析失败：${error.message}`);
    }
  },

  renderAnalysisView(session) {
    const analysis = session?._analysis || {};
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

    let html = `
      <div class="detail-hero">
        <span class="topic-badge"><i class="fa-solid fa-magnifying-glass-chart"></i> 深度分析</span>
        <h3>${this.escapeHtml(session?.topic || "当前主题")}</h3>
        <div class="lead">文献对比 · 研究脉络 · 空白发现</div>
      </div>
      <div class="detail-blocks" style="margin-top:16px;">
    `;

    if (analysis.compare) {
      html += `
        <div class="panel-block">
          <div class="panel-block-head">
            <strong><i class="fa-solid fa-table-columns"></i> 文献对比分析</strong>
          </div>
          <div class="markdown">${marked.parse(analysis.compare)}</div>
        </div>
      `;
    }

    if (analysis.lineage) {
      html += `
        <div class="panel-block">
          <div class="panel-block-head">
            <strong><i class="fa-solid fa-timeline"></i> 研究脉络梳理</strong>
          </div>
          <div class="markdown">${marked.parse(analysis.lineage)}</div>
        </div>
      `;
    }

    if (analysis.gaps) {
      html += `
        <div class="panel-block">
          <div class="panel-block-head">
            <strong><i class="fa-solid fa-lightbulb"></i> 研究空白发现</strong>
          </div>
          <div class="markdown">${marked.parse(analysis.gaps)}</div>
        </div>
      `;
    }

    html += `
        <div class="panel-block" style="text-align:center;padding:12px;">
          <button class="secondary-btn" onclick="notebooklm.generateAnalysisAction()" style="font-size:13px;">
            <i class="fa-solid fa-rotate"></i> 重新生成分析报告
          </button>
        </div>
      </div>
    `;

    return html;
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
          conv_id: this.state.currentConvId,
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
        body: JSON.stringify({
          message: "确认修改",
          view_mode: this.state.currentViewMode,
          chat_mode: "agent",
          current_paper_id: this.state.currentPaperId,
          conv_id: this.state.currentConvId,
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
    } catch (e) {
      this._skillsState._defaultSkills = {};
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

    fetch("/api/knowledge/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: message, copilot_session_id: self._currentSessionId || "" }),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        self._hideTyping();
        var reply = data.reply || "抱歉，无法生成回答。";
        var meta = "";
        if (data.has_rag) {
          meta = "基于 " + data.search_count + " 条跨项目资料";
        }
        self._addMessage("agent", reply, meta);
        self._loading = false;
        self._els.send.disabled = false;
        self._els.input.focus();
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


