import os
import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "/app/storage"))


def get_db_path() -> Path:
    storage = Path(os.getenv("STORAGE_DIR", str(STORAGE_DIR)))
    storage.mkdir(parents=True, exist_ok=True)
    return storage / "omnidoc.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(get_db_path()), timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def init_db():
    """Create tables and indices if they do not exist."""
    conn = get_connection()
    try:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    uploadedAt TEXT NOT NULL,
                    status TEXT NOT NULL,
                    path TEXT NOT NULL,
                    chunks INTEGER DEFAULT 0,
                    embeddingModel TEXT,
                    indexVersion INTEGER DEFAULT 0,
                    error TEXT,
                    summary TEXT,
                    suggested_questions_json TEXT
                );
            """)

            # Add columns if migrating existing SQLite database
            try:
                conn.execute("ALTER TABLE documents ADD COLUMN summary TEXT;")
            except sqlite3.OperationalError:
                pass

            try:
                conn.execute("ALTER TABLE documents ADD COLUMN suggested_questions_json TEXT;")
            except sqlite3.OperationalError:
                pass

            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversations_document_id 
                ON conversations(document_id);
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    sources_json TEXT,
                    created_at TEXT NOT NULL
                );
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_conversation_id 
                ON messages(conversation_id);
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS query_usage (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,
                    message_id TEXT REFERENCES messages(id) ON DELETE SET NULL,
                    prompt_tokens INTEGER DEFAULT 0,
                    completion_tokens INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    prompt_cache_hit_tokens INTEGER DEFAULT 0,
                    prompt_cache_miss_tokens INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                );
            """)

            # Ensure workspace virtual document '__all__' exists for global threads
            conn.execute("""
                INSERT OR IGNORE INTO documents 
                (id, name, size, type, uploadedAt, status, path, chunks)
                VALUES ('__all__', 'All Documents', 0, 'workspace/all', '2026-01-01T00:00:00', 'ready', '', 0);
            """)
    finally:
        conn.close()

    # Migrate from legacy documents.json if present and documents table is empty
    migrate_legacy_json_if_needed()


def migrate_legacy_json_if_needed():
    """Migrate documents from documents.json to SQLite if documents table is empty."""
    storage = Path(os.getenv("STORAGE_DIR", str(STORAGE_DIR)))
    legacy_file = storage / "documents.json"
    if not legacy_file.exists():
        return

    conn = get_connection()
    try:
        count = conn.execute("SELECT COUNT(*) FROM documents WHERE id != '__all__'").fetchone()[0]
        if count == 0:
            try:
                data = json.loads(legacy_file.read_text(encoding="utf-8"))
                if isinstance(data, list) and data:
                    with conn:
                        for d in data:
                            conn.execute("""
                                INSERT OR REPLACE INTO documents 
                                (id, name, size, type, uploadedAt, status, path, chunks, embeddingModel, indexVersion, error)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                d.get("id"),
                                d.get("name"),
                                d.get("size", 0),
                                d.get("type", "text/plain"),
                                d.get("uploadedAt", datetime.utcnow().isoformat()),
                                d.get("status", "processing"),
                                d.get("path", ""),
                                d.get("chunks", 0),
                                d.get("embeddingModel"),
                                d.get("indexVersion", 0),
                                d.get("error")
                            ))
                    print(f"Migrated {len(data)} documents from {legacy_file} to SQLite.")
            except Exception as e:
                print(f"Warning: Failed to migrate legacy documents.json: {e}")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Document CRUD operations
# ---------------------------------------------------------------------------

def list_documents() -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM documents WHERE id != '__all__' ORDER BY uploadedAt DESC").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_document(doc_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def insert_document(doc: Dict[str, Any]):
    conn = get_connection()
    try:
        with conn:
            conn.execute("""
                INSERT INTO documents 
                (id, name, size, type, uploadedAt, status, path, chunks, embeddingModel, indexVersion, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                doc["id"],
                doc["name"],
                doc["size"],
                doc["type"],
                doc["uploadedAt"],
                doc["status"],
                doc["path"],
                doc.get("chunks", 0),
                doc.get("embeddingModel"),
                doc.get("indexVersion", 0),
                doc.get("error")
            ))
    finally:
        conn.close()


def update_document(doc_id: str, **fields):
    if not fields:
        return
    set_clauses = [f"{k} = ?" for k in fields.keys()]
    values = list(fields.values()) + [doc_id]
    query = f"UPDATE documents SET {', '.join(set_clauses)} WHERE id = ?"
    
    conn = get_connection()
    try:
        with conn:
            conn.execute(query, values)
    finally:
        conn.close()


def delete_document(doc_id: str) -> bool:
    if doc_id == "__all__":
        return False
    conn = get_connection()
    try:
        with conn:
            cur = conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            return cur.rowcount > 0
    finally:
        conn.close()


