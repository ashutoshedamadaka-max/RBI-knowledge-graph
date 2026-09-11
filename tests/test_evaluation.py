from pathlib import Path

from app.config.settings import Settings
from app.evaluation.harness import EvaluationHarness
from app.evaluation.models import EvaluationCase, QuestionCategory
from app.ingestion.service import IngestionService
from app.models.documents import IngestRequest
from app.models.retrieval import RetrievalRoute


def test_harness_reports_measured_source_recall(tmp_path: Path) -> None:
    source = tmp_path / "rbi.txt"
    source.write_text("The Reserve Bank of India requires lenders to disclose penal charges.")
    settings = Settings(data_dir=tmp_path / "data")
    IngestionService(settings).ingest(IngestRequest(local_path=str(source), title="RBI circular"))
    cases = [EvaluationCase(
        case_id="eval_1",
        question="What must lenders disclose about penal charges?",
        category=QuestionCategory.SINGLE_HOP,
        hop_count=1,
        expected_route=RetrievalRoute.VECTOR,
        expected_source_urls=[],
    )]
    report = EvaluationHarness(settings).run(cases)

    assert report.total_cases == 1
    assert report.routing_accuracy == 1.0
    assert report.citation_validity == 1.0


def test_labeled_dataset_has_required_breadth() -> None:
    cases = EvaluationHarness.load_cases(Path("data/evaluation/questions.json"))

    assert 30 <= len(cases) <= 50
    assert {case.category for case in cases} == set(QuestionCategory)
