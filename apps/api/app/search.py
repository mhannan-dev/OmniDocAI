"""Hybrid search engine combining BM25 lexical retrieval with dense vector search using Reciprocal Rank Fusion (RRF)."""
import re
import math
from collections import Counter
from typing import List, Dict, Any, Tuple, Optional

# Match words: sequences of alphanumeric characters and hyphens/underscores, OR Bengali characters
WORD_RE = re.compile(r'[a-zA-Z0-9]+(?:[-_][a-zA-Z0-9]+)*|[\u0980-\u09FF]+')


def tokenize(text: str) -> List[str]:
    """Tokenize text for BM25.

    Preserves exact identifiers like X-Request-Id, HR-311, FIN-88, sk_test_
    and splits sub-parts so both exact tokens and partial keywords match.
    Supports Bengali Unicode words natively.
    """
    if not text:
        return []
    tokens = []
    for match in WORD_RE.finditer(text.lower()):
        token = match.group()
        tokens.append(token)
        # If token contains '-' or '_', also add sub-parts so both exact token and components match
        if '-' in token or '_' in token:
            sub_parts = re.split(r'[-_]+', token)
            for part in sub_parts:
                if part and part != token:
                    tokens.append(part)
    return tokens


class BM25Index:
    """BM25Okapi inverted index with positive Robertson-Spärck Jones IDF."""

    def __init__(self, corpus_chunks: List[str], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus_size = len(corpus_chunks)
        self.doc_lengths = []
        self.doc_token_counts = []
        self.df = Counter()

        for chunk in corpus_chunks:
            tokens = tokenize(chunk)
            self.doc_lengths.append(len(tokens))
            counts = Counter(tokens)
            self.doc_token_counts.append(counts)
            for token in counts:
                self.df[token] += 1

        self.avgdl = (sum(self.doc_lengths) / max(1, self.corpus_size)) if self.corpus_size > 0 else 1.0
        self.idf = {}
        for token, freq in self.df.items():
            # Standard non-negative Okapi variant (Lucene / RankBM25)
            self.idf[token] = math.log(((self.corpus_size - freq + 0.5) / (freq + 0.5)) + 1.0)

    def get_scores(self, query: str) -> List[float]:
        """Compute BM25 relevance scores for all documents given a query string."""
        query_tokens = tokenize(query)
        scores = [0.0] * self.corpus_size
        if not query_tokens or self.corpus_size == 0:
            return scores

        for q in query_tokens:
            if q not in self.idf:
                continue
            q_idf = self.idf[q]
            for idx, counts in enumerate(self.doc_token_counts):
                tf = counts.get(q, 0)
                if tf == 0:
                    continue
                doc_len = self.doc_lengths[idx]
                denom = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / self.avgdl))
                scores[idx] += q_idf * (tf * (self.k1 + 1.0)) / denom

        return scores


def reciprocal_rank_fusion(
    dense_ranked_ids: List[str],
    bm25_ranked_ids: List[str],
    k: int = 60,
    dense_weight: float = 1.0,
    bm25_weight: float = 1.0
) -> List[Tuple[str, float]]:
    """Compute Reciprocal Rank Fusion (RRF) scores across two ranked candidate lists."""
    rrf_scores: Dict[str, float] = {}

    for rank, doc_id in enumerate(dense_ranked_ids, start=1):
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + (dense_weight / (k + rank))

    for rank, doc_id in enumerate(bm25_ranked_ids, start=1):
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + (bm25_weight / (k + rank))

    sorted_results = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_results


def hybrid_search(
    query: str,
    all_ids: List[str],
    all_chunks: List[str],
    all_metadatas: List[Dict[str, Any]],
    dense_results: Dict[str, Any],
    top_k: int = 5,
    document_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Perform hybrid search fusing ChromaDB dense retrieval with BM25 lexical ranking."""
    if not all_ids or not all_chunks:
        return []

    # Map id -> (chunk_text, metadata)
    doc_map = {cid: (chunk, meta) for cid, chunk, meta in zip(all_ids, all_chunks, all_metadatas)}

    # 1. Dense rankings
    dense_ranked_ids = []
    if dense_results and dense_results.get("ids") and dense_results["ids"][0]:
        dense_ranked_ids = dense_results["ids"][0]

    # 2. BM25 rankings
    bm25_index = BM25Index(all_chunks)
    bm25_scores = bm25_index.get_scores(query)

    # Pair all IDs with their BM25 score
    bm25_scored = list(zip(all_ids, bm25_scores))
    # Only keep chunks that had a non-zero match for BM25 ranking
    bm25_matching = [item for item in bm25_scored if item[1] > 0.0]
    bm25_matching.sort(key=lambda x: x[1], reverse=True)
    bm25_ranked_ids = [item[0] for item in bm25_matching]

    # 3. Reciprocal Rank Fusion
    fused_ranking = reciprocal_rank_fusion(dense_ranked_ids, bm25_ranked_ids, k=60)

    # 4. Form final top_k results
    sources = []
    max_rrf = fused_ranking[0][1] if fused_ranking else 1.0

    for doc_id, rrf_score in fused_ranking[:top_k]:
        if doc_id not in doc_map:
            continue
        content, metadata = doc_map[doc_id]
        norm_score = round(rrf_score / max_rrf, 4) if max_rrf > 0 else 0.0
        sources.append({
            "document_id": metadata.get("document_id", document_id or "Unknown"),
            "document_name": metadata.get("document_name", "Unknown"),
            "content": content,
            "score": norm_score,
            "chunk_id": doc_id,
        })

    return sources
