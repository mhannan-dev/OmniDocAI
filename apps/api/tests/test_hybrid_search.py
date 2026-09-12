"""Tests for Hybrid Search: multilingual BM25, tokenization, and Reciprocal Rank Fusion."""
import pytest
from app.search import tokenize, BM25Index, reciprocal_rank_fusion, hybrid_search


def test_tokenize_preserves_identifiers():
    text = "Check header X-Request-Id and API key sk_test_secret123 with Policy HR-311."
    tokens = tokenize(text)
    assert "x-request-id" in tokens
    assert "x" in tokens
    assert "request" in tokens
    assert "id" in tokens
    assert "hr-311" in tokens
    assert "hr" in tokens
    assert "311" in tokens
    assert "sk_test_secret123" in tokens


def test_tokenize_bengali_unicode():
    text = "বগুড়ায় অবস্থিত প্রাচীনতম নগর মহাস্থানগড়।"
    tokens = tokenize(text)
    assert "বগুড়ায়" in tokens
    assert "অবস্থিত" in tokens
    assert "প্রাচীনতম" in tokens
    assert "নগর" in tokens
    assert "মহাস্থানগড়" in tokens


def test_bm25_exact_match_ranking():
    chunks = [
        "This is an employee handbook about daily work hours and parking regulations.",
        "Under Policy HR-311, employees must register all corporate devices with IT security.",
        "Travel expense reimbursement guidelines are outlined in section finance.",
    ]
    index = BM25Index(chunks)
    scores = index.get_scores("What does HR-311 govern?")

    assert scores[1] > 0.0
    assert scores[1] > scores[0]
    assert scores[1] > scores[2]
    # The chunk with HR-311 must score highest
    best_idx = scores.index(max(scores))
    assert best_idx == 1


def test_bm25_bengali_keyword_match():
    chunks = [
        "সুন্দরবন বাংলাদেশের একটি বিখ্যাত প্রাকৃতিক ম্যানগ্রোভ বন।",
        "সিলেট জেলা প্রাচীনকাল থেকেই চা বাগানের জন্য বিশ্বখ্যাত।",
        "রাজশাহী জেলা তার সুস্বাদু আম ও রেশম শিল্পের জন্য পরিচিত।",
    ]
    index = BM25Index(chunks)
    scores = index.get_scores("চা বাগান কোন জেলা?")

    assert scores[1] > 0.0
    best_idx = scores.index(max(scores))
    assert best_idx == 1


def test_reciprocal_rank_fusion():
    dense_ranked = ["doc_a", "doc_b", "doc_c", "doc_d"]
    bm25_ranked = ["doc_c", "doc_a", "doc_e"]

    fused = reciprocal_rank_fusion(dense_ranked, bm25_ranked, k=60)
    top_ids = [item[0] for item in fused]

    # doc_a is rank 1 in dense, rank 2 in bm25 -> very high RRF
    # doc_c is rank 3 in dense, rank 1 in bm25 -> very high RRF
    assert top_ids[0] in {"doc_a", "doc_c"}
    assert top_ids[1] in {"doc_a", "doc_c"}
    # doc_e is only in bm25, but should still be in fused results
    assert "doc_e" in top_ids


def test_hybrid_search_end_to_end():
    chunks = [
        "General introduction about cloud infrastructure and web servers.",
        "Error 429: Rate limit exceeded. Refer to Retry-After response header.",
        "Database connection pooling recommendations and timeouts.",
    ]
    ids = ["c0", "c1", "c2"]
    metadatas = [{"document_name": "api.md"}, {"document_name": "api.md"}, {"document_name": "api.md"}]

    # Simulate dense results where c1 was ranked poorly (e.g. at position 2 behind c0)
    dense_results = {
        "ids": [["c0", "c1", "c2"]],
        "distances": [[0.1, 0.4, 0.5]],
        "documents": [chunks],
        "metadatas": [metadatas],
    }

    results = hybrid_search(
        query="What does Retry-After mean?",
        all_ids=ids,
        all_chunks=chunks,
        all_metadatas=metadatas,
        dense_results=dense_results,
        top_k=3,
        document_id="doc123"
    )

    assert len(results) == 3
    # c1 has the exact keyword Retry-After, so it should rank #1 in hybrid search
    assert results[0]["chunk_id"] == "c1"
    assert "Retry-After" in results[0]["content"]
    assert results[0]["score"] == 1.0  # normalized max
