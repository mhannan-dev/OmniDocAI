# OmniDocAI

Minimal scaffold: FastAPI backend + SvelteKit/Tailwind frontend, wired together with Docker Compose.

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

| Service | URL |
| --- | --- |
| API health | http://localhost:8000/health |
| API docs | http://localhost:8000/docs |
| Web UI | http://localhost:5173 |

Both services run with live reload — edits under `apps/api` and `apps/web` apply without a rebuild.

## Layout

```
apps/api      FastAPI app (app/main.py)
apps/web      SvelteKit app (src/routes)
storage/      Shared, persistent volumes
  chroma_db/  Vector store
  uploads/    Uploaded documents
```

## Tests

Dev dependencies are kept out of the runtime image, so install them into the
running container first:

```bash
docker compose exec api sh -c "pip install -q -r requirements-dev.txt && python -m pytest"
```

`tests/conftest.py` redirects `STORAGE_DIR` to a temp directory before importing
the app, so runs never touch `storage/`.

What is covered:

| File | Guards against |
|---|---|
| `test_chunking.py` | The `chunk_text` loop that never terminated — a 2 KB file grew the container to 6 GB and blocked the event loop |
| `test_sources.py` | Truncating retrieved chunks to 500 characters *before* building the model context, which silently hid half of every chunk |
| `test_upload.py` | File-type validation, the 10 MB cap, registry listing and delete |

## Retrieval evaluation

Measures whether the chunks handed to the model actually contain the answer.
No LLM is involved, so it is free, fast and deterministic — safe to run on every
commit, unlike generation metrics.

```bash
docker compose exec api python eval/run_eval.py                      # report
docker compose exec api python eval/run_eval.py --save baseline.json # record
docker compose exec api python eval/run_eval.py --compare baseline.json
docker compose exec api python eval/run_eval.py --fail-under 0.90    # CI gate
```

| File | Purpose |
|---|---|
| `eval/corpus/` | Three documents that exercise known weak spots: identifiers, codes, facts near chunk seams |
| `eval/golden_set.json` | 36 questions, each with an `evidence` snippet |
| `eval/baseline.json` | Recorded scores to compare against |

Relevance is marked by an evidence snippet, **not** a chunk index — indices shift
whenever chunking changes, which is exactly when the golden set matters most.
The whole corpus is pooled into one collection so the retriever has to pick the
right document as well as the right chunk; indexing each document separately
would make `recall@5` 1.0 by construction.

Results are snapshotted in `eval/results/` so each change can be compared
against the one before it.

| Change | recall@1 | recall@3 | recall@5 | MRR |
|---|---|---|---|---|
| 01 Fixed-size chunking | **0.722** | 0.861 | 0.944 | **0.793** |
| 02 Structure-aware chunking (T9) | 0.639 | **0.917** | **0.972** | 0.772 |

A deliberate trade. `search_document` retrieves `top_k=5` and puts **all five**
chunks into the model's context, so recall@5 is what decides whether the model
can answer at all; recall@1 and MRR would matter more if a single chunk were
shown or used. Structure-aware chunking wins on recall@3 and recall@5 and gives
up ranking precision, so it is kept.

An ablation confirmed the heading-path prefix carries its weight — without it,
recall@5 falls to 0.917 and recall@3 to 0.889.

Still unretrieved: `X-Request-Id`, an exact identifier. That is the weakness
hybrid search (T10 in `FeaturePlan.md`) exists to close.
