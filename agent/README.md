# Academic Research Agent

面向学术文献调研的 LLM Agent 应用。给定一个研究主题，Agent 自主规划检索策略，从 arXiv / Semantic Scholar / Crossref / OpenAlex 等学术数据库搜索前沿论文，阅读摘要和全文，记录结构化笔记，生成深度分析，并最终产出万字级文献综述。

支持 **CLI 命令行** 和 **Web 交互式平台** 两种运行模式。Web 平台提供会话驱动的交互式调研体验，支持**手动分步操作**和**一键自动进行**两种工作流。

---

## 核心架构：三种推理框架的有机融合

```
┌─────────────────────────────────────────────────┐
│  阶段 0: Plan-and-Execute（规划 → 执行）          │
│  Agent 先产出一个显式的研究计划：                  │
│  关键词拆分 → 数据库选择 → 备选策略 → 预期深度     │
├─────────────────────────────────────────────────┤
│  阶段 1-N: ReAct（推理 → 行动循环）               │
│  [思考] → 选择工具 → [执行] → 观察结果 → [再思考]  │
├─────────────────────────────────────────────────┤
│  内置: Reflexion（自我反思，5 个层次）             │
│  L1: 单次错误即时反馈（JSON格式/未知工具/运行异常） │
│  L2: 连续 3 次同类错误 → 深度反思提示              │
│  L3: FINISH 前自主质检（Self-Critique）            │
│  L4: PDF 自动兜底下载                             │
│  L5: 论文列表自动传递到前端                        │
└─────────────────────────────────────────────────┘
```

### Plan-and-Execute

Agent 在执行任何工具调用之前，先调用一次 LLM 产出一个显式研究计划，涵盖：
- 中英关键词拆分策略
- 数据库选择与调用顺序
- 零结果/限流时的备选方案
- 预计搜集篇数与阅读深度

该计划作为第一条 trace 记录在面板中，Agent 可在执行过程中动态修订。

### ReAct（Reasoning + Acting）

每一轮 Agent 都遵循固定的思考-行动-观察循环：
1. `thought`：分析当前状态，决定下一步行动
2. `action`：选择调用的工具名称
3. `action_input`：填入工具参数
4. `observation`：获取工具返回的环境事实
5. 进入下一轮直到 FINISH

### Reflexion（五层自我反思）

| 层次 | 触发条件 | 机制 |
|------|---------|------|
| **L1 即时反馈** | JSON 格式错误 / 工具名不存在 / 工具运行时异常 | 将错误信息反馈给 LLM，要求下一轮修正 |
| **L2 深度反思** | 连续 3 次同一类型错误 | 注入深度反思提示：分析根因、承认策略失败、提出全新替代方案 |
| **L3 自主质检** | FINISH 前且笔记数 >= 3 | 要求 Agent 逐篇审查笔记的完备性（标题/作者/DOI/方法/发现/关联），缺口补全后允许 FINISH |
| **L4 PDF 自动兜底** | Agent 主循环结束后 | 系统自动扫描所有轨迹中的论文 ID，批量下载 PDF 至 `papers/` 目录 |
| **L5 论文列表传递** | Agent 主循环结束后 | 自动收集已下载的 PDF 列表，通过 API 传递给前端，用户可在"参考论文"标签页查看/下载 |

### 质量门禁

FINISH 前系统自动检查是否收录了足够论文（默认 >= 3 篇，可通过 `AGENT_MIN_PAPERS` 环境变量调整），不满足则拦截并提示 Agent 继续搜集。

---

## 工具管理（16 个工具，6 个分类）

所有工具通过 `core/tool_registry.py` 统一管理，支持启用/禁用，配置持久化到 `config/tools.json`。控制台「工具管理」面板可开关式勾选。

### 工具分类与阶段标注

| 分类 | 工具 | 使用阶段 |
|------|------|---------|
| 🔍 学术搜索 | `arxiv_search`、`arxiv_fetch`、`semantic_scholar_search`、`semantic_scholar_fetch`、`crossref_search`、`crossref_fetch_doi`、`openalex_search` | 搜索阶段 |
| 📄 PDF 处理 | `arxiv_pdf_reader`、`arxiv_download_pdf` | 搜索阶段 / 笔记阶段 |
| ✏️ 文件操作 | `clear_notes`、`append_note` | 笔记阶段 |
| 💬 对话检索 | `retriever`（BM25 检索器） | 对话阶段 |
| 📝 笔记生成 | `rag_note_generator`（Embedding RAG 深度笔记） | 笔记阶段 |
| 📋 收录管理 | `paper_register`（下载 PDF + 登记到论文列表） | 搜索阶段 |

