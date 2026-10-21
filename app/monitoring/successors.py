"""Find what a document says about the documents it replaces, amends or is replaced by.

Only explicit statements become links, and only inside the wording RBI uses for them:
a repeal annex, a sentence with a repeal or supersession verb, or an old page naming its
replacement. A circular number that is merely cited ("as amended from time to time",
"please refer to ...") is never a link. Every proposal carries an exact quote from the text
it was read from.
"""

import re
from datetime import date

from app.corpus.identifiers import Reference, find_references, parse_date
from app.models.documents import DocumentMetadata
from app.models.links import LinkProposal, LinkRelation, LinkScope

_ANNEX_HEADING = re.compile(
    r"Annex(?:ure)?\s*[-–]?\s*[IVX\d]+\s*:?\s*List of (?:circulars|instructions|directions|master directions)[^\n]*repeal[^\n]*",
    re.IGNORECASE,
)
_TABLE_HEADER_LINES = {"s.no.", "sr. no.", "sr.no.", "circular no.", "circular number", "date", "subject", "sl. no.", ""}
_INDEX_LINE = re.compile(r"\s*\d+\.\s*$")
_DATE_LINE = re.compile(r"\s*\d{2}[./]\d{2}[./]\d{4}\s*$")
_MAX_LINES_BEFORE_DATE = 4

# A repeal or supersession verb. Self-referring wording ("this circular stands withdrawn")
# carries no reference number and so produces no proposal here.
_REPEAL_VERB = re.compile(
    r"\bstands?\s+(?:repealed|withdrawn|superseded)\b|\b(?:are|is|be|stand)\s+hereby\s+(?:repealed|withdrawn|superseded)\b"
    r"|\bhereby\s+(?:repeals?|supersedes?|withdraws?)\b|\bin\s+supersession\s+of\b|\bsupersed(?:e|es|ing)\b|\brepeals?\b",
    re.IGNORECASE,
)
_PARTIAL = re.compile(
    r"\b(?:paragraphs?|paras?|clauses?|sub-clauses?|sections?|chapters?|annex(?:ure)?s?|items?)\b[^.\n]{0,40}\b(?:of|in|from)\b",
    re.IGNORECASE,
)
_NEW_PARAGRAPH = re.compile(r"\s*\d+\.\s+[A-Z]")
_MESSENGER = re.compile(
    r"\b(?:communicated|notified|announced|conveyed|advised)\s+(?:vide|in|through|by)\s+(?:the\s+)?(?:RBI\s+)?"
    r"(?:circular|notification|press\s+release)?\s*(?:no\.?)?\s*$",
    re.IGNORECASE,
)
_WINDOW_LINES = 4

_BACKWARD = re.compile(
    r"\bthis\s+(?:circular|master\s+circular|master\s+direction|directions?|document)\b[^.\n]{0,100}?"
    r"\b(?:superseded|replaced)\s+(?:by|with)\b(?P<tail>[^\n]{0,300})",
    re.IGNORECASE,
)
# RBI's banner on a repealed page: "The Circular has been repealed. Please refer to <title> dated <date>."
_REPEAL_BANNER = re.compile(
    r"\b(?:the|this)\s+(?:circular|master\s+circular|master\s+direction|directions?|notification)\s+has\s+been\s+"
    r"(?:repealed|withdrawn|superseded)\.?\s*please\s+refer\s+to\s+(?P<tail>[^\n]{0,300})",
    re.IGNORECASE,
)
_REISSUE = re.compile(r"Please refer to the Master Circular\b", re.IGNORECASE)
_AMENDMENT_BASE = re.compile(r"Please refer to\s+(?:the\s+)?(?P<title>[^\n]{10,300}?)\s*\(hereinafter[^)\n]*\)", re.IGNORECASE)
_UPDATED_SUFFIX = re.compile(r"\s*\((?:updated|as updated)[^)]*\)\s*$", re.IGNORECASE)
_HEADER_CHARS = 3000


def find_forward_links(text: str, own_references: frozenset[str] = frozenset()) -> list[LinkProposal]:
    """Links read from the new document: what it repeals, supersedes, amends or re-issues.

    ``own_references`` are the document's own numbers, which can never be a repeal target.
    """
    proposals = _repeal_annex_rows(text) + _repeal_sentences(text, own_references)
    proposals += _amendment_base(text) + _master_circular_reissue(text)
    return proposals


