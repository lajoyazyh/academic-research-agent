const app = {
    pollTimer: null,
    chatMessages: [],
    
    init() {
        this.topicInput = document.getElementById("topic");
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
        
        this.loadHistory();
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
        const topic = this.topicInput.value.trim();

        if (!topic) {
            alert("请输入研究主题");
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
                    this.loadHistory();
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

    async loadHistory() {
        this.historyList.innerHTML = '<div style="color:#999; font-size:0.85rem;">加载中...</div>';
        try {
            const res = await fetch("/api/agent/history");
            const data = await res.json();
            
            if (!data || data.length === 0) {
                this.historyList.innerHTML = '<div style="color:#999; font-size:0.85rem;">暂无历史记录</div>';
                return;
            }
            
            this.historyList.innerHTML = "";
            data.forEach(item => {
                const div = document.createElement("div");
                div.className = "history-item";
                div.onclick = () => this.loadHistoryDetail(item.filename);
                
                div.innerHTML = `
                    <strong>${item.filename}</strong><br>
                    <span style="color:#666; font-size:0.85rem;">${(item.size / 1024).toFixed(1)} KB</span>
                `;
                this.historyList.appendChild(div);
            });
            
        } catch(e) {
            this.historyList.innerHTML = `<div style="color:red; font-size:0.85rem;">加载失败: ${e.message}</div>`;
        }
    },

    async loadHistoryDetail(filename) {
        this.setStatus("running", `正在加载 ${filename}...`);
        try {
            const res = await fetch(`/api/agent/history/${filename}`);
            const data = await res.json();
            
            if (!res.ok) throw new Error(data.detail);
            
            this.tracesContainer.innerHTML = '<div style="color: #666; text-align: center; margin-top: 2rem;">旧记录，无 Trace</div>';
            
            if (data.researcher_result) {
                this.researchResult.innerHTML = marked.parse(data.researcher_result);
            } else {
                this.researchResult.innerHTML = '<div style="color: #666; text-align: center; margin-top: 2rem;">旧记录，无单独摘要</div>';
            }
            
            if (data.writer_result) {
                this.writerResult.innerHTML = marked.parse(data.writer_result);
            } else {
                this.writerResult.innerHTML = marked.parse(data.content);
            }
            
            this.renderPapers(filename, data.papers || []);
            this.outputPath.textContent = filename;

            this.setStatus("done", "成功加载历史综述");
            this.switchTab('writer');
        } catch(e) {
            this.setStatus("error", `加载详情失败: ${e.message}`);
        }
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
        contentDiv.textContent = text;
        
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
    }
};

window.onload = () => {
    app.init();
};
