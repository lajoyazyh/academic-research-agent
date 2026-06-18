# Agent 评估

对学术 Agent 的输出进行自动化评估。支持：**完整评估**（运行 Agent + 打分）、**从文件导入**（traces + answer 分别导入）。

核心流程：**数据集 → Agent Pipeline / 文件导入 → LLM 裁判打分 → 结果入库**。

快速使用
```bash
cd 迭代三\evaluation

# python 版本为3.11，与迭代二评估平台一致
python -m pip install -r requirements.txt
python -m pip install -r requirements-eval.txt

# 完整评估
python run_eval.py --dataset-id 1

# 从独立文件分别导入 traces 和 answer (从session中复制路径或者将trace和draft放在同级目录下)
python run_eval.py --dataset-id 1 --from-traces traces.json --from-answer draft.md

```
---

## 目录结构

```
evaluation/
├── run_eval.py               # ★ 独立评估脚本（支持 A/B/C 三种模式）
├── eval_platform.db          # SQLite 数据库（数据集 + 评估结果）
├── evaluation_tasks.csv      # 历史评估记录
├── README.md                 # 本文件
│
└── code/                     # 评估平台后端代码
    ├── main.py               # FastAPI Web 服务入口（端口 8001）
    ├── database.py           # 数据库引擎
    ├── ModelS.py             # ORM 模型
    ├── schemas.py            # Pydantic 模型
    ├── crud.py               # 数据库操作
    ├── services.py           # 评估服务逻辑
    ├── evaluation_methods.py # 评估器（LLMBasedEvaluator + ragas/fallback）
    └── routers/              # API 路由
```

---

## 脚本运行

### 快速开始

```bash
cd 迭代三\evaluation

# ━━━ 模式 A：完整评估（运行 Agent + 评估）━━━
python run_eval.py --dataset-id 1

# ━━━ 模式 B：从独立文件分别导入 traces 和 answer ━━━
python run_eval.py --dataset-id 1 --from-traces traces.json --from-answer draft.md

```

### 命令行参数

| 参数 | 简写 | 模式 | 默认值 | 说明 |
|---|---|---|---|---|
| `--dataset-id` | `-d` | A/B/C | **必填** | 从 `eval_platform.db` 加载数据集 |
| `--method` | `-m` | A/B/C | `explicit_metrics` | `result_oriented` / `process_oriented` / `explicit_metrics` |
| `--from-traces` | — | **B** | — | JSON 文件路径，导入 traces（须同时指定 `--from-answer`） |
| `--from-answer` | — | **B** | — | 文件路径，导入 answer（`.txt`/`.md` 纯文本或 JSON） |
| `--max-loops` | — | A | `10` | Agent 最大 ReAct 循环数 |
| `--timeout` | `-t` | A | `1800` | Agent 执行超时秒数 |
| `--output` | `-o` | A/B | `eval_results.json` | 结果 JSON 输出路径 |
| `--sample` | `-s` | A/B | `0`（全部） | 只处理前 N 个样本 |
| `--task-name` | — | A/B | 自动生成 | 数据库任务名称 |
| `--save-db` | — | A/B | 开启 | 保存结果到数据库 |
| `--no-save-db` | — | A/B | — | 不保存到数据库 |

### 运行模式

```
┌─────────────────────────────────────────────────────────────┐
│ 模式 A：完整评估                                             │
│   dataset ──▶ Agent Pipeline ──▶ answer + traces ──▶ 评估器 │
│                                                              │
│ 模式 B：从文件导入（跳过 Agent）                              │
│   --from-traces (JSON) ──┐                                   │
│                          ├──▶ 评估器                         │
│   --from-answer (txt/md)─┘                                   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 模式 B 支持的文件格式

**`--from-traces`（JSON 文件）：**
```json
[
  {"thought": "...", "action": "arxiv_search", "observation": "..."},
  {"thought": "...", "action": "finish", "observation": "..."}
]
```


**`--from-answer`（纯文本或 JSON）：**
```markdown
<!-- review.md — 直接读取全文作为 answer -->
# 深度学习综述
...
```

```json
// answer.json — 自动提取 answer 字段
{"answer": "..."}
{"writer_result": "..."}
{"results": {"answer": "..."}}
```

### 数据集格式

数据集存储在 `eval_platform.db` → `evaluation_datasets` 表中，字段结构：

| 字段 | 类型 | 说明 |
|---|---|---|
| `dataset_name` | TEXT | 数据集名称（如"深度学习"） |
| `description` | TEXT | 数据集描述 |
| `data_samples` | TEXT | 单个 user_query 字符串，或 JSON 数组（多样本模式自动识别） |
| `ground_truths` | JSON | 参考答案（可为空，评估器会自动生成 reference） |

`data_samples` 支持两种格式：

```json
// 单样本模式（一个字符串）
"深度学习"

// 多样本模式（JSON 数组，脚本自动识别并逐条评估）
[
  "深度学习",
  "强化学习在机器人中的应用",
  "Transformer 架构的最新进展"
]
```


### 输出

**JSON 文件：**

```json
{
  "task_name": "...", "dataset_id": 1, "method": "explicit_metrics",
  "question": "...", "answer": "...", "traces": [...],
  "scores": {"answer_correctness": 0.72, "overall_score": 0.65},
  "records": [...], "backend": "ragas+llm"
}
```

**数据库**（`eval_platform.db` → `evaluation_tasks`，`status` 字段：`running` → `completed`/`failed`）

**控制台示例（模式 B）：**

```
======================================================================
  模式: 仅评估（traces: traces.json, answer: review.md）
======================================================================
📂 从文件加载 traces: traces.json
📂 从文件加载 answer: review.md
📏 [Eval] 开始评估 (method=explicit_metrics) ...
✅ [Eval] 评估完成，耗时 12.1s
  📊 评分摘要: overall_score: 0.6500
💾 结果已保存到数据库 (task_id=8)
```

---

## 评估方法

`evaluation_methods.py` → `LLMBasedEvaluator`（ragas + LLM Judge）

| 方法 | 关注点 |
|---|---|
| `result_oriented` | 答案正确性、完整性、相关性 |
| `process_oriented` | 检索精度、推理质量、步骤连贯性 |
| `explicit_metrics`（默认） | 综合以上 + faithfulness、helpfulness、overall_score |

---

## 环境配置

仓库根目录 `.env`：

```env
ZHIPU_API_KEY=your_api_key
ZHIPU_BASE_URL=https://open.bigmodel.cn/api/paas/v4
ZHIPU_MODEL=glm-4-flash
ZHIPU_EMBEDDING_MODEL=embedding-2
EVAL_USE_RAGAS=true
EVAL_AGENT_TIMEOUT_SEC=1800
AGENT_LOOP_DELAY_SEC=3
AGENT_MIN_PAPERS=3
```

---
