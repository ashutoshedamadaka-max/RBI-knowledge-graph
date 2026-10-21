"""Three ways to cut an RBI document into chunks, behind one function (Phase 2).

- fixed: about 500-token windows with 50 tokens of overlap, ignoring structure.
- recursive: split at headings, then at line breaks, then at sentence ends, packing up to 500 tokens.
- structure: one chunk per numbered paragraph (RBI's own unit), with its heading path prepended;
  tables are never split; paragraphs over 600 tokens split at sub-item boundaries; paragraphs
  under 100 tokens merge with the next paragraph in the same section.

Every chunk ID is built from document + page + position (paragraph number for structure), so
it is stable when the same document is chunked again.
"""

import hashlib
import re
from dataclasses import dataclass, field
from functools import lru_cache

from app.corpus.identifiers import find_references
from app.models.chunks import ChunkMetadata
from app.models.documents import DocumentLifecycle, DocumentMetadata

FIXED_TOKENS, FIXED_OVERLAP = 500, 50
RECURSIVE_TOKENS = 500
STRUCTURE_MIN, STRUCTURE_MAX = 100, 600

_PAGE_NUMBER = re.compile(r"\s*\d{1,3}\s*$")
_CHAPTER = re.compile(r"\s*(?:Chapter|CHAPTER|Part|PART)\s+[IVXLC\d]+\b.{0,120}$")
_SECTION = re.compile(r"\s*[A-Z]\.\s+[A-Z][^.]{2,110}$")
# "Schedule" is a heading only when numbered: "Schedule of charges" is a caption.
_ANNEX = re.compile(r"\s*(?:(?:Annex|Annexure|Appendix)(?:\s*[-–]?\s*[IVXLC\d]+)?|Schedule\s*[-–]?\s*[IVXLC\d]+)\b.{0,150}$",
                    re.IGNORECASE)
_PARAGRAPH = re.compile(r"\s*(\d{1,3})\.(?!\d)\s*(?=\S)")
_SUB_ITEM = re.compile(r"\s*(?:\((?:\d{1,3}|[ivxlc]{1,6}|[a-z])\)|\d{1,2}(?:\.\d{1,2}){1,3}\.?)\s")
_CONTENTS = re.compile(r"\s*(?:table\s+of\s+contents|contents|index)\s*", re.IGNORECASE)
_TABLE_CELL_CHARS, _TABLE_MIN_RUN = 40, 6
_LIST_MARKER = re.compile(r"\s*\((?:\d{1,3}|[ivxlc]{1,6}|[a-z])\)\s*")
_CELL_VALUE = re.compile(r"\s*(?:\d{1,3}\.?|\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|[\d,.]+%?)\s*")
_FOOTNOTE = re.compile(r"\s*\[\^(\d{1,3})\]:")  # written by the PDF parser at the end of a page
_TOC_LEADER = re.compile(r"\.{4,}\s*\d+\s*$")


@lru_cache(maxsize=1)
def _encoding():
    import tiktoken

    return tiktoken.get_encoding("cl100k_base")  # the tokenizer of text-embedding-3-small


def count_tokens(text: str) -> int:
    return len(_encoding().encode(text))


@dataclass
class Unit:
    """A run of document lines: a numbered paragraph, or text under a heading before one."""

    label: str
    heading_path: tuple[str, ...]
    page: int
    lines: list[str] = field(default_factory=list)


def page_lines(pages: list[str]) -> list[tuple[int, str]]:
    """Non-empty lines with their page number, without the printed page number at the top."""
    numbered = []
    for page_number, text in enumerate(pages, start=1):
        lines = [line.rstrip() for line in text.splitlines() if line.strip()]
        if lines and _PAGE_NUMBER.fullmatch(lines[0]):
            lines = lines[1:]
        numbered.extend((page_number, line) for line in lines)
    return numbered


def _entry(line: str) -> str:
    """A contents line compared without its dot leaders, page number or letter case."""
    return re.sub(r"\s+", " ", re.sub(r"\.{2,}\s*\d*\s*$", "", line)).strip(" .").lower()


def _contents_range(numbered: list[tuple[int, str]], longest: int = 400) -> tuple[int, int] | None:
    """Lines of a table of contents: from its heading to the first line that repeats an entry.

    The body starts where an entry appears again ("Chapter I – Preliminary", "1. GENERAL"). With no
    repeat within ``longest`` lines the "Contents" line was not a table of contents.
    """
    start = next((index for index, (_, line) in enumerate(numbered) if _CONTENTS.fullmatch(line)), None)
    if start is None:
        return None
    entries: set[str] = set()
    for index in range(start + 1, min(len(numbered), start + 1 + longest)):
        entry = _entry(numbered[index][1])
        if entry in entries and len(entry) > 3:
            return start, index
        entries.add(entry)
    return None


def segment(pages: list[str]) -> list[Unit]:
    """Split a document into RBI's own units: numbered paragraphs under their headings.

    A line counts as a new paragraph only when its number follows the previous one (3 after 2),
    so table cells and cross-references such as "1." inside a list are not mistaken for one.
    """
    units: list[Unit] = []
    chapter: str | None = None
    section: str | None = None
    expected: int | None = None
    current: Unit | None = None

    def path() -> tuple[str, ...]:
        return tuple(item for item in (chapter, section) if item)

    numbered = page_lines(pages)
    contents = _contents_range(numbered)
    for index, (page, line) in enumerate(numbered):
        stripped = line.strip()
        if contents and contents[0] <= index < contents[1]:
            # Contents entries look like headings and paragraphs; keep them as one text block.
            if index == contents[0]:
                units.append(Unit(label="contents", heading_path=(), page=page))
            units[-1].lines.append(stripped)
            current = None
            continue
        footnote = _FOOTNOTE.match(line)
        if footnote:
            # Attach the footnote (RBI's amendment history) to the paragraph that carries its marker.
            marker = f"[^{footnote.group(1)}]"
            owner = next((unit for unit in reversed(units) if any(marker in text for text in unit.lines)), current)
            if owner is not None:
                owner.lines.append(stripped)
                continue
        if _TOC_LEADER.search(line):  # a table-of-contents entry, not the heading itself
            if current is None:
                current = Unit(label="text", heading_path=path(), page=page)
                units.append(current)
            current.lines.append(stripped)
            continue
        if _CHAPTER.fullmatch(line) and len(stripped) < 130:
            chapter, section, current = stripped, None, None
            continue
        if _ANNEX.fullmatch(line) and len(stripped) < 160:
            chapter, section, current, expected = stripped, None, None, None
            continue
        if _SECTION.fullmatch(line) and not _PARAGRAPH.match(line):
            section, current = stripped, None
            continue
        number = _PARAGRAPH.match(line)
        if number and (expected is None or int(number.group(1)) == expected):
            current = Unit(label=number.group(1), heading_path=path(), page=page, lines=[stripped])
            units.append(current)
            expected = int(number.group(1)) + 1
            continue
        if current is None:
            current = Unit(label="text", heading_path=path(), page=page)
            units.append(current)
        current.lines.append(stripped)
    return [unit for unit in units if unit.lines]


def _cell(line: str) -> bool:
    """A table cell as extracted text shows it: short, or a circular number or a date on its own."""
    if _LIST_MARKER.fullmatch(line):  # "(19)" alone on a line starts a list item, not a cell
        return False
    return len(line) <= _TABLE_CELL_CHARS or bool(_CELL_VALUE.fullmatch(line)) or bool(find_references(line)) \
        and len(line) <= 60


def _table_runs(lines: list[str]) -> list[tuple[int, int]]:
    """Line ranges that look like a table: one cell per line, many in a row.

    A single longer cell (a subject, up to 120 characters) may sit between cells; wrapped prose
    lines (80-95 characters each) never form a run because most of a run must be cells.
    """
    cells = [_cell(line) for line in lines]
    runs, index = [], 0
    while index < len(lines):
        if not cells[index]:
            index += 1
            continue
        end = index
        while end < len(lines) and (cells[end] or (
                len(lines[end]) <= 120 and end + 1 < len(lines) and cells[end + 1] and cells[end - 1])):
            end += 1
        if end - index >= _TABLE_MIN_RUN and sum(cells[index:end]) >= 0.6 * (end - index):
            runs.append((index, end))
        index = max(end, index + 1)
    return runs


