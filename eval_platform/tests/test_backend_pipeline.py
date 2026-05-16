import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import ModelS
import crud
import database
import services
import evaluation_methods as evaluation_methods_module
from api import app
from evaluation_methods import get_evaluator
from schemas import EvaluationDatasetCreate, EvaluationTaskCreate


def test_root_route_is_available():
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "Agent Evaluation Platform Backend"}


def test_default_evaluation_uses_fallback_similarity():
    evaluation_methods_module.RAGAS_AVAILABLE = False
    evaluator = get_evaluator("result_oriented")

    result = evaluator.evaluate(
        ["What is retrieval augmented generation?"],
        ["RAG combines retrieval with generation."],
        [["ctx"]],
        ["RAG combines retrieval with generation."],
    )

    assert result["backend"] == "fallback"
    assert result["method"] == "result_oriented"
    assert result["sample_count"] == 1
    assert result["metric_names"] == [
        "similarity_score",
        "truth_coverage_score",
        "token_f1_score",
        "context_support_score",
    ]
    assert "similarity_score" in result["scores"]
    assert "truth_coverage_score" in result["scores"]
    assert "token_f1_score" in result["scores"]
    assert "context_support_score" in result["scores"]
    assert isinstance(result["individual_scores"], list)
    assert result["individual_scores"][0]["similarity_score"] >= 0


def test_ragas_path_uses_embeddings_and_ground_truths(monkeypatch):
    monkeypatch.setattr(evaluation_methods_module, "RAGAS_AVAILABLE", True, raising=False)
    monkeypatch.setattr(evaluation_methods_module, "_build_ragas_llm", lambda: object(), raising=False)

    sentinel_embeddings = object()
    monkeypatch.setattr(
        evaluation_methods_module,
        "_build_ragas_embeddings",
        lambda: sentinel_embeddings,
        raising=False,
    )

    captured = {}

    class FakeDataset:
        @staticmethod
        def from_dict(data):
            captured["dataset"] = data
            return data

    class FakeFrame:
        def to_dict(self, orient="records"):
            return [
                {
                    "answer_relevancy": 0.5,
                    "answer_correctness": 0.75,
                    "answer_similarity": 0.9,
                }
            ]

    class FakeResult:
        def to_pandas(self):
            return FakeFrame()

    def fake_evaluate(dataset, metrics=None, llm=None, embeddings=None, **kwargs):
        captured["metrics"] = metrics
        captured["llm"] = llm
        captured["embeddings"] = embeddings
        captured["dataset"] = dataset
        captured["kwargs"] = kwargs
        return FakeResult()

    monkeypatch.setattr(evaluation_methods_module, "Dataset", FakeDataset, raising=False)
    monkeypatch.setattr(evaluation_methods_module, "evaluate", fake_evaluate, raising=False)

    evaluator = get_evaluator("result_oriented")
    result = evaluator.evaluate(
        ["What is retrieval augmented generation?"],
        ["RAG combines retrieval with generation."],
        [["ctx"]],
        ["RAG combines retrieval with generation."],
    )

    assert result["backend"] == "ragas+llm"
    assert captured["embeddings"] is sentinel_embeddings
    assert captured["dataset"]["ground_truth"] == ["RAG combines retrieval with generation."]
    assert "answer_relevancy" in result["scores"]


def test_perform_evaluation_writes_completed_result(monkeypatch, tmp_path):
    verify_db = None
    db_path = tmp_path / "eval_platform_test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    ModelS.Base.metadata.create_all(bind=engine)

    monkeypatch.setattr(database, "engine", engine, raising=False)
    monkeypatch.setattr(database, "SessionLocal", TestingSessionLocal, raising=False)
    monkeypatch.setattr(services, "SessionLocal", TestingSessionLocal, raising=False)
    monkeypatch.setattr(services, "run_agent_pipeline", object(), raising=False)
    monkeypatch.setattr(
        services,
        "_run_agent_in_agent_dir",
        lambda user_query, max_loops, agent_callback: {
            "writer_result": "Final answer",
            "traces": [{"action": "search", "observation": "found"}],
        },
        raising=False,
    )

    class FakeEvaluator:
        def evaluate(self, questions, answers, contexts, ground_truths):
            return {
                "backend": "fallback",
                "method": "result_oriented",
                "sample_count": 1,
                "scores": {"similarity_score": 0.88},
            }

    monkeypatch.setattr(services, "get_evaluator", lambda method: FakeEvaluator(), raising=False)

    db = TestingSessionLocal()
    try:
        dataset = crud.create_evaluation_dataset(
            db,
            EvaluationDatasetCreate(
                dataset_name="CI Dataset",
                description="backend pipeline test",
                data_samples="What is RAG?",
                ground_truths="RAG combines retrieval with generation.",
            ),
        )
        task = crud.create_evaluation_task(
            db,
            EvaluationTaskCreate(
                task_name="CI Task",
                agent_id="default-agent",
                dataset_id=dataset.id,
                method="result_oriented",
            ),
        )

        asyncio.run(services.perform_evaluation(db, task.id))

        db.close()
        verify_db = TestingSessionLocal()
        updated = crud.get_evaluation_task(verify_db, task.id)
        assert updated.status == "completed"
        assert updated.results["backend"] == "fallback"
        assert updated.results["scores"]["similarity_score"] == 0.88
        assert updated.results["traces"][0]["action"] == "search"
        assert updated.results["answer"] == "Final answer"
    finally:
        if verify_db is not None:
            verify_db.close()
        db.close()
        engine.dispose()