# Academic Research Agent 详细设计文档

**版本**：v3.0  
**日期**：2026-06-18  
**范围**：迭代三当前实现架构

---

## 1. 总体架构

系统由五层组成：

```text
前端页面
  -> FastAPI 路由层
  -> Session / Skill / Knowledge 管理层
  -> Agent Pipeline 与工具层
  -> 文件系统持久化与 evaluation 支撑
```

主要入口：

- Web：`agent/web_app.py`
- CLI：`agent/main.py`
- 前端：`agent/frontend/`
- 后端路由：`agent/backend/routes/`
- Session 数据：`agent/sessions/`

---

## 2. 后端模块

### 2.1 Web 入口

`web_app.py` 负责：

- 创建 FastAPI 应用。
- 初始化 SessionManager、GlobalKnowledgeBase、SkillManager、CopilotManager、ToolRegistry。
- 调用 `init_deps()` 注入共享依赖。
- 注册各路由模块。
- 挂载静态文件。

### 2.2 路由模块

```text
backend/routes/
├── deps.py          # 共享依赖与运行时 RUNS
├── models.py        # Pydantic 请求模型
├── pages.py         # 页面、收藏、历史、PDF
├── session.py       # Session、论文、笔记、分析持久化
├── agent.py         # plan/search/notes/analyze/write/auto
├── chat.py          # Session 内聊天与修订
├── conversation.py  # 多会话聊天管理
├── draft.py         # 草稿保存
└── admin.py         # 工具、Skills、全局知识库、Copilot
```

设计原则：

- 固定路径路由优先于参数路由注册。
- 共享对象通过 `deps.py` 延迟注入，避免循环导入。
- 请求模型集中到 `models.py`，减少重复定义。

---

## 3. 数据模型与存储

### 3.1 Session 目录

```text
sessions/{session_id}/
├── metadata.json
├── plan/
│   ├── initial_plan.md
│   └── confirmed_keywords.json
├── papers/
│   ├── papers_list.json
│   ├── deleted_papers.json
│   └── *.pdf / *.txt
├── notes/
│   └── draft_notes.md
├── analysis/
│   └── analysis_results.json
├── draft/
│   ├── draft_v*.md
│   └── current_draft.md
├── traces/
│   └── run_traces.json
└── chats/
    ├── _index.json
    └── conv_*.json
```

### 3.2 状态机

```text
planning -> plan_confirmed -> searching -> search_complete
-> reviewing_notes -> writing -> reviewing_draft -> complete
```

实现要点：

- 状态转移由 `SessionManager` 校验。
- 自动流程按合法状态推进。
- 卡住状态可自动修复到稳定状态。

---

## 4. Agent Pipeline

### 4.1 分步执行

分步模式对应接口：

```text
POST /api/sessions/{id}/run/plan
POST /api/sessions/{id}/run/search
POST /api/sessions/{id}/run/notes
POST /api/sessions/{id}/run/analyze
POST /api/sessions/{id}/run/write
```

用户可在每个阶段之间检查和修改中间产物。

### 4.2 自动执行

自动模式对应：

```text
POST /api/sessions/{id}/run/auto
GET  /api/sessions/{id}/run/status
POST /api/sessions/{id}/run/cancel
```

自动流程：

```text
规划 -> 搜索 -> 笔记 -> 分析 -> 综述
```

执行状态保存在 `RUNS` 中，前端通过轮询获取进度、论文列表、分析结果和 traces。

---

## 5. 推理与工具

### 5.1 Plan-and-Execute

规划阶段先生成检索计划，包括关键词拆分、数据库选择、筛选策略和回退策略。用户确认关键词后进入搜索。

### 5.2 ReAct 搜索循环

搜索阶段由 `BaseAgent` 执行：

```text
thought -> action -> action_input -> observation -> next thought
```

Agent 可调用注册工具，包括 arXiv、OpenAlex、Crossref、PaperRegister 等。每一步写入 trace。

