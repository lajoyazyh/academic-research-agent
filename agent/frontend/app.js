const app = {
    pollTimer: null,
    chatMessages: [],
    
    init() {
        this.startBtn = document.getElementById("startBtn");
        this.statusBadge = document.getElementById("statusBadge");
        this.historyList = document.getElementById("historyList");
        
        this.tracesContainer = document.getElementById("tracesContainer");
        this.researchResult = document.getElementById("researchResult");
        this.writerResult = document.getElementById("writerResult");
        this.outputPath = document.getElementById("outputPath");
        this.failureSummaryDiv = document.getElementById("failureSummary");
        
        // Chat 组件初始化
        this.chatInput = document.getElementById("chatInput");
        this.chatSendBtn = document.getElementById("chatSendBtn");
        this.chatMessagesContainer = document.getElementById("chatMessages");
        
        // 恢复主题偏好
        this.loadTheme();
        
        this.loadFavorites();
        this.loadSessions();  // 加载 Session 列表
    },

    initConsole (){
        app.currentPage = 'console';
        this.startBtn = document.getElementById("startBtn");
        this.statusBadge = document.getElementById("statusBadge");
        this.historyList = document.getElementById("historyList");

        this.tracesContainer = document.getElementById("tracesContainer");
        this.researchResult = document.getElementById("researchResult");
        this.writerResult = document.getElementById("writerResult");
        this.outputPath = document.getElementById("outputPath");
        this.failureSummaryDiv = document.getElementById("failureSummary");

        this.chatInput = document.getElementById("chatInput");
        this.chatSendBtn = document.getElementById("chatSendBtn");
        this.chatMessagesContainer = document.getElementById("chatMessages");

        this.loadTheme();
        this.loadFavorites();
        this.loadSessions();

        // 绑定智能按钮行为（根据当前是否有会话决定点击行为）
        if (this.startBtn) {
            this.startBtn.onclick = () => this.smartAction();
        }
        // 对话框发送事件
        if (this.chatSendBtn) {
            this.chatSendBtn.onclick = () => this.sendChatMessage();
        }
        if (this.chatInput) {
            this.chatInput.onkeypress = (e) => {
                if (e.key === 'Enter') this.sendChatMessage();
            };
        }
        // 默认显示控制台的初始内容
        this.setStatus("idle", "就绪");
        this.switchTab('traces');

        // 在 initConsole 末尾添加
        const urlParams = new URLSearchParams(window.location.search);
        const sessionId = urlParams.get('sessionId');
        const newTopic = urlParams.get('newTopic');
        if (sessionId) {
            // 自动加载指定会话
            this.selectSession(sessionId);
        } else if (newTopic) {
            // 如果是新建会话请求，打开新建会话弹窗并预填主题
            this.currentTopic = newTopic;
            this.showNewSessionDialog();
        }

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

    initHistoryPage() {
        app.currentPage = 'history';
        // 加载收藏夹
        this.loadFavorites();
        // 加载会话列表
        this.loadSessionsForHistory();
    },

    initChatPage() {
        app.currentPage = 'chat';
        this.chatInput = document.getElementById("chatInput");
        this.chatSendBtn = document.getElementById("chatSendBtn");
        this.chatMessagesContainer = document.getElementById("chatMessages");

        if (this.chatSendBtn) {
            this.chatSendBtn.onclick = () => this.sendChatMessage();
        }
        if (this.chatInput) {
            this.chatInput.onkeypress = (e) => {
                if (e.key === 'Enter') this.sendChatMessage();
            };
        }
    },

    // ━━━ 智能动作按钮：根据上下文自动切换行为 ━━━
    smartAction() {
        if (this.currentSessionId) {
            // 有活跃会话 → 触发 onClick（renderSessionGuide 已设置好）
            this.startBtn.click();
        } else {
            // 无活跃会话 → 新建会话
            this.showNewSessionDialog();
        }
    },
    
    // 主题切换
    toggleTheme() {
        document.body.classList.toggle('light-mode');
        const isLight = document.body.classList.contains('light-mode');
        localStorage.setItem('se-assistant-theme', isLight ? 'light' : 'dark');
        const icon = document.querySelector('#themeToggle i');
        if (icon) {
            icon.className = isLight ? 'fas fa-moon' : 'fas fa-sun';
        }
    },
    
    loadTheme() {
        const saved = localStorage.getItem('se-assistant-theme');
        if (saved === 'light') {
            document.body.classList.add('light-mode');
            const icon = document.querySelector('#themeToggle i');
            if (icon) icon.className = 'fas fa-moon';
        }
    },
    
    // 对话框收放
    toggleChat() {
        const chat = document.querySelector('.chat-container');
        const container = document.querySelector('.container');
        const btn = document.querySelector('.chat-toggle-btn i');
        chat.classList.toggle('collapsed');
        container.classList.toggle('chat-collapsed');
        if (btn) {
            btn.className = chat.classList.contains('collapsed') 
                ? 'fas fa-chevron-up' 
                : 'fas fa-chevron-down';
        }
    },

    setStatus(type, text) {
        this.statusBadge.className = `status-badge status-${type}`;
        this.statusBadge.textContent = text;
    },

    switchTab(tabId) {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
        
        const tabs = {
            'traces': 0,
            'research': 1,
            'writer': 2,
            'papers': 3
        };
        
        document.querySelectorAll('.tab')[tabs[tabId]].classList.add('active');
        document.getElementById(`${tabId}Tab`).classList.add('active');
    },

    renderTraces(traces) {
        this.tracesContainer.innerHTML = "";
        
        if (!traces || traces.length === 0) {
            this.tracesContainer.innerHTML = '<div style="color: #666; text-align: center; margin-top: 2rem;">暂无轨迹</div>';
            return;
        }

        traces.forEach((item, index) => {
            const card = document.createElement("article");
            card.className = "trace-item";

            const meta = document.createElement("div");
            meta.className = "trace-meta";
            
            const role = document.createElement("span");
            role.className = "trace-role";
            role.textContent = `第 ${index + 1} 轮 - ${item.action || "执行"}`;
            
            meta.appendChild(role);

            const content = document.createElement("div");
            content.className = "trace-content";
            
            let text = "";
            if (item.thought) text += `[思考]\n${item.thought}\n\n`;
            if (item.input) text += `[参数]\n${JSON.stringify(item.input, null, 2)}\n\n`;
            if (item.observation) text += `[观察]\n${item.observation}`;
            
            content.textContent = text.trim();

            card.append(meta, content);
            this.tracesContainer.appendChild(card);
        });
        
        // auto scroll to bottom
        this.tracesContainer.scrollTop = this.tracesContainer.scrollHeight;
    },

    async startAgent() {
        const topic = this.currentTopic || "";

        if (!topic) {
            this.showNewSessionDialog();
            return;
        }

        this.startBtn.disabled = true;
        this.startBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 执行中...';
        this.setStatus("running", "任务启动中...");
        
        this.switchTab('traces');
        this.tracesContainer.innerHTML = '<div style="color: #666; text-align: center; margin-top: 2rem;">正在初始化 Agent...</div>';
        this.researchResult.innerHTML = '<div style="color: #666; text-align: center; margin-top: 2rem;">执行中...</div>';
        this.writerResult.innerHTML = '<div style="color: #666; text-align: center; margin-top: 2rem;">执行中...</div>';
        this.outputPath.textContent = "-";
        if (this.failureSummaryDiv) this.failureSummaryDiv.innerHTML = "";

        try {
            const startResp = await fetch("/api/run/start", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ topic, max_loops: 20 }) // default to 20 in backend call
            });

            const startData = await startResp.json();

            if (!startResp.ok) {
                throw new Error(startData.detail || "启动任务失败");
            }

            const runId = startData.run_id;

            if (this.pollTimer) {
                clearInterval(this.pollTimer);
            }

            const poll = async () => {
                const statusResp = await fetch(`/api/run/${runId}`);
                if (!statusResp.ok) throw new Error("查询执行状态失败");
                
                const statusData = await statusResp.json();

                this.renderTraces(statusData.traces || []);
                this.renderFailureSummary(statusData.failure_summary || {});
                
                if (statusData.researcher_result) {
                    this.researchResult.innerHTML = marked.parse(statusData.researcher_result);
                }
                
                if (statusData.writer_result) {
                    this.writerResult.innerHTML = marked.parse(statusData.writer_result);
                }
                
                if (statusData.papers !== undefined) {
                    this.renderPapers(statusData.output_file, statusData.papers || []);
                }
                
                if (statusData.output_file) {
                    this.outputPath.textContent = statusData.output_file;
                }

                if (statusData.status === "running") {
                    this.setStatus("running", `执行中（阶段：${statusData.phase}，已产生 ${statusData.traces ? statusData.traces.length : 0} 轮轨迹）`);
                    return;
                }

                clearInterval(this.pollTimer);
                this.pollTimer = null;

                if (statusData.status === "done") {
                    this.setStatus("done", "执行完成");
                    this.resetBtn();
                    this.switchTab('writer');
                    this.loadFavorites();
                    if (statusData.output_file) {
                        this.showFavoriteBtn(statusData.output_file);
                    }
                } else {
                    throw new Error(statusData.error || "任务执行失败");
                }
            };

            await poll();
            this.pollTimer = setInterval(async () => {
                try {
                    await poll();
                } catch (err) {
                    clearInterval(this.pollTimer);
                    this.pollTimer = null;
                    this.setStatus("error", `执行失败：${err.message}`);
                    this.resetBtn();
                }
            }, 1000);

        } catch (err) {
            if (this.pollTimer) {
                clearInterval(this.pollTimer);
                this.pollTimer = null;
            }
            this.setStatus("error", `启动失败：${err.message}`);
            this.resetBtn();
        }
    },

    resetBtn() {
        this.startBtn.disabled = false;
        this.startBtn.innerHTML = '<i class="fas fa-play"></i> 开始研究';
    },

    renderFailureSummary(summary) {
        if (!this.failureSummaryDiv) return;
        const keys = Object.keys(summary || {});
        if (keys.length === 0) {
            this.failureSummaryDiv.innerHTML = "";
            return;
        }
        const items = keys.map(k => `<span style="display:inline-block;margin:2px 6px 0 0;padding:2px 8px;border:1px solid #eee;border-radius:12px;background:#fff;">${k}: <strong>${summary[k]}</strong></span>`).join(" ");
        this.failureSummaryDiv.innerHTML = `<div style="margin-top:6px;"><span style="color:#777; margin-right:4px;">错误统计:</span>${items}</div>`;
    },

    async loadFavorites() {
        const listDiv = document.getElementById("historyList");
        if (!listDiv) return;
        listDiv.innerHTML = '<div style="color:var(--text-secondary);font-size:0.85rem;">加载收藏夹...</div>';

        fetch("/api/favorites")
            .then(res => res.json())
            .then(data => {
                // 兼容后端可能返回对象或数组
                const favorites = Array.isArray(data) ? data : (data.favorites || []);

                if (favorites.length === 0) {
                    listDiv.innerHTML = '<div style="color:var(--text-secondary);font-size:0.85rem;">暂无收藏</div>';
                    return;
                }

                listDiv.innerHTML = "";
                favorites.forEach(f => {
                    const div = document.createElement("div");
                    div.className = "history-item";
                    const safeFilename = f.filename.replace(/'/g, "\\'");
                    const fnName = app.currentPage === 'history'
                        ? 'loadHistoryDetailHistory'
                        : 'loadHistoryDetailConsole';
                    div.innerHTML = `
                        <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
                            ${app.escapeHtml(f.filename)}
                        </span>
                        <button class="btn-fav" data-filename="${safeFilename}" 
                            onclick="event.stopPropagation(); app.removeFavorite('${safeFilename}')">
                            <i class="fas fa-trash"></i>
                        </button>
                    `;
                    div.title = "点击查看详情";
                    div.addEventListener('click', () => {
                        app[fnName](f.filename);
                    });
                    listDiv.appendChild(div);
                });
            })
            .catch(e => {
                listDiv.innerHTML = `<div style="color:var(--error-color);">加载失败: ${e.message}</div>`;
            });
    },

    async loadHistoryDetailConsole(filename) {
        // 确保状态显示元素存在
        const statusBadge = document.getElementById("statusBadge");
        if (statusBadge) {
            statusBadge.textContent = `加载中...`;
            statusBadge.className = "badge running";
        }

        try {
            const res = await fetch(`/api/agent/history/${filename}`);
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail);

            // 控制台专用：Traces 区域显示占位
            const traces = document.getElementById("tracesContainer");
            if (traces) {
                traces.innerHTML = '<div style="color:#666;text-align:center;margin-top:2rem;">历史记录无 Trace</div>';
            }

            // 研究者结果
            const researchDiv = document.getElementById("researchResult");
            if (researchDiv) {
                if (data.researcher_result) {
                    researchDiv.innerHTML = marked.parse(data.researcher_result);
                } else {
                    researchDiv.innerHTML = '<div style="color:#666;text-align:center;margin-top:2rem;">无单独摘要</div>';
                }
            }

            // 撰写结果
            const writerDiv = document.getElementById("writerResult");
            if (writerDiv) {
                writerDiv.innerHTML = marked.parse(data.writer_result || data.content);
            }

            // 输出路径显示
            const pathSpan = document.getElementById("outputPath");
            if (pathSpan) pathSpan.textContent = filename;

            // 论文 PDF 渲染
            app.renderPapers(filename, data.papers || []);

            // 显示收藏按钮
            app.showFavoriteBtn(filename);

            // 切换标签到撰写结果
            if (typeof app.switchTab === 'function') {
                app.switchTab('writer');
            }

            if (statusBadge) {
                statusBadge.textContent = "加载完成";
                statusBadge.className = "badge idle";
            }
        } catch (e) {
            if (statusBadge) {
                statusBadge.textContent = "加载失败";
                statusBadge.className = "badge error";
            }
            alert("加载详情失败：" + e.message);
        }
    },

    async loadHistoryDetailHistory(filename) {
        const detailView = document.getElementById("detailView");
        const detailTitle = document.getElementById("detailTitle");
        const detailContent = document.getElementById("detailContent");

        if (!detailView || !detailContent) return;

        // 显示加载状态
        detailView.style.display = "block";
        detailContent.innerHTML = '<div style="color:var(--text-secondary);text-align:center;padding:2rem;">加载中...</div>';

        try {
            const res = await fetch(`/api/agent/history/${filename}`);
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail);

            if (detailTitle) detailTitle.textContent = `综述详情: ${filename}`;
            detailContent.innerHTML = marked.parse(data.content);

            // 论文 PDF 列表
            app.renderPapers(filename, data.papers || []);

            // 不需要显示收藏按钮（历史页暂时不提供按钮或可复用，可忽略）
        } catch (e) {
            detailContent.innerHTML = `<div style="color:var(--error-color);">加载失败: ${e.message}</div>`;
        }
    },

    async deleteHistory(filename) {
        if (!confirm(`确定要删除 \"${filename}\" 吗？也会从收藏夹中移除。`)) return;
        try {
            await fetch(`/api/agent/history/${filename}`, { method: "DELETE" });
            this.loadFavorites();
            this.setStatus("done", `已删除`);
        } catch (e) {
            this.setStatus("error", `删除失败: ${e.message}`);
        }
    },

    async unfavorite(filename) {
        if (!confirm(`确定取消收藏吗？`)) return;
        try {
            await fetch(`/api/favorites/${encodeURIComponent(filename)}`, { method: "DELETE" });
            this.loadFavorites();
            this.setStatus("done", "已取消收藏");
        } catch (e) {
            this.setStatus("error", `操作失败: ${e.message}`);
        }
    },

    async addFavorite(filename, topic) {
        try {
            const res = await fetch("/api/favorites", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ filename, topic }),
            });
            if (!res.ok) throw new Error((await res.json()).detail || "收藏失败");
            this.loadFavorites();
            this.setStatus("done", "⭐ 已加入收藏夹");
        } catch (e) {
            this.setStatus("error", `收藏失败: ${e.message}`);
        }
    },

    async deleteAllHistory() {
        // 收藏夹模式下不再需要"一键清空"——改为逐个取消收藏
        const items = this.historyList.querySelectorAll(".history-item");
        if (items.length === 0) return;
        if (!confirm(`确定要清空全部 ${items.length} 条收藏吗？`)) return;
        let count = 0;
        for (const item of items) {
            const strong = item.querySelector("strong");
            if (!strong) continue;
            const filename = strong.textContent.replace(/^[★⭐]\s*/, "").trim();
            try {
                await fetch(`/api/favorites/${encodeURIComponent(filename)}`, { method: "DELETE" });
                count++;
            } catch (e) { /* skip */ }
        }
        this.loadFavorites();
        this.setStatus("done", `已清空 ${count} 条收藏`);
    },

    toggleHistoryPanel() {
        const wrapper = document.getElementById("historyListWrapper");
        const icon = document.getElementById("historyToggleIcon");
        if (!wrapper || !icon) return;
        const collapsed = wrapper.style.display === "none";
        wrapper.style.display = collapsed ? "block" : "none";
        icon.className = collapsed ? "fas fa-chevron-up" : "fas fa-chevron-down";
    },

    renderPapers(filename, papers) {
        const listDiv = document.getElementById("papersList");
        if (!listDiv) return;
        if (!papers || papers.length === 0) {
            listDiv.innerHTML = '<div style="color: var(--text-secondary); text-align: center; margin-top: 2rem;">该记录下没有保存对应的原论文PDF</div>';
            return;
        }

        listDiv.innerHTML = papers.map(p => `
            <div style="display: flex; justify-content: space-between; padding: 1rem; border: 1px solid var(--border-color); border-radius: 10px; background: var(--card-background); align-items: center;">
                <span style="font-weight: 500; color: var(--text-color);"><i class="fas fa-file-pdf" style="color: #ec4899;"></i> ${p}</span>
                <a href="/api/agent/document/${filename}/papers/${p}" target="_blank" style="color: var(--primary-color); text-decoration: none; padding: 0.4rem 0.8rem; border: 1px solid var(--primary-color); border-radius: 6px; font-size: 0.9rem; font-weight: 500;">
                    <i class="fas fa-external-link-alt"></i> 查看/下载
                </a>
            </div>
        `).join('');
    },
    
    // 对话框相关方法
    sendChatMessage() {
        const message = this.chatInput.value.trim();
        if (!message) return;
        
        // 禁用发送按钮
        this.chatSendBtn.disabled = true;
        
        // 渲染用户消息
        this.renderChatMessage(message, 'user');
        this.chatInput.value = '';
        
        // 自动滚动到底部
        this.chatMessagesContainer.scrollTop = this.chatMessagesContainer.scrollHeight;
        
        // 获取 AI 回复（暂时返回模拟数据）
        this.getChatResponse(message).then(response => {
            this.renderChatMessage(response, 'agent');
            this.chatSendBtn.disabled = false;
            this.chatMessagesContainer.scrollTop = this.chatMessagesContainer.scrollHeight;
        }).catch(err => {
            console.error('Failed to get response:', err);
            this.renderChatMessage('抱歉，我出了点问题。请稍后重试。', 'agent');
            this.chatSendBtn.disabled = false;
        });
    },
    
    renderChatMessage(text, role = 'user') {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'chat-message';
        
        const avatarDiv = document.createElement('div');
        avatarDiv.className = `message-avatar ${role}`;
        avatarDiv.innerHTML = role === 'user' 
            ? '<i class="fas fa-user"></i>'
            : '<i class="fas fa-robot"></i>';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = `message-content ${role}`;
        contentDiv.classList.add("markdown");
        contentDiv.innerHTML = marked.parse(text);
        
        messageDiv.appendChild(avatarDiv);
        messageDiv.appendChild(contentDiv);
        
        this.chatMessagesContainer.appendChild(messageDiv);
    },
    
    async getChatResponse(userMessage) {
        // TODO: 连接实际的后端 API
        // const response = await fetch("/api/chat", {
        //     method: "POST",
        //     headers: { "Content-Type": "application/json" },
        //     body: JSON.stringify({ message: userMessage })
        // });
        // const data = await response.json();
        // return data.response;
        
        // 暂时返回模拟数据
        return new Promise((resolve) => {
            setTimeout(() => {
                const responses = [
                    '我已理解你的问题。这个话题涉及多个学术维度...',
                    '根据当前的研究内容，这个方面确实很重要。让我为你详细解释...',
                    '好的，我会基于已有的笔记来帮助你改进综述...',
                    '这是一个很好的想法！我建议可以从以下几个方面考虑...',
                    '（后端接口待实现）'
                ];
                const randomResponse = responses[Math.floor(Math.random() * responses.length)];
                resolve(randomResponse);
            }, 500);
        });
    },

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    //  Session-aware: Session 管理
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    currentSessionId: null,
    currentKeywords: [],
    currentPlan: "",
    currentTopic: "",
    sessionMode: "interactive",  // "interactive" | "quick"

    onModeChange(mode) {
        this.sessionMode = mode;
        const interactiveLabel = document.getElementById("modeInteractiveLabel");
        const quickLabel = document.getElementById("modeQuickLabel");
        const quickHint = document.getElementById("quickModeHint");
        const createBtn = document.getElementById("createSessionBtn");
        
        if (mode === "quick") {
            interactiveLabel.style.background = "var(--surface-light)";
            interactiveLabel.style.border = "1px solid var(--border-color)";
            quickLabel.style.background = "rgba(245,158,11,0.1)";
            quickLabel.style.border = "1px solid var(--warning-color)";
            quickHint.style.display = "block";
            createBtn.innerHTML = '<i class="fas fa-bolt"></i> 一键快速调研';
        } else {
            interactiveLabel.style.background = "rgba(99,102,241,0.1)";
            interactiveLabel.style.border = "1px solid var(--primary-color)";
            quickLabel.style.background = "var(--surface-light)";
            quickLabel.style.border = "1px solid var(--border-color)";
            quickHint.style.display = "none";
            createBtn.innerHTML = '<i class="fas fa-check"></i> 创建并开始规划';
        }
    },

    async addCustomPaper() {
        const input = document.getElementById("customPaperInput");
        const val = input.value.trim();
        if (!val) {
            alert("请输入 arXiv ID 或 PDF URL");
            return;
        }
        if (!this.currentSessionId) {
            alert("当前没有活跃的会话，请先创建会话！");
            return;
        }

        const btn = document.getElementById("addCustomPaperBtn");
        const originHTML = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 正在下载解析...';
        btn.disabled = true;

        try {
            const res = await fetch(`/api/sessions/${this.currentSessionId}/papers/custom`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ paper_id: val })
            });

            const data = await res.json();
            if (!res.ok) {
                alert(`追加论文失败，请检查论文编号或链接是否正确`);
                return;
            }

            if (data.exists) {
                alert("此论文已存在于列表中。");
            } else {
                alert("✅ 追加新论文成功并更新了笔记，您可以随时在研究笔记下方生成新的综述！");
            }
            
            input.value = "";
            this.switchTab("research"); // 切换到笔记而不是直接切到综述
            
            // 刷新当前会话 UI（包括笔记、论文列表和综述草稿）
            await this.selectSession(this.currentSessionId);
            
        } catch (e) {
            alert("网络错误：" + e.message);
        } finally {
            btn.innerHTML = originHTML;
            btn.disabled = false;
        }
    },

    async loadSessions() {
        const listDiv = document.getElementById("sessionList");
        if (!listDiv) return;
        listDiv.innerHTML = '<div style="color:var(--text-secondary); font-size:0.85rem;">加载中...</div>';
        try {
            const res = await fetch("/api/sessions/list");
            const sessions = await res.json();
            if (!sessions || sessions.length === 0) {
                listDiv.innerHTML = '<div style="color:var(--text-secondary); font-size:0.85rem;">暂无会话</div>';
                return;
            }
            listDiv.innerHTML = "";
            sessions.forEach(s => {
                const div = document.createElement("div");
                div.className = "session-item";
                if (s.session_id === this.currentSessionId) {
                    div.classList.add("active-session");
                }
                
                const infoSpan = document.createElement("span");
                infoSpan.style.cssText = "flex:1;display:flex;justify-content:space-between;align-items:center;cursor:pointer;min-width:0;";
                infoSpan.innerHTML = `
                    <span class="session-topic" title="${this.escapeHtml(s.topic)}" style="flex:1;min-width:0;">${this.escapeHtml(s.topic)}</span>
                    <span class="session-state state-${s.state}" style="flex-shrink:0;">${s.state_label || s.state}</span>
                `;
                infoSpan.onclick = () => this.selectSession(s.session_id);
                
                const editBtn = document.createElement("i");
                editBtn.className = "fas fa-edit";
                editBtn.style.cssText = "color:var(--accent-color);cursor:pointer;padding:2px 4px;font-size:0.75rem;flex-shrink:0;margin-left:4px;opacity:0.6;";
                editBtn.title = "编辑会话（关键词/主题）";
                editBtn.onclick = (e) => {
                    e.stopPropagation();
                    this.editSession(s.session_id, s.topic);
                };
                editBtn.onmouseenter = () => { editBtn.style.opacity = "1"; };
                editBtn.onmouseleave = () => { editBtn.style.opacity = "0.6"; };
                
                const delBtn = document.createElement("i");
                delBtn.className = "fas fa-trash";
                delBtn.style.cssText = "color:var(--error-color);cursor:pointer;padding:2px 4px;font-size:0.75rem;flex-shrink:0;margin-left:4px;opacity:0.6;";
                delBtn.title = "删除会话";
                delBtn.onclick = (e) => {
                    e.stopPropagation();
                    this.deleteSession(s.session_id);
                };
                delBtn.onmouseenter = () => { delBtn.style.opacity = "1"; };
                delBtn.onmouseleave = () => { delBtn.style.opacity = "0.6"; };
                
                div.appendChild(infoSpan);
                div.appendChild(editBtn);
                div.appendChild(delBtn);
                listDiv.appendChild(div);
            });
        } catch (e) {
            listDiv.innerHTML = `<div style="color:var(--error-color); font-size:0.85rem;">加载失败: ${e.message}</div>`;
        }
    },

    // 专门为历史页面定制的会话列表加载（可点击跳转至控制台查看）
    async loadSessionsForHistory() {
        const listDiv = document.getElementById("sessionList");
        if (!listDiv) return;
        listDiv.innerHTML = '<div style="color:var(--text-secondary); font-size:0.85rem;">加载中...</div>';

        fetch("/api/sessions/list")
            .then(res => res.json())
            .then(sessions => {
                if (!sessions || sessions.length === 0) {
                    listDiv.innerHTML = '<div style="color:var(--text-secondary); font-size:0.85rem;">暂无会话</div>';
                    return;
                }
                listDiv.innerHTML = "";
                sessions.forEach(s => {
                    const div = document.createElement("div");
                    div.className = "session-item";
                    div.innerHTML = `
                        <span style="flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
                            ${this.escapeHtml(s.topic || s.session_id)}
                        </span>
                        <span class="session-state state-${s.state}">${s.state_label || s.state}</span>
                    `;
                    div.title = "点击跳转到控制台查看详情";
                    div.onclick = () => {
                        // 跳转到控制台并带上 sessionId
                        window.location.href = `/app/console?sessionId=${s.session_id}`;
                    };
                    listDiv.appendChild(div);
                });
            })
            .catch(e => {
                listDiv.innerHTML = `<div style="color:var(--error-color); font-size:0.85rem;">加载失败: ${e.message}</div>`;
            });
    },

    async selectSession(sessionId) {
        try {
            const res = await fetch(`/api/sessions/${sessionId}`);
            const session = await res.json();
            if (!res.ok) throw new Error(session.detail || "加载失败");

            this.currentSessionId = sessionId;
            this.currentKeywords = session.keywords || [];
            this.currentPlan = session.initial_plan || "";
            this.currentTopic = session.topic || "";

            // ━━━ 先清空所有面板，避免旧会话数据残留 ━━━
            this.tracesContainer.innerHTML = '<div style="color: var(--text-secondary); text-align: center; margin-top: 2rem;">等待运行...</div>';
            this.researchResult.innerHTML = '<div style="color: var(--text-secondary); text-align: center; margin-top: 2rem;">研究完成后显示...</div>';
            this.writerResult.innerHTML = '<div style="color: var(--text-secondary); text-align: center; margin-top: 2rem;">综述生成后显示...</div>';
            document.getElementById("papersList").innerHTML = '<div style="color: var(--text-secondary); text-align: center; margin-top: 2rem;">加载记录后显示已下载的 PDF...</div>';
            // 清理旧的收藏按钮
            const oldFavBtn = document.getElementById("favToggleBtn");
            if (oldFavBtn) oldFavBtn.remove();

            // 显示当前会话信息
            const infoDiv = document.getElementById("currentSessionInfo");
            if (infoDiv) {
                infoDiv.style.display = "block";
                document.getElementById("currentSessionId").textContent = session.topic || sessionId;
            }

            // 更新当前主题
            if (session.topic) {
                this.currentTopic = session.topic;
            }

            // 根据状态恢复界面
            this.setStatus("done", `已加载会话: ${session.state}`);

            // 加载论文列表
            if (session.papers && session.papers.length > 0) {
                this.renderSessionPapers(sessionId, session.papers);
            }

            // 加载笔记
            if (session.notes) {
                this.researchResult.innerHTML = marked.parse(session.notes);
            }

            // 加载草稿
            if (session.draft) {
                this.writerResult.innerHTML = marked.parse(session.draft);
                this.showFavoriteBtn(sessionId);
            }

            // 加载运行轨迹
            if (session.traces && session.traces.length > 0) {
                this.renderTraces(session.traces);
            } else if (session.notes) {
                this.tracesContainer.innerHTML = '<div style="color: var(--text-secondary); text-align: center; margin-top: 2rem;">已完成搜索阶段（轨迹存储在会话中）</div>';
            }

            // 根据会话状态引导按钮
            this.renderSessionGuide(session);

            // 刷新列表高亮
            this.loadSessions();

            // 如果是 planning 状态，显示关键词弹窗
            if (session.state === "planning" && session.keywords && session.keywords.length > 0) {
                this.showKeywordModal(session.topic, session.keywords);
            }

        } catch (e) {
            this.setStatus("error", `加载会话失败: ${e.message}`);
        }
    },

    async editSession(sessionId, topic) {
        // 加载会话的关键词并打开编辑弹窗
        try {
            const res = await fetch(`/api/sessions/${sessionId}`);
            const session = await res.json();
            this.currentSessionId = sessionId;
            this.currentTopic = session.topic || topic;
            this.currentKeywords = session.keywords || [];
            this.showKeywordModal(this.currentTopic, this.currentKeywords);
        } catch (e) {
            this.setStatus("error", `加载会话失败: ${e.message}`);
        }
    },

    async deleteSession(sessionId) {
        if (!confirm(`确定要删除会话 "${sessionId}" 吗？此操作不可撤销。`)) return;
        try {
            const res = await fetch(`/api/sessions/${sessionId}`, { method: "DELETE" });
            if (!res.ok) throw new Error((await res.json()).detail || "删除失败");
            if (this.currentSessionId === sessionId) {
                this.currentSessionId = null;
                this.currentKeywords = [];
                const infoDiv = document.getElementById("currentSessionInfo");
                if (infoDiv) infoDiv.style.display = "none";
            }
            this.loadSessions();
            this.setStatus("done", `已删除会话`);
        } catch (e) {
            this.setStatus("error", `删除失败: ${e.message}`);
        }
    },

    toggleSessionPanel() {
        const content = document.getElementById("sessionPanelContent");
        const icon = document.getElementById("sessionToggleIcon");
        if (!content || !icon) return;
        const collapsed = content.style.display === "none";
        content.style.display = collapsed ? "block" : "none";
        icon.className = collapsed ? "fas fa-chevron-up" : "fas fa-chevron-down";
    },

    showNewSessionDialog() {
        document.getElementById("newSessionTopic").value = this.currentTopic || "";
        document.getElementById("newSessionModal").classList.add("active");
    },

    closeNewSessionDialog() {
        document.getElementById("newSessionModal").classList.remove("active");
    },

    async createNewSession() {
        const topic = document.getElementById("newSessionTopic").value.trim();
        if (!topic) {
            alert("请输入研究主题");
            return;
        }
        document.getElementById("newSessionModal").classList.remove("active");
        
        if (this.sessionMode === "quick") {
            await this.runQuickMode(topic);
        } else {
            await this.createSession(topic);
        }
    },

    // 新建会话并跳转到控制台（历史页专用）
    createNewSessionAndGo() {
        const topic = prompt("请输入研究主题：");
        if (!topic) return;
        window.location.href = "/app/console?newTopic=" + encodeURIComponent(topic);
    },

    // ━━━ 快速模式：立即创建 Session → 后台执行 → 结果填入 Session → 清理临时文件 ━━━
    async runQuickMode(topic) {
        // 1. 立即创建 Session，在会话列表中立即可见（按钮灰掉）
        let sessionId, outputFile;
        try {
            const sRes = await fetch("/api/sessions/create", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ topic }),
            });
            const sData = await sRes.json();
            if (!sRes.ok) throw new Error(sData.detail || "创建会话失败");
            sessionId = sData.session_id;
            this.currentSessionId = sessionId;
            this.currentTopic = topic;
            // 标记为快速模式执行中
            await fetch(`/api/sessions/${sessionId}/state`, {
                method: "PUT", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ state: "plan_confirmed" }),
            }).catch(() => {});
            await fetch(`/api/sessions/${sessionId}/state`, {
                method: "PUT", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ state: "searching" }),
            }).catch(() => {});
            this.loadSessions(); // 列表中立即出现
        } catch (e) {
            this.setStatus("error", `创建会话失败: ${e.message}`);
            return;
        }

        // 2. 按钮显示执行状态
        this.startBtn.disabled = true;
        this.startBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 快速执行中...';
        this.setStatus("running", "快速模式：全自动调研中...");
        this.switchTab('traces');
        this.tracesContainer.innerHTML = '<div style="color:#666;text-align:center;margin-top:2rem;">正在初始化快速调研（全自动模式）...</div>';
        this.researchResult.innerHTML = '<div style="color:#666;text-align:center;">执行中...</div>';
        this.writerResult.innerHTML = '<div style="color:#666;text-align:center;">执行中...</div>';

        try {
            const startResp = await fetch("/api/run/start", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ topic, max_loops: 20 }),
            });
            const startData = await startResp.json();
            if (!startResp.ok) throw new Error(startData.detail || "启动失败");
            const runId = startData.run_id;

            if (this.pollTimer) clearInterval(this.pollTimer);

            const poll = async () => {
                const statusResp = await fetch(`/api/run/${runId}`);
                if (!statusResp.ok) throw new Error("查询状态失败");
                const sd = await statusResp.json();

                this.renderTraces(sd.traces || []);
                this.renderFailureSummary(sd.failure_summary || {});
                if (sd.researcher_result) this.researchResult.innerHTML = marked.parse(sd.researcher_result);
                if (sd.writer_result) this.writerResult.innerHTML = marked.parse(sd.writer_result);
                if (sd.papers !== undefined) this.renderPapers(sd.output_file, sd.papers || []);
                if (sd.output_file) {
                    this.outputPath.textContent = sd.output_file;
                    outputFile = sd.output_file;
                }
                if (sd.status === "running") {
                    this.setStatus("running", `快速模式执行中...（${sd.phase}，${sd.traces?.length || 0} 步）`);
                    return;
                }
                clearInterval(this.pollTimer); this.pollTimer = null;

                if (sd.status === "done") {
                    // 3. 把结果填入 Session
                    try {
                        if (sd.researcher_result) {
                            await fetch(`/api/sessions/${sessionId}/notes`, {
                                method: "PUT", headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({ content: sd.researcher_result, version_note: "快速模式自动调研" }),
                            });
                        }
                        if (sd.traces) {
                            await fetch(`/api/sessions/${sessionId}/run/plan`, {
                                method: "POST", headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({ topic, start_phase: "plan" }),
                            }).catch(() => {});
                        }
                        // 复制 PDF 到 session papers 目录
                        if (outputFile && sd.papers?.length > 0) {
                            for (const pdf of sd.papers) {
                                try {
                                    const pdfResp = await fetch(`/api/agent/document/${outputFile}/papers/${pdf}`);
                                    if (pdfResp.ok) {
                                        const blob = await pdfResp.blob();
                                        // 通过 formData 上传到 session
                                        const formData = new FormData();
                                        formData.append("file", blob, pdf);
                                        await fetch(`/api/sessions/${sessionId}/upload-pdf`, {
                                            method: "POST", body: formData,
                                        }).catch(() => {});
                                    }
                                } catch (e) { /* skip */ }
                            }
                        }
                        await fetch(`/api/sessions/${sessionId}/state`, {
                            method: "PUT", headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ state: "search_complete" }),
                        }).catch(() => {});
                        // 4. 清理 documents 中的临时文件
                        if (outputFile) {
                            await fetch(`/api/agent/history/${outputFile}`, {
                                method: "DELETE",
                            }).catch(() => {});
                        }
                    } catch (e) {
                        console.warn("Session 保存失败:", e);
                    }

                    this.setStatus("done", "快速调研完成！");
                    this.resetBtn();
                    this.switchTab('writer');
                    this.loadSessions();
                    this.loadFavorites();
                    if (sessionId) {
                        this.showFavoriteBtn(sessionId);
                        this.addFavorite(sessionId, topic);
                    }
                } else {
                    throw new Error(sd.error || "执行失败");
                }
            };

            await poll();
            this.pollTimer = setInterval(async () => {
                try { await poll(); } catch (err) {
                    clearInterval(this.pollTimer); this.pollTimer = null;
                    this.setStatus("error", `失败: ${err.message}`);
                    this.resetBtn();
                }
            }, 1000);
        } catch (err) {
            if (this.pollTimer) { clearInterval(this.pollTimer); this.pollTimer = null; }
            this.setStatus("error", `快速模式失败: ${err.message}`);
            this.resetBtn();
        }
    },

    async createSession(topic) {
        try {
            const res = await fetch("/api/sessions/create", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ topic }),
            });
            const session = await res.json();
            if (!res.ok) throw new Error(session.detail || "创建失败");

            this.currentSessionId = session.session_id;
            this.currentTopic = topic;

            this.setStatus("done", "会话已创建，正在生成规划...");
            this.loadSessions();

            // 自动执行 Plan 阶段
            await this.runPlanPhase(session.session_id, topic);

        } catch (e) {
            this.setStatus("error", `创建会话失败: ${e.message}`);
        }
    },

    async runPlanPhase(sessionId, topic) {
        this.setStatus("running", "正在生成关键词规划...");
        this.startBtn.disabled = true;
        this.startBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 规划中...';

        try {
            const res = await fetch(`/api/sessions/${sessionId}/run/plan`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ topic, start_phase: "plan" }),
            });
            const result = await res.json();
            if (!res.ok) throw new Error(result.detail || "规划失败");

            this.currentKeywords = result.keywords || [];
            this.currentPlan = result.initial_plan || "";

            // 显示关键词确认弹窗
            this.showKeywordModal(topic, this.currentKeywords);
            this.setStatus("running", "请确认关键词方案");
            this.resetBtn();

        } catch (e) {
            this.setStatus("error", `规划失败: ${e.message}`);
            this.resetBtn();
        }
    },

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    //  Session-aware: 关键词确认
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    showKeywordModal(topic, keywords) {
        document.getElementById("kwTopic").textContent = topic;
        const listDiv = document.getElementById("keywordList");
        listDiv.innerHTML = "";

        if (!keywords || keywords.length === 0) {
            this.addKeywordRow();
        } else {
            keywords.forEach(kw => this.addKeywordRow(kw));
        }

        document.getElementById("keywordModal").classList.add("active");
    },

    closeKeywordModal() {
        document.getElementById("keywordModal").classList.remove("active");
    },

    addKeywordRow(kwData = null) {
        const listDiv = document.getElementById("keywordList");
        const row = document.createElement("div");
        row.className = "keyword-row";

        const idx = listDiv.children.length + 1;
        row.innerHTML = `
            <span style="font-size:0.8rem;color:var(--text-secondary);min-width:60px;">关键词${idx}</span>
            <input type="text" class="kw-original" placeholder="中文原词" value="${this.escapeHtml(kwData?.original || '')}">
            <input type="text" class="kw-english" placeholder="英文学术语" value="${this.escapeHtml(kwData?.english || '')}">
            <input type="text" class="kw-synonyms" placeholder="同义词（逗号分隔）" value="${this.escapeHtml(kwData?.synonyms || '')}">
            <button class="kw-del-btn" onclick="this.parentElement.remove()" title="删除">✕</button>
        `;
        listDiv.appendChild(row);
    },

    collectKeywords() {
        const rows = document.querySelectorAll("#keywordList .keyword-row");
        const keywords = [];
        rows.forEach(row => {
            const orig = row.querySelector(".kw-original")?.value?.trim() || "";
            const eng = row.querySelector(".kw-english")?.value?.trim() || "";
            const syns = row.querySelector(".kw-synonyms")?.value?.trim() || "";
            if (orig || eng) {
                keywords.push({ original: orig, english: eng, synonyms: syns });
            }
        });
        return keywords;
    },

    async confirmKeywords() {
        const keywords = this.collectKeywords();
        if (keywords.length === 0) {
            alert("请至少添加一个关键词");
            return;
        }

        document.getElementById("keywordModal").classList.remove("active");

        if (!this.currentSessionId) {
            alert("没有活跃的会话");
            return;
        }

        this.setStatus("running", "正在保存关键词...");

        try {
            // 先保存关键词
            await fetch(`/api/sessions/${this.currentSessionId}/keywords`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ keywords }),
            });

            // 更新状态为 plan_confirmed
            await fetch(`/api/sessions/${this.currentSessionId}/state`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ state: "plan_confirmed" }),
            });

            this.currentKeywords = keywords;
            this.setStatus("done", "关键词已确认，请点击「开始搜索」继续");
            this.startBtn.disabled = false;
            this.startBtn.innerHTML = '<i class="fas fa-search"></i> 开始搜索';
            this.startBtn.onclick = () => this.startSearchPhase();

            this.loadSessions();

        } catch (e) {
            this.setStatus("error", `保存关键词失败: ${e.message}`);
        }
    },

    async replanKeywords() {
        if (!this.currentSessionId || !this.currentTopic) return;

        document.getElementById("keywordModal").classList.remove("active");
        this.setStatus("running", "正在重新规划...");

        try {
            await fetch(`/api/sessions/${this.currentSessionId}/state`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ state: "planning" }),
            });
            await this.runPlanPhase(this.currentSessionId, this.currentTopic);
        } catch (e) {
            this.setStatus("error", `重新规划失败: ${e.message}`);
        }
    },

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    //  Session-aware: 搜索阶段（在关键词确认后触发）
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async startSearchPhase() {
        if (!this.currentSessionId) {
            alert("请先创建或选择一个会话");
            return;
        }
        const topic = this.currentTopic;
        if (!topic) {
            alert("请先选择或创建一个会话");
            return;
        }

        this.startBtn.disabled = true;
        this.startBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 搜索中...';
        this.setStatus("running", "正在启动搜索阶段...");
        this.switchTab('traces');

        try {
            const res = await fetch(`/api/sessions/${this.currentSessionId}/run/search`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ topic, start_phase: "search", keywords: this.currentKeywords || [], max_loops: 20 }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "搜索启动失败");

            this.setStatus("running", "搜索进行中，请在会话列表中查看状态...");
            this.resetBtn();
            this.startBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 搜索中...';
            this.startBtn.disabled = true;

            // 轮询会话状态（实时显示 traces）
            let pollCount = 0;
            const pollSearch = async () => {
                pollCount++;
                const sRes = await fetch(`/api/sessions/${this.currentSessionId}`);
                const session = await sRes.json();

                // 实时更新 traces
                if (session.traces && session.traces.length > 0) {
                    this.renderTraces(session.traces);
                }

                if (["search_complete", "search_partial", "search_failed"].includes(session.state)) {
                    if (session.notes) this.researchResult.innerHTML = marked.parse(session.notes);
                    if (session.papers) this.renderSessionPapers(this.currentSessionId, session.papers);
                    if (session.traces && session.traces.length > 0) {
                        this.renderTraces(session.traces);
                    }
                    const latestRun = (session.search_runs || []).slice(-1)[0] || {};
                    const stateLabel = session.state === "search_complete" ? "done" : "error";
                    this.setStatus(stateLabel, latestRun.message || (session.state === "search_partial" ? "检索部分完成，可继续检索" : session.state === "search_failed" ? "检索失败，请调整关键词后重试" : "搜索完成！请审核笔记"));
                    this.showFavoriteBtn(this.currentSessionId);
                    this.loadSessions();
                    this.renderSessionGuide(session);
                    clearInterval(this.pollTimer);
                    this.pollTimer = null;
                } else if (session.state === "searching") {
                    this.setStatus("running", `搜索中... (${pollCount * 3}s) — 轨迹实时更新中`);
                } else {
                    this.loadSessions();
                    clearInterval(this.pollTimer);
                    this.pollTimer = null;
                }
            };

            await pollSearch();
            this.pollTimer = setInterval(pollSearch, 3000);

        } catch (e) {
            this.setStatus("error", `搜索失败: ${e.message}`);
            this.resetBtn();
        }
    },

    // 会话状态引导：根据当前状态显示合适的按钮
    renderSessionGuide(session) {
        const state = session.state;
        this.startBtn.disabled = false;

        if (state === "planning") {
            this.startBtn.innerHTML = '<i class="fas fa-key"></i> 编辑关键词';
            this.startBtn.onclick = () => this.showKeywordModal(session.topic, session.keywords || []);
        } else if (state === "plan_confirmed") {
            this.startBtn.innerHTML = '<i class="fas fa-search"></i> 开始搜索';
            this.startBtn.onclick = () => this.startSearchPhase();
        } else if (state === "searching") {
            this.startBtn.disabled = true;
            this.startBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 搜索中...';
        } else if (state === "search_complete") {
            this.startBtn.innerHTML = '<i class="fas fa-pen"></i> 审核笔记';
            this.startBtn.onclick = () => { this.switchTab('research'); };
            // 同时显示撰写按钮
            this.showWriteBtnAfterSearch();
        } else if (state === "search_partial" || state === "search_failed") {
            this.startBtn.innerHTML = '<i class="fas fa-search-plus"></i> 继续检索';
            this.startBtn.onclick = () => this.startSearchPhase();
        } else if (state === "reviewing_notes") {
            this.startBtn.innerHTML = '<i class="fas fa-file-alt"></i> 开始撰写';
            this.startBtn.onclick = () => this.runWritePhase();
        } else if (state === "writing") {
            this.startBtn.disabled = true;
            this.startBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 撰写中...';
        } else if (state === "reviewing_draft") {
            this.startBtn.innerHTML = '<i class="fas fa-sync"></i> 提交反馈';
            this.startBtn.onclick = () => { this.switchTab('writer'); };
        } else if (state === "complete") {
            this.startBtn.innerHTML = '<i class="fas fa-check-circle" style="color:var(--success-color);"></i> 已完成';
            this.startBtn.disabled = true;
        } else {
            this.startBtn.innerHTML = '<i class="fas fa-play"></i> 开始研究';
            this.startBtn.onclick = () => this.startAgent();
        }
    },

    async runWritePhase() {
        if (!this.currentSessionId) return;
        const topic = this.currentTopic;
        this.startBtn.disabled = true;
        this.startBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 撰写中...';
        this.setStatus("running", "正在撰写综述...");
        try {
            const res = await fetch(`/api/sessions/${this.currentSessionId}/run/write`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ topic, start_phase: "write" }),
            });
            const data = await res.json();
            if (data.draft) {
                this.writerResult.innerHTML = marked.parse(data.draft);
                this.showFavoriteBtn(this.currentSessionId);
            }
            this.setStatus("done", "撰写完成！请查看草稿");
            this.switchTab('writer');
            this.loadSessions();
            this.resetBtn();
            this.renderSessionGuide({ state: "reviewing_draft" });
        } catch (e) {
            this.setStatus("error", `撰写失败: ${e.message}`);
            this.resetBtn();
        }
    },

    showWriteBtnAfterSearch() {
        // 在笔记区域底部添加「开始撰写」按钮
        const existing = document.getElementById("writeAfterSearchBtn");
        if (existing) existing.remove();
        
        const btn = document.createElement("button");
        btn.id = "writeAfterSearchBtn";
        btn.style.cssText = "margin-top:1rem;padding:0.6rem 1.5rem;border-radius:8px;font-size:0.9rem;font-weight:600;cursor:pointer;background:linear-gradient(135deg, var(--primary-color), var(--secondary-color));color:white;border:none;box-shadow:0 4px 12px rgba(99,102,241,0.3);";
        btn.innerHTML = '<i class="fas fa-file-alt"></i> 开始撰写综述';
        btn.onclick = () => this.runWritePhase();
        
        const researchResult = document.getElementById("researchResult");
        if (researchResult) {
            researchResult.appendChild(btn);
        }
    },

    renderSessionPapers(sessionId, papers) {
        const listDiv = document.getElementById("papersList");
        if (!listDiv) return;
        if (!papers || papers.length === 0) {
            listDiv.innerHTML = '<div style="color: var(--text-secondary); text-align: center; margin-top: 2rem;">暂无论文</div>';
            return;
        }
        listDiv.innerHTML = papers.map(p => `
            <div style="display: flex; justify-content: space-between; padding: 0.8rem; border: 1px solid var(--border-color); border-radius: 10px; background: var(--card-background); align-items: center;">
                <div>
                    <div style="font-weight:500;color:var(--text-color);">${this.escapeHtml(p.title || p.paper_id)}</div>
                    <div style="font-size:0.75rem;color:var(--text-secondary);">
                        来源: ${p.source || 'agent_search'}
                        <span style="margin-left:8px;padding:1px 6px;border-radius:4px;font-size:0.7rem;background:${p.status==='accepted'?'rgba(16,185,129,0.2)':p.status==='rejected'?'rgba(239,68,68,0.2)':'rgba(148,163,184,0.2)'};color:${p.status==='accepted'?'#6ee7b7':p.status==='rejected'?'#fca5a5':'#cbd5e1'}">${p.status || 'pending'}</span>
                    </div>
                </div>
                <a href="/api/agent/document/${sessionId}/papers/${p.paper_id}.pdf" target="_blank" style="color:var(--primary-color);text-decoration:none;padding:0.3rem 0.6rem;border:1px solid var(--primary-color);border-radius:6px;font-size:0.8rem;">
                    <i class="fas fa-external-link-alt"></i> PDF
                </a>
            </div>
        `).join('');
    },

    async showFavoriteBtn(filename) {
        const existing = document.getElementById("favToggleBtn");
        if (existing) existing.remove();
        
        // 检查是否已收藏
        let isFavorited = false;
        try {
            const favRes = await fetch("/api/favorites");
            const favs = await favRes.json();
            isFavorited = favs.some(f => f.filename === filename);
        } catch (e) { /* ignore */ }
        
        const btn = document.createElement("button");
        btn.id = "favToggleBtn";
        btn.style.cssText = "margin-top:0.5rem;padding:0.4rem 1rem;border-radius:6px;font-size:0.85rem;cursor:pointer;background:var(--surface-light);border:1px solid var(--border-color);color:var(--text-secondary);";
        
        if (isFavorited) {
            btn.innerHTML = '<i class="fas fa-star" style="color:var(--warning-color);"></i> 取消收藏';
            btn.onclick = () => {
                this.unfavorite(filename);
                btn.innerHTML = '<i class="far fa-star" style="color:var(--warning-color);"></i> 加入收藏夹';
                btn.onclick = () => { this.addFavorite(filename, this.currentTopic || filename); btn.innerHTML = '<i class="fas fa-star" style="color:var(--warning-color);"></i> 已收藏'; btn.disabled = true; };
            };
        } else {
            btn.innerHTML = '<i class="far fa-star" style="color:var(--warning-color);"></i> 加入收藏夹';
            btn.onclick = () => {
                this.addFavorite(filename, this.currentTopic || filename);
                btn.innerHTML = '<i class="fas fa-star" style="color:var(--warning-color);"></i> 取消收藏';
                btn.onclick = () => { this.unfavorite(filename); btn.innerHTML = '<i class="far fa-star" style="color:var(--warning-color);"></i> 加入收藏夹'; };
            };
        }
        
        const pathEl = document.getElementById("outputPath");
        if (pathEl && pathEl.parentElement) {
            pathEl.parentElement.appendChild(btn);
        }
    },

    escapeHtml(str) {
        if (!str) return "";
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }
};

/*
window.onload = () => {
    app.init();
};
 */

// 移除原有的 window.onload 自动执行，改为按需初始化
document.addEventListener('DOMContentLoaded', () => {
    const page = document.body.getAttribute('data-page');
    if (page === 'console') {
        app.initConsole();
    } else if (page === 'history') {
        app.initHistoryPage();
        app.loadFavorites();
    } else if (page === 'chat') {
        app.initChatPage();
    }
});

