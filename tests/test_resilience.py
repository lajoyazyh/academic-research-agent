import json

from backend.rate_limit import SlidingWindowLimiter, policy_for
from backend.run_store import PersistentRunStore
from main import assess_review_quality


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
