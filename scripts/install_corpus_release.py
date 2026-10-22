"""Verify and unpack the evaluated corpus into a Docker image, without network access.

Refuses to overwrite different existing files. This is an image-build operation,
not a production database migration or a way to replace a running service's data.
"""

import argparse
import hashlib
import json
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def install(archive: Path, checksum_file: Path, destination: Path) -> dict:
    expected = checksum_file.read_text(encoding="utf-8").split()[0]
    if len(expected) != 64 or digest(archive) != expected:
        raise ValueError("Corpus archive checksum does not match the release checksum.")

    with tempfile.TemporaryDirectory(prefix="rbi-corpus-release-") as temporary:
        staged = Path(temporary)
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            if len(names) != len(set(names)):
                raise ValueError("Corpus archive contains duplicate entries.")
            manifest = json.loads(bundle.read("release-manifest.json"))
            files = manifest["files"]
            if set(names) != set(files) | {"release-manifest.json"}:
                raise ValueError("Corpus archive entries differ from its manifest.")
            for name, expected_hash in files.items():
                relative = PurePosixPath(name)
                if (relative.is_absolute() or ".." in relative.parts or "\\" in name
                        or ":" in name or not relative.parts
                        or relative.parts[0] not in {"raw", "processed", "runtime", "graph", "register.html"}):
                    raise ValueError("Corpus archive contains an unsafe path.")
                if stat.S_ISLNK(bundle.getinfo(name).external_attr >> 16):
                    raise ValueError("Corpus archive contains a symbolic link.")
                target = staged.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(name) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
                if digest(target) != expected_hash:
                    raise ValueError(f"Corpus file checksum mismatch: {name}")

        documents = json.loads((staged / "runtime/documents.json").read_text(encoding="utf-8"))
        chunks = json.loads((staged / "runtime/vectors.json").read_text(encoding="utf-8"))
        graph = json.loads((staged / "graph/graph.json").read_text(encoding="utf-8"))
        if (len(documents), len(chunks), len(graph["nodes"]), len(graph["edges"])) != (
                manifest["documents"], manifest["chunks"], manifest["graph_nodes"], manifest["graph_edges"]):
            raise ValueError("Corpus counts differ from the release manifest.")
        fingerprint = hashlib.sha256("".join(sorted(
            f"{document['document_id']}:{document['content_hash']}" for document in documents
        )).encode()).hexdigest()
        if fingerprint != manifest["corpus_fingerprint"]:
            raise ValueError("Corpus fingerprint differs from the release manifest.")
        document_ids = {document["document_id"] for document in documents}
        if (len(document_ids) != len(documents)
                or len({row["chunk"]["chunk_id"] for row in chunks}) != len(chunks)
                or any(row["chunk"]["document_id"] not in document_ids for row in chunks)):
            raise ValueError("Corpus contains duplicate IDs or orphan chunks.")

        # Validate every collision before writing anything to the destination.
        for name, expected_hash in files.items():
            target = destination / name
            if target.exists() and (not target.is_file() or digest(target) != expected_hash):
                raise ValueError(f"Refusing to overwrite existing corpus data: {name}")
        for name in files:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copyfile(staged / name, target)

    return {key: manifest[key] for key in (
        "documents", "chunks", "graph_nodes", "graph_edges", "corpus_fingerprint"
    )}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--checksum-file", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(install(args.archive, args.checksum_file, args.data_dir)))


if __name__ == "__main__":
    main()
