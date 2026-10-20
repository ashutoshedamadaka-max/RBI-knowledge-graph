"""The rule that decides whether a successor may become current without a person.

Automation may remove trust on its own; it adds trust only on explicit official evidence.
A link is auto-trusted only when every condition below holds. Anything else waits for a
person, with the failed conditions listed as the reasons.
"""

from dataclasses import dataclass
from urllib.parse import urlsplit

from app.models.documents import DocumentLifecycle, DocumentMetadata
from app.models.links import LinkRelation, LinkScope, LinkTrust

# Methods that read an explicit statement of repeal or supersession. A re-issue or a
# similarity match is never one of them.
EXPLICIT_METHODS = frozenset({"repeal_annex", "repeal_sentence", "supersession_sentence", "superseded_by_statement"})
RBI_DOMAIN = "rbi.org.in"
NON_OPERATIVE = frozenset({DocumentLifecycle.WITHDRAWN, DocumentLifecycle.REPEALED, DocumentLifecycle.SUPERSEDED})


@dataclass(frozen=True)
class TrustDecision:
    trust: LinkTrust
    reasons: list[str]


def is_rbi_owned(url: str | None) -> bool:
    host = (urlsplit(url or "").hostname or "").lower()
    return host == RBI_DOMAIN or host.endswith("." + RBI_DOMAIN)


def decide_trust(
    *, relation: LinkRelation, scope: LinkScope, method: str, evidence_quote: str,
    new: DocumentMetadata, old: DocumentMetadata, matched_old_count: int, auto_trust_enabled: bool,
) -> TrustDecision:
    failed: list[str] = []
    if not auto_trust_enabled:
        failed.append("automatic trust is switched off")
    if relation is not LinkRelation.SUPERSEDES:
        failed.append(f"a {relation.value.lower()} link does not replace the old document and needs review")
    if scope is not LinkScope.WHOLE:
        failed.append("only part of the old document is repealed")
    if method not in EXPLICIT_METHODS:
        failed.append(f"'{method}' is not an explicit statement of repeal or supersession")
    if not evidence_quote.strip():
        failed.append("no quoted evidence")
    if matched_old_count != 1:
        failed.append(f"the statement matches {matched_old_count} documents in the corpus, not exactly one")
    if not is_rbi_owned(new.source_url) or not is_rbi_owned(old.source_url):
        failed.append("a document is not on an RBI-owned domain")
    if not new.publication_date or not old.publication_date:
        failed.append("an issue date is missing")
    elif new.publication_date <= old.publication_date:
        failed.append("the new document was not issued after the old one")
    if new.lifecycle in NON_OPERATIVE:
        failed.append(f"RBI marks the new document {new.lifecycle.value.lower()}")
    if new.document_id == old.document_id:
        failed.append("a document cannot replace itself")
    if failed:
        return TrustDecision(LinkTrust.REVIEW_REQUIRED, failed)
    return TrustDecision(LinkTrust.AUTO_TRUSTED, [
        "explicit statement of repeal or supersession, quoted",
        "both documents on an RBI-owned domain",
        "the new document was issued after the old one",
        "the statement matches exactly one corpus document",
    ])
