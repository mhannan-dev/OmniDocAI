# OmniDocAI — Production-Grade Multilingual RAG Engine & Document Workspace

[![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![SvelteKit](https://img.shields.io/badge/SvelteKit-2.0-FF3E00?logo=svelte&logoColor=white)](https://kit.svelte.dev/)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector_Store-orange)](https://www.trychroma.com/)
[![DeepSeek](https://img.shields.io/badge/LLM-DeepSeek--V3-blueviolet)](https://www.deepseek.com/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Tests](https://img.shields.io/badge/Tests-60%2F60%20Passing-brightgreen)](https://docs.pytest.org/)

**OmniDocAI** is an end-to-end, production-grade Retrieval-Augmented Generation (RAG) platform and conversational document workspace. Built from first principles, it features **multilingual hybrid search (BM25 + Dense RRF)**, an **automated retrieval evaluation suite with empirical benchmarks**, **interactive in-document citation highlighting**, and **multi-document cross-synthesis**.

---

## 🏗️ System Architecture

```
                                 [ User Web Interface ]
                            (SvelteKit 5 + TailwindCSS)
                                         │
                         Server-Sent Events (SSE) / REST
                                         ▼
                             [ FastAPI Core Backend ]
     ┌───────────────────────────────────┼───────────────────────────────────┐
     ▼                                   ▼                                   ▼
[ Document Ingestion ]         [ Hybrid Search Engine ]            [ SQLite DB (WAL) ]
 ├─ pdfplumber (PDF)            ├─ Dense: Multilingual MiniLM       ├─ documents table
 ├─ python-docx (Tables)        ├─ Lexical: Custom BM25Okapi        ├─ conversations
 ├─ JSON flattener              └─ Fusion: RRF (k=60)               ├─ messages
 └─ Heading-aware chunker                │                          └─ token/cache usage
                                         ▼
                               [ DeepSeek LLM API ]
                       (Contextual Grounding + SSE Stream)
```

---

## 🌟 Core Engineering Highlights

* 🔍 **Multilingual Hybrid Search with Reciprocal Rank Fusion (RRF)**: Overcomes dense vector blind spots on exact codes (`X-Request-Id`, `HR-311`) and non-Latin scripts (Bengali Unicode) by fusing BM25 with dense cosine similarities ($k=60$).
* 🎯 **Interactive In-Context Citation Grounding**: Solves hallucination verification by letting users click any source citation card to open the document viewer, auto-scroll to, and highlight the cited passage with glowing `<mark>` tags.
* 🌐 **Multi-Document Workspace Cross-Search**: Dedicated "All Documents" workspace mode that searches and contrasts across all files simultaneously.
* ⚡ **Zero-Click Document Onboarding**: Automatically generates a 2-sentence executive summary and 3 clickable starter question chips in the document's native language.
* 💾 **SQLite WAL Persistence & Observability**: Thread history, cascading deletions, and live DeepSeek prompt-cache hit telemetry (`prompt_cache_hit_tokens`).

---

## 🛠️ Tech Stack

| Layer | Technologies | Key Responsibilities |
|---|---|---|
| **Backend** | Python 3.11, FastAPI, Uvicorn | Async SSE streaming, REST API, file parsing, token telemetry |
| **Search Engine** | ChromaDB, FastEmbed, Custom BM25 | 384-dim multilingual embeddings, inverted lexical index, RRF ($k=60$) |
| **LLM Provider** | DeepSeek V3 (`deepseek-chat`) | Low-latency chat completion, structured JSON extraction |
| **Database** | SQLite3 (WAL Mode) | Persistent documents, chat sessions, message history, token usage |
| **Frontend** | SvelteKit 5, TypeScript, TailwindCSS | Reactive chat UI, citation modal, zero-click question chips |
| **DevOps** | Docker, Docker Compose | Multi-container reproducible runtime with bind mounts |

---

## 📊 Empirical Retrieval Evaluation

Retrieval quality is measured deterministically without calling LLMs, ensuring tests run quickly and repeatably in CI on every commit.

```bash
# Generate evaluation report against the 48-question golden set
docker compose exec api python eval/run_eval.py

# Run with CI regression gate (e.g. fail if recall@5 < 90%)
docker compose exec api python eval/run_eval.py --fail-under 0.90
```

### Benchmark Progression (Golden Set: 48 Questions across English & Bengali)

| Stage | Model / Strategy | Questions | recall@1 | recall@3 | recall@5 | MRR |
|---|---|---|---|---|---|---|
| `01` | Fixed-size chunking (English-only) | 36 | 0.722 | 0.861 | 0.944 | 0.793 |
| `02` | Structure-aware chunking (Heading paths) | 36 | 0.639 | 0.917 | 0.972 | 0.772 |
| `03` | Added Bengali test suite | 48 | 0.479 | 0.792 | 0.979 | 0.653 |
| `04` | Multilingual embeddings (`paraphrase-multilingual`) | 48 | 0.438 | 0.729 | 0.896 | 0.597 |
| `05` | **Hybrid Search (BM25 + Dense RRF)** | **48** | **0.583** | **0.917** | **0.958** | **0.751** |

> **Key Takeaway**: Introducing Hybrid Search over the multilingual dense baseline increased `recall@1` from **0.438 → 0.583 (+14.6%)**, `recall@3` from **0.729 → 0.917 (+18.8%)**, and `MRR` from **0.597 → 0.751 (+15.5%)**, eliminating top identifier misses (`Retry-After`, `HR-311`, `Due 4 April`).

---

## 🚀 Quick Start

### 1. Clone & Configure Environment

```bash
git clone https://github.com/yourusername/OmniDocAI.git
cd OmniDocAI

# Copy environment template and configure DeepSeek API key
cp .env.example .env
```

Edit `.env`:
```ini
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
STORAGE_DIR=/app/storage
```

### 2. Launch with Docker Compose

```bash
docker compose up --build -d
```

| Service | URL |
|---|---|
| **Web UI** | [http://localhost:5173](http://localhost:5173) |
| **FastAPI Swagger Docs** | [http://localhost:8000/docs](http://localhost:8000/docs) |
| **API Health Check** | [http://localhost:8000/](http://localhost:8000/) |

Both services mount source directories with live reload enabled.

---

## 🧪 Testing & Verification

OmniDocAI maintains comprehensive automated test coverage across both backend and frontend layers:

### Run Backend Unit & Integration Tests (60/60 Passing)

```bash
docker compose exec api python -m pytest tests/ -v
```

| Test Suite | Coverage & Guards |
|---|---|
| `test_chunking.py` | Heading-aware chunk budget splits, table parsing, loop termination guards |
| `test_hybrid_search.py` | Multilingual tokenization, exact identifier retention, BM25 scoring, RRF rank fusion |
| `test_database.py` | SQLite WAL persistence, cascading deletions, multi-turn message history, token usage |
| `test_upload.py` | File validation (.pdf, .docx, .md, .txt, .json), 10MB limits, multi-document search (`__all__`), summary caching |
| `test_sources.py` | Citation payload integrity, raw content preservation for frontend text highlighting |

### Run Frontend Type & Component Checks

```bash
docker compose exec web npm run check
```

---

## 📂 Project Structure

```
OmniDocAI/
├── apps/
│   ├── api/
│   │   ├── app/
│   │   │   ├── main.py        # FastAPI endpoints, SSE streaming, multi-doc search
│   │   │   ├── search.py      # Custom BM25Index, multilingual tokenizer, RRF (k=60)
│   │   │   └── db.py          # SQLite database layer (WAL mode, foreign keys)
│   │   ├── eval/
│   │   │   ├── golden_set.json # 48-question retrieval evaluation set
│   │   │   └── run_eval.py    # Metric runner (Recall@K, MRR, ablation reports)
│   │   └── tests/             # Pytest test suite (60 unit & integration tests)
│   └── web/
│       ├── src/
│       │   ├── lib/
│       │   │   ├── ChatInterface.svelte  # Chat UI, summary card, question chips
│       │   │   ├── DocViewerModal.svelte # In-document citation highlight modal
│       │   │   └── Sidebar.svelte        # Document list & "All Documents" toggle
│       │   └── routes/+page.svelte       # Main layout & state orchestrator
├── storage/                   # Persistent volume (SQLite DB, ChromaDB, uploads)
├── docker-compose.yml         # Multi-container orchestration
└── README.md
```

---

## 📄 License

This project is licensed under the MIT License.