### 5.3 Reflexion 与质量门禁

系统对以下情况进行反馈：

- JSON 解析错误。
- 未知工具名。
- 工具运行时异常。
- 连续同类错误。
- FINISH 前论文数量不足。

---

## 6. 笔记、分析与写作

### 6.1 RAG 笔记生成

`RAGNoteGenerator` 的策略：

- PDF 文本切块。
- Embedding 检索相关片段。
- Embedding 不可用时回退 BM25。
- PDF 不可用时基于摘要生成。
- 输出结构化 Markdown 笔记。

### 6.2 深度分析

`tools/analysis_tools.py` 提供：

- `compare`：文献方法对比。
- `lineage`：研究脉络。
- `gaps`：研究空白。
- `all`：生成完整分析文档。

分析结果存入：

```text
sessions/{session_id}/analysis/analysis_results.json
```

前端以三张 Markdown 卡片展示，并支持单独编辑。

### 6.3 综述写作

Writer 输入：

- 聚合后的笔记。
- 用户反馈。
- 写作 Skill。
- 分析阶段生成的洞察上下文。

输出：

- Markdown 综述草稿。
- 是否使用分析上下文的标记。
- 被引用论文列表。

---

## 7. Skills 设计

### 7.1 Skill 类型

| 类型 | 阶段 | 注入点 |
|------|------|------|
| search | 搜索 | `run_search_only()` |
| notes | 笔记 | `RAGNoteGenerator.generate()` |
| write | 综述 | `run_write_from_notes()` |

### 7.2 双通道机制

```text
Skill 有效 -> 使用 Skill 策略
Skill 缺失/空/删除/加载失败 -> 回退默认策略
```

### 7.3 可观测性

三阶段都会写入：

```json
{
  "action": "SKILL_STATUS",
  "input": {
    "phase": "write",
    "skill_id": "skill_xxx",
    "skill_title": "自定义写作策略",
    "loaded": true,
    "fallback_default": false
  },
  "error_type": "skill_info"
}
```

---

## 8. 对话系统

### 8.1 Session 内聊天

每个 Session 支持多个 conversation。聊天入口会：

- 保存用户消息和助手回复。
- 检索当前 Session 的论文内容。
- 管理上下文窗口。
- 判断是否需要触发笔记或综述修订。

### 8.2 上下文压缩

当对话轮次较多时，系统可将早期消息压缩成摘要，保留近期对话，降低上下文压力。

---

## 9. 全局知识库

`GlobalKnowledgeBase` 扫描所有真实 Session：

- 论文摘要。
- 笔记片段。
- 最新综述草稿。

检索使用 TF-IDF/BM25 风格索引。`/api/knowledge/chat` 支持：

- 默认全局检索。
- 传入 `session_ids` 后限定范围检索。

---

## 10. 前端设计

主要页面：

- `home.html`：首页、项目列表、统计、全局 Copilot。
- `index.html`：控制台。
- `history.html`：历史记录。
- `help.html`：帮助。

控制台能力：

- 阶段标签页。
- 论文卡片。
- Vditor Markdown 编辑器。
- 分析三卡片。
- trace 实时查看。
- 自动模式进度展示。

---

## 11. 评估与测试

评估目录：

```text
evaluation/
├── evaluation_tasks.csv
├── eval_platform.db
├── run_eval.py
└── code/
```

测试：

- 使用 `pytest -q` 运行现有测试。
- 文档更新后仍建议跑测试，避免导入路径或接口说明与实现脱节。

---

## 12. 关键设计取舍

- 自动模式与分步模式共用同一套 Pipeline，避免维护两套逻辑。
- 分析阶段作为写作上下文增强，而不是独立孤立功能。
- Skills 失败时默认回退，保证演示稳定性。
- 全局 Copilot 默认全局检索，但允许用户显式选择范围。
- 外部 API 不稳定时，禁用部分工具属于工程稳定性策略。
