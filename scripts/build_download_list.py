"""Write the list of RBI direction PDFs that must be downloaded by hand.

rbidocs.rbi.org.in shows automated clients a CAPTCHA, so PDFs are saved from a browser
into data/source_pdfs/ with their original file names. This script reads the Master
Directions index on www.rbi.org.in, applies config/corpus/inclusion.yaml, and records:

  data/source_pdfs/manifest.json       included directions, their PDF, and whether it is present
  data/source_pdfs/inclusion-log.json  every index entry with its include/exclude reason
  data/source_pdfs/DOWNLOAD.md         the files still needed, as clickable links

Run it again at any time: a direction RBI has updated gets a new PDF file name and
reappears on the list.
"""

import argparse
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import clock  # noqa: E402
from app.monitoring.master_directions import INDEX_URL, IndexEntry, decide_inclusion, match_pdf, parse_index  # noqa: E402

USER_AGENT = "Mozilla/5.0 (RBI lending corpus research; contact via project repository)"


def adopt_renamed_files(folder: Path, entries: list[IndexEntry]) -> list[str]:
    """Rename hand-saved PDFs to RBI's file name when their content identifies exactly one direction.

    Browsers often save these PDFs under their title. The printed title, file size and
    "Updated as on" date must all match (see match_pdf), so an older version is never adopted.
    Returns the names of PDFs that could not be recognised.
    """
    import fitz

    expected = {entry.pdf_file_name.lower() for entry in entries if entry.pdf_file_name}
    unmatched = []
    for path in sorted(item for item in folder.iterdir() if item.suffix.lower() == ".pdf"):
        if path.name.lower() in expected:
            continue
        with fitz.open(path) as pdf:
            text = "\n".join(pdf[number].get_text("text") for number in range(min(2, len(pdf))))
        entry = match_pdf(text, path.stat().st_size / 1024, entries)
        target = folder / entry.pdf_file_name if entry and entry.pdf_file_name else None
        if target is None or target.exists():
            unmatched.append(path.name)
            continue
        path.rename(target)
        print(f"Recognised {path.name} as {target.name}")
    return unmatched


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--folder", type=Path, default=ROOT / "data" / "source_pdfs")
    parser.add_argument("--index-file", type=Path, help="Use a saved copy of the index instead of fetching it.")
    args = parser.parse_args()

    if args.index_file:
        page = args.index_file.read_text(encoding="utf-8")
    else:
        response = httpx.get(INDEX_URL, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=60)
        response.raise_for_status()
        page = response.text
    decisions = decide_inclusion(parse_index(page), ROOT / "config" / "corpus" / "inclusion.yaml")
    args.folder.mkdir(parents=True, exist_ok=True)
    included = [item.entry for item in decisions if item.included]
    unmatched = adopt_renamed_files(args.folder, included)
    present = {path.name.lower() for path in args.folder.iterdir() if path.suffix.lower() == ".pdf"}

    manifest = [{
        "page_id": entry.page_id, "page_url": entry.page_url, "title": entry.title,
        "updated_as_on": entry.updated_as_on.isoformat() if entry.updated_as_on else None,
        "pdf_url": entry.pdf_url, "pdf_file_name": entry.pdf_file_name, "listed_size_kb": entry.size_kb,
        "file_present": bool(entry.pdf_file_name and entry.pdf_file_name.lower() in present),
    } for entry in included]
    checked = clock.now().isoformat()
    (args.folder / "manifest.json").write_text(json.dumps({"index_url": INDEX_URL, "checked_at": checked,
                                                           "directions": manifest}, indent=2), encoding="utf-8")
    (args.folder / "inclusion-log.json").write_text(json.dumps({"checked_at": checked, "decisions": [
        {"page_id": item.entry.page_id, "title": item.entry.title, "included": item.included, "reason": item.reason}
        for item in decisions
    ]}, indent=2), encoding="utf-8")

    missing = [row for row in manifest if not row["file_present"]]
    lines = [
        "# RBI direction PDFs to download",
        "",
        f"Generated {checked[:10]} from the [Master Directions index]({INDEX_URL}) using `config/corpus/inclusion.yaml`.",
        "",
        "Open each PDF link in your browser, complete the RBI check if asked, and save the file into this folder",
        "**keeping its original file name**. Then run `python scripts/build_download_list.py` again to confirm.",
        "",
        f"{len(manifest) - len(missing)} of {len(manifest)} files present.",
        "",
        "| # | Direction | Updated as on | PDF (size) |",
        "|---|---|---|---|",
    ]
    for number, row in enumerate(missing, start=1):
        lines.append(f"| {number} | [{row['title']}]({row['page_url']}) | {row['updated_as_on'] or '-'} | "
                     f"[{row['pdf_file_name']}]({row['pdf_url']}) ({row['listed_size_kb']:.0f} KB) |")
    if not missing:
        lines.append("| | All files present. | | |")
    (args.folder / "DOWNLOAD.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(decisions)} index entries; {len(manifest)} included; {len(missing)} PDFs still to download.")
    for name in unmatched:
        print(f"Not recognised (left as is): {name}")


if __name__ == "__main__":
    main()
