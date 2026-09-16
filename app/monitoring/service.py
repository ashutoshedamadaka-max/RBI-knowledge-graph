import hashlib
import re
from datetime import UTC, datetime
from typing import Callable
from uuid import uuid4

from app.models.documents import DocumentLifecycle
from app.models.monitoring import (
    DiscoveryStatus, DocumentVersion, Materiality, MonitoringRunStatus,
    RegulatorySource, RegulatoryUpdate, SourceCheck,
)
from app.monitoring.alerts import LogAlertSender, RegulatoryAlertSender
from app.monitoring.diff import deterministic_diff, normalize_regulatory_text
from app.monitoring.fetcher import SourceFetcher
from app.monitoring.lifecycle import LifecycleResolution
from app.monitoring.store import MonitoringStore
from app.monitoring.interpretation import DeterministicChangeInterpreter

Processor = Callable[[object, str, int], tuple[str | None, list[str]]]


class RegulatoryMonitor:
    def __init__(self, store: MonitoringStore, fetcher: SourceFetcher,
                 processor: Processor | None = None, alert_sender: RegulatoryAlertSender | None = None) -> None:
        self.store = store
        self.fetcher = fetcher
        self.processor = processor
        self.alert_sender = alert_sender or LogAlertSender()
        self.interpreter = DeterministicChangeInterpreter()

    def check_source(self, source: RegulatorySource) -> tuple[SourceCheck, list[RegulatoryUpdate]]:
        run_id, now = f"run_{uuid4().hex}", datetime.now(UTC)
        try:
            discovered = self.fetcher.discover(source)
        except Exception as exc:
            check = SourceCheck(run_id=run_id, source_id=source.source_id, checked_at=now,
                                status=MonitoringRunStatus.SOURCE_UNAVAILABLE, error=str(exc))
            self.store.add_check(check)
            return check, []

        updates: list[RegulatoryUpdate] = []
        try:
            for document in discovered:
                if not self._is_lending_relevant(document.title, source.regulatory_topics):
                    continue
                previous = self.store.current_version(document.canonical_url)
                text = self.fetcher.download_text(document)
                resolution = self.fetcher.lifecycle_resolution(document)
                if (
                    source.approved_lifecycle in {DocumentLifecycle.ACTIVE, DocumentLifecycle.AMENDED}
                    and (resolution is None or resolution.lifecycle in {
                        DocumentLifecycle.REVIEW_REQUIRED,
                        DocumentLifecycle.UNKNOWN,
                    })
                ):
                    # A curated approval can resolve an absence of a positive RBI
                    # lifecycle signal, but can never overwrite an explicit
                    # withdrawal, repeal, or supersession detected on the source.
                    resolution = LifecycleResolution(
                        source.approved_lifecycle,
                        source.approval_evidence_excerpt or "Curated official RBI source approved for current-guidance intake.",
                        datetime.now(UTC),
                        "CURATED_APPROVAL",
                    )
                lifecycle = resolution.lifecycle if resolution else DocumentLifecycle.REVIEW_REQUIRED
                normalized_text = normalize_regulatory_text(text)
                content_hash = hashlib.sha256(normalized_text.encode()).hexdigest()
                if previous and previous.normalized_text_hash == content_hash:
                    if hasattr(self.processor, "assess_lifecycle"):
                        lifecycle = self.processor.assess_lifecycle(document, text, resolution).lifecycle
                    lifecycle_changed = self.store.update_current_lifecycle(document.canonical_url, lifecycle.value)
                    if lifecycle_changed:
                        update = RegulatoryUpdate(
                            update_id=f"update_{hashlib.sha256((previous.version_id + lifecycle.value).encode()).hexdigest()[:20]}",
                            source_id=source.source_id,
                            title=document.title,
                            publication_date=document.publication_date,
                            detected_at=now,
                            change_type=DiscoveryStatus.LIFECYCLE_CHANGED,
                            summary=(
                                f"The monitored RBI page changed lifecycle status from "
                                f"{previous.lifecycle.value.replace('_', ' ').lower()} to "
                                f"{lifecycle.value.replace('_', ' ').lower()}."
                            ),
                            previous_version_id=previous.version_id,
                            new_version_id=previous.version_id,
                            materiality=Materiality.HIGH if lifecycle in {
                                DocumentLifecycle.WITHDRAWN,
                                DocumentLifecycle.REPEALED,
                                DocumentLifecycle.SUPERSEDED,
                            } else Materiality.MEDIUM,
                            source_url=document.canonical_url,
                            citation_valid=False,
                            regulatory_fact=resolution.excerpt if resolution else "",
                            potential_operational_impact=(
                                "Current-guidance eligibility changed; review affected research answers."
                            ),
                        )
                        if self.store.add_update_once(update):
                            updates.append(update)
                    continue
                status = DiscoveryStatus.NEW if previous is None else DiscoveryStatus.MODIFIED
                version_number = 1 if previous is None else previous.version + 1
                document_id, chunk_ids = self.processor(document, text, version_number) if self.processor else (None, [])
                # Apply the observed lifecycle after processing. A changed RBI page
                # can create a new document record, and that latest record—not the
                # prior snapshot—must receive the current status evidence.
                if hasattr(self.processor, "assess_lifecycle"):
                    lifecycle = self.processor.assess_lifecycle(document, text, resolution).lifecycle
                version = DocumentVersion(
                    version_id=f"version_{hashlib.sha256((document.canonical_url + content_hash).encode()).hexdigest()[:20]}",
                    source_id=source.source_id, canonical_url=document.canonical_url, title=document.title,
                    document_identifier=document.document_identifier, publication_date=document.publication_date,
                    content_hash=content_hash,
                    normalized_text_hash=content_hash,
                    text_snapshot=text,
                    document_id=document_id, version=version_number, lifecycle=lifecycle,
                    is_current=True, valid_from=now,
                )
                self.store.add_version(version)
                if previous and previous.document_id and hasattr(self.processor, "mark_previous"):
                    self.processor.mark_previous(previous.document_id, now.isoformat())
                # Curated cornerstone documents establish the initial baseline. They are
                # not regulatory changes merely because monitoring was enabled later.
                if previous is None and source.parser_strategy == "rbi_document":
                    continue
                diff = deterministic_diff(previous.text_snapshot, text) if previous else None
                interpretation = self.interpreter.interpret(status, diff, chunk_ids)
                update = RegulatoryUpdate(
                    update_id=f"update_{hashlib.sha256((version.version_id + status.value).encode()).hexdigest()[:20]}",
                    source_id=source.source_id, title=document.title, publication_date=document.publication_date,
                    detected_at=now, change_type=status, summary=self._summary(status),
                    previous_version_id=previous.version_id if previous else None, new_version_id=version.version_id,
                    materiality=interpretation.materiality, affected_entities=self._entities(text),
                    affected_requirements=interpretation.affected_requirements, affected_processes=self._processes(text),
                    evidence_chunk_ids=chunk_ids, source_url=document.canonical_url, diff=diff,
                    citation_valid=bool(chunk_ids),
                    regulatory_fact=interpretation.change_summary,
                    potential_operational_impact=(", ".join(self._processes(text)) + " may need compliance review."
                                                  if self._processes(text) else ""),
                )
                if self.store.add_update_once(update):
                    updates.append(update)
                    if update.materiality in {Materiality.MEDIUM, Materiality.HIGH} and self.store.mark_alerted(update.update_id):
                        self.alert_sender.send_regulatory_alert(update)
        except Exception as exc:
            check = SourceCheck(run_id=run_id, source_id=source.source_id, checked_at=now,
                                status=MonitoringRunStatus.PARTIAL_FAILURE, discovered_count=len(discovered),
                                changes_detected=len(updates), error=str(exc))
            self.store.add_check(check)
            return check, updates

        check = SourceCheck(run_id=run_id, source_id=source.source_id, checked_at=now,
                            status=MonitoringRunStatus.CHANGES_DETECTED if updates else MonitoringRunStatus.NO_CHANGES,
                            discovered_count=len(discovered), changes_detected=len(updates))
        self.store.add_check(check)
        return check, updates

    @staticmethod
    def _is_lending_relevant(title: str, topics: list[str]) -> bool:
        haystack = title.lower()
        return any(topic.lower() in haystack for topic in topics) or any(
            term in haystack for term in ("loan", "lending", "credit", "nbfc", "borrower", "penal")
        )

    @staticmethod
    def _summary(status: DiscoveryStatus) -> str:
        return ("New lending-relevant RBI document detected; awaiting evidence-backed interpretation."
                if status is DiscoveryStatus.NEW else
                "A previously monitored RBI document changed; deterministic differences are attached for review.")

    @staticmethod
    def _materiality(status: DiscoveryStatus, diff: object) -> Materiality:
        if status is DiscoveryStatus.NEW:
            return Materiality.MEDIUM
        return Materiality.HIGH if diff and (diff.changed_numbers or diff.changed_dates) else Materiality.MEDIUM

    @staticmethod
    def _entities(text: str) -> list[str]:
        candidates = ["NBFCs", "Banks", "Regulated Entities", "Borrowers"]
        return [item for item in candidates if re.search(rf"\b{re.escape(item.rstrip('s'))}", text, re.I)]

    @staticmethod
    def _processes(text: str) -> list[str]:
        mapping = {"disclose": "loan agreements", "penal": "pricing", "recovery": "collections", "kfs": "Key Fact Statements"}
        return [process for signal, process in mapping.items() if signal in text.lower()]
