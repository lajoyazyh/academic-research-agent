# 评估平台 (Eval Platform)

这是一个用于对大语言模型 Agent 进行可重复、可持久化评估的全栈平台。平台包含后端 API、前端可视化面板，以及用于驱动 agent 的代码和评估指标模块。

**目录概览**

- `backend/`：评估后端服务，负责任务管理、持久化（SQLite）、与 `agent` 的联动调用。
- `frontend/`：前端可视化面板（开发中）。
- `agent/`：Agent 实现与运行入口（研究者+写作者流水线），产出 `documents/` 结果目录。
- `metrics/`：评估指标实现（来自迭代一的各维度度量模块）。

**快速说明：当前平台包含**

- 后端 API：基于 FastAPI，启动脚本位于 `backend/main.py`。
- Agent：位于 `agent/`，通过函数 `run_agent_pipeline` 被后端调用并在 `agent/documents/` 下写入产物（如 `research_notes.md`、`final_review.md`）。
- 数据库：使用 SQLite，通过 `backend` 的 `database` 模块管理任务与结果持久化。

**下文将说明如何配置、启动与常见故障排查。**

**安装与环境配置**

- **Python 环境**: 建议使用虚拟环境并安装依赖，例如：
# 评估平台 (Eval Platform)

这是一个用于对大语言模型 Agent 进行可重复、可持久化评估的全栈平台。平台已经形成“数据集 - 任务 - Agent 执行 - 评估 - 结果查看”的完整闭环。

## 目录概览

- `backend/`：后端服务，负责任务管理、SQLite 持久化、评估器调用和 Agent 联动。
- `frontend/`：前端可视化面板，当前采用原生 HTML/CSS/JavaScript。
- `tests/`：平台后端测试用例。

## 当前架构

- 后端基于 FastAPI，启动入口为 `backend/main.py`。
- 任务和数据集通过 SQLAlchemy + SQLite 持久化。
- 后端调用 `agent/main.py` 中的 `run_agent_pipeline` 执行研究与写作流程。
- `backend/evaluation_methods.py` 支持 `ragas` 和 fallback 两条评估路径，优先保证平台稳定可用。
- `ragas` 路径同时会使用 Zhipu/OpenAI 兼容的 embedding 客户端，因此要真正跑通 `ragas`，需要同时具备聊天模型和 embedding 配置。

## 当前状态

- 数据集管理、任务创建、任务触发、状态查询和结果查询已经接通。
- Agent 执行结果会落到数据库中，同时生成 `agent/documents/<timestamp>/research_notes.md` 和 `final_review.md`。
- 后端启动时会显式加载仓库根目录的 `.env`，并在调用 Agent 前切换工作目录，避免路径和环境变量问题。
- 目前对外主要维护智谱配置：`ZHIPU_API_KEY`、`ZHIPU_BASE_URL`、`ZHIPU_MODEL`。
- 在 `ragas` 不可用时，fallback 评估会输出多项可解释指标，包括 `similarity_score`、`truth_coverage_score`、`token_f1_score` 和 `context_support_score`。
- 任务触发后会先进入 `queued`，随后转为 `running`；如果 Agent 长时间卡住，可通过 `EVAL_AGENT_TIMEOUT_SEC` 控制超时失败。
- 目前 Zhipu 兼容模式下，默认优先使用 `answer_relevancy` 和 `answer_similarity`；`answer_correctness` 是可选项，默认关闭以避免接口参数错误。

## 环境配置

建议使用仓库根目录的虚拟环境，并安装依赖：

```powershell
cd 迭代二
python -m pip install -r requirements.txt
python -m pip install -r requirements-eval.txt
```

推荐在仓库根目录放置 `.env`，平台会自动读取。

### 推荐变量

- `ZHIPU_API_KEY`：必填，智谱 API Key。
- `ZHIPU_BASE_URL`：可选，默认模型服务地址。
- `ZHIPU_MODEL`：可选，默认模型名。
- `ZHIPU_EMBEDDING_MODEL`：可选，ragas 使用的 embedding 模型名，默认 `embedding-2`。
- `EVAL_USE_RAGAS`：可选，默认关闭。设为 `true` 时启用 `ragas`。
- `RAGAS_INCLUDE_ANSWER_CORRECTNESS`：可选，默认关闭。仅在你确认当前 Zhipu 接口兼容该指标时再打开；否则 ragas 可能因参数错误回退到 fallback。

平台内部已兼容底层库对 `OPENAI_API_KEY` / `OPENAI_BASE_URL` 的读取需求，一般不需要手工维护这两项。

## 启动方式

启动后端：

```powershell
cd 迭代二/eval_platform/backend
python main.py
```

启动后 API 默认运行在 `http://127.0.0.1:8001`。

### 前端启动

```powershell
cd 迭代二/eval_platform/frontend
python -m http.server 8080
```

浏览器打开 `http://127.0.0.1:8080` 即可使用前端面板。前端为原生 HTML/CSS/JavaScript SPA，无额外构建步骤。

## 评估方法及其指标

系统提供三种评估方式，每种的指标如下：

### 面向结果（result_oriented）

侧重于评估最终答案的质量和相关性。

| 指标 | 来源 | 评估依据 | 说明 |
|------|------|----------|------|
| `answer_relevancy` | ragas | question + answer | 答案是否切题 |
| `answer_similarity` | ragas | answer + contexts | 答案与上下文的语义相似度 |
| `answer_correctness` | LLM 判分 | answer vs ground truth（数据集或默认） | 答案与参考答案的事实/数值正确性 |
| `completeness_score` | LLM 判分 | answer vs question | 答案是否覆盖所有要点 |
| `relevance_score` | LLM 判分 | answer vs question | 答案是否与问题保持相关 |

### 面向过程（process_oriented）

侧重于评估检索质量和推理过程。

| 指标 | 来源 | 评估依据 | 说明 |
|------|------|----------|------|
| `context_precision` | ragas | question + contexts | 检索上下文中真正相关的比例 |
| `grounding_score` | LLM 判分 | answer vs contexts | 答案依赖实际证据的程度 |
| `reasoning_score` | LLM 判分 | answer + traces | 多步推理的逻辑清晰度 |
| `step_coherence_score` | LLM 判分 | answer + traces | 推理步骤间的连贯性 |

### 综合指标（explicit_metrics）

全方位综合评估。

| 指标 | 来源 | 评估依据 | 说明 |
|------|------|----------|------|
| `answer_relevancy` | ragas | question + answer | 答案是否切题 |
| `context_precision` | ragas | question + contexts | 检索上下文精度 |
| `answer_correctness` | LLM 判分 | answer vs ground truth（数据集或默认） | 事实正确性 |
| `answer_similarity` | LLM 判分 | answer vs ground truth（数据集或默认） | 语义相似度 |
| `context_recall` | LLM 判分 | contexts vs question | 检索是否覆盖全部关键证据 |
| `faithfulness_score` | LLM 判分 | answer vs contexts | LLM 视角的忠实性补充评分 |
| `helpfulness_score` | LLM 判分 | answer vs question | 答案的实用性和可执行性 |

### 指标与输入数据的关系

```
question（问题）   ──┬──→ answer_relevancy、completeness_score、relevance_score、helpfulness_score
                    │
answer（候选答案）──┼──→ answer_relevancy、answer_similarity、answer_correctness
                    │
contexts（上下文）──┼──→ context_precision、context_recall、grounding_score、faithfulness_score
                    │
traces（轨迹）   ──┴──→ reasoning_score、step_coherence_score
```

- ragas 指标（answer_relevancy / answer_similarity / context_precision）无需参考答案，直接由 question + answer + contexts 计算。
- LLM 判分指标：优先使用数据集 `ground_truths`；若未提供，则使用默认 `ground_truth`：`成功检索相关文献、完成多源证据综合，并输出含引用的结构化综述结论。`。
- 数据集字段说明：`data_samples` 为 `[{"query": "..."}]` 格式的问题列表，`ground_truths` 为 `[{"answer": "..."}]` 格式的参考答案列表，可为空（为空时回退到上述默认 `ground_truth`）。

## 常用 API

- `POST /datasets/create`：创建数据集。
- `GET /datasets/list`：查询数据集列表。
- `POST /tasks/create`：创建评估任务。
- `POST /tasks/evaluate/{task_id}`：触发 Agent 评估。
- `GET /tasks/status/{task_id}`：查询任务状态。
- `GET /tasks/results/{task_id}`：查询任务结果。

## 如何判断评估完成

1. 创建数据集并创建任务。
2. 触发 `/tasks/evaluate/{task_id}`。
3. 轮询 `/tasks/status/{task_id}`，直到变成 `completed`。
4. 再访问 `/tasks/results/{task_id}`，确认结果中包含 `backend`、`method`、`scores`、`sample_count`、`traces`。

如果任务变成 `failed`，优先检查 `error_message`，其次检查 `.env`、模型配置和依赖版本。

## 端到端验证

1. 启动后端。
2. 新建一个小数据集。
3. 新建评估任务并触发执行。
4. 查看状态从 `running` 到 `completed` 的变化。
5. 确认数据库结果和 `agent/documents/` 目录下产物同时生成。

## 进一步优化方向

### 评估层

- fallback 评估器已经补充了更可解释的多指标输出；下一步可以继续加上关键短语命中率、句级覆盖率和分主题统计。
- 给 `ragas` 路径加依赖锁定和兼容性检查，降低升级风险。
- 把评分结果统一成更稳定的 schema，方便前端图表和历史对比。

### 任务层

- 任务已经增加 `queued` 状态和可配置超时；下一步可以补重试策略、取消任务和后台 worker。
- 引入持久化后台队列，避免进程重启导致的任务丢失。
- 给每次评估保留更清晰的失败分类与错误原因。

### 数据层

- 为数据集增加标签、版本和来源字段，方便做版本化评测。
- 为任务结果增加运行耗时、重试次数和模型版本记录。

### 工程层

- 补充 `.env.example`。
- 增加更细的 API 测试和评估器测试。
- 进一步收紧 GitHub Actions，保证提交前回归更稳定。