"""Tests for SQLite database persistence, conversations, messages, usage, and migration."""
import json
import uuid
from app import db, main


def test_sqlite_document_crud():
    doc_id = str(uuid.uuid4())
    doc = {
        "id": doc_id,
        "name": "manual.pdf",
        "size": 1024,
        "type": "application/pdf",
        "uploadedAt": "2026-09-12T12:00:00",
        "status": "processing",
        "path": "/tmp/manual.pdf",
        "chunks": 0,
        "embeddingModel": None,
        "indexVersion": 5,
        "error": None
    }
    db.insert_document(doc)

    fetched = db.get_document(doc_id)
    assert fetched is not None
    assert fetched["name"] == "manual.pdf"
    assert fetched["status"] == "processing"

    db.update_document(doc_id, status="ready", chunks=5)
    updated = db.get_document(doc_id)
    assert updated["status"] == "ready"
    assert updated["chunks"] == 5

    all_docs = db.list_documents()
    assert any(d["id"] == doc_id for d in all_docs)

    deleted = db.delete_document(doc_id)
    assert deleted is True
    assert db.get_document(doc_id) is None


def test_legacy_json_migration(tmp_path, monkeypatch):
    """Test automatic migration from documents.json when sqlite documents table is empty."""
    json_path = db.get_db_path().parent / "documents.json"
    dummy_data = [
        {
            "id": "migrated-1",
            "name": "legacy.txt",
            "size": 123,
            "type": "text/plain",
            "uploadedAt": "2026-08-01T10:00:00",
            "status": "ready",
            "path": "/storage/uploads/legacy.txt",
            "chunks": 2,
            "embeddingModel": "minilm",
            "indexVersion": 5,
            "error": None
        }
    ]
    json_path.write_text(json.dumps(dummy_data), encoding="utf-8")

    db.migrate_legacy_json_if_needed()

    doc = db.get_document("migrated-1")
    assert doc is not None
    assert doc["name"] == "legacy.txt"
    assert doc["chunks"] == 2


def test_conversation_and_message_lifecycle():
    doc_id = str(uuid.uuid4())
    doc = {
        "id": doc_id,
        "name": "test_doc.md",
        "size": 500,
        "type": "text/markdown",
        "uploadedAt": "2026-09-12T12:00:00",
        "status": "ready",
        "path": "/tmp/test_doc.md",
        "chunks": 1,
        "embeddingModel": "test",
        "indexVersion": 1,
        "error": None
    }
    db.insert_document(doc)

    conv = db.create_conversation(doc_id, title="Test Thread")
    assert conv["document_id"] == doc_id
    assert conv["title"] == "Test Thread"

    msg1 = db.add_message(conv["id"], "user", "What is OmniDocAI?")
    assert msg1["role"] == "user"
    assert msg1["content"] == "What is OmniDocAI?"

    sources = [{"document_id": doc_id, "document_name": "test_doc.md", "content": "OmniDocAI is cool", "score": 0.95}]
    msg2 = db.add_message(conv["id"], "assistant", "OmniDocAI is an AI tool.", sources=sources)
    assert msg2["role"] == "assistant"
    assert msg2["sources"] == sources

    messages = db.get_conversation_messages(conv["id"])
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["sources"][0]["score"] == 0.95

    # Test query usage recording
    usage = db.record_query_usage(
        conversation_id=conv["id"],
        message_id=msg2["id"],
        prompt_tokens=150,
        completion_tokens=50,
        total_tokens=200,
        prompt_cache_hit_tokens=100,
        prompt_cache_miss_tokens=50
    )
    assert usage["total_tokens"] == 200
    assert usage["prompt_cache_hit_tokens"] == 100

    total_usage = db.get_total_usage()
    assert total_usage["grand_total_tokens"] >= 200
    assert total_usage["total_cache_hit_tokens"] >= 100


def test_cascade_delete_on_document():
    doc_id = str(uuid.uuid4())
    db.insert_document({
        "id": doc_id,
        "name": "cascade_test.txt",
        "size": 100,
        "type": "text/plain",
        "uploadedAt": "2026-09-12T12:00:00",
        "status": "ready",
        "path": "/tmp/cascade_test.txt"
    })
    conv = db.create_conversation(doc_id)
    db.add_message(conv["id"], "user", "Hello")

    assert db.get_conversation(conv["id"]) is not None
    assert len(db.get_conversation_messages(conv["id"])) == 1

    # Deleting document must cascade delete conversations & messages
    db.delete_document(doc_id)
    assert db.get_conversation(conv["id"]) is None
    assert len(db.get_conversation_messages(conv["id"])) == 0


def test_conversation_api_endpoints(client):
    # 1. Create a document first
    doc_res = client.post(
        "/documents/upload",
        files={"file": ("doc1.txt", b"sample content", "text/plain")}
    )
    assert doc_res.status_code == 200
    doc_id = doc_res.json()["document"]["id"]

    # 2. Create conversation
    create_res = client.post("/conversations", json={"document_id": doc_id, "title": "API Thread"})
    assert create_res.status_code == 200
    conv_id = create_res.json()["conversation"]["id"]

    # 3. List conversations for document
    list_res = client.get(f"/documents/{doc_id}/conversations")
    assert list_res.status_code == 200
    convs = list_res.json()["conversations"]
    assert any(c["id"] == conv_id for c in convs)

    # 4. Get conversation with messages
    get_res = client.get(f"/conversations/{conv_id}")
    assert get_res.status_code == 200
    assert get_res.json()["conversation"]["id"] == conv_id
    assert get_res.json()["messages"] == []

    # 5. Check analytics endpoint
    analytics_res = client.get("/analytics/usage")
    assert analytics_res.status_code == 200
    assert "grand_total_tokens" in analytics_res.json()

    # 6. Delete conversation
    del_res = client.delete(f"/conversations/{conv_id}")
    assert del_res.status_code == 200
    assert client.get(f"/conversations/{conv_id}").status_code == 404


def test_document_summary_persistence_and_endpoint(client):
    doc_id = str(uuid.uuid4())
    db.insert_document({
        "id": doc_id,
        "name": "summary_test.txt",
        "size": 120,
        "type": "text/plain",
        "uploadedAt": "2026-09-12T12:00:00",
        "status": "ready",
        "path": "/tmp/summary_test.txt"
    })

    # Initially None
    assert db.get_document_summary(doc_id) is None

    # Save summary & questions
    test_summary = "This is a brief summary of the document."
    test_questions = ["What is the topic?", "Who is the author?", "When was it made?"]
    db.save_document_summary(doc_id, test_summary, test_questions)

    cached = db.get_document_summary(doc_id)
    assert cached is not None
    assert cached["summary"] == test_summary
    assert cached["questions"] == test_questions

    # Test endpoint returns cached summary
    res = client.get(f"/documents/{doc_id}/summary")
    assert res.status_code == 200
    data = res.json()
    assert data["summary"] == test_summary
    assert len(data["questions"]) == 3
    assert data["questions"][0] == "What is the topic?"
