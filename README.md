# 迭代二：模块化 Agent 架构与全栈评测平台

迭代二已经从“脚本化验证”推进到“可运行、可评测、可追踪、可持续迭代”的工程阶段。当前仓库的核心可以概括为两条主线：

1. `agent/` 负责学术检索、阅读、笔记和综述生成。
2. `eval_platform/` 负责数据集、任务、评测、结果和前端展示。

## 演示视频

- 南京大学智能软件与工程学院软工三小组作业-迭代二-学术综述agent与相应评估评测平台：
	https://www.bilibili.com/video/BV1Fq5A61EMV

## 核心模块

- `agent/`：Agent 主实现，包含 `core/`、`tools/`、`llms/` 和 `documents/`。
- `eval_platform/`：评估平台，包含后端 API、数据库、评估器、前端与测试。
- `tests/`：Agent 工具和平台联动的自动化测试。
- `scripts/`：辅助验证脚本。

## 当前实现现状

- Agent 已形成 Researcher + Writer 双阶段流水线，能够持续产出 `research_notes.md` 与 `final_review.md`。
- 评估平台后端已打通数据集创建、任务创建、任务触发、状态轮询和结果查询。
- 后端在执行 Agent 时会切换到 `agent/` 目录，并显式加载仓库根 `.env`，避免 `find_dotenv()` 受启动目录影响。
- 评估器当前采用双路径策略：`ragas` 可用时走高级评测，不可用时回退到字符串相似度评估，保证平台可用性。
- GitHub Actions 已覆盖 `agent` 与 `eval_platform` 的测试，适合提交前做回归验证。

## 环境安装

建议使用仓库根目录的虚拟环境，然后安装依赖：

```powershell
cd 迭代二
python -m pip install -r requirements.txt
python -m pip install -r requirements-eval.txt
```

如果只需要验证评估平台，也可以单独安装 `requirements-eval.txt` 里的依赖。

## 配置方式

当前平台对外主要依赖智谱配置：`ZHIPU_API_KEY`、`ZHIPU_BASE_URL`、`ZHIPU_MODEL`。

平台内部会兼容底层库对 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL` 的读取需求，因此通常不需要手工补充额外变量。

推荐把 `.env` 放在仓库根目录，并由平台自动读取。

## 运行方式

启动后端：

```powershell
cd 迭代二/eval_platform/backend
python main.py
```

启动 Agent：

```powershell
cd 迭代二/agent
python main.py
```

前端是静态页面，可通过本地 HTTP 服务打开 `frontend/index.html`。

## 评估平台当前能力

- 数据集管理：创建、查询、删除评估数据集。
- 任务管理：创建、触发、查询、删除评估任务。
- 自动执行：后端异步调用 Agent 并收集 trace。
- 结果落库：评估结果以统一 JSON 结构写入数据库。
- 结果查看：支持通过 API 或前端页面查看状态和评分结果。

## 如何确认评估已完成

1. 创建数据集。
2. 创建评测任务。
3. 调用 `/tasks/evaluate/{task_id}`。
4. 轮询 `/tasks/status/{task_id}`，直到状态变为 `completed`。
5. 再访问 `/tasks/results/{task_id}`，确认返回中包含 `backend`、`method`、`scores`、`sample_count` 和 `traces`。

如果状态变为 `failed`，优先查看 `error_message`，其次检查 `.env`、依赖版本和模型配置。

## 进一步优化和完善方案

### 1. 评估能力增强

- 给 fallback 评估器补充更多可解释指标，例如答案覆盖率、关键词重合度和上下文命中率。
- 给 `ragas` 路径增加版本锁定和兼容性校验，避免依赖升级后行为漂移。
- 把评估结果拆成“总分 + 分项指标 + 原始记录”，便于前端做图表和回放。

### 2. 任务执行增强

- 为任务增加更细的状态机，例如 `queued`、`running`、`completed`、`failed`、`cancelled`。
- 增加超时控制、重试策略和失败原因归类，减少排障成本。
- 引入任务队列或后台 worker，避免 `asyncio.create_task` 在进程重启时丢失任务。

### 3. 数据与可视化增强

- 增加任务历史对比视图，支持同一主题不同版本 Agent 的横向比较。
- 把 `traces` 结构标准化，支持前端时间轴、折线图和节点回放。
- 为数据集增加标签、来源和版本字段，方便后续做可重复评测。

### 4. 工程化增强

- 补充 `.env.example`、更完整的测试数据和更细粒度的单测。
- 进一步收紧 GitHub Actions，增加后端 API 测试和评估器测试。
- 给平台补充更明确的接口示例，减少新成员上手成本。