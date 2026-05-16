# 📊 Agent Eval Platform Frontend (评估中台前端)

本文档详细说明了 Agent Eval Platform 前端模块的架构、核心页面功能以及与后端的 API 交互规范。前端采用原生 HTML/CSS/JavaScript 构建，运用 Hash 路由机制实现了轻量级单页应用 (SPA) 体验。

## 🛠️ 1. 技术栈与设计特点

- **核心框架**：原生 HTML5 + CSS3 + Vanilla JavaScript（零复杂构建工具、零前端重型框架依赖）。
- **HTTP/API 调用**：[Axios](https://github.com/axios/axios) 库实现异步的 RESTful API 交互。
- **数据可视化**：[Apache ECharts](https://echarts.apache.org/) 实现多维评测指标（Radar雷达图）渲染。
- **默认 API 服务地址**：`http://127.0.0.1:8001`（统一在 `app.js` 头部的 `API_BASE` 中配置）。
- **UI 设计**：一套自建响应式 CSS 系统（`styles.css`），内置了卡片视图、骨架屏加载动画（Skeleton Loading）、响应式侧边栏及可复用的组件样式。

## 🗺️ 2. 页面结构与路由规划

系统实现了自研的一套基础 Hash Router (`routes` 映射)，包含以下主要模块视图：

### 2.1 任务记录列表 (`#/tasks` & 默认路由)
- **核心职能**：展示评估中台内的任务执行历史 (Histories) 与运行概要。
- **UI 呈现**：一个自适应的表格，结合了状态彩色标签（pending/completed）以及骨架屏加载状态。
- **交互功能**：
  - 加载并渲染任务列表（限制 50 条）。
  - **触发评测**：点击“开始评测”可主动向后端请求评估当前任务，执行反馈后重新刷新视图。
  - **查看详情**：点击跳转进入单一任务的多维度详情页。
- **关联后端接口**：
  - `GET /tasks/list?skip=0&limit=50`: 拉取历史任务数据。
  - `POST /tasks/evaluate/{taskId}`: 下发评估任务。

### 2.2 任务详情剖析 (`#/tasks/detail/:taskId`)
- **核心职能**：深入拆解特定评估任务的过程轨迹、消耗及得分详情。
- **UI 呈现**：
  - **动态监控**：展示实时任务卡片概况（耗时、Token量、最新状态），若任务在“运行中 (running)”予以特殊提示。
  - **雷达图诊断**：使用 ECharts 绘制囊括 `Faithfulness`, `Answer Relevance`, `Tool Accuracy`, `Planning`, `Robustness` 这 5 个子维度的雷达图。
  - **执行轨迹 Timeline**：格式化呈现 Agent 决策的时间线 (Trajectory/Logs) 步骤和执行详情。
- **关联后端接口**：
  - `GET /tasks/detail/{taskId}`: 获取基础属性及决策日志轨迹。
  - `GET /tasks/results/{taskId}`: 提取模型多维评测结果与分数。

### 2.3 数据集管理 (`#/dataset`)
- **核心职能**：管理评估系统用于 Benchmark 测试的基准数据集。
- **UI 呈现**：
  - 显示系统内可供测试的数据集。
  - 通过模态弹窗 (Modal) 的方式完成新数据集的提交创建动作。
- **交互功能**：
  - **载入集合**：初始化时请求并展示所有数据集的核心元数据。
  - **创建机制**：填写并校验表单包含名称、描述、测试样本 (Data Samples) 以及基准真值 (Ground Truths)，提交到服务器建立新标准集。
- **关联后端接口**：
  - `GET /datasets/list?skip=0&limit=50`: 列出现有数据集。
  - `POST /datasets/create`: 创建并注册新的关联任务测试集。

*(注意：侧边栏中保留了 `#/dashboard` `大盘概览` 扩展口，此外也有通过 `styles.css` 预留的 Compare View 对比页面样式支持方案供未来扩展。)*

## 🧪 3. 评估方法及其指标说明

系统提供了三种评估方式（`result_oriented` / `process_oriented` / `explicit_metrics`），每种方式组合了不同的评测指标。指标分为两类：**ragas 指标**（无需参考答案，直接基于问题、答案和上下文计算）和 **LLM 判分指标**（由 LLM 先生成 AI 参考答案，再对候选答案打分）。

### 3.1 面向结果 (result_oriented)

侧重于评估最终答案的质量和相关性。

| 指标 | 来源 | 评估依据 | 说明 |
|------|------|----------|------|
| `answer_relevancy` | ragas | question + answer | 答案是否切题、是否直接回答问题意图 |
| `answer_similarity` | ragas | answer + contexts | 答案与上下文的语义相似度 |
| `answer_correctness` | LLM 判分 | answer vs ground truth（数据集或默认） | 答案与参考答案的事实/数值正确性 |
| `completeness_score` | LLM 判分 | answer vs question | 答案是否覆盖问题要求的所有要点 |
| `relevance_score` | LLM 判分 | answer vs question | 答案内容是否与问题保持相关、不跑题 |

### 3.2 面向过程 (process_oriented)

侧重于评估检索质量、推理过程和证据引用。

| 指标 | 来源 | 评估依据 | 说明 |
|------|------|----------|------|
| `context_precision` | ragas | question + contexts | 检索到的上下文中，真正与答案相关的比例（衡量检索噪声） |
| `grounding_score` | LLM 判分 | answer vs contexts | 答案在多大程度上依赖实际证据来支持结论 |
| `reasoning_score` | LLM 判分 | answer + traces | 多步推理的逻辑清晰度与思路正确性 |
| `step_coherence_score` | LLM 判分 | answer + traces | 推理各步骤之间是否连贯、无矛盾或跳跃 |

### 3.3 综合指标 (explicit_metrics)

综合使用所有可用指标进行全方位评估。

| 指标 | 来源 | 评估依据 | 说明 |
|------|------|----------|------|
| `answer_relevancy` | ragas | question + answer | 答案是否切题 |
| `context_precision` | ragas | question + contexts | 检索上下文的相关精度 |
| `answer_correctness` | LLM 判分 | answer vs ground truth（数据集或默认） | 答案的事实正确性 |
| `answer_similarity` | LLM 判分 | answer vs ground truth（数据集或默认） | 答案的语义相似度 |
| `context_recall` | LLM 判分 | contexts vs question | 检索是否覆盖了回答问题所需的全部关键证据 |
| `faithfulness_score` | LLM 判分 | answer vs contexts | 答案对上下文的忠实程度（LLM 视角补充评分） |
| `helpfulness_score` | LLM 判分 | answer vs question | 答案对用户解决问题的实用性和可执行性 |

### 3.4 指标与输入数据的关系

```
question（问题） ──┬──→ answer_relevancy、completeness_score、relevance_score、helpfulness_score
                  │
answer（候选答案） ─┼──→ answer_relevancy、answer_similarity、answer_correctness
                  │
contexts（上下文） ─┼──→ context_precision、context_recall、grounding_score、faithfulness_score
                  │
traces（轨迹） ────┴──→ reasoning_score、step_coherence_score
```

- 无需 ground truth 的指标（ragas）：直接由 `question` + `answer` + `contexts` 计算，包括 `answer_relevancy`、`answer_similarity`、`context_precision`。
- 需要参考答案的指标（LLM 判分）：优先使用数据集 `ground_truths`；若未提供则使用默认 `ground_truth`，再将 `answer` 与之对比打分。

## 🚀 4. 快速启动与运行指南

本项目追求极致的极简配置，没有庞大复杂的 `node_modules` 依赖即可运行：

1. **核对后端环境**：确保本地后端 API 在 `http://127.0.0.1:8001` 或目标地址运行。若后端端口变更，请对应修改 `app.js` 第一行：`const API_BASE = '...';`
2. **启动前端服务**：由于目前现代浏览器会拦截跨目录模块读取及部分本地数据请求 (CORS)，强烈建议启动一个本地 HTTP 静态服务器。

```bash
# 进入前端工作目录
cd 迭代二/eval_platform/frontend

# ---- 方法 A：使用 Python 3 内置简易 Server（推荐）----
python -m http.server 8080

# ---- 方法 B：使用 Node.js 的 http-server 组件 ----
npx http-server -p 8080
```

3. **进入应用**：服务端拉起后，在浏览器访问 `http://127.0.0.1:8080` 即可体验平台！