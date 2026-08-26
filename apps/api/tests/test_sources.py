"""Tests for preview_sources.

The regression these exist for: search_document used to truncate each chunk to
500 characters, and generate_chat_response then built the model's context from
that truncated text. Chunks run up to 1000 characters, so the model never saw
half of what was retrieved. The visible symptom was the app answering "the
document does not specify who founded Google" about a document that says
"Founded: 1998 by Larry Page and Sergey Brin" at offset 592 of its first chunk.

Truncation is for display only. These tests pin that boundary.
"""
from app.main import preview_sources

LIMIT = 500


def source(content, name="Document.md", score=0.8):
    return {
        "document_id": "abc",
        "document_name": name,
        "content": content,
        "score": score,
    }


def test_truncation_does_not_mutate_the_caller_data():
    """The model context is built from the original list, which must stay intact."""
    original = source("z" * 900)
    sources = [original]

    preview_sources(sources)

    assert len(original["content"]) == 900
    assert sources[0] is original


def test_long_content_is_shortened_for_display():
    result = preview_sources([source("z" * 900)])[0]

    assert result["content"] == "z" * LIMIT + "..."
    assert len(result["content"]) == LIMIT + 3


def test_short_content_is_untouched():
    text = "A short chunk."
    assert preview_sources([source(text)])[0]["content"] == text


def test_content_at_exactly_the_limit_is_not_truncated():
    text = "z" * LIMIT
    result = preview_sources([source(text)])[0]

    assert result["content"] == text
    assert not result["content"].endswith("...")


def test_metadata_survives_truncation():
    result = preview_sources([source("z" * 900, name="Report.pdf", score=0.42)])[0]

    assert result["document_name"] == "Report.pdf"
    assert result["score"] == 0.42
    assert result["document_id"] == "abc"


def test_the_regression_case_late_facts_reach_the_model():
    """A fact past the display limit must still be in the data used for context."""
    chunk = "padding. " * 70 + "Founded: 1998 by Larry Page and Sergey Brin."
    assert len(chunk) > LIMIT

    sources = [source(chunk)]
    previews = preview_sources(sources)

    # Trimmed for the browser...
    assert "Larry Page" not in previews[0]["content"]
    # ...but still present in what the model is given.
    assert "Larry Page" in sources[0]["content"]


def test_empty_source_list():
    assert preview_sources([]) == []
