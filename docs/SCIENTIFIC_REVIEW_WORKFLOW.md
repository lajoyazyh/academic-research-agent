# 科学化综述工作流

## 核心状态

新项目使用 `workflow_version=2`，执行顺序为：

1. 创建并确认研究协议。
2. 运行一个或多个可恢复检索批次。
3. 将检索结果登记为候选记录，而不是直接纳入综述。
4. 完成标题摘要初筛和全文/人工筛选。
5. 确认最终纳入快照。
6. 生成结构化证据、逐领域质量评价和综合分组。
7. 根据方法学账本、证据矩阵和纳入快照撰写综述。
8. 建立 Claim Ledger 并检查引用标识。

自动流程会在协议确认和最终纳入确认两个检查点暂停。

## 综述模式

| 模式 | 默认候选上限 | 可调整范围 | 输出约束 |
|---|---:|---:|---|
| 快速证据综述 | 100 | 30–300 | 不得标记为系统综述 |
| 严格系统综述 | 500 | 100–2000 | 配置查询、筛选、提取与审计完成后才允许使用系统综述标签 |
| 范围综述/系统映射 | 500 | 100–2000 | 以概念和证据分布为主 |
| 计算机与 AI 技术综述 | 300 | 50–1000 | 增加数据泄漏、基线公平性、复现性和成本评价 |

模式切换会创建新协议版本。候选元数据和全文可以复用，但筛选决定必须按新版协议重新产生。

## 主要接口

- `GET /api/sessions/scientific/catalog`
- `GET|PUT /api/sessions/{id}/protocol`
- `POST /api/sessions/{id}/protocol/confirm`
- `POST /api/sessions/{id}/protocol/version`
- `GET /api/sessions/{id}/scientific`
- `GET /api/sessions/{id}/candidates`
- `POST /api/sessions/{id}/screening`
- `POST /api/sessions/{id}/screening/batch`
- `POST /api/sessions/{id}/inclusion-snapshots/confirm`
- `PUT /api/sessions/{id}/extractions`
- `PUT /api/sessions/{id}/appraisals`
- `GET /api/sessions/{id}/methodology-audit`

`POST .../run/auto` 支持：

- `resume_from=plan`：规划和检索，在最终纳入检查点暂停。
- `resume_from=notes`：从已确认纳入快照继续证据提取、评价、分析和写作。

用户设置的本轮论文数只控制批次收集目标，不再作为研究检索的完成条件。严格模式还会核验每个已确认数据源的分页任务以及 OpenAlex 前向、后向引用追踪；限流、超时或预算耗尽会保留游标和失败状态，下一轮从账本继续。

## 数据库升级

部署前执行 Supabase migration：

```powershell
npx supabase db push
```

新增关系位于 `supabase/migrations/003_scientific_review_workflow.sql`。服务端仍把完整方法学状态写入 `research_sessions.snapshot` 和 `scientific_methodology` artifact，因此新表短暂不可用时不会丢失研究状态；新表用于审计和查询。

历史项目保持可读。历史论文不会被伪造为已完成两阶段筛选；进入新流程后需要创建/确认协议，并重新确认最终纳入快照。

## 验证

```powershell
python -m compileall -q agent
python -m pytest -q
node --check agent/frontend/notebooklm.js
npm run build
```

20 个固定主题位于 `evals/scientific_review/topics.json`，计算机/AI 与通用主题各 10 个。将一次评测导出的候选、筛选和流程计数保存为 predictions JSON 后运行：

```powershell
python scripts/evaluate_scientific_workflow.py path/to/predictions.json --output eval-report.json
```

评测器计算候选召回率、标题摘要筛选敏感度和流程对账率，并以 90%、95%、100% 作为门槛。实时指标必须在配置真实数据源和模型后运行，不能由单元测试替代。

手工验证重点：

1. 未确认协议时，搜索和自动流程返回 `protocol_confirmation_required`。
2. 搜索完成后论文显示为候选记录，而不是默认最终纳入。
3. 自动流程显示 `waiting_for_confirmation`，确认纳入后从 notes 阶段继续。
4. 改变纳入集合后，旧 inclusion snapshot 不能通过写作质量门禁。
5. 快速模式的标题和文档状态不能宣称为系统综述。
6. 严格模式在配置检索尚未完成时返回 `configured_search_queries_incomplete`。
7. 方法、筛选计数和参考文献均能从 methodology audit 追溯。
