import json

from backend.rate_limit import SlidingWindowLimiter, policy_for
from backend.run_store import PersistentRunStore
from main import _normalize_citation_markers, assess_review_quality


def test_persistent_run_store_never_writes_credentials(tmp_path):
    store = PersistentRunStore(tmp_path)
    record = store.create(
        "sess_safe",
        kind="search",
        payload={
            "topic": "safe topic",
            "provider": {
                "provider_id": "openai",
                "api_key": "should-never-be-written",
                "chat_model": "gpt-test",
            },
            "github_token": "also-secret",
        },
    )

    saved_path = tmp_path / ".runs" / "sess_safe" / f"{record['run_id']}.json"
    raw = saved_path.read_text(encoding="utf-8")
    saved = json.loads(raw)

    assert "should-never-be-written" not in raw
    assert "also-secret" not in raw
    assert saved["payload"]["provider"]["provider_id"] == "openai"
    assert "api_key" not in saved["payload"]["provider"]


def test_persistent_run_store_marks_stale_run_retryable(tmp_path):
    store = PersistentRunStore(tmp_path)
    record = store.create("sess_restart", kind="auto", payload={"topic": "topic", "language": "en"})

    interrupted = store.mark_interrupted("sess_restart", record["run_id"])

    assert interrupted["status"] == "interrupted"
    assert interrupted["retryable"] is True
    assert "restart" in interrupted["message"].lower()


def test_sliding_window_limiter_blocks_after_budget():
    limiter = SlidingWindowLimiter()

    assert limiter.allow("user:run", 2, 60)[0] is True
    assert limiter.allow("user:run", 2, 60)[0] is True
    allowed, retry_after = limiter.allow("user:run", 2, 60)

    assert allowed is False
    assert retry_after >= 1
    assert policy_for("/api/sessions/one/run/search", "POST") == ("agent-run", 8, 60)
    assert policy_for("/api/sessions", "GET") is None


def test_review_quality_flags_uncited_claims_and_abstract_only_sources():
    review = """## 摘要
这是摘要。
## 研究范围
这里说明范围。
## 主题综合
该方法在 120 个样本中取得显著结果。
## 方法比较
另一种模型使用对照实验并报告结果 [P1]。
## 局限
存在局限。
## 结论
这是结论。
## 参考来源
- [P1] Paper one
"""
    quality = assess_review_quality(
        review,
        [{"id": "P1", "title": "Paper one", "evidence_basis": "abstract"}],
    )

    assert quality["status"] == "needs_review"
    assert quality["unsupported_claims"]
    assert quality["claim_citation_coverage"] < 1
    assert quality["abstract_only_sources"] == ["P1"]


def test_review_quality_splits_chinese_sentences_without_whitespace():
    review = """## 摘要
这是摘要。
## 研究范围
这里说明范围。
## 主题综合
该方法在 120 个样本中取得显著结果。另一种模型在 80 个样本中报告结果 [P1]。
【方法记录】本次方法筛选了 4 篇研究。
## 方法
这里说明方法。
## 局限
存在局限。
## 结论
这是结论。
## 参考来源
- [P1] Paper one
"""
    quality = assess_review_quality(
        review,
        [{"id": "P1", "title": "Paper one", "evidence_basis": "full_text"}],
    )

    assert len(quality["unsupported_claims"]) == 1
    assert "120" in quality["unsupported_claims"][0]
    # The explicit method record is excluded from empirical claims. Of the two
    # numerical claims, one is cited and one is unsupported.
    assert quality["claim_citation_coverage"] == 0.5


def test_review_quality_accepts_standard_review_headings_and_chinese_brackets():
    review = """## 摘要
摘要内容。
## 引言
研究问题与范围。
## 方法
检索与筛选过程。
## 结果与证据综合
该方法在 120 个样本上报告结果【P1】。
## 讨论与限制
现有证据存在限制。
## 结论
结论内容。
## 参考文献
- [P1] Paper one
"""
    quality = assess_review_quality(
        review,
        [{"id": "P1", "title": "Paper one", "evidence_basis": "full_text"}],
    )

    assert quality["section_coverage"] == 1
    assert quality["citation_coverage"] == 1
    assert quality["claim_citation_coverage"] == 1
    assert quality["status"] == "passed"
    assert _normalize_citation_markers("结论【P1】与（P2，P3），P4 提出补充。") == (
        "结论[P1]与[P2] [P3]，[P4] 提出补充。"
    )
