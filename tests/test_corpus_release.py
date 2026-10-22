import hashlib
import json
import zipfile

import pytest

from scripts.install_corpus_release import install


def bundle(tmp_path, *, extra_name=None, orphan=False):
    documents = [{"document_id": "doc-1", "content_hash": "original-hash"}]
    files = {
        "runtime/documents.json": json.dumps(documents).encode(),
        "runtime/vectors.json": json.dumps([
            {"chunk": {"chunk_id": "chunk-1", "document_id": "missing" if orphan else "doc-1"}}
        ]).encode(),
        "graph/graph.json": b'{"nodes": [], "edges": []}',
    }
    if extra_name:
        files[extra_name] = b"unexpected"
    manifest = {
        "documents": 1, "chunks": 1, "graph_nodes": 0, "graph_edges": 0,
        "corpus_fingerprint": hashlib.sha256(b"doc-1:original-hash").hexdigest(),
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
    }
    archive = tmp_path / "release.zip"
    with zipfile.ZipFile(archive, "w") as output:
        for name, data in files.items():
            output.writestr(name, data)
        output.writestr("release-manifest.json", json.dumps(manifest))
    checksum = tmp_path / "release.sha256"
    checksum.write_text(hashlib.sha256(archive.read_bytes()).hexdigest())
    return archive, checksum


def test_release_installs_and_can_be_rechecked(tmp_path):
    archive, checksum = bundle(tmp_path)
    destination = tmp_path / "installed"
    assert install(archive, checksum, destination)["chunks"] == 1
    assert install(archive, checksum, destination)["documents"] == 1
    assert json.loads((destination / "runtime/documents.json").read_text())[0]["document_id"] == "doc-1"


def test_corrupt_archive_is_rejected_without_writes(tmp_path):
    archive, checksum = bundle(tmp_path)
    archive.write_bytes(archive.read_bytes() + b"corrupted")
    with pytest.raises(ValueError, match="checksum"):
        install(archive, checksum, tmp_path / "installed")
    assert not (tmp_path / "installed").exists()


def test_archive_cannot_escape_destination(tmp_path):
    archive, checksum = bundle(tmp_path, extra_name="../escaped")
    with pytest.raises(ValueError, match="unsafe path"):
        install(archive, checksum, tmp_path / "installed")
    assert not (tmp_path / "escaped").exists()
    assert not (tmp_path / "installed").exists()


def test_existing_runtime_data_is_preserved(tmp_path):
    archive, checksum = bundle(tmp_path)
    destination = tmp_path / "installed"
    runtime = destination / "runtime"
    runtime.mkdir(parents=True)
    (runtime / "documents.json").write_text("production snapshot")
    with pytest.raises(ValueError, match="Refusing to overwrite"):
        install(archive, checksum, destination)
    assert (runtime / "documents.json").read_text() == "production snapshot"
    assert not (destination / "graph").exists()


def test_orphan_chunks_are_rejected_without_writes(tmp_path):
    archive, checksum = bundle(tmp_path, orphan=True)
    with pytest.raises(ValueError, match="orphan chunks"):
        install(archive, checksum, tmp_path / "installed")
    assert not (tmp_path / "installed").exists()
