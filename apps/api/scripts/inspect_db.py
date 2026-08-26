"""Show what OmniDocAI has actually persisted.

Run inside the API container:
    docker compose exec api python scripts/inspect_db.py
"""
import json
import os
import sqlite3
from pathlib import Path

STORAGE = Path(os.getenv("STORAGE_DIR", "/app/storage"))
CHROMA = STORAGE / "chroma_db"


def section(title):
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def show_registry():
    section("1. documents.json  (the document registry)")
    db = STORAGE / "documents.json"
    if not db.exists():
        print("  (no documents yet)")
        return
    docs = json.loads(db.read_text(encoding="utf-8"))
    print(f"  {len(docs)} document(s)\n")
    for d in docs:
        print(f"  - {d['name']}  [{d['status']}]")
        print(f"      id     : {d['id']}")
        print(f"      chunks : {d.get('chunks')}   model: {d.get('embeddingModel')}   v{d.get('indexVersion')}")
        print(f"      file   : {d['path']}")
        if d.get("error"):
            print(f"      error  : {d['error']}")


def show_uploads():
    section("2. uploads/  (original files, as uploaded)")
    files = sorted(p for p in (STORAGE / "uploads").glob("*") if p.name != ".gitkeep")
    if not files:
        print("  (empty)")
    for p in files:
        print(f"  {p.stat().st_size:>9,} B  {p.name}")


def show_vectors():
    section("3. ChromaDB  (chunks + embeddings)")
    import chromadb
    from chromadb.config import Settings

    client = chromadb.PersistentClient(path=str(CHROMA), settings=Settings(anonymized_telemetry=False))
    names = client.list_collections()
    print(f"  {len(names)} collection(s)")
    for name in names:
        col = client.get_collection(name)
        space = (col.metadata or {}).get("hnsw:space", "l2 (default)")
        print(f"\n  {name}\n    chunks={col.count()}  distance={space}")
        got = col.get(include=["documents", "metadatas", "embeddings"])
        for i, cid in enumerate(got["ids"]):
            emb = got["embeddings"][i]
            text = " ".join(got["documents"][i].split())
            print(f"    [{got['metadatas'][i]['chunk_index']}] dims={len(emb)} chars={len(got['documents'][i])}")
            print(f"        {text[:70]}...")


def show_disk_health():
    section("4. Disk health  (leftovers from deleted documents)")
    con = sqlite3.connect(CHROMA / "chroma.sqlite3")
    live_segments = {r[0] for r in con.execute("SELECT id FROM segments")}

    rows = con.execute("SELECT segment_id, COUNT(*) FROM embeddings GROUP BY segment_id").fetchall()
    live_rows = sum(n for s, n in rows if s in live_segments)
    dead_rows = sum(n for s, n in rows if s not in live_segments)
    print(f"  embedding rows : {live_rows} live, {dead_rows} orphaned")

    live_mb = dead_mb = 0.0
    for d in CHROMA.iterdir():
        if not d.is_dir():
            continue
        mb = sum(f.stat().st_size for f in d.iterdir()) / 1024 / 1024
        if d.name in live_segments:
            live_mb += mb
        else:
            dead_mb += mb
    print(f"  vector files   : {live_mb:.2f} MB live, {dead_mb:.2f} MB orphaned")
    if dead_mb > live_mb and dead_mb > 1:
        print("\n  NOTE: ChromaDB does not reclaim space when a collection is deleted.")


if __name__ == "__main__":
    show_registry()
    show_uploads()
    show_vectors()
    show_disk_health()
