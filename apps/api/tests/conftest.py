"""Shared fixtures.

`app.main` builds a ChromaDB client and creates directories at import time, so
STORAGE_DIR is redirected to a temp directory *before* the import happens.
Without this, running the tests would write into the real storage/ tree.
"""
import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="omnidocai-tests-")
os.environ["STORAGE_DIR"] = _TMP
os.environ.setdefault("DEEPSEEK_API_KEY", "")  # keep tests offline

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402


@pytest.fixture
def client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_registry():
    """Each test starts with an empty document registry and fresh SQLite database."""
    if main.DOCUMENTS_DB.exists():
        main.DOCUMENTS_DB.unlink()
    db_path = main.db.get_db_path()
    if db_path.exists():
        db_path.unlink()
    # Also clean up WAL / SHM files if any
    wal = db_path.with_name(db_path.name + "-wal")
    if wal.exists():
        wal.unlink()
    shm = db_path.with_name(db_path.name + "-shm")
    if shm.exists():
        shm.unlink()
    main.db.init_db()
    yield