def _blocks(lines: list[str]) -> list[list[str]]:
    """A paragraph's sub-items, with each table (and the line before it, its caption) kept whole."""
    protected = set()
    for start, end in _table_runs(lines):
        protected.update(range(max(0, start - 1), end))
    blocks: list[list[str]] = []
    for index, line in enumerate(lines):
        starts_block = _SUB_ITEM.match(line) and index not in protected
        if not blocks or starts_block:
            blocks.append([line])
        else:
            blocks[-1].append(line)
    return blocks


def _fit(block: list[str], limit: int = STRUCTURE_MAX) -> list[list[str]]:
    """Split a block over the maximum at line boundaries; a table repeats its caption in each part."""
    if count_tokens("\n".join(block)) <= limit:
        return [block]
    # The caption is the line just above the table's first value (a number, date or circular number).
    first_value = next((index for index, line in enumerate(block)
                        if _CELL_VALUE.fullmatch(line) or find_references(line)), None) if _table_runs(block) else None
    caption = block[first_value - 1:first_value] if first_value else []
    parts, packed = [], []
    for line in block:
        while count_tokens(line) > limit:  # one enormous line: cut by tokens
            encoded = _encoding().encode(line)
            parts.append(caption + [_encoding().decode(encoded[:limit - 20])])
            line = _encoding().decode(encoded[limit - 20:])
        if packed and count_tokens("\n".join(packed + [line])) > limit:
            parts.append(packed)
            packed = list(caption)
        packed.append(line)
    if packed:
        parts.append(packed)
    return parts


def _chunk(document: DocumentMetadata, page: int, position: str, text: str, chunker: str, ordinal: int,
           heading_path: str | None = None, paragraph_ref: str | None = None, parent_id: str | None = None
           ) -> ChunkMetadata:
    identity = f"{document.document_id}:{page}:{chunker}:{position}"
    return ChunkMetadata(
        chunk_id=f"chunk_{hashlib.sha256(identity.encode()).hexdigest()[:20]}",
        document_id=document.document_id, document_title=document.title, page_number=page, chunk_index=ordinal,
        text=text, source_url=document.source_url, document_version=document.document_version,
        is_current=document.is_current, lifecycle=document.lifecycle,
        authority_current=document.lifecycle in {DocumentLifecycle.ACTIVE, DocumentLifecycle.AMENDED},
        valid_from=document.valid_from, valid_to=document.valid_to,
        in_force_from=document.in_force_from, in_force_to=document.in_force_to,
        heading_path=heading_path, paragraph_ref=paragraph_ref, token_count=count_tokens(text),
        parent_id=parent_id, chunker=chunker,
    )


def _heading_tokens(heading_path: tuple[str, ...]) -> int:
    return count_tokens(f"[{' > '.join(heading_path)}]\n") if heading_path else 0


