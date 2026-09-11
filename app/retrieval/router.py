import logging
import re

from app.models.retrieval import RetrievalRoute, RouteDecision

logger = logging.getLogger(__name__)


class QueryRouter:
    """Cheap deterministic router; deliberately transparent and testable."""

    graph_signals = {
        "appl": "applicability",
        "apply to": "applicability",
        "subject to": "applicability",
        "which entities": "entity scope",
        "relationship": "relationship",
        "related": "relationship",
        "replaced": "replacement",
        "replaces": "replacement",
        "supersed": "supersession",
        "amend": "amendment",
        "changed": "change",
        "change between": "comparison",
        "difference": "comparison",
        "compare": "comparison",
    }
    vector_signals = {"what is", "what does", "define", "purpose", "meaning", "penal charges"}

    def route(self, query: str) -> RouteDecision:
        normalized = re.sub(r"\s+", " ", query.lower()).strip()
        graph_reasons = [reason for signal, reason in self.graph_signals.items() if signal in normalized]
        vector_reasons = [signal for signal in self.vector_signals if signal in normalized]
        entity_mentions = len(re.findall(r"\b(?:rbi|nbfc|bank|borrower|lender|circular|direction)\w*\b", normalized))

        if graph_reasons and (vector_reasons or entity_mentions >= 2):
            decision = RouteDecision(route=RetrievalRoute.HYBRID, reasons=graph_reasons + vector_reasons)
        elif graph_reasons:
            decision = RouteDecision(route=RetrievalRoute.GRAPH, reasons=graph_reasons)
        else:
            decision = RouteDecision(route=RetrievalRoute.VECTOR, reasons=vector_reasons or ["single-fact default"])

        logger.info("query_routed route=%s reasons=%s", decision.route.value, decision.reasons)
        return decision