def find_backward_links(text: str) -> list[LinkProposal]:
    """Links read from the old page, which names its own replacement."""
    proposals = []
    matches = sorted([*_BACKWARD.finditer(text), *_REPEAL_BANNER.finditer(text)], key=lambda match: match.start())
    for match in matches:
        tail = match.group("tail")
        tail_start = match.start("tail")
        references = find_references(tail)
        if not references and not tail.strip():
            continue
        named = re.split(r"\.\s|\.$", tail)[0]
        end = tail_start + (references[-1].end if references else len(named))
        # "Reserve Bank of India (Digital Lending) Directions, 2025 dated May 8, 2025"
        title, _, dated = named.partition(" dated ")
        proposals.append(LinkProposal(
            relation=LinkRelation.SUPERSEDES, scope=LinkScope.WHOLE, method="superseded_by_statement",
            evidence_quote=text[match.start():end].strip(), evidence_in="old",
            target_references=[item.key for item in references],
            target_date=_date_after(tail, references[0]) if references else parse_date(dated),
            target_title=None if references else title.strip(" .:;")[:200] or None,
        ))
    return proposals


def _repeal_annex_rows(text: str) -> list[LinkProposal]:
    proposals: list[LinkProposal] = []
    for heading in _ANNEX_HEADING.finditer(text):
        proposals.extend(_parse_annex_table(text, heading.end()))
    return proposals


def _parse_annex_table(text: str, start: int) -> list[LinkProposal]:
    """Rows of ``index / numbers / date / subject``; the table ends at the first non-row line.

    Footnotes follow the table on RBI pages and cite other circulars, so reading stops
    as soon as a line does not continue the table.
    """
    lines = []
    offset = start
    for line in text[start:].splitlines(keepends=True):
        lines.append((offset, line))
        offset += len(line)
    position = 0
    while position < len(lines) and lines[position][1].strip().lower() in _TABLE_HEADER_LINES:
        position += 1
    proposals = []
    while position < len(lines) and _INDEX_LINE.match(lines[position][1]):
        position += 1
        reference_lines = []
        while position < len(lines) and not _DATE_LINE.match(lines[position][1]):
            if len(reference_lines) >= _MAX_LINES_BEFORE_DATE or _INDEX_LINE.match(lines[position][1]):
                return proposals
            reference_lines.append(lines[position])
            position += 1
        if position >= len(lines) or not reference_lines:
            return proposals
        date_text = lines[position][1]
        position += 1
        subject = lines[position] if position < len(lines) else None
        if subject is None or _INDEX_LINE.match(subject[1]) or not subject[1].strip():
            return proposals
        position += 1
        row_start = reference_lines[0][0] + (len(reference_lines[0][1]) - len(reference_lines[0][1].lstrip()))
        row_end = subject[0] + len(subject[1].rstrip())
        references = find_references("".join(line for _, line in reference_lines))
        proposals.append(LinkProposal(
            relation=LinkRelation.SUPERSEDES, scope=LinkScope.WHOLE, method="repeal_annex",
            evidence_quote=text[row_start:row_end],
            target_references=[item.key for item in references], target_date=parse_date(date_text),
            target_title=subject[1].strip(),
        ))
        while position < len(lines) and not lines[position][1].strip():
            position += 1
    return proposals


def _repeal_sentences(text: str, own_references: frozenset[str]) -> list[LinkProposal]:
    proposals: list[LinkProposal] = []
    lines = []
    offset = 0
    for line in text.splitlines(keepends=True):
        lines.append((offset, line))
        offset += len(line)
    used: set[int] = set()
    for index, (line_start, line) in enumerate(lines):
        verb = _REPEAL_VERB.search(line)
        if not verb or index in used:
            continue
        window_end = _window_end(lines, index)
        first_line = _window_start(lines, index)
        window_start = lines[first_line][0]
        window_stop = lines[window_end - 1][0] + len(lines[window_end - 1][1])
        window = text[window_start:window_stop]
        # The document's own header numbers are not targets of its repeal sentence, and nor is
        # a circular that only announced the repeal ("stand repealed, as communicated vide
        # circular DOR.RRC.REC.302/...").
        references = [
            item for item in find_references(window)
            if item.key not in own_references and not _MESSENGER.search(window[max(0, item.start - 60):item.start])
        ]
        if not references:
            continue
        before_first = window[max(0, references[0].start - 120):references[0].start]
        before_verb = window[:verb.start()][-120:]
        partial = bool(_PARTIAL.search(before_first) or _PARTIAL.search(before_verb))
        method = "supersession_sentence" if re.search(r"supersed", verb.group(0), re.IGNORECASE) else "repeal_sentence"
        for reference_group in _group_adjacent(window, references):
            proposals.append(LinkProposal(
                relation=LinkRelation.SUPERSEDES, scope=LinkScope.PARTIAL if partial else LinkScope.WHOLE,
                method=method, evidence_quote=window.strip(),
                target_references=[item.key for item in reference_group],
                target_date=_date_after(window, reference_group[-1]),
            ))
        used.update(range(first_line, window_end))
    return proposals