def chunk_structure(document: DocumentMetadata, pages: list[str]) -> list[ChunkMetadata]:
    pieces: list[tuple[Unit, str, list[str]]] = []  # (unit, part label, lines)
    for unit in segment(pages):
        limit = STRUCTURE_MAX - _heading_tokens(unit.heading_path)  # the prepended heading counts too
        if count_tokens("\n".join(unit.lines)) <= limit:
            pieces.append((unit, "", unit.lines))
            continue
        # Each footnote joins the block that carries its marker before packing, so it counts
        # toward the size limit and stays beside the text it annotates.
        blocks = _blocks([line for line in unit.lines if not _FOOTNOTE.match(line)])
        for note in (line for line in unit.lines if _FOOTNOTE.match(line)):
            marker = note.split(":", 1)[0].strip()
            found = next(((block, index) for block in blocks for index, line in enumerate(block) if marker in line), None)
            if found:  # right after the marked line, so a split cannot separate them
                found[0].insert(found[1] + 1, note)
            else:
                blocks[-1].append(note)
        part, packed = 1, []
        for block in (piece for block in blocks for piece in _fit(block, limit)):
            if packed and count_tokens("\n".join(packed + block)) > limit:
                pieces.append((unit, f"part{part}", packed))
                part, packed = part + 1, []
            packed = packed + block
        if packed:
            pieces.append((unit, f"part{part}" if part > 1 else "", packed))

    # Merge short pieces forward within the same heading path, up to the minimum size.
    merged: list[tuple[Unit, str, list[str], list[str]]] = []  # (first unit, part, labels, lines)
    for unit, part, lines in pieces:
        previous = merged[-1] if merged else None
        if (previous and previous[0].heading_path == unit.heading_path and not part and not previous[1]
                and count_tokens("\n".join(previous[3])) < STRUCTURE_MIN
                and count_tokens("\n".join(previous[3] + lines)) <= STRUCTURE_MAX - _heading_tokens(unit.heading_path)):
            previous[2].append(unit.label)
            previous[3].extend(lines)
            continue
        merged.append((unit, part, [unit.label], list(lines)))

    chunks, seen = [], {}
    for ordinal, (unit, part, labels, lines) in enumerate(merged):
        heading = " > ".join(unit.heading_path) or None
        paragraph_ref = "–".join(dict.fromkeys([labels[0], labels[-1]])) + (f" ({part})" if part else "")
        text = (f"[{heading}]\n" if heading else "") + "\n".join(lines)
        parent = f"{document.document_id}:{heading or 'document'}"
        # Heading path + paragraph identifies a chunk; a repeat (text blocks, annexes restarting
        # their numbering) gets an occurrence number, which is still the same on every re-run.
        position = f"{heading}|{paragraph_ref}"
        seen[position] = seen.get(position, 0) + 1
        position += f"#{seen[position]}" if seen[position] > 1 else ""
        chunks.append(_chunk(document, unit.page, position, text, "structure", ordinal,
                             heading_path=heading, paragraph_ref=paragraph_ref,
                             parent_id=hashlib.sha256(parent.encode()).hexdigest()[:20]))
    return chunks


def chunk_fixed(document: DocumentMetadata, pages: list[str]) -> list[ChunkMetadata]:
    """Token windows over the whole document; a chunk's page is where it starts."""
    encoding = _encoding()
    tokens, token_pages = [], []
    for page, line in page_lines(pages):
        line_tokens = encoding.encode(line + "\n")
        tokens.extend(line_tokens)
        token_pages.extend([page] * len(line_tokens))
    chunks, start, ordinal = [], 0, 0
    while start < len(tokens):
        end = min(start + FIXED_TOKENS, len(tokens))
        chunks.append(_chunk(document, token_pages[start], str(ordinal), encoding.decode(tokens[start:end]).strip(),
                             "fixed", ordinal))
        if end == len(tokens):
            break
        start, ordinal = end - FIXED_OVERLAP, ordinal + 1
    return chunks


def chunk_recursive(document: DocumentMetadata, pages: list[str]) -> list[ChunkMetadata]:
    """Headings first, then lines, then sentences; pieces packed up to the size limit."""
    sections: list[list[tuple[int, str]]] = [[]]
    for page, line in page_lines(pages):
        if (_CHAPTER.fullmatch(line) or _ANNEX.fullmatch(line) or _SECTION.fullmatch(line)) and sections[-1]:
            sections.append([])
        sections[-1].append((page, line))
    pieces: list[tuple[int, str]] = []
    for section in sections:
        for page, line in section:
            if count_tokens(line) <= RECURSIVE_TOKENS:
                pieces.append((page, line))
            else:
                pieces.extend((page, sentence) for sentence in re.split(r"(?<=[.;:])\s+", line) if sentence)
        pieces.append((-1, ""))  # section boundary: never pack across it
    chunks, packed, packed_page, ordinal = [], [], None, 0
    for page, piece in pieces:
        boundary = page == -1
        if packed and (boundary or count_tokens("\n".join(packed + [piece])) > RECURSIVE_TOKENS):
            chunks.append(_chunk(document, packed_page, str(ordinal), "\n".join(packed), "recursive", ordinal))
            packed, ordinal = [], ordinal + 1
        if not boundary:
            packed_page = page if not packed else packed_page
            packed.append(piece)
    return chunks


CHUNKERS = {"fixed": chunk_fixed, "recursive": chunk_recursive, "structure": chunk_structure}
