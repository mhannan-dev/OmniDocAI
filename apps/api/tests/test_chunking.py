"""Tests for chunk_text.

The regression these exist for: `start = end - overlap` used to run after the
final chunk, parking `start` at `len(text) - overlap` forever. The loop then
appended the same tail chunk until the process exhausted memory — a 2 KB file
grew the container to 6 GB and blocked the event loop, so even /health hung.

Anything asserting a finite chunk count is guarding that loop.
"""
import pytest

from app.main import chunk_text

CHUNK_SIZE = 1000
OVERLAP = 200


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("", id="empty"),
        pytest.param("Short document.", id="one-sentence"),
        pytest.param("x" * (CHUNK_SIZE - 1), id="just-under-chunk-size"),
        pytest.param("x" * CHUNK_SIZE, id="exactly-chunk-size"),
    ],
)
def test_short_text_is_a_single_chunk(text):
    assert chunk_text(text) == [text]


@pytest.mark.parametrize(
    "text",
    [
        # 2112 chars was the exact size that hung the app in production.
        pytest.param(("Sentence number one is here. " * 75)[:2112], id="regression-2112-bytes"),
        pytest.param("x" * (CHUNK_SIZE + 1), id="one-over-chunk-size"),
        # No '.' anywhere, so the sentence-boundary branch never fires.
        pytest.param("word " * 10_000, id="no-sentence-boundaries"),
        # Every character is a boundary — rfind always matches.
        pytest.param("." * 5_000, id="all-boundaries"),
        # A trailing run shorter than `overlap`, the shape that caused the hang.
        pytest.param("a." * 600, id="short-tail"),
        pytest.param("Sentence. " * 500, id="many-short-sentences"),
    ],
)
def test_long_text_terminates_and_stays_bounded(text):
    chunks = chunk_text(text)

    # A correct chunker cannot need more chunks than one per (chunk_size - overlap)
    # step, plus one for the tail. The old code produced an unbounded list here.
    max_expected = len(text) // (CHUNK_SIZE - OVERLAP) + 2
    assert 0 < len(chunks) <= max_expected

    assert all(len(c) <= CHUNK_SIZE for c in chunks)
    assert all(c for c in chunks), "empty chunks should be filtered out"


def test_covers_the_whole_document():
    """Every sentence must survive chunking, or retrieval silently loses content."""
    sentences = [f"Fact number {i} is that code RX-{1000 + i} exists." for i in range(200)]
    text = " ".join(sentences)

    joined = " ".join(chunk_text(text))
    for sentence in sentences:
        assert sentence in joined


def test_chunks_overlap_so_context_is_not_cut_at_the_seam():
    text = "".join(f"Sentence {i} carries some filler words here. " for i in range(200))
    chunks = chunk_text(text)

    assert len(chunks) > 1
    for previous, following in zip(chunks, chunks[1:]):
        tail = previous[-OVERLAP // 2:]
        assert tail.strip(), "overlap region should not be empty"


def test_respects_custom_sizes():
    text = "y" * 500
    chunks = chunk_text(text, chunk_size=100, overlap=20)

    assert len(chunks) > 1
    assert all(len(c) <= 100 for c in chunks)
