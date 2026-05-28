# Academic Research Agent

面向学术文献调研的 LLM Agent 应用。给定一个研究主题，Agent 自主规划检索策略，从 arXiv / Semantic Scholar / Crossref 等学术数据库搜索前沿论文，阅读摘要和全文，记录结构化笔记，最终生成万字级文献综述。

## 核心架构：三种推理框架的有机融合

```
┌─────────────────────────────────────────────────┐
│  阶段 0: Plan-and-Execute（规划 - 执行）          │
│  Agent 先产出一个显式的研究计划：                  │
│  关键词拆分 → 数据库选择 → 备选策略 → 预期深度     │
├─────────────────────────────────────────────────┤
│  阶段 1-N: ReAct（推理 - 行动循环）               │
│  [思考] → 选择工具 → [执行] → 观察结果 → [再思考]  │
├─────────────────────────────────────────────────┤
│  内置: Reflexion（自我反思，3 个层次）             │
│  L1: 单次错误即时反馈（JSON格式/未知工具/运行异常） │
│  L2: 连续 3 次同类错误 → 深度反思提示              │
│  L3: FINISH 前自主质检（Self-Critique）            │
└─────────────────────────────────────────────────┘
```

### Plan-and-Execute

Agent 在执行任何工具调用之前，先调用一次 LLM 产出一个 300 字以内的显式研究计划，涵盖：
- 中英关键词拆分策略
- 数据库选择与调用顺序
- 零结果/限流时的备选方案
- 预计搜集篇数与阅读深度

该计划作为第一条 trace 记录在面板中，整个执行过程 Agent 可以动态修订计划。

### ReAct（Reasoning + Acting）

每一轮 Agent 都遵循固定的思考-行动-观察循环：
1. `thought`：分析当前状态，决定下一步行动
2. `action`：选择调用的工具名称
3. `action_input`：填入工具参数
4. `observation`：获取工具返回的环境事实
5. 进入下一轮直到 FINISH

### Reflexion（三层自我反思）

| 层次 | 触发条件 | 机制 |
|------|---------|------|
| **L1 即时反馈** | JSON 格式错误 / 工具名不存在 / 工具运行时异常 | 将错误信息反馈给 LLM，要求下一轮修正 |
| **L2 深度反思** | 连续 3 次同一类型错误 | 注入深度反思提示：分析根因、承认策略失败、提出全新替代方案 |
| **L3 自主质检** | FINISH 前且笔记数 >= 3 | 要求 Agent 逐篇审查笔记的完备性（标题/作者/DOI/方法/发现/关联），缺口补全后并通过质检后才允许 FINISH |
| **L4 PDF 自动兜底** | Agent 主循环结束后 | 系统自动扫描所有轨迹中的论文 ID，批量下载 PDF 至 `papers/` 目录 |
| **L5 论文列表传递** | Agent 主循环结束后 | 系统自动收集已下载的 PDF 列表，通过 API 传递给前端，用户可在"参考论文"标签页查看/下载 |

---

## 外部工具（9 个真实 API 工具）

| 工具 | 对接 API | 功能 |
|------|---------|------|
| `arxiv_search` | arXiv API | 搜索论文，返回标题+作者+摘要 |
| `arxiv_fetch` | arXiv API | 按 ID 获取单篇论文详情 |
| `arxiv_download_pdf` | arXiv PDF | 下载论文 PDF 到本地 |
| `arxiv_pdf_reader` | arXiv PDF + PyMuPDF | 下载 PDF 并提取正文文本 |
| `semantic_scholar_search` | Semantic Scholar API | 搜索论文，返回元数据+摘要 |
| `semantic_scholar_fetch` | Semantic Scholar API | 按 ID 获取论文详情 |
| `crossref_search` | Crossref API | 按关键词检索文献元数据 |
| `crossref_fetch_doi` | Crossref API | 按 DOI 精确获取引用信息 |
| `openalex_search` | OpenAlex API | 跨学科综合学术搜索（推荐人文/社科/医学优先使用） |

内置工程优化：全局限流器（arXiv 最小 5s 间隔）、429 指数退避重试（arXiv 10s x attempt、Semantic Scholar >= 30s）、查询变体自动降级、低相关度过滤。

