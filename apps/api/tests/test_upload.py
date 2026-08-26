"""Tests for upload validation and the document registry.

These cover the checks that run before any indexing happens: file type, the
10 MB cap, and that a rejected upload leaves nothing behind on disk.
"""
import io

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def upload(client, name, content=b"hello world", content_type="text/plain"):
    return client.post(
        "/documents/upload",
        files={"file": (name, io.BytesIO(content), content_type)},
    )


def test_health_route(client):
    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_registry_starts_empty(client):
    assert client.get("/documents").json()["documents"] == []


def test_accepts_supported_types(client):
    for name, ctype in [
        ("notes.txt", "text/plain"),
        ("readme.md", "text/markdown"),
        ("paper.pdf", "application/pdf"),
        ("report.docx", DOCX),
    ]:
        assert upload(client, name, content_type=ctype).status_code == 200, name


def test_rejects_unsupported_type(client):
    res = upload(client, "photo.png", content_type="image/png")

    assert res.status_code == 400
    assert "Unsupported file type" in res.json()["detail"]


def test_generic_content_type_falls_back_to_extension(client):
    """Browsers often send application/octet-stream; the extension decides."""
    res = upload(client, "notes.md", content_type="application/octet-stream")
    assert res.status_code == 200
    assert res.json()["document"]["type"] == "text/markdown"


def test_unknown_extension_with_generic_type_is_rejected(client):
    res = upload(client, "archive.zip", content_type="application/octet-stream")
    assert res.status_code == 400


def test_rejects_files_over_the_size_cap(client):
    oversized = b"x" * (10 * 1024 * 1024 + 1)
    res = upload(client, "big.txt", content=oversized)

    assert res.status_code == 400
    assert "too large" in res.json()["detail"].lower()


def test_rejected_oversized_upload_leaves_no_file_behind(client):
    from app.main import UPLOAD_DIR

    before = set(UPLOAD_DIR.iterdir())
    upload(client, "big.txt", content=b"x" * (10 * 1024 * 1024 + 1))

    assert set(UPLOAD_DIR.iterdir()) == before


def test_upload_records_metadata(client):
    doc = upload(client, "notes.txt", content=b"some text").json()["document"]

    assert doc["name"] == "notes.txt"
    assert doc["size"] == len(b"some text")
    assert doc["status"] in {"processing", "ready", "error"}
    assert doc["id"]


def test_stored_filename_is_randomised_but_keeps_the_extension(client):
    """Two uploads of the same name must not collide on disk."""
    first = upload(client, "notes.txt").json()["document"]
    second = upload(client, "notes.txt").json()["document"]

    assert first["id"] != second["id"]
    assert first["path"] != second["path"]
    assert first["path"].endswith(".txt")


def test_uploaded_document_appears_in_the_listing(client):
    doc = upload(client, "notes.txt").json()["document"]

    listed = client.get("/documents").json()["documents"]
    assert [d["id"] for d in listed] == [doc["id"]]


def test_delete_removes_the_document_and_its_file(client):
    from pathlib import Path

    doc = upload(client, "notes.txt").json()["document"]

    assert client.delete(f"/documents/{doc['id']}").status_code == 200
    assert client.get("/documents").json()["documents"] == []
    assert not Path(doc["path"]).exists()


def test_delete_unknown_document_is_a_404(client):
    assert client.delete("/documents/does-not-exist").status_code == 404
