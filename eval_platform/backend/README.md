# Agent评估平台后端

此后端提供分层 API，用于管理评估数据集、调度 Agent 执行并保存评测结果。

## 架构

- 表现层：`routers/` 处理 HTTP 请求。
- 服务层：`services.py` 负责任务执行、Agent 调用和结果写回。
- 数据访问层：`crud.py` 负责数据库读写。
- 数据层：`ModelS.py` 和 `database.py` 负责模型定义与连接。

## 评估方法

`evaluation_methods.py` 提供三种评估器：

- `result_oriented`：面向结果，主要看最终答案质量。
- `process_oriented`：面向过程，主要看上下文和检索质量。
- `explicit_metrics`：综合多个显式指标。

当前默认优先使用 `ragas`，但如果第三方依赖不可用或未启用 `EVAL_USE_RAGAS=true`，会自动回退到稳定的字符串相似度评估，保证任务不中断。

## 运行方式

安装依赖：

```powershell
cd 迭代二
python -m pip install -r requirements.txt
python -m pip install -r requirements-eval.txt
```

启动后端：

```powershell
cd 迭代二/eval_platform/backend
python main.py
```

API 默认在 `http://127.0.0.1:8001` 可用。

`main.py` 会显式加载仓库根目录 `.env`。当前平台只需要维护智谱相关配置：`ZHIPU_API_KEY`、`ZHIPU_BASE_URL`、`ZHIPU_MODEL`。

## API 端点

### 任务

- `POST /tasks/create`
- `POST /tasks/evaluate/{task_id}`
- `GET /tasks/status/{task_id}`
- `GET /tasks/results/{task_id}`
- `GET /tasks/list`
- `GET /tasks/detail/{task_id}`
- `DELETE /tasks/delete/{task_id}`

### 数据集

- `POST /datasets/create`
- `GET /datasets/list`
- `GET /datasets/detail/{dataset_id}`
- `DELETE /datasets/delete/{dataset_id}`

## 结果结构

任务完成后，`results` 字段会保存统一结构，方便前端和后续分析脚本直接消费：

- `method`：评测方法名
- `backend`：`ragas` 或 `fallback`
- `sample_count`：参与评测的样本数
- `scores`：标准化评分字典
- `records`：`ragas` 的逐样本原始结果（如果可用）
- `traces`：Agent 运行轨迹摘要
- `question` / `answer` / `ground_truths`：输入输出快照

## 当前约束

- 对外主要维护智谱配置即可，底层兼容项由程序自动映射。
- 默认使用 fallback 评估，避免第三方依赖升级导致平台不可用；fallback 会输出 `similarity_score`、`truth_coverage_score`、`token_f1_score` 和 `context_support_score`。
- `ragas` 路径需要同时具备聊天模型和 embedding 配置；默认 embedding 模型名可通过 `ZHIPU_EMBEDDING_MODEL` 调整。
- 默认的 Zhipu 兼容 ragas 子集会优先跑 `faithfulness`、`answer_relevancy` 和 `answer_similarity`；`answer_correctness` 仅在显式打开 `RAGAS_INCLUDE_ANSWER_CORRECTNESS=true` 时启用。
- `RAGAS_INCLUDE_ANSWER_CORRECTNESS` 建议默认保持关闭，只有在你已经确认当前 Zhipu 接口兼容该指标时才打开。
- 任务触发后会先标记为 `queued`，随后由后台切换到 `running`；可以通过 `EVAL_AGENT_TIMEOUT_SEC` 控制单次 Agent 执行时长。
- 如果需要启用 `ragas`，建议先锁定版本并在本地完成单独验证。

## 测试

平台后端已提供基础联动测试，重点覆盖：

- 根路由可用性。
- fallback 评估器行为。
- 评估任务执行后能正确写回结果和状态。

这些测试可直接用于 GitHub 提交前回归。