内置工程优化：全局限流器（arXiv 最小 5s 间隔）、429 指数退避重试（arXiv 10s × attempt、Semantic Scholar >= 30s）、查询变体自动降级、低相关度过滤。

---

## 工作流模式

### 手动分步模式

用户在每个关键节点手动确认和触发：

```
首页 → 输入主题 → 创建 Session
  → [规划] 点击「生成关键词」→ 编辑确认关键词
  → [搜索] 点击「AI检索论文」→ 后台搜索（实时轨迹可见）
  → [笔记] 选中论文 → 点击「生成笔记」→ RAG 深度笔记
  → [分析] 点击「生成深度分析报告」→ 文献对比 / 研究脉络 / 研究空白
  → [综述] 点击「生成综述」→ 撰写综述草稿
  → [修订] 对话区提交修改意见 → Agent 重写
```

### 一键自动模式 🚀

点击「自动进行」按钮，系统自动依次执行全部阶段：

```
规划 → 搜索 → 笔记 → 分析 → 综述
```

全程实时显示进度（状态栏 + 轨迹视图），分析阶段会在综述写作前生成 `compare / lineage / gaps` 三类洞察，并作为综述写作的额外上下文。完成后自动切换到综述视图。支持随时点击「停止」取消。

---

## 快速开始

### 1. 环境准备

```bash
# 安装依赖
pip install openai httpx python-dotenv PyMuPDF fastapi uvicorn
```

`.env` 最小配置：

```env
ZHIPU_API_KEY=your_key_here
ZHIPU_MODEL=glm-4-flash
```

可选但强烈推荐：

```env
SEMANTIC_SCHOLAR_API_KEY=your_free_key   # 免费注册 https://api.semanticscholar.org
ARXIV_USER_AGENT=YourApp/1.0 (mailto:you@example.com)
AGENT_MIN_PAPERS=3                       # 质量门禁：最少收录论文数
AGENT_LOOP_DELAY_SEC=3                   # Agent 循环间冷却秒数
```

### 2. 命令行运行

```bash
cd agent/
python main.py
```

输入研究主题后，CLI Agent 自动完成搜索-阅读-笔记-综述，结果保存在 `documents/{主题}_{时间戳}/` 下：

- `papers/` — 下载的 PDF 原文
- `research_notes.md` — Agent 的研究笔记
- `final_review.md` — 最终文献综述
- `plan.md` — 初始检索计划

### 3. Web 界面运行

```bash
cd agent/
python web_app.py
```

浏览器打开 `http://127.0.0.1:8000`，即可进入 **会话驱动的交互式调研平台**。

**首页功能**：
- 新建综述（输入主题 → AI 关键词规划 → 确认后进入控制台）
- 最近打开的综述列表（卡片式展示，含论文数/笔记状态）
- 工作台概览（综述项目数、收录论文数、笔记数、完成综述数、状态分布）
- 最近活动时间线

**控制台功能**：
- 🔍 **关键词审核/编辑** — AI 生成后可手动调整
- 📄 **论文管理** — 检索、添加（arXiv ID/链接/拖拽上传 PDF）、选中/移除
- ✏️ **Vditor Markdown 编辑器** — 在线编辑笔记、分析卡片和综述
- 📝 **AI 判意修订** — 对话区隐式修改意图先判定再确认执行
- 🛑 **检索打断** — 搜索进行中可随时停止
- 📊 **实时轨迹视图** — 搜索进行中即可查看每一步的思考/行动/观察
- 📊 **深度分析阶段** — 基于论文与笔记生成文献对比、研究脉络、研究空白三张 Markdown 卡片，可单独编辑并写入综述上下文
- 🚀 **一键自动模式** — 规划→搜索→笔记→分析→综述全自动执行
- 📎 **PDF 查看** — 已下载论文可在浏览器中直接查看
- ⭐ **收藏夹** — 收藏重要综述，支持取消收藏和删除
- 🛠 **工具管理** — 控制台「工具管理」面板，6 类 16 个工具开关式启用/禁用，配置持久化
- 💬 **全局 Copilot 助手** — 首页侧边栏：跨 Session 全局知识问答，多轮对话历史，内嵌工具勾选面板

---

## Session 状态机

```
planning → plan_confirmed → searching → search_complete
→ reviewing_notes → writing → reviewing_draft → complete
```

任意状态可跳回 `searching`（追加调研）。自动修复机制：加载 Session 时检测卡住状态（如 `writing`），若已有草稿文件则自动修复为 `complete`。

> 注：`analysis` 是自动运行时阶段和持久化产物目录，不作为 Session 状态机的独立持久状态；自动模式会在 `reviewing_notes` 之后、`writing` 之前生成分析结果。

---

## 目录结构

```
agent/
├── backend/
│   ├── api.py              # 独立 API（备用）
│   └── session_manager.py  # Session 会话状态管理（8 阶段状态机 + 自动修复）
├── config/
│   ├── __init__.py         # 配置模块
│   └── tools.json          # 工具注册中心配置文件
├── core/
│   ├── agent.py            # Agent 主循环（Plan+ReAct+Reflexion+质量门禁）
│   ├── tools.py            # 工具基类
│   ├── tool_registry.py    # 工具注册中心（启用/禁用 + 参数管理）
│   └── memory.py           # 短期记忆
├── tools/
│   ├── arxiv_tools.py      # arXiv 搜索/获取
│   ├── semantic_scholar_tools.py  # Semantic Scholar 搜索/获取
│   ├── crossref_tools.py   # Crossref 搜索/DOI 补全
│   ├── openalex_tools.py   # OpenAlex 跨学科搜索
│   ├── pdf_tools.py        # PDF 下载/解析/全量提取
│   ├── paper_register.py   # 论文收录一体化工具（审核摘要 + 下载 PDF + 登记）
│   ├── rag_note_generator.py  # Embedding RAG 深度笔记生成器
│   ├── retriever.py        # BM25 检索器（对话 RAG）
│   └── file_tools.py       # 笔记管理（CLI 模式）
├── llms/
│   └── client.py           # LLM 客户端（智谱/OpenAI 兼容）
├── sessions/               # Session 数据存储
│   └── {session_id}/
│       ├── metadata.json   # 会话元数据（状态/时间戳）
│       ├── plan/           # 规划与关键词
│       ├── papers/         # 论文 PDF + 元数据
│       ├── notes/          # 笔记草稿 + 编辑历史
│       ├── analysis/       # 深度分析结果（compare/lineage/gaps + 合并 document）
│       ├── draft/          # 综述草稿多版本
│       ├── traces/         # 执行轨迹
│       └── chats/          # 多会话聊天记录
│           ├── _index.json # 会话索引
│           └── conv_*.json # 消息历史
├── prompts/                # Prompt 模板
├── utils/
│   └── parser.py           # JSON 解析器
├── frontend/
│   ├── index.html          # 控制台页面
│   ├── home.html           # 首页
│   ├── history.html        # 历史记录页面
│   ├── chat.html           # 对话页面
│   ├── help.html           # 帮助页面
│   ├── app.js              # 前端入口逻辑
│   ├── notebooklm.js       # 页面交互与状态管理（核心前端逻辑）
│   ├── styles.css          # 基础样式
│   └── notebooklm.css      # UI 样式库
├── main.py                 # CLI 入口 + Agent 管线（Plan/Search/Write 断点执行）
├── web_app.py              # Web 入口（FastAPI，全部 API 端点）
├── .env                    # 环境配置
├── documents/              # CLI 运行输出与迭代二兼容目录
└── README.md
```

---

## API 端点总览

### Session 管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/sessions/create` | 创建新会话 |
| GET | `/api/sessions/list` | 列出所有会话 |
| GET | `/api/sessions/{id}` | 获取会话完整状态 |
| PUT | `/api/sessions/{id}` | 更新会话元数据 |
| DELETE | `/api/sessions/{id}` | 删除会话 |
| PUT | `/api/sessions/{id}/state` | 状态转移（带状态机校验） |
| POST | `/api/sessions/{id}/state/auto-fix` | 修复卡住状态 |
| GET | `/api/sessions/state-machine` | 获取状态机定义 |
| PUT | `/api/sessions/{id}/keywords` | 保存确认后的关键词 |

