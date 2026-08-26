"""Reclaim ChromaDB disk space by rebuilding the vector store from scratch.

ChromaDB does not free SQLite rows or HNSW files when a collection is deleted,
so a store that has seen many uploads/deletes keeps growing. Deleting rows by
hand risks corrupting Chroma's internal fts5 tables, so instead this drops the
whole vector store. Nothing is lost: the original files in uploads/ and the
registry in documents.json are untouched, and the API rebuilds every index on
its next startup (see index_is_healthy in app/main.py).

The API must be stopped first, or it will keep writing to files as they are
removed:

    docker compose stop api
    docker compose run --rm api python scripts/rebuild_index.py
    docker compose up -d api
"""
import json
import os
import shutil
import sqlite3
from pathlib import Path

STORAGE = Path(os.getenv("STORAGE_DIR", "/app/storage"))
CHROMA = STORAGE / "chroma_db"


def dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def report_orphans() -> None:
    db = CHROMA / "chroma.sqlite3"
    if not db.exists():
        return
    con = sqlite3.connect(db)
    try:
        live = {r[0] for r in con.execute("SELECT id FROM segments")}
        rows = con.execute("SELECT segment_id, COUNT(*) FROM embeddings GROUP BY segment_id").fetchall()
    except sqlite3.Error as e:
        print(f"  (could not read segment info: {e})")
        return
    finally:
        con.close()
    dead = sum(n for s, n in rows if s not in live)
    alive = sum(n for s, n in rows if s in live)
    print(f"  embedding rows : {alive} live, {dead} orphaned")


def main() -> None:
    if not CHROMA.exists():
        print("No chroma_db directory; nothing to do.")
        return

    docs = []
    registry = STORAGE / "documents.json"
    if registry.exists():
        docs = json.loads(registry.read_text(encoding="utf-8"))

    before = dir_size(CHROMA)
    print(f"Vector store before : {before / 1024 / 1024:.2f} MB")
    report_orphans()

    for entry in CHROMA.iterdir():
        if entry.name == ".gitkeep":
            continue
        shutil.rmtree(entry) if entry.is_dir() else entry.unlink()

    after = dir_size(CHROMA)
    print(f"Vector store after  : {after / 1024 / 1024:.2f} MB")
    print(f"Reclaimed           : {(before - after) / 1024 / 1024:.2f} MB")
    print(f"\n{len(docs)} document(s) will be re-indexed on the next API startup.")


if __name__ == "__main__":
    main()
