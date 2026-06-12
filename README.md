# 迭代三：连续对话与交互式调研平台

迭代三在迭代二 Agent 的基础上，从“一次性黑盒执行”升级为**会话驱动的交互式调研平台**——用户可在关键决策点参与、编辑、反馈，与 Agent 协作完成高质量文献综述。

当前版本已完成统一聊天入口与对话式修订协同：普通问题会走 AI 问答，Agent 模式下的隐式修改意图会先由 AI 判定，再在对话内确认后执行，显式 `/修订` 仍可直接触发修订。

## 演示视频
- 迭代二：https://www.bilibili.com/video/BV1Fq5A61EMV

## 核心模块

agent/
├── web_app.py              # FastAPI Web 服务入口
├── main.py                 # Agent 管线（Plan / Search / Write 断点执行）
├── backend/
│   ├── session_manager.py  # Session 会话状态管理（8 阶段状态机）
│   └── api.py              # 独立 API（备用）
├── core/                   # Agent 核心（ReAct 循环、工具调度）
├── tools/
│   ├── arxiv_tools.py      # arXiv 搜索/获取
│   ├── crossref_tools.py   # Crossref 搜索/DOI
│   ├── openalex_tools.py   # OpenAlex 搜索
│   ├── pdf_tools.py        # PDF 下载/解析/全量提取
│   ├── paper_register.py   # 下载+收录一体化工具
│   ├── retriever.py        # BM25 检索器（对话 RAG）
│   └── rag_note_generator.py  # Embedding RAG 笔记生成器
├── llms/                   # LLM 客户端（智谱 API）
├── config/                 # 配置管理
├── utils/                  # 辅助工具与解析器
├── frontend/               # Web UI
│   ├── index.html
│   ├── home.html
│   ├── history.html
│   ├── chat.html
│   ├── help.html
│   ├── app.js
│   ├── notebooklm.js
│   ├── styles.css
│   └── notebooklm.css
├── sessions/               # Session 数据存储
│   └── {session_id}/
│       ├── metadata.json
│       ├── plan/           # 规划与关键词
│       ├── papers/         # 论文 PDF + 元数据
│       ├── notes/          # 笔记草稿 + 编辑历史
│       └── draft/          # 综述草稿多版本
├── documents/              # CLI 运行输出与迭代二兼容目录
└── prompts/                # Prompt 模板

tests/                      # 自动化测试目录
docs/                       # 文档相关目录

## 迭代三核心创新

### 1. Session 会话模型
```
planning → plan_confirmed → searching → search_complete
→ reviewing_notes → writing → reviewing_draft → complete
```
任意状态可跳回 `searching`（追加调研）。

### 2. Agent 检索三阶段

| 阶段 | 功能 | 核心工具 |
|------|------|---------|
| **Plan** | LLM 生成关键词方案，用户可编辑确认 | `_build_initial_plan` |
| **Search** | Agent 搜索 → 审核摘要 → `paper_register` 下载+登记 | `paper_register`, `arxiv_search` |
| **Notes** | RAG 生成深度笔记：PDF 全文 → Embedding → 逐节 LLM | `RAGNoteGenerator` |

### 3. RAG 检索增强架构

| 场景 | 方案 |
|------|------|
| **AI 对话栏** | BM25 检索 PDF 段落 → 注入问答/修订 prompt |
| **首次生成笔记** | Embedding 向量检索 → Top-K 原文段落 → LLM 逐节生成 |

### 4. 前端功能
- 🔍 关键词审核/编辑 · 📄 论文管理 · ✏️ Vditor 编辑器 · 📝 AI 判意修订
- 🛑 检索打断 · 📊 轨迹视图（时间戳+目录+追加调研分隔）
- 🛠 工具管理 · 💬 全局 Copilot 侧边栏

### 5. 工具管理（16 个工具，6 个分类）

所有工具通过 `core/tool_registry.py` 统一管理，支持启用/禁用，配置持久化到 `config/tools.json`。