### 论文管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/sessions/{id}/papers` | 获取论文列表 |
| DELETE | `/api/sessions/{id}/papers/{paper_id}` | 删除单篇论文 |
| POST | `/api/sessions/{id}/papers/batch-delete` | 批量删除论文 |
| PUT | `/api/sessions/{id}/papers/{paper_id}/status` | 更新论文状态（accepted/pending） |
| POST | `/api/sessions/{id}/papers/custom` | 添加自定义论文元数据 |
| POST | `/api/sessions/{id}/papers/upload` | 上传论文 PDF 进行解析 |

### 笔记与草稿

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/sessions/{id}/notes` | 获取研究笔记 |
| PUT | `/api/sessions/{id}/notes` | 保存修改后的笔记 |
| PUT | `/api/sessions/{id}/analysis` | 保存单张分析卡片或完整分析 Markdown |
| PUT | `/api/sessions/{id}/feedback` | 提交综述修改意见 |
| GET | `/api/sessions/{id}/draft` | 获取综述草稿（支持版本号） |
| PUT | `/api/sessions/{id}/draft` | 保存草稿编辑 |

### Agent 执行

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/sessions/{id}/run/plan` | 执行规划阶段 |
| POST | `/api/sessions/{id}/run/search` | 执行搜索阶段（后台+轮询） |
| POST | `/api/sessions/{id}/run/notes` | RAG 深度笔记生成 |
| POST | `/api/sessions/{id}/run/notes/revise` | 根据反馈修订笔记 |
| POST | `/api/sessions/{id}/run/analyze` | 生成深度分析（compare / lineage / gaps） |
| POST | `/api/sessions/{id}/run/write` | 撰写综述 |
| POST | `/api/sessions/{id}/run/auto` | 🚀 一键自动模式（规划→搜索→笔记→分析→综述） |
| POST | `/api/sessions/{id}/run/cancel` | 打断正在运行的任务 |
| GET | `/api/sessions/{id}/run/status` | 轮询执行状态（含实时 traces） |

### 对话与聊天

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/sessions/{id}/chat` | 统一聊天入口（普通问答 + Agent 模式修订） |
| GET | `/api/sessions/{id}/conversations` | 获取聊天会话列表 |
| POST | `/api/sessions/{id}/conversations` | 创建新聊天会话 |
| GET | `/api/sessions/{id}/conversations/{conv_id}/messages` | 获取指定会话的消息历史 |
| DELETE | `/api/sessions/{id}/conversations/{conv_id}` | 删除聊天会话 |

### 工具管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/tools` | 获取所有工具元数据（含启用状态和配置） |
| PUT | `/api/tools/{name}/toggle` | 切换工具的启用/禁用状态 |
| PUT | `/api/tools/{name}/config` | 更新工具配置参数 |
| PUT | `/api/tools/batch-toggle` | 批量切换工具启用状态 |
| POST | `/api/tools/reset` | 重置为默认配置 |

### 其他

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/stats` | 工作台统计数据 |
| GET | `/api/favorites` | 获取收藏夹 |
| POST | `/api/favorites` | 加入收藏 |
| DELETE | `/api/favorites/{filename}` | 取消收藏 |
| POST | `/api/keywords/extract` | 仅提取关键词（不创建 Session） |
| GET | `/api/agent/history` | 历史综述列表（迭代二兼容） |
| GET | `/api/agent/history/{filename}` | 历史综述详情 |
| DELETE | `/api/agent/history/{filename}` | 删除历史综述 |
| GET | `/api/agent/document/{filename}/papers/{pdf_name}` | 获取 PDF 文件 |

### 页面路由

| 路径 | 页面 |
|------|------|
| `/` | 首页 |
| `/app/console` | 控制台 |
| `/app/history` | 历史记录 |
| `/app/chat` | 对话页面 |
| `/app/help` | 帮助页面 |

---

## Agent 断点执行（Python API）

```python
from main import (
    run_plan_only,           # 阶段 1：仅规划
    run_search_only,         # 阶段 2：仅搜索
    run_write_from_notes,    # 阶段 3：仅撰写
    run_agent_pipeline,      # 全链路（CLI 模式）
    run_agent_pipeline_session,  # Session 感知统一入口
)
```

---

## 工具注册中心（Tool Registry）

系统内置了一个**工具注册中心**（`core/tool_registry.py`），支持动态管理 Agent 可用工具的启用/禁用状态和配置参数。

### 架构

```
config/tools.json          ← 持久化配置文件（启用状态 + 参数）
       ↕