def get_document_summary(doc_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT summary, suggested_questions_json FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not row or not row["summary"]:
            return None
        questions = []
        if row["suggested_questions_json"]:
            try:
                questions = json.loads(row["suggested_questions_json"])
            except Exception:
                questions = []
        return {
            "summary": row["summary"],
            "questions": questions
        }
    finally:
        conn.close()


def save_document_summary(doc_id: str, summary: str, questions: List[str]):
    conn = get_connection()
    try:
        with conn:
            conn.execute("""
                UPDATE documents 
                SET summary = ?, suggested_questions_json = ? 
                WHERE id = ?
            """, (summary, json.dumps(questions, ensure_ascii=False), doc_id))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Conversation & Message operations
# ---------------------------------------------------------------------------

def create_conversation(document_id: str, title: Optional[str] = None) -> Dict[str, Any]:
    conv_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    conv_title = title or f"Chat - {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"

    conn = get_connection()
    try:
        with conn:
            conn.execute("""
                INSERT INTO conversations (id, document_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (conv_id, document_id, conv_title, now, now))
        return {
            "id": conv_id,
            "document_id": document_id,
            "title": conv_title,
            "created_at": now,
            "updated_at": now,
        }
    finally:
        conn.close()


def get_conversation(conv_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_or_create_active_conversation(document_id: str) -> Dict[str, Any]:
    """Get the most recently updated conversation for a document, or create one."""
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT * FROM conversations 
            WHERE document_id = ? 
            ORDER BY updated_at DESC 
            LIMIT 1
        """, (document_id,)).fetchone()
        if row:
            return dict(row)
    finally:
        conn.close()
    return create_conversation(document_id)


def list_conversations(document_id: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        if document_id:
            rows = conn.execute("""
                SELECT * FROM conversations 
                WHERE document_id = ? 
                ORDER BY updated_at DESC
            """, (document_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM conversations ORDER BY updated_at DESC").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def update_conversation_title_if_default(conv_id: str, new_title: str):
    conn = get_connection()
    try:
        with conn:
            conn.execute("""
                UPDATE conversations 
                SET title = ?, updated_at = ? 
                WHERE id = ? AND title LIKE 'Chat - %'
            """, (new_title[:60], datetime.utcnow().isoformat(), conv_id))
    finally:
        conn.close()


def touch_conversation(conv_id: str):
    conn = get_connection()
    try:
        with conn:
            conn.execute("""
                UPDATE conversations 
                SET updated_at = ? 
                WHERE id = ?
            """, (datetime.utcnow().isoformat(), conv_id))
    finally:
        conn.close()


def delete_conversation(conv_id: str) -> bool:
    conn = get_connection()
    try:
        with conn:
            cur = conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
            return cur.rowcount > 0
    finally:
        conn.close()


def add_message(
    conversation_id: str,
    role: str,
    content: str,
    sources: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    msg_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    sources_json = json.dumps(sources) if sources is not None else None

    conn = get_connection()
    try:
        with conn:
            conn.execute("""
                INSERT INTO messages (id, conversation_id, role, content, sources_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (msg_id, conversation_id, role, content, sources_json, now))
            conn.execute("""
                UPDATE conversations SET updated_at = ? WHERE id = ?
            """, (now, conversation_id))
        return {
            "id": msg_id,
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "sources": sources,
            "created_at": now
        }
    finally:
        conn.close()


def get_conversation_messages(conversation_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        if limit:
            # Get latest N messages ordered chronologically
            rows = conn.execute("""
                SELECT * FROM (
                    SELECT * FROM messages 
                    WHERE conversation_id = ? 
                    ORDER BY created_at DESC 
                    LIMIT ?
                ) ORDER BY created_at ASC
            """, (conversation_id, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM messages 
                WHERE conversation_id = ? 
                ORDER BY created_at ASC
            """, (conversation_id,)).fetchall()

        messages = []
        for r in rows:
            m = dict(r)
            m["sources"] = json.loads(m["sources_json"]) if m.get("sources_json") else None
            messages.append(m)
        return messages
    finally:
        conn.close()


def record_query_usage(
    conversation_id: Optional[str],
    message_id: Optional[str],
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    prompt_cache_hit_tokens: int = 0,
    prompt_cache_miss_tokens: int = 0
) -> Dict[str, Any]:
    usage_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    conn = get_connection()
    try:
        with conn:
            conn.execute("""
                INSERT INTO query_usage 
                (id, conversation_id, message_id, prompt_tokens, completion_tokens, total_tokens, 
                 prompt_cache_hit_tokens, prompt_cache_miss_tokens, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                usage_id,
                conversation_id,
                message_id,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                prompt_cache_hit_tokens,
                prompt_cache_miss_tokens,
                now
            ))
        return {
            "id": usage_id,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "prompt_cache_hit_tokens": prompt_cache_hit_tokens,
            "prompt_cache_miss_tokens": prompt_cache_miss_tokens,
            "created_at": now
        }
    finally:
        conn.close()


def get_total_usage() -> Dict[str, Any]:
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT 
                COALESCE(SUM(prompt_tokens), 0) as total_prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) as total_completion_tokens,
                COALESCE(SUM(total_tokens), 0) as grand_total_tokens,
                COALESCE(SUM(prompt_cache_hit_tokens), 0) as total_cache_hit_tokens,
                COALESCE(SUM(prompt_cache_miss_tokens), 0) as total_cache_miss_tokens,
                COUNT(*) as query_count
            FROM query_usage
        """).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()