| 分类 | 工具 | 使用阶段 |
|------|------|---------|
| 🔍 学术搜索 | `arxiv_search`、`arxiv_fetch`、`semantic_scholar_search`、`semantic_scholar_fetch`、`crossref_search`、`crossref_fetch_doi`、`openalex_search` | 搜索阶段 |
| 📄 PDF 处理 | `arxiv_pdf_reader`、`arxiv_download_pdf` | 搜索/笔记阶段 |
| ✏️ 文件操作 | `clear_notes`、`append_note` | 笔记阶段 |
| 💬 对话检索 | `retriever`（BM25 检索器） | 对话阶段 |
| 📝 笔记生成 | `rag_note_generator`（Embedding RAG） | 笔记阶段 |
| 📋 收录管理 | `paper_register` | 搜索阶段 |

### 6. 全局 Copilot 助手
- 首页侧边栏：跨 Session 全局知识问答
- 多轮对话历史管理
- 内嵌工具勾选面板（可选择参考哪些工具来源）

## 环境安装

```powershell
cd 迭代三
python -m pip install -r requirements.txt
```

## 配置方式
依赖智谱 API：在 agent/.env 中配置 ZHIPU_API_KEY、ZHIPU_BASE_URL、ZHIPU_MODEL。

## 运行方式

```powershell
cd 迭代三/agent
python web_app.py
```

浏览器打开 `http://127.0.0.1:8000/`

## Session 管理 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/sessions/create | 创建新会话 |
| GET | /api/sessions/list | 列出所有会话 |
| GET | /api/sessions/{id} | 获取会话完整状态 |
| DELETE | /api/sessions/{id} | 删除会话 |
| PUT | /api/sessions/{id} | 更新会话元数据 |
| PUT | /api/sessions/{id}/state | 状态转移（带校验） |
| PUT | /api/sessions/{id}/keywords | 保存确认后的关键词 |
| GET | /api/sessions/{id}/papers | 获取论文列表 |
| DELETE | /api/sessions/{id}/papers/{paper_id} | 删除单篇论文 |
| POST | /api/sessions/{id}/papers/batch-delete | 批量删除论文 |
| PUT | /api/sessions/{id}/papers/{paper_id}/status | 更新论文状态 |
| POST | /api/sessions/{id}/papers/custom | 添加自定义论文元数据 |
| POST | /api/sessions/{id}/papers/upload | 上传论文PDF进行解析 |
| GET | /api/sessions/{id}/notes | 获取研究笔记 |
| PUT | /api/sessions/{id}/notes | 保存修改后的研究笔记 |
| PUT | /api/sessions/{id}/feedback | 提交综述修改审核意见 |
| GET | /api/sessions/{id}/draft | 获取所有综述草稿列表 |
| GET | /api/sessions/state-machine | 获取状态机定义 |
| POST | /api/sessions/{id}/run/plan | 执行规划阶段 |
| POST | /api/sessions/{id}/run/search | 执行搜索阶段 |
| POST | /api/sessions/{id}/run/search | 执行搜索（后台+轮询） |
| POST | /api/sessions/{id}/run/cancel | 打断搜索 |
| GET | /api/sessions/{id}/run/status | 轮询执行状态 |
| POST | /api/sessions/{id}/run/notes | RAG 深度笔记生成 |
| POST | /api/sessions/{id}/run/write | 撰写综述 |
| POST | /api/sessions/{id}/chat | 统一聊天入口 |
| POST | /api/sessions/{id}/state/auto-fix | 修复卡住状态 |

## Agent 断点执行

```python
run_plan_only(topic)
run_search_only(topic, plan, keywords)
run_write_from_notes(topic, notes, feedback)
run_agent_pipeline_session(session_id, ...)   # Session 感知统一入口
```

## 进一步规划
- 迭代四：多用户协作、自动化评测集成、模板预设