core/tool_registry.py      ← 注册中心（ToolRegistry 类）
       ↕
main.py                    ← CLI 模式从注册中心加载已启用工具
web_app.py                 ← Web 模式通过 API 管理工具
```

### 内置工具清单（16 个，6 类）

| 工具名 | 类别 | 阶段 | 默认状态 | 说明 |
|--------|------|------|---------|------|
| `arxiv_search` | search | 搜索阶段 | ✅ 启用 | arXiv 搜索 |
| `arxiv_fetch` | search | 搜索阶段 | ✅ 启用 | arXiv 按 ID 获取详情 |
| `arxiv_pdf_reader` | pdf | 搜索/笔记 | ✅ 启用 | 下载并解析 PDF 全文 |
| `arxiv_download_pdf` | pdf | 搜索阶段 | ✅ 启用 | 仅下载 PDF（轻量快速） |
| `semantic_scholar_search` | search | 搜索阶段 | ✅ 启用 | Semantic Scholar 搜索 |
| `semantic_scholar_fetch` | search | 搜索阶段 | ✅ 启用 | Semantic Scholar 按 ID 获取 |
| `crossref_search` | search | 搜索阶段 | ✅ 启用 | Crossref 关键词检索 |
| `crossref_fetch_doi` | search | 搜索阶段 | ✅ 启用 | Crossref DOI 补全元数据 |
| `openalex_search` | search | 搜索阶段 | ✅ 启用 | OpenAlex 跨学科搜索 |
| `clear_notes` | file | 笔记阶段 | ✅ 启用 | 清空研究笔记（CLI） |
| `append_note` | file | 笔记阶段 | ✅ 启用 | 追加结构化笔记（CLI） |
| `retriever` | chat | 对话阶段 | ✅ 启用 | BM25 检索器（对话 RAG） |
| `rag_note_generator` | notes | 笔记阶段 | ✅ 启用 | Embedding RAG 深度笔记生成 |
| `paper_register` | register | 搜索阶段 | ✅ 启用 | 审核摘要 → 收录论文 |

### 管理方式

**方式一：直接编辑配置文件**

编辑 `config/tools.json`，修改 `enabled` 字段和 `config` 参数：

```json
{
  "arxiv_search": {
    "enabled": true,
    "config": { "max_results": 10 }
  },
  "semantic_scholar_search": {
    "enabled": false,
    "config": { "limit": 5 }
  }
}
```

**方式二：通过 Python API**

```python
from core.tool_registry import get_registry

registry = get_registry("config/tools.json")

# 启用/禁用工具
registry.set_enabled("semantic_scholar_search", True)

# 调整配置参数
registry.set_config("arxiv_search", "max_results", 10)

# 批量设置
registry.batch_set_enabled({"crossref_search": True, "openalex_search": False})

# 重置为默认
registry.reset_to_defaults()

# 查看所有已启用工具
for tool in registry.get_enabled():
    print(f"{tool.name}: {tool.description}")
