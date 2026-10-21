"""Historical replay: play the corpus forward through time and score the change handling.

RBI's side of the world is simulated from dated, official facts: each document appears on
its issue date; the 28 November 2025 consolidation (RBI/2025-26/100) withdraws the rules
RBI's register lists; a withdrawn page shows its watermark on its withdrawal date. The
system's side is the production code, run as a daily check under a simulated clock:
monitoring status, successor linking, and answers.

Gold never comes from system output (brief rule 2): withdrawal from RBI's register and
watermarks, successor links from Ashu's answers (data/evaluation/gold/phase1_labels.json),
dates from RBI's printed text. Assumptions are written into the report.

A document with an RBI-stated successor (Ashu answered yes) gets no simulated watermark,
so only successor linking can retire it: that is what the replay tests.
"""

import shutil
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from app import clock
from app.config.settings import Settings
from app.ingestion.manifest import DocumentManifest
from app.ingestion.service import IngestionService
from app.models.documents import DocumentLifecycle, DocumentMetadata
from app.models.links import LinkTrust
from app.monitoring.linking import LinkingService
from app.monitoring.trust import EXPLICIT_METHODS
from app.monitoring.withdrawn_register import CONSOLIDATION
from app.retrieval.query_service import RegulatoryQueryService


@dataclass
class Timeline:
    """When each document is in force according to the gold sources."""

    start: dict[str, date] = field(default_factory=dict)
    end: dict[str, date | None] = field(default_factory=dict)  # None: still in force
    end_known: dict[str, bool] = field(default_factory=dict)   # False: withdrawn by today, date unknown

    def in_force(self, document_id: str, day: date) -> bool:
        end = self.end.get(document_id)
        return self.start[document_id] <= day and (end is None or day < end)


def gold_timeline(documents: list[DocumentMetadata], labels: dict, today: date) -> tuple[Timeline, dict[str, str]]:
    """In-force windows from RBI's dates, RBI's register/watermarks and Ashu's link answers.

    Returns the timeline and, per replaced document, the document that replaced it.
    """
    by_url = {item.source_url: item for item in documents}
    timeline = Timeline()
    for item in documents:
        timeline.start[item.document_id] = item.in_force_from or item.publication_date or today
    successors: dict[str, str] = {}
    for key, repeals in labels.get("explicit_links", {}).items():
        old_url, new_url = key.split(" -> ")
        if repeals and old_url in by_url and new_url in by_url:
            old, new = by_url[old_url], by_url[new_url]
            successors[old.document_id] = new.document_id
            timeline.end[old.document_id] = timeline.start[new.document_id]
            timeline.end_known[old.document_id] = True
    for item in documents:
        if item.document_id in timeline.end or item.lifecycle is not DocumentLifecycle.WITHDRAWN:
            continue
        issued = item.publication_date or today
        timeline.end[item.document_id] = CONSOLIDATION if issued < CONSOLIDATION else today
        timeline.end_known[item.document_id] = issued < CONSOLIDATION
    for url, in_force in labels.get("directions_in_force", {}).items():
        if url in by_url and in_force is False:
            timeline.end[by_url[url].document_id] = today
            timeline.end_known[by_url[url].document_id] = False
    return timeline, successors


def _raw_file(source: Settings, document: DocumentMetadata) -> Path | None:
    return next((path for path in source.raw_dir.glob(f"{document.document_id}.*")), None)


