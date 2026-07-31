# RAG 方法学深度回归包

这是从旧版52条候选记录确定性重建的审计样例，不是一次新的在线检索，也不伪造历史中缺失的方法字段。

建议按以下顺序检查：

1. `formal_review_v2.md` / `.html` / `.docx` / `.pdf`：重写后的技术证据综述草稿。
2. `methodology_audit.json`：59→52→17→12的流程对账与缺失信息。
3. `search_ledger_v2.json`：三条真实归档检索式及未记录字段。
4. `screening_ledger_v2.json`：全部52条标题摘要决定与17条全文决定。
5. `evidence_cards_v2.json`：一级/二级证据分层后的证据卡。
6. `claim_ledger.json`：论断类型、来源适配、数字降级和术语门禁。
7. `quality_gate.json`：八部分质量门禁；当前诚实结论为 `needs_revision`。

关键变化：P1/P6/P12只用于分类和背景；CRAG/DRAGIN增加机制、失败传播和适用条件；47.4%与8.6%因上下文不完整被降级；P8的局部执行时间与跨研究成本证据缺口不再互相矛盾；正文含三张表和一张概念图。