```

**方式三：CLI 模式自动加载**

CLI 模式（`python main.py`）会自动从 `config/tools.json` 读取已启用的工具，仅将启用的工具注入 Agent。Web 模式的搜索阶段目前使用固定工具列表（`run_search_only`），后续将统一接入注册中心。

### 工具配置参数

| 工具 | 可调参数 | 默认值 | 说明 |
|------|---------|--------|------|
| `arxiv_search` | `max_results` | 5 | 单次搜索最大返回数 |
| `arxiv_pdf_reader` | `read_full_default` | false | 是否默认读取全文 |
| `semantic_scholar_search` | `limit` | 5 | 单次搜索最大返回数 |
| `crossref_search` | `rows` | 5 | 单次搜索最大返回数 |
| `openalex_search` | `limit` | 5 | 单次搜索最大返回数 |

---

## Skills 管理（用户自定义 Agent 行为策略）

Skills 系统允许用户为 Agent 的三个执行阶段定义**自定义提示词模板**，精确控制 Agent 的行为策略。如果未指定 Skill，系统使用内置默认策略。

### 三个阶段

| 阶段 | 类型标识 | 生效时机 | 注入位置 |
|------|---------|---------|---------|
| **搜索阶段** | `search` | Agent 检索论文时 | `main.py` → `run_search_only()` |
| **笔记阶段** | `notes` | 为论文生成笔记时 | `tools/rag_note_generator.py` → `generate()` |
| **综述阶段** | `write` | 撰写/重写综述时 | `main.py` → `run_write_from_notes()` |

### 管理界面

访问 `/app/skills` 进入 Skills 管理页面，支持：

- **查看默认策略**：每个阶段都有系统内置的默认 Skill（虚线边框 + "系统内置" 徽章），点击可查看完整内容
- **创建自定义 Skill**：点击「创建」按钮，使用 Vditor 编辑器编写 Markdown 格式的策略
- **编辑 Skill**：点击用户创建的 Skill 卡片进入编辑
- **删除 Skill**：hover 卡片显示删除按钮（软删除，7 天可恢复）
- **查看默认**：编辑器中可点击「查看默认」参考系统内置策略，并可一键填入编辑器

### 使用方式

**方式一：创建 Session 时指定**

在首页新建综述时，可以为每个阶段选择已创建的 Skill：

```
首页 → 新建综述 → 选择 Skill（可选）→ 进入控制台
```

Session 创建后，`metadata.json` 中会记录 `skills` 配置：
```json
{
  "skills": {
    "search": "skill_abc123",
    "notes": null,
    "write": "skill_def456"
  }
}
```

`null` 表示该阶段使用系统默认策略。

**方式二：通过 API 管理**

```python
# 列出所有 Skills
GET /api/skills

# 查看默认策略
GET /api/skills/defaults

# 创建 Skill
POST /api/skills
{
  "title": "我的搜索策略",
  "type": "search",
  "content": "# 自定义搜索策略\n\n..."
}

# 更新 Skill
PUT /api/skills/{skill_id}
{"title": "新标题", "content": "新内容"}

# 删除 Skill（软删除）
DELETE /api/skills/{skill_id}

# 查看 Skill 被哪些 Session 引用
GET /api/skills/{skill_id}/usage
```

### Skill 示例

**搜索阶段 Skill 示例：**

```markdown
# Skill：AI 学术论文检索

**功能**：根据主题自动检索论文，不追问用户。

**执行规则**
- 使用 Semantic Scholar 等公开 API 检索，若失败则改用 arXiv。
- 关键词自动提取：提取核心概念并扩展同义词，默认使用 AND 组合。
- 默认过滤条件：时间范围近 5 年，不限语言，期刊+会议，按相关性排序。
- 返回前 5 篇，去重，排除明显不相关。

**输出格式**
- 列表：序号、标题、作者、年份、出版物、一句话贡献、DOI/链接、被引量。
- 末尾注明检索式与总命中数。
```

**笔记阶段 Skill 示例：**

```markdown
# Skill: AI 论文笔记生成

**功能**：根据用户提供的论文文本/信息生成结构化笔记，不追问细节，缺信息留空。

**执行规则**
- 默认生成"速览笔记"，除非用户明确"精读"或"复现"。
- 笔记结构固定为：
  - 元数据（标题、作者、年份、DOI）
  - 一句话总结
  - 研究问题
  - 方法要点
  - 主要结果
  - 关键局限
- 所有内容仅从用户提供材料提取，无则标注"未提及"，不编造。

**输出格式**
- 直接输出 Markdown，一级标题为论文标题。
```

**综述阶段 Skill 示例：**

```markdown
# Skill：AI 文献综述生成（基于论文笔记）

**功能**：根据多条论文笔记直接生成结构化综述，自动分类，不征求用户意见。

**执行规则**
- 输入：多条论文笔记（至少 3 条），含标题、方法、结果、局限。
- 处理：自动按方法/技术路线聚类，生成分类框架。
- 综述结构：
  - 背景段（2-3 句）
  - 分类体系（一段说明）
  - 各类详细描述（每类介绍共性，再列代表工作要点）
  - 综合对比表（方法、数据集、性能、优缺点）
  - 未来方向（基于笔记局限提炼 2-3 点）
- 引用格式：`[第一作者, 年份]`，仅引用已提供笔记中的文献。

**输出格式**
- Markdown 连续文本，不询问是否调整。
```

### 双通道注入机制

系统采用"双通道"设计，确保 Skill 和默认策略无缝切换：

| 通道 | 条件 | 行为 |
|------|------|------|
| **通道 A（Skill 优先）** | Session 配置了 Skill 且内容非空 | 用 Skill 内容替换默认写作要求，仅保留最小核心约束 |
| **通道 B（默认兜底）** | 未配置 Skill 或 Skill 为空/已删除 | 使用系统内置默认策略 |

Skill 加载失败时（如文件损坏、已删除），自动静默回退到通道 B，确保流程不被中断。

### 存储结构

```
sessions/
├── .skills/                  ← Skills 存储目录
│   ├── _index.json           ← 索引（标题、类型、时间戳）
│   └── skill_{uuid}.json     ← 完整 Skill 数据
└── {session_id}/
    └── metadata.json         ← skills 字段记录该 Session 使用的 Skill ID
```

---

## 对话系统

### 多会话聊天管理

每个 Session 支持**多个独立的聊天会话**（Conversation），数据存储在 `sessions/{id}/chats/` 下：

```
chats/
├── _index.json          # 会话索引（标题、消息数、时间戳）
├── conv_{uuid}.json     # 消息历史（role + text + timestamp）
└── ...
```

**功能**：
- 创建/删除聊天会话（至少保留一个）
- 自动保存每轮对话（用户消息 + AI 回复）
- 旧版 `chat_history.json` 自动迁移到新版多会话模式
- 支持切换不同会话上下文

### 统一聊天入口

底部对话区同时承担**普通问答**和**修订协同**两种功能，共用 `POST /api/sessions/{id}/chat` 端点：

```
用户消息
  ├── 普通模式：直接 LLM 问答（含 RAG 检索增强）
  └── Agent 模式：
        ├── 显式 /修订 指令 → 直接执行修订
        ├── AI 意图判定（隐式修改）→ 确认后执行
        └── 意图不明确 → 要求用户澄清
```

### RAG 检索增强对话

对话栏集成了 **BM25 检索器**（`tools/retriever.py`），回答用户问题时自动：

1. 从当前 Session 的所有已下载 PDF 中检索相关段落
2. 将 Top-5 原文段落注入 LLM prompt
3. 回答中标注来源（论文标题 + 页码）

响应中会包含 `rag_status` 字段：`"used"`（使用了检索结果）/ `"no_results"`（未检索到）/ `"no_pdfs"`（无 PDF 文件）。

### AI 判意修订流程

当用户在 Agent 模式下发送消息时，系统先调用 LLM 进行意图分类：

| 判定结果 | 行为 |
|---------|------|
| `intent=chat` | 正常问答，不触发修订 |
| `intent=revise`（confidence >= 0.6） | 返回确认提示，用户确认后执行修订 |
| `intent=clarify` | 提示用户明确意图 |

修订支持两种目标：
- **笔记修订**（`target=report`）：修改单篇论文的研究笔记
- **综述修订**（`target=review`）：根据反馈重写综述草稿

---

## 如何添加新工具

1. 在 `tools/` 下新建 Python 文件，继承 `core.tools.BaseTool`
2. 设置 `name`、`description`、`parameters`，实现 `execute(**kwargs)` 方法
3. 在 `core/tool_registry.py` 的 `BUILTIN_TOOLS` 字典中注册元数据
4. 在 `main.py` 的 `_tool_factories` 字典中注册工厂函数
5. 在 `main.py` 的 `_build_research_query()` 中添加工具说明
6. 新工具默认启用，可在 `config/tools.json` 中管理

---

## 当前限制

- 依赖 LLM 稳定输出 JSON 格式，模型质量直接影响 Agent 成功率
- Semantic Scholar 无 API Key 时限流严重（60% 429），建议注册免费 Key
- arXiv `id_list` 端点限流比 `search_query` 严格得多，已通过全局限流器和退避策略缓解
- 对话区的普通问答与修订动作共用 `/api/sessions/{session_id}/chat`；修订不会直接执行，Agent 模式会先做 AI 意图判定并要求用户二次确认
- 自动模式的笔记生成阶段依赖 `RAGNoteGenerator`，需要 Embedding 模型支持
- Web 搜索阶段（`run_search_only`）目前使用固定工具列表，尚未接入 ToolRegistry；CLI 模式已接入
