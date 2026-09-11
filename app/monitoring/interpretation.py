from app.models.monitoring import ChangeInterpretation, DiscoveryStatus, Materiality, StructuredDiff


class DeterministicChangeInterpreter:
    """No-cost fallback; OpenAI can be added behind this contract after corpus review."""

    def interpret(self, status: DiscoveryStatus, diff: StructuredDiff | None,
                  evidence_chunk_ids: list[str]) -> ChangeInterpretation:
        changed = (diff.added if diff else [])[:3]
        return ChangeInterpretation(
            change_summary=("New RBI lending document detected." if status is DiscoveryStatus.NEW
                            else "Document update detected from deterministic text comparison."),
            change_type=status.value,
            affected_requirements=changed,
            materiality=(Materiality.HIGH if diff and (diff.changed_dates or diff.changed_numbers)
                         else Materiality.MEDIUM),
            evidence_chunk_ids=evidence_chunk_ids,
            confidence=0.7,
        )
