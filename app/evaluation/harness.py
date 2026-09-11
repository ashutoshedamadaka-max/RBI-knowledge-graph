import json
import statistics
from pathlib import Path

from app.config.settings import Settings
from app.llm.citations import validate_citations
from app.llm.generation import DeterministicAnswerGenerator
from app.models.chunks import ChunkMetadata
from app.models.query import QueryResponse
from app.models.retrieval import RetrievalRoute
from app.evaluation.models import CaseResult, EvaluationCase, EvaluationReport
from app.retrieval.query_service import RegulatoryQueryService
from app.retrieval.service import VectorRetrievalService


class EvaluationHarness:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.query_service = RegulatoryQueryService(settings)
        self.vector_service = VectorRetrievalService(settings)

    @staticmethod
    def load_cases(path: Path) -> list[EvaluationCase]:
        return [EvaluationCase.model_validate(item) for item in json.loads(path.read_text())]

    @staticmethod
    def _recall(evidence: list[ChunkMetadata], expected_urls: list[str]) -> float:
        if not expected_urls:
            return 1.0 if not evidence else 0.0
        found = {item.source_url for item in evidence if item.source_url}
        return len(found & set(expected_urls)) / len(expected_urls)

    def run(self, cases: list[EvaluationCase], top_k: int | None = None) -> EvaluationReport:
        results = []
        generator = DeterministicAnswerGenerator()
        for case in cases:
            vector_evidence = self.vector_service.retrieve_vector(case.question, top_k)
            baseline_answer = generator.generate(case.question, vector_evidence)
            response: QueryResponse = self.query_service.query(case.question, top_k)
            results.append(CaseResult(
                case_id=case.case_id,
                category=case.category,
                hop_count=case.hop_count,
                route_correct=response.route == case.expected_route,
                vector_recall=self._recall(vector_evidence, case.expected_source_urls),
                proposed_recall=self._recall(response.retrieved_evidence, case.expected_source_urls),
                citation_valid=validate_citations(response.answer, response.retrieved_evidence) if response.retrieved_evidence else True,
                latency_ms=response.latency_ms,
                estimated_cost_usd=response.estimated_cost_usd,
            ))

        grouped: dict[str, list[CaseResult]] = {}
        for result in results:
            grouped.setdefault(str(result.hop_count), []).append(result)
        by_hop = {
            hop: {
                "vector_recall_at_k": sum(row.vector_recall for row in rows) / len(rows),
                "proposed_recall_at_k": sum(row.proposed_recall for row in rows) / len(rows),
                "count": float(len(rows)),
            }
            for hop, rows in grouped.items()
        }
        return EvaluationReport(
            total_cases=len(results),
            retrieval_recall_at_k=sum(row.proposed_recall for row in results) / len(results) if results else 0,
            citation_validity=sum(row.citation_valid for row in results) / len(results) if results else 0,
            routing_accuracy=sum(row.route_correct for row in results) / len(results) if results else 0,
            median_latency_ms=statistics.median(row.latency_ms for row in results) if results else 0,
            estimated_cost_usd=sum(row.estimated_cost_usd for row in results),
            by_hop_count=by_hop,
            results=results,
        )