---

## 快速开始

### 1. 环境准备

```bash
# 安装依赖
pip install openai httpx python-dotenv PyMuPDF
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
```

### 2. 命令行运行

```bash
cd agent/
python main.py
```

输入研究主题后，Agent 自动完成搜索-阅读-笔记-综述，结果保存在 `documents/{主题}_{时间戳}/` 下：

- `papers/` — 下载的 PDF 原文
- `research_notes.md` — Agent 的研究笔记
- `final_review.md` — 最终文献综述
- `plan.md` — 初始检索计划

### 3. Web 界面运行

```bash
cd agent/
python web_app.py
```

浏览器打开 `http://127.0.0.1:8000`，即可进入 **会话驱动的交互式调研平台**：
- **全流程干预**：分为关键词规划、搜集论文、提取笔记、撰写综述等多个可暂停检查的阶段。
- **互动审批机制**：可编辑检索计划（Plan）、剔除或上传相关论文（Papers）、在线修改文献笔记（Notes）。
- **综述反馈重写**：系统多版本保存最终草稿，用户提供建议后 Agent 可自动重写、反馈迭代（Drafts/Review）。
- **运行轨迹与参考**：保留运行中间日志的溯源能力，并附带所有相关 PDF 文件的本地下载和审阅功能。
- **统一聊天入口**：页面底部对话区同时承担普通问答和修订协同；普通问题会直接生成回答，Agent 模式下的隐式修改意图会先由 AI 判定，再在聊天中确认后执行，显式 `/修订` 仍可直接执行。

---

## 目录结构

```
agent/
├── backend/
│   ├── api.py            # 独立 API
│   └── session_manager.py # Session 会话状态管理
├── config/               # 配置管理
├── core/
│   ├── agent.py          # Agent 主循环（Plan+ReAct+Reflexion）
│   ├── tools.py          # 工具基类
│   └── memory.py         # 短期记忆
├── tools/
│   ├── arxiv_tools.py    # arXiv 搜索/获取/下载/读取
│   ├── semantic_scholar_tools.py  # Semantic Scholar
│   ├── crossref_tools.py # Crossref 元数据
│   ├── openalex_tools.py # OpenAlex 综合搜索
│   ├── pdf_tools.py      # PDF 下载与正文提取
│   └── file_tools.py     # 笔记管理
├── llms/
│   └── client.py         # LLM 客户端（智谱/OpenAI 兼容）
├── sessions/             # Session 数据存储
├── prompts/              # Prompt 模板
├── utils/
│   └── parser.py         # JSON 解析器
├── frontend/
│   ├── index.html        # Web 界面入口
│   ├── home.html         # 首页
│   ├── history.html      # 历史记录页面
│   ├── chat.html         # 对话页面
│   ├── help.html         # 帮助页面
│   ├── app.js            # 前端入口逻辑
│   ├── notebooklm.js     # 页面内部交互与状态管理
│   ├── styles.css        # 基础样式
│   └── notebooklm.css    # UI 样式库
├── main.py               # CLI 入口
├── web_app.py            # Web 入口（FastAPI）
├── .env                  # 环境配置
├── documents/            # CLI 运行输出与迭代二兼容目录
└── README.md
```

---

## 如何添加新工具

1. 在 `tools/` 下新建 Python 文件
2. 继承 `core.tools.BaseTool`，设置 `name`、`description`、`parameters`
3. 实现 `execute(**kwargs)` 方法
4. 在 `main.py` 中导入并注册到工具列表
5. 在 `main.py` 的 prompt 中添加工具说明

---

## 当前限制

- 依赖 LLM 稳定输出 JSON 格式，模型质量直接影响 Agent 成功率
- Semantic Scholar 无 API Key 时限流严重（60% 429），建议注册免费 Key
- arXiv `id_list` 端点限流比 `search_query` 严格得多，已通过全局限流器和退避策略缓解
- 对话区的普通问答与修订动作共用 `/api/sessions/{session_id}/chat`；其中修订不会直接执行，Agent 模式会先做 AI 意图判定并要求用户二次确认
