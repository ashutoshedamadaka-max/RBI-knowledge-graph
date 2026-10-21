"""Phase 1 answer key: Ashu's decisions, recorded without showing the system's guesses.

Three kinds of question, saved after every answer (stop and resume at any time):
  1. Is each NBFC direction in force on RBI's site today?
  2. For each withdrawn rule: which current NBFC direction now holds it? Picked from a fixed
     alphabetical list; the system's own suggestion is never shown.
  3. For each link read from RBI's own text: does the quoted RBI text repeal that document?

Answers go to data/evaluation/gold/phase1_labels.json, keyed by RBI page address (stable
across re-ingestion). Gold labels never come from system output (brief rule 2).

    python scripts/label_phase1.py --data-dir data/runtime/corpus-v1

To change an answer, clear it and you will be asked again, for example:
    python scripts/label_phase1.py --data-dir data/runtime/corpus-v1 --forget "Id=12472"
"""
import argparse
import json
import sys
import textwrap
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.ingestion.manifest import DocumentManifest  # noqa: E402
from app.models.documents import DocumentLifecycle  # noqa: E402
from app.monitoring.link_store import LinkStore  # noqa: E402
from app.monitoring.linking import _reissued_later  # noqa: E402
from app.monitoring.successors import _ANNEX_HEADING  # noqa: E402

GOLD = ROOT / "data" / "evaluation" / "gold" / "phase1_labels.json"


def ask(prompt: str, allowed) -> str:
    while True:
        answer = input(prompt).strip().lower()
        if allowed(answer):
            return answer
        print("  Please answer as shown in the brackets.")


def show(label: str, text: str) -> None:
    print(textwrap.fill(f"{label}: {text}", width=100, subsequent_indent="    "))


def annex_heading(data_dir: Path, document_id: str, quote: str) -> str | None:
    """The repeal-list heading printed above a quoted table row, if the quote is such a row."""
    processed = data_dir / "processed" / f"{document_id}.json"
    if not processed.exists():
        return None
    text = "\n".join(page["text"] for page in json.loads(processed.read_text(encoding="utf-8"))["pages"])
    position = text.find(quote)
    headings = [match for match in _ANNEX_HEADING.finditer(text) if position != -1 and match.start() < position]
    return headings[-1].group(0).strip() if headings else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--forget", metavar="TEXT", help="Clear answers whose RBI address contains TEXT, to answer again.")
    args = parser.parse_args()
    runtime = args.data_dir / "runtime"
    documents = DocumentManifest(runtime / "documents.json").all()
    by_id = {item.document_id: item for item in documents}
    links = LinkStore(runtime / "document_links.json").all()
    def load() -> dict:
        return json.loads(GOLD.read_text(encoding="utf-8")) if GOLD.exists() else {
            "directions_in_force": {}, "successors": {}, "explicit_links": {}}

    def write(data: dict) -> None:
        data["updated_at"] = datetime.now(UTC).isoformat()
        GOLD.parent.mkdir(parents=True, exist_ok=True)
        GOLD.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def record(part: str, key: str, value) -> None:
        """Re-read the file and change only this answer, so edits made elsewhere are never lost."""
        data = load()
        data[part][key] = value
        write(data)
        gold[part][key] = value

    if args.forget:
        data = load()
        cleared = [(part, key) for part, answers in data.items() if isinstance(answers, dict)
                   for key in answers if args.forget in key]
        for part, key in cleared:
            del data[part][key]
        write(data)
        print(f"Cleared {len(cleared)} answer(s) containing '{args.forget}'; you will be asked again.")
    gold = load()

    # The current directions are the hand-downloaded set, not every old Master Direction page.
    current = {row["page_url"] for row in json.loads(
        (ROOT / "data" / "source_pdfs" / "manifest.json").read_text(encoding="utf-8"))["directions"]}
    directions = sorted((item for item in documents if item.source_url in current), key=lambda item: item.title)
    print(f"\nPart 1 of 3: {len(directions)} NBFC directions. Open each RBI page and check it is not marked Withdrawn.")
    for item in directions:
        if item.source_url in gold["directions_in_force"]:
            continue
        print()
        show("Direction", item.title)
        show("RBI page", item.source_url)
        answer = ask("  In force on RBI's site today? [y = yes, n = no, ? = not sure, q = quit] ", lambda a: a in {"y", "n", "?", "q"})
        if answer == "q":
            return
        record("directions_in_force", item.source_url, {"y": True, "n": False, "?": None}[answer])

    explicit = [link for link in links if link.method != "candidate_content_match"]
    print(f"\nPart 2 of 3: {len(explicit)} statements read from RBI's own text.")
    for link in explicit:
        old, new = by_id[link.old_document_id], by_id[link.new_document_id]
        key = f"{old.source_url} -> {new.source_url}"
        if key in gold["explicit_links"]:
            continue
        print()
        show("RBI text, from", f"{new.title} ({new.source_url})")
        heading = annex_heading(args.data_dir, new.document_id, link.evidence_quote)
        if heading:
            show("From the RBI list headed", heading)
        show("Quoted", link.evidence_quote)
        show("Document", f"{old.title}, issued {old.publication_date} ({old.source_url})")
        answer = ask("  Does the quoted text repeal or replace this document? [y/n/?/q] ", lambda a: a in {"y", "n", "?", "q"})
        if answer == "q":
            return
        record("explicit_links", key, {"y": True, "n": False, "?": None}[answer])

    # Every withdrawn rule (latest version of a re-issued title), not only those the system made a
    # suggestion for: otherwise replacements the system missed could never be counted.
    withdrawn = sorted((item for item in documents if item.lifecycle is DocumentLifecycle.WITHDRAWN
                        and not _reissued_later(item, documents)), key=lambda item: item.title)
    print(f"\nPart 3 of 3: {len(withdrawn)} withdrawn rules. Which current NBFC direction now holds each one?")
    for number, item in enumerate(directions, start=1):
        print(f"  {number:>2}. {item.title}")
    for item in withdrawn:
        if item.source_url in gold["successors"]:
            continue
        print()
        show("Withdrawn rule", f"{item.title}, issued {item.publication_date}")
        show("RBI page", item.source_url)
        answer = ask(
            "  Number(s) of the direction(s) that now hold it, e.g. 7 or 3,7  [0 = none of these, ? = not sure, "
            "l = list again, q = quit] ",
            lambda a: a in {"0", "?", "q", "l"} or all(p.strip().isdigit() and 1 <= int(p) <= len(directions)
                                                         for p in a.split(",")),
        )
        if answer == "q":
            return
        if answer == "l":
            for number, choice in enumerate(directions, start=1):
                print(f"  {number:>2}. {choice.title}")
            answer = ask("  Number(s), 0, ? or q: ", lambda a: a in {"0", "?", "q"} or all(
                p.strip().isdigit() and 1 <= int(p) <= len(directions) for p in a.split(",")))
            if answer == "q":
                return
        record("successors", item.source_url, None if answer == "?" else [] if answer == "0" else [
            directions[int(p) - 1].source_url for p in answer.split(",")])
    print(f"\nDone. Saved to {GOLD.relative_to(ROOT)}.")


if __name__ == "__main__":
    main()
