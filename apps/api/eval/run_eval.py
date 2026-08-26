"""Measure retrieval quality against the golden set.

No LLM is involved: this only asks whether the chunks handed to the model
actually contain the answer. That makes it free, fast and deterministic, so it
can gate every commit — unlike generation metrics, which cost money and vary
between runs.

    docker compose exec api python eval/run_eval.py
    docker compose exec api python eval/run_eval.py --save baseline.json
    docker compose exec api python eval/run_eval.py --compare baseline.json

Runs against a throwaway ChromaDB in a temp directory, so the real storage/ tree
is never touched.
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
CORPUS_DIR = EVAL_DIR / "corpus"
GOLDEN_SET = EVAL_DIR / "golden_set.json"
KS = (1, 3, 5)
CORPUS_COLLECTION = "eval_corpus"

# Point the app at a scratch store before importing it — app.main builds its
# ChromaDB client and creates directories at import time.
_TMP = tempfile.mkdtemp(prefix="omnidocai-eval-")
os.environ["STORAGE_DIR"] = _TMP
sys.path.insert(0, str(EVAL_DIR.parent))

from app import main  # noqa: E402


def embed(texts):
    """Use the app's own embedding function, so the eval measures the real thing."""
    return [list(map(float, v)) for v in main.get_embedding_fn()(texts)]


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).lower()


def build_index() -> dict:
    """Chunk and embed the whole corpus into ONE collection.

    Every document could be indexed separately, but with only a handful of
    chunks each, asking for the top 5 returns the entire document and recall@5
    is 1.0 by construction — a metric that measures nothing. Pooling forces the
    retriever to pick the right document *and* the right chunk, which is both a
    real test and the direction the product is heading (multi-document chat).
    """
    ids, documents, metadatas = [], [], []
    indexed = {}

    for path in sorted(CORPUS_DIR.glob("*.md")):
        chunks = main.chunk_text(path.read_text(encoding="utf-8"))
        indexed[path.name] = chunks
        for i, chunk in enumerate(chunks):
            ids.append(f"{path.stem}_{i}")
            documents.append(chunk)
            metadatas.append({"document_name": path.name, "chunk_index": i})

    collection = main.chroma_client.create_collection(
        name=CORPUS_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )
    collection.add(
        ids=ids,
        documents=documents,
        embeddings=embed(documents),
        metadatas=metadatas,
    )
    return indexed


def rank_of_first_hit(question: str, document: str, evidence: str, top_k: int):
    """1-based rank of the first retrieved chunk that answers the question.

    A chunk counts only if it comes from the expected document *and* contains
    the evidence, so a lucky match in an unrelated file is not scored as a hit.
    """
    collection = main.chroma_client.get_collection(name=CORPUS_COLLECTION)

    result = collection.query(
        query_embeddings=embed([question]),
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas"],
    )
    needle = normalise(evidence)
    for position, (chunk, meta) in enumerate(
        zip(result["documents"][0], result["metadatas"][0]), start=1
    ):
        if meta["document_name"] == document and needle in normalise(chunk):
            return position
    return None


def evaluate() -> dict:
    golden = json.loads(GOLDEN_SET.read_text(encoding="utf-8"))["questions"]
    indexed = build_index()

    total_chunks = sum(len(c) for c in indexed.values())
    print(f"Corpus   : {len(indexed)} documents, {total_chunks} chunks")
    print(f"Questions: {len(golden)}\n")

    per_question = []
    for item in golden:
        rank = rank_of_first_hit(
            item["question"], item["document"], item["evidence"], max(KS)
        )
        per_question.append({**item, "rank": rank})

    hits = {k: sum(1 for q in per_question if q["rank"] and q["rank"] <= k) for k in KS}
    metrics = {f"recall@{k}": hits[k] / len(golden) for k in KS}
    metrics["mrr"] = sum(1 / q["rank"] for q in per_question if q["rank"]) / len(golden)

    misses = [q for q in per_question if not q["rank"]]
    if misses:
        print(f"Not retrieved in top {max(KS)} ({len(misses)}):")
        for q in misses:
            print(f"  {q['id']}  {q['question']}")
            print(f"        looking for: {q['evidence']!r}")
        print()

    weak = [q for q in per_question if q["rank"] and q["rank"] > 1]
    if weak:
        print(f"Retrieved but not ranked first ({len(weak)}):")
        for q in weak:
            print(f"  rank {q['rank']}  {q['id']}  {q['question']}")
        print()

    print("Metrics")
    for name, value in metrics.items():
        print(f"  {name:<10} {value:.3f}")

    return {
        "metrics": metrics,
        "chunks": total_chunks,
        "questions": len(golden),
        "ranks": {q["id"]: q["rank"] for q in per_question},
    }


def compare(current: dict, baseline_path: Path) -> None:
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    print(f"\nAgainst {baseline_path.name}")
    print(f"  {'metric':<10} {'before':>8} {'after':>8} {'delta':>8}")
    for name, after in current["metrics"].items():
        before = baseline["metrics"].get(name)
        if before is None:
            continue
        delta = after - before
        arrow = "+" if delta > 0.0005 else ("-" if delta < -0.0005 else " ")
        print(f"  {name:<10} {before:>8.3f} {after:>8.3f} {arrow}{abs(delta):>7.3f}")

    regressed = [
        qid for qid, rank in current["ranks"].items()
        if baseline["ranks"].get(qid) and (rank is None or rank > baseline["ranks"][qid])
    ]
    if regressed:
        print(f"\n  regressed questions: {', '.join(sorted(regressed))}")


def main_cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", metavar="FILE", help="write results for later comparison")
    parser.add_argument("--compare", metavar="FILE", help="compare against saved results")
    parser.add_argument("--fail-under", type=float, metavar="X",
                        help="exit non-zero if recall@5 falls below X (for CI)")
    args = parser.parse_args()

    try:
        results = evaluate()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)

    if args.compare:
        compare(results, EVAL_DIR / args.compare)

    if args.save:
        target = EVAL_DIR / args.save
        target.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nSaved to {target.relative_to(EVAL_DIR.parent)}")

    if args.fail_under is not None and results["metrics"]["recall@5"] < args.fail_under:
        print(f"\nFAIL: recall@5 {results['metrics']['recall@5']:.3f} < {args.fail_under}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