def run_replay(source_dir: Path, work_dir: Path, labels: dict, today: date, auto_trust_enabled: bool = True) -> dict:
    source = Settings(_env_file=None, data_dir=source_dir)
    documents = DocumentManifest(source.runtime_dir / "documents.json").all()
    timeline, gold_successors = gold_timeline(documents, labels, today)
    directions = {url for url, ok in labels.get("directions_in_force", {}).items() if ok}

    if work_dir.exists():
        shutil.rmtree(work_dir)
    settings = Settings(_env_file=None, data_dir=work_dir, vector_backend="filesystem", database_url=None,
                        answer_provider="deterministic", extraction_provider="deterministic",
                        auto_trust_enabled=auto_trust_enabled)
    ingestion = IngestionService(settings)
    linking = LinkingService(ingestion, settings)
    arrivals: dict[date, list[DocumentMetadata]] = {}
    for item in documents:
        arrivals.setdefault(item.publication_date or today, []).append(item)
    watermark_on: dict[date, list[str]] = {}
    for document_id, end in timeline.end.items():
        if end and document_id not in gold_successors:
            watermark_on.setdefault(end, []).append(document_id)
    questions = {item.document_id: f"What do RBI's rules on {item.title} require for loans?"
                 for item in documents if timeline.end.get(item.document_id)}
    ask_on: dict[date, list[str]] = {}
    for document_id in questions:
        end = timeline.end[document_id]
        for day in ((end, today) if timeline.end_known.get(document_id) else (today,)):
            ask_on.setdefault(day, []).append(document_id)

    days = sorted(set(arrivals) | set(watermark_on) | set(ask_on) | {CONSOLIDATION, today})
    answers, link_first_seen, failures = [], {}, []
    for day in days:
        with clock.simulated(lambda day=day: datetime(day.year, day.month, day.day, 9, tzinfo=UTC)):
            for item in arrivals.get(day, []):
                raw = _raw_file(source, item)
                if raw is None:
                    failures.append(f"no stored source for {item.document_id}")
                    continue
                created = ingestion.ingest_content(raw.read_bytes(), item.source_url, f"source{raw.suffix}", item.title).document
                ingestion.manifest.set_fields(created.document_id, circular_numbers=item.circular_numbers,
                                              publication_date=item.publication_date, effective_date=item.effective_date,
                                              issuing_department=item.issuing_department, document_type=item.document_type)
                ingestion.set_in_force(created.document_id, timeline.start[item.document_id], None)
                ingestion.set_lifecycle(created.document_id, DocumentLifecycle.REVIEW_REQUIRED, item.source_url or "",
                                        "No RBI status signal on the page when published.", clock.now(), "AUTOMATED")
            if day == CONSOLIDATION:
                for item in ingestion.list_documents():
                    if item.source_url in directions:  # Ashu's Part 1 approval, assumed same day
                        ingestion.approve_lifecycle(item.document_id, DocumentLifecycle.ACTIVE, item.source_url,
                                                    "Reviewer confirmed the direction is in force on RBI's site.", clock.now())
            for document_id in watermark_on.get(day, []):
                if ingestion.get(document_id):
                    ingestion.set_lifecycle(document_id, DocumentLifecycle.WITHDRAWN, "",
                                            f"RBI Withdrawn watermark (replay: withdrawn {day}).", clock.now(), "AUTOMATED")
            linking.reconcile()
            for link in linking.store.all():
                link_first_seen.setdefault(link.link_id, day)
            for document_id in ask_on.get(day, []):
                response = RegulatoryQueryService(settings).query(questions[document_id], as_of=day)
                evidence = {chunk.document_id for chunk in response.retrieved_evidence}
                cited = {citation.document_id for citation in response.citations}
                answers.append({
                    "day": day.isoformat(), "about": document_id,
                    "stale_evidence": sorted(d for d in evidence if d in timeline.start and not timeline.in_force(d, day)),
                    "stale_citations": sorted(d for d in cited if d in timeline.start and not timeline.in_force(d, day)),
                    "notices": [notice.kind for notice in response.notices],
                })

    links = linking.store.all()
    return _report(documents, timeline, gold_successors, labels, links, link_first_seen, answers, failures,
                   auto_trust_enabled, today)


def _ratio(numerator: int, denominator: int) -> dict:
    return {"value": round(numerator / denominator, 4) if denominator else None, "numerator": numerator,
            "denominator": denominator}