def _window_start(lines: list[tuple[int, str]], index: int) -> int:
    """First line of the sentence: a previous line that does not end a sentence belongs to it."""
    start = index
    while start > 0 and index - start < 2:
        previous = lines[start - 1][1].rstrip()
        if not previous or previous.endswith((".", ";", ":")) or _NEW_PARAGRAPH.match(lines[start][1]):
            break
        start -= 1
    return start


def _window_end(lines: list[tuple[int, str]], index: int) -> int:
    """Line after the repeal sentence: its own line, plus list items it introduces or its wrapped rest.

    A sentence that ends on its own line stays on that line, so an unrelated citation in the
    next paragraph or list item can never become a repeal target.
    """
    first = lines[index][1].rstrip()
    introduces_list = first.endswith(":")
    if not introduces_list and first.endswith((".", ";")):
        return index + 1
    end = index + 1
    while end < min(len(lines), index + _WINDOW_LINES + 3):
        following = lines[end][1]
        if not following.strip() or _NEW_PARAGRAPH.match(following):
            break
        end += 1
        if not introduces_list and following.rstrip().endswith((".", ";", ":")):
            break
    return end


def _group_adjacent(window: str, references: list[Reference]) -> list[list[Reference]]:
    """Numbers printed side by side (an RBI number then its department number) name one document."""
    groups: list[list[Reference]] = []
    for item in references:
        if groups and not window[groups[-1][-1].end:item.start].strip(" \t\r\n,;/"):
            groups[-1].append(item)
        else:
            groups.append([item])
    return groups


def _date_after(text: str, reference: Reference) -> date | None:
    following = text[reference.end:reference.end + 40]
    if re.match(r"\W{0,3}(?:dated|issued on|of)?\s*(?:[A-Z][a-z]+\s+\d{1,2},?\s+\d{4}|\d{2}[./]\d{2}[./]\d{4})", following):
        return parse_date(following)
    return None


def _amendment_base(text: str) -> list[LinkProposal]:
    """An amendment names the document it changes by title ("the Directions")."""
    header = text[:_HEADER_CHARS]
    if not re.search(r"\bAmendment\b", header) or not re.search(r"\bmodif(?:y|ies)\b|\bamend(?:s|ed)?\b", header, re.IGNORECASE):
        return []
    match = _AMENDMENT_BASE.search(header)
    if not match:
        return []
    title = _UPDATED_SUFFIX.sub("", match.group("title")).strip()
    return [LinkProposal(
        relation=LinkRelation.AMENDS, scope=LinkScope.PARTIAL, method="amendment_base",
        evidence_quote=match.group(0), target_title=title,
    )]


def _master_circular_reissue(text: str) -> list[LinkProposal]:
    """A revised Master Circular consolidates the previous year's, without repeal wording: review only."""
    header = text[:_HEADER_CHARS]
    match = _REISSUE.search(header)
    if not match or not re.search(r"\brevised\s+Master\s+Circular\b", header, re.IGNORECASE):
        return []
    references = find_references(header[match.end():match.end() + 200])
    if not references:
        return []
    first = references[0]
    absolute_end = match.end() + first.end
    return [LinkProposal(
        relation=LinkRelation.CANDIDATE, scope=LinkScope.WHOLE, method="master_circular_reissue",
        evidence_quote=header[match.start():absolute_end], target_references=[first.key],
        target_date=_date_after(header[match.end():], first),
    )]


def match_documents(proposal: LinkProposal, documents: list[DocumentMetadata]) -> list[DocumentMetadata]:
    """Corpus documents a proposal refers to: by any printed number, else by exact title."""
    if proposal.target_references:
        wanted = set(proposal.target_references)
        return [item for item in documents if wanted & set(item.circular_numbers)]
    if proposal.target_title:
        wanted_tokens = re.findall(r"[a-z0-9]+", proposal.target_title.lower())
        return [item for item in documents if re.findall(r"[a-z0-9]+", item.title.lower()) == wanted_tokens]
    return []
