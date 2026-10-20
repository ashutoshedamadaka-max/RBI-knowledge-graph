"""Link new RBI documents to the ones they replace, and switch current answers over.

Runs after each monitoring pass and is safe to repeat: links are found again from the
stored text, a decision already made is never reset, and a switch is applied once.

On a trusted SUPERSEDES link the old rule stays in force until the new one takes effect
(its effective date, else its issue date; ADR-010). On that day the old document becomes
SUPERSEDED, its chunks leave current answers, and it remains stored for history.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import date

from app import clock
from app.config.settings import Settings
from app.ingestion.service import IngestionService, NON_OPERATIVE, OfficialStatusError
from app.models.documents import DocumentLifecycle, DocumentMetadata
from app.models.links import DocumentLink, LinkProposal, LinkRelation, LinkScope, LinkTrust
from app.monitoring.link_store import LinkStore, link_id_for
from app.monitoring.successors import candidate_successors, find_backward_links, find_forward_links, match_documents
from app.monitoring.trust import decide_trust

logger = logging.getLogger(__name__)
TRUSTED = {LinkTrust.AUTO_TRUSTED, LinkTrust.APPROVED}
_REVIEWABLE_STATUS = {DocumentLifecycle.REVIEW_REQUIRED, DocumentLifecycle.UNKNOWN}


@dataclass
class LinkingSummary:
    links_created: int = 0
    auto_trusted: int = 0
    review_required: int = 0
    switches_applied: int = 0
    failures: list[str] = field(default_factory=list)


class LinkingService:
    def __init__(self, ingestion: IngestionService, settings: Settings) -> None:
        self.ingestion = ingestion
        self.settings = settings
        self.store = LinkStore(settings.runtime_dir / "document_links.json")

    def reconcile(self) -> LinkingSummary:
        """Find links for every document, decide trust, and apply switches that are due."""
        summary = LinkingSummary()
        documents = self.ingestion.list_documents()  # the latest version of each page
        for document in documents:
            try:
                self._link_document(document, documents, summary)
            except Exception as exc:  # one unreadable document must not stop the others
                logger.exception("successor_linking_failed document_id=%s", document.document_id)
                summary.failures.append(f"{document.document_id}: {exc}")
        for link in self.store.all():
            if link.trust in TRUSTED and self._apply_switch(link):
                summary.switches_applied += 1
        return summary

    def approve(self, link_id: str, evidence_url: str, excerpt: str) -> DocumentLink:
        """A reviewer confirms a suggested link; a candidate becomes a whole replacement."""
        link = self._require(link_id)
        new = self.ingestion.get(link.new_document_id)
        if new and new.lifecycle in NON_OPERATIVE:
            raise OfficialStatusError(f"RBI marks the new document {new.lifecycle.value.lower()}; it cannot replace another.")
        relation = LinkRelation.SUPERSEDES if link.relation is LinkRelation.CANDIDATE else link.relation
        scope = LinkScope.WHOLE if link.relation is LinkRelation.CANDIDATE else link.scope
        link = link.model_copy(update={
            "relation": relation, "scope": scope, "trust": LinkTrust.APPROVED, "decided_by": "ADMIN_REVIEW",
            "decided_at": clock.now(), "reviewer_evidence_url": evidence_url, "reviewer_excerpt": excerpt,
        })
        self.store.replace(link)
        self._apply_switch(link)
        return link

    def reject(self, link_id: str) -> DocumentLink:
        """Undo a link's effect. Trust it added is removed; nothing becomes active by rejection."""
        link = self._require(link_id)
        was_trusted = link.trust in TRUSTED
        link = link.model_copy(update={"trust": LinkTrust.REJECTED, "decided_by": "ADMIN_REVIEW", "decided_at": clock.now()})
        self.store.replace(link)
        if was_trusted and link.relation is LinkRelation.SUPERSEDES:
            self._revert_switch(link)
        return link

    # Finding links

    def _link_document(self, document: DocumentMetadata, documents: list[DocumentMetadata], summary: LinkingSummary) -> None:
        text = self._text(document)
        if not text:
            return
        own = frozenset(document.circular_numbers)
        for proposal in find_forward_links(text, own):
            targets = [item for item in match_documents(proposal, documents) if item.document_id != document.document_id]
            for old in targets:
                self._record(proposal, old=old, new=document, matched_old_count=len(targets), summary=summary)
        for proposal in find_backward_links(text):
            targets = [item for item in match_documents(proposal, documents) if item.document_id != document.document_id]
            for new in targets:
                self._record(proposal, old=document, new=new, matched_old_count=1 if len(targets) == 1 else len(targets),
                             summary=summary)
        # A replaced document with no explicit statement gets reviewable suggestions only.
        if document.lifecycle in NON_OPERATIVE and not self.store.for_old(document.document_id):
            for new, similarity in candidate_successors(document, documents)[:3]:
                proposal = LinkProposal(
                    relation=LinkRelation.CANDIDATE, scope=LinkScope.WHOLE, method="candidate_title_similarity",
                    evidence_quote=f"Same department, issued later, title similarity {similarity}: “{document.title}” → “{new.title}”",
                )
                self._record(proposal, old=document, new=new, matched_old_count=1, summary=summary)

    def _record(self, proposal: LinkProposal, *, old: DocumentMetadata, new: DocumentMetadata, matched_old_count: int,
                summary: LinkingSummary) -> None:
        decision = decide_trust(
            relation=proposal.relation, scope=proposal.scope, method=proposal.method,
            evidence_quote=proposal.evidence_quote, new=new, old=old,
            matched_old_count=matched_old_count, auto_trust_enabled=self.settings.auto_trust_enabled,
        )
        link = DocumentLink(
            link_id=link_id_for(proposal.relation.value, old.document_id, new.document_id, proposal.method),
            relation=proposal.relation, scope=proposal.scope, old_document_id=old.document_id,
            new_document_id=new.document_id, method=proposal.method, evidence_quote=proposal.evidence_quote,
            evidence_url=(new.source_url if proposal.evidence_in == "new" else old.source_url),
            evidence_in=proposal.evidence_in, trust=decision.trust, trust_reasons=decision.reasons,
            created_at=clock.now(), decided_at=clock.now() if decision.trust is LinkTrust.AUTO_TRUSTED else None,
        )
        link, created = self.store.add_if_new(link)
        if created:
            summary.links_created += 1
            summary.auto_trusted += link.trust is LinkTrust.AUTO_TRUSTED
            summary.review_required += link.trust is LinkTrust.REVIEW_REQUIRED
            self.ingestion.graph_service.store.set_document_link(
                link.link_id, old.document_id, old.title, new.document_id, new.title,
                link.relation.value, link.evidence_quote, link.trust.value,
            )

    # Switching over

    def _apply_switch(self, link: DocumentLink) -> bool:
        """Make the successor current and end the old rule on the successor's in-force date."""
        if link.relation is not LinkRelation.SUPERSEDES or link.scope is not LinkScope.WHOLE:
            return False
        old, new = self.ingestion.get(link.old_document_id), self.ingestion.get(link.new_document_id)
        if not old or not new or new.lifecycle in NON_OPERATIVE:
            return False
        method = "AUTO_SUCCESSOR" if link.trust is LinkTrust.AUTO_TRUSTED else "ADMIN_REVIEW"
        now = clock.now()
        changed = False
        if new.lifecycle in _REVIEWABLE_STATUS:
            self.ingestion.set_lifecycle(new.document_id, DocumentLifecycle.ACTIVE, link.evidence_url or new.source_url or "",
                                         link.evidence_quote, now, method)
            changed = True
        switch_day: date | None = new.in_force_from or new.effective_date or new.publication_date
        if switch_day and old.in_force_to != switch_day and (old.in_force_to is None or switch_day < old.in_force_to):
            self.ingestion.set_in_force(old.document_id, old.in_force_from, switch_day)
            self.ingestion.manifest.set_fields(old.document_id, successor_document_id=new.document_id)
            changed = True
        old = self.ingestion.get(old.document_id)
        due = switch_day is None or switch_day <= now.date()
        if due and old.lifecycle in {DocumentLifecycle.ACTIVE, DocumentLifecycle.AMENDED, *_REVIEWABLE_STATUS}:
            self.ingestion.set_lifecycle(old.document_id, DocumentLifecycle.SUPERSEDED, link.evidence_url or "",
                                         link.evidence_quote, now, method)
            self.ingestion.mark_document_not_current(old.document_id, now.isoformat())
            changed = True
        return changed

    def _revert_switch(self, link: DocumentLink) -> None:
        old, new = self.ingestion.get(link.old_document_id), self.ingestion.get(link.new_document_id)
        now = clock.now()
        if old:
            self.ingestion.set_in_force(old.document_id, old.in_force_from, None)
            self.ingestion.manifest.set_fields(old.document_id, successor_document_id=None)
            if old.lifecycle is DocumentLifecycle.SUPERSEDED and old.status_evidence_excerpt == link.evidence_quote:
                self.ingestion.set_lifecycle(old.document_id, DocumentLifecycle.REVIEW_REQUIRED, old.source_url or "",
                                             "A reviewer rejected the successor link that superseded this document.", now,
                                             "ADMIN_REVIEW")
                self.ingestion.mark_document_current(old.document_id)
        if new and new.status_resolution_method in {"AUTO_SUCCESSOR", "ADMIN_REVIEW"} and new.status_evidence_excerpt == link.evidence_quote:
            self.ingestion.set_lifecycle(new.document_id, DocumentLifecycle.REVIEW_REQUIRED, new.source_url or "",
                                         "A reviewer rejected the successor link that made this document current.", now,
                                         "ADMIN_REVIEW")
        if old and new:
            self.ingestion.graph_service.store.set_document_link(
                link.link_id, old.document_id, old.title, new.document_id, new.title,
                link.relation.value, link.evidence_quote, LinkTrust.REJECTED.value, present=False,
            )

    def _require(self, link_id: str) -> DocumentLink:
        link = self.store.get(link_id)
        if link is None:
            raise KeyError(link_id)
        return link

    def _text(self, document: DocumentMetadata) -> str:
        processed = self.ingestion.settings.processed_dir / f"{document.document_id}.json"
        if processed.exists():
            return "\n".join(page["text"] for page in json.loads(processed.read_text(encoding="utf-8"))["pages"])
        return "\n".join(chunk.text for chunk in self.ingestion.vector_store.get_by_document_id(document.document_id))