def _report(documents, timeline, gold_successors, labels, links, link_first_seen, answers, failures,
            auto_trust_enabled, today) -> dict:
    by_url = {item.source_url: item.document_id for item in documents}
    judged = {}
    for key, value in labels.get("explicit_links", {}).items():
        old_url, new_url = key.split(" -> ")
        if value is not None and old_url in by_url and new_url in by_url:
            judged[(by_url[old_url], by_url[new_url])] = value
    # Scored per document pair: two RBI statements (a repeal list and a banner) about the same
    # replacement are one link, not two.
    explicit = {(link.old_document_id, link.new_document_id) for link in links if link.method in EXPLICIT_METHODS}
    explicit_judged = [pair for pair in explicit if pair in judged]
    correct = [pair for pair in explicit_judged if judged[pair]]
    found = explicit
    true_pairs = [pair for pair, value in judged.items() if value]
    auto = {(link.old_document_id, link.new_document_id) for link in links if link.trust is LinkTrust.AUTO_TRUSTED}
    auto_judged = [pair for pair in auto if pair in judged]

    successors_gold = labels.get("successors", {})
    candidate_hits = candidate_total = 0
    for link in links:
        if link.method != "candidate_content_match":
            continue
        old_url = next((item.source_url for item in documents if item.document_id == link.old_document_id), None)
        new_url = next((item.source_url for item in documents if item.document_id == link.new_document_id), None)
        answer = successors_gold.get(old_url)
        if answer is not None:
            candidate_total += 1
            candidate_hits += new_url in answer

    switch_days = []
    for old_id, new_id in gold_successors.items():
        link = next((item for item in links if (item.old_document_id, item.new_document_id) == (old_id, new_id)
                     and item.trust in {LinkTrust.AUTO_TRUSTED, LinkTrust.APPROVED}), None)
        if link:
            switch_days.append(max(0, (link_first_seen[link.link_id] - timeline.start[new_id]).days))

    current = [document for document in documents if document.lifecycle is DocumentLifecycle.WITHDRAWN]
    return {
        "today": today.isoformat(),
        "auto_trust_enabled": auto_trust_enabled,
        "documents": len(documents),
        "assumptions": [
            f"Register-listed rules issued before {CONSOLIDATION} are withdrawn on that date (RBI/2025-26/100, "
            "'with immediate effect'), unless an RBI-stated successor (Ashu: yes) ended them earlier.",
            "Rules withdrawn but issued after the consolidation have no known withdrawal date: checked only today.",
            f"Ashu's 'in force' approvals of the 16 NBFC directions take effect on {CONSOLIDATION} (no review delay).",
            "Documents with an RBI-stated successor get no simulated watermark, so only successor linking retires them.",
            "Questions are templated from each replaced rule's own title; answers are deterministic (no model).",
        ],
        "successor_links_from_rbi_text": {
            "precision": _ratio(len(correct), len(explicit_judged)),
            "recall_over_rbi_statements_judged_true": _ratio(len(found & set(true_pairs)), len(true_pairs)),
            "awaiting_answer": len(explicit) - len(explicit_judged),
        },
        "auto_trust_precision": {
            **_ratio(sum(judged[pair] for pair in auto_judged), len(auto_judged)),
            "auto_trusted": len(auto), "awaiting_answer": len(auto) - len(auto_judged),
        },
        "candidate_suggestions": {
            "accuracy": _ratio(candidate_hits, candidate_total),
            "suggestions": sum(1 for link in links if link.method == "candidate_content_match"),
            "note": "Scored only against Part 3 answers given so far; not yet measured until Part 3 is complete.",
        },
        "stale_answer_rate": {
            "evidence": _ratio(sum(bool(item["stale_evidence"]) for item in answers), len(answers)),
            "citations": _ratio(sum(bool(item["stale_citations"]) for item in answers), len(answers)),
        },
        "time_to_switch_days": {"per_link": switch_days, "max": max(switch_days) if switch_days else None,
                                "note": "Days from the successor's in-force date to the daily check that applied it."},
        "review_items_created": sum(1 for link in links if link.trust is LinkTrust.REVIEW_REQUIRED),
        "withdrawn_documents_in_corpus": len(current),
        "answers": answers,
        "failures": failures,
    }
