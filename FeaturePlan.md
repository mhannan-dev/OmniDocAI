# OmniDocAI — Feature Plan

বর্তমান working scaffold থেকে একটা portfolio-grade RAG product পর্যন্ত রোডম্যাপ।
নিচের প্রতিটা আইটেম এই বিল্ডে **আসলে দেখা** কোনো সমস্যা থেকে এসেছে — সাধারণ
চেকলিস্ট থেকে নয়।

---

## 1. এখন প্রজেক্ট কোথায় দাঁড়িয়ে

**End to end কাজ করছে:** upload (`pdf` / `txt` / `md` / `docx`, সর্বোচ্চ 10 MB) →
text extraction → chunking → local embeddings → ChromaDB → নির্দিষ্ট ডকুমেন্টে
streamed উত্তর সহ chat, সাথে cited sources।

| Layer | কী আছে |
|---|---|
| API | FastAPI, ৫টা route: `/`, `GET /documents`, `POST /documents/upload`, `DELETE /documents/{id}`, `POST /chat` |
| Embeddings | `all-MiniLM-L6-v2`, 384-dim, লোকাল (API খরচ শূন্য), image-এ বেক করা |
| Vector store | ChromaDB, প্রতি ডকুমেন্টে একটা collection, cosine distance |
| Chat model | DeepSeek `deepseek-chat`, SSE দিয়ে stream |
| Registry | `storage/documents.json` — একটা সাধারণ ফাইল, ডাটাবেস নয় |
| Frontend | SvelteKit 5 + Tailwind 4, sidebar + chat, indexing চলাকালে poll করে |
| Tests / CI | নেই |

Helper script দুটো: `apps/api/scripts/inspect_db.py` (তিনটা storage layer-ই দেখায়),
`apps/api/scripts/rebuild_index.py` (ChromaDB-র ডিস্ক ফেরত আনে)।

---

## 2. যেসব দুর্বলতা এই প্ল্যানের ভিত্তি

প্রতিটাই এই codebase-এ reproduce করা, আর প্রতিটার সাথে সমাধানকারী task জোড়া দেওয়া।

**W1 — Exact identifier খুঁজে পায় না।**
৫০-chunk ডকুমেন্টে "section 147"-এর reference code চাইলে RX-1137, RX-1129 আর
RX-1145-এর chunk সঠিকটার উপরে উঠে এসেছিল। উত্তর ঠিক এসেছিল শুধু এজন্য যে
`top_k=5`-এ সঠিকটাও ঢুকে পড়েছিল। ২০০ chunk হলে মিস করত। Dense vector সংখ্যা,
কোড আর ID-তে দুর্বল।
→ *Hybrid search (T10), reranking (T11)*

**W2 — Chunk শব্দের মাঝখানে কাটছে।**
`Document.md`-এর chunk 1 শুরু হয় `"ny:** Alphabet Inc."` দিয়ে — "Parent Company"
দুই টুকরো হয়ে গেছে, কারণ fixed-size chunking শুধু `.` দেখে ভাঙে।
→ *Structure-aware chunking (T9)*

**W3 — Conversation সংরক্ষিত হয় না।**
`messages` শুধু ব্রাউজারের মেমরিতে; refresh দিলেই thread উধাও। প্রতিটা প্রশ্নও
স্বাধীন, তাই follow-up ("ওটা আরেকটু বুঝাও") কাজ করে না।
→ *Persistence (T1), query rewriting (T16)*

**W4 — Registry-তে write race আছে।**
প্রতিটা লেখা হলো load → mutate → save, একটাই JSON ফাইলে। দুজন একসাথে upload
করলে একটা entry নীরবে হারিয়ে যাবে।
→ *SQLite migration (T1)*

**W5 — Token usage আসছে, কিন্তু ফেলে দিচ্ছি।**
DeepSeek শেষ stream chunk-এ `CompletionUsage` ফেরত দেয় — `prompt_cache_hit_tokens`
আর `prompt_cache_miss_tokens` সহ — `stream_options` ছাড়াই। লাইভ API-তে যাচাই করা।
আমরা সেটা ফেলে দিচ্ছি।
→ *Usage capture (T2), cost dashboard (T5)*

**W6 — কোনো test নেই।**
দুটো আসল বাগ শিপ হয়েছিল, ধরা পড়েছে শুধু হাতে খুঁটিয়ে দেখে: `chunk_text`-এ একটা
infinite loop যেটা 6 GB RAM খেয়ে ফেলেছিল, আর ৫০০-অক্ষরের truncation যেটা প্রতিটা
retrieved chunk-এর অর্ধেক মডেলের কাছে পৌঁছানোর আগেই কেটে দিচ্ছিল। দুটোই কয়েক
মিনিটের unit test-এ ধরা পড়ত।
→ *Test suite (T3), retrieval eval (T7)*

**W7 — ডিলিট করা ডকুমেন্ট ডিস্ক ছাড়ে না।**
`delete_collection()`-এ ChromaDB না SQLite রো মোছে, না HNSW ফাইল। এই বিল্ডে
1.6 MB live-এর বিপরীতে 15.2 MB orphaned জমেছিল। `rebuild_index.py` দিয়ে সামলানো
যায়, কিন্তু সেটা ম্যানুয়াল রুটিন।
→ *Scheduled compaction (T24)*

**W8 — Dev reload watcher মরে গেছে।**
OOM-এর পর `watchfiles` `Cannot allocate memory` দিয়ে বন্ধ হয়ে আর ফেরেনি; এখন API
কোড বদলালে `docker compose restart api` দিতে হয়।
→ *T25*

---

## 3. Roadmap

Effort আন্দাজ: **S** ≈ কয়েক ঘণ্টা, **M** ≈ ১–২ দিন, **L** ≈ ৩+ দিন।

### Phase 1 — Foundation

একটা JSON ফাইলের উপর দাঁড়িয়ে কিছুই মাপা যায় না।

| # | Task | কেন | Effort |
|---|---|---|---|
| T1 | `documents.json` সরিয়ে SQLite (documents, chunks, conversations, messages, usage) | W4 সারায়; T2, T5, T16 আনলক করে | M |
| T2 | শেষ stream chunk থেকে `CompletionUsage` ধরে প্রতি query-তে সংরক্ষণ | W5 সারায়; ডেটা তো আসছেই | S |
| T3 | Test suite: `chunk_text` edge case, source truncation, upload validation | W6 সারায়; যে বাগগুলো খেয়েছি সেগুলোই কোডে বাঁধা পড়ে | S |

### Phase 2 — Cost visibility

প্রথম দৃশ্যমান ফিচার, আর Phase 1 হয়ে গেলে সস্তা।

| # | Task | কেন | Effort |
|---|---|---|---|
| T4 | খরচের হিসাব, rate `.env`-এ — কখনো hardcode নয় | DeepSeek cache-hit আর cache-miss input-এর দাম আলাদা রাখে, আর rate বদলায় | S |
| T5 | Dashboard route: প্রতি query / ডকুমেন্ট / দিনে token ও খরচ, cache hit-rate | দেখায় লোকাল embedding-এর সিদ্ধান্তটা কাজে দিয়েছে — embedding খরচ এখন শূন্য | M |

### Phase 3 — Measurement

Retrieval-এ হাত দেওয়ার **আগে** এটা বানাতে হবে, নাহলে উন্নতি প্রমাণ করা যাবে না।

| # | Task | কেন | Effort |
|---|---|---|---|
| T6 | Golden set: ২০–৩০টা প্রশ্ন, প্রত্যাশিত উত্তর ও source chunk সহ | এর পরের সবকিছুর মাপকাঠি | M |
| T7 | Deterministic retrieval metric: recall@k, MRR | LLM লাগে না — ফ্রি, দ্রুত, নির্ধারিত, CI-তে চলে | S |
| T8 | GitHub Actions: প্রতি push-এ test + retrieval eval | W6-এর মতো regression নিজে থেকেই ধরা পড়বে | S |

### Phase 4 — Retrieval engine

প্রতিটা task-এর পাশে Phase 3 থেকে before/after সংখ্যা থাকবে।

| # | Task | কেন | Effort |
|---|---|---|---|
| T9 | Structure-aware chunking (markdown heading ধরে ভাঙা, শব্দ কখনো না কাটা) | W2 সারায় | S |
| T10 | Hybrid search: BM25 + dense, fused | W1 সারায় — সবচেয়ে স্পষ্ট observed failure | M |
| T11 | Cross-encoder reranking: ২০টা এনে ৫টায় নামানো | সাধারণত মানের একক সবচেয়ে বড় লাফ | M |
| T12 | Contextual retrieval: embed করার আগে প্রতি chunk-এ ডকুমেন্ট-প্রেক্ষাপট জোড়া | মাপা যায় এমন উন্নতি; Phase 3 সায় দিলে তবেই রাখুন | M |
| T13 | Metadata filtering (document, type, date) | Multi-document scoping-এর পূর্বশর্ত | S |

### Phase 5 — Product

যা এটাকে demo থেকে product-এ পরিণত করে।

| # | Task | কেন | Effort |
|---|---|---|---|
| T14 | Multi-document chat — সব বা নির্বাচিত কয়েকটা জুড়ে প্রশ্ন | এখন একটার বেশি জিজ্ঞেস করা যায় না; RAG-এর আসল প্রতিশ্রুতি এটাই | M |
| T15 | Clickable citation — সোর্সে ক্লিক করলে ডকুমেন্ট খুলে ওই অংশ highlight | ডেমোতে এটাই "wow" মুহূর্ত | M |
| T16 | Conversation persist; query rewriting সহ multi-turn | W3 সারায় | M |
| T17 | Upload-এর পরই auto-summary আর ৩টা suggested question | ডেমোতে দারুণ, খাটুনি কম | S |
| T18 | Public deploy, ২–৩টা sample ডকুমেন্ট প্রি-লোড করে | রিভিউয়ার ৫ মিনিট দেয়, repo clone করবে না | M |

### Phase 6 — Agentic

| # | Task | কেন | Effort |
|---|---|---|---|
| T19 | Tool-using agent: search / compare / summarise — কোনটা লাগবে নিজে বাছে | Single-shot RAG-এর বাইরে orchestration দেখায় | L |
| T20 | Multi-step retrieval — agent নিজে ঠিক করে আরেকবার খুঁজতে হবে কিনা | এক দফা retrieval-এ যেসব প্রশ্নের উত্তর হয় না, সেগুলো সামলায় | M |
| T21 | Citation verification: প্রতিটা দাবি সোর্সে আছে কিনা যাচাই | সরাসরি anti-hallucination গল্প | M |
| T22 | Cross-document comparison | T14 আর T19-এর উপর দাঁড়ায় | M |

### Phase 7 — Generation quality

| # | Task | কেন | Effort |
|---|---|---|---|
| T23 | RAGAS — faithfulness ও answer relevancy, judge হিসেবে DeepSeek, embeddings লোকাল | Deterministic retrieval metric-এর উপরে দ্বিতীয় স্তর | M |
| T24 | `rebuild_index.py` দিয়ে scheduled compaction | W7 স্বয়ংক্রিয় করে | S |
| T25 | Dev reload ফেরানো, নাহলে restart-এর নিয়ম ডকুমেন্ট করা | W8 সারায় | S |

---

## 4. ইচ্ছাকৃতভাবে বাদ

**TruLens.** এর মূল আকর্ষণ নিজস্ব Streamlit dashboard। SvelteKit থাকতে শুধু ওটার
জন্য তৃতীয় একটা সার্ভিস দাঁড় করানো অদ্ভুত, আর নিজে dashboard বানালে অন্যের
রেডিমেড বসানোর চেয়ে অনেক বেশি দক্ষতা দেখায়।

**CI-তে RAGAS.** এর metric গুলো LLM-judged, তাই প্রতিবার টাকা লাগে আর ফল একটু
অস্থির। ম্যানুয়ালি বা রাতে চালান; CI-তে deterministic metric (T7) রাখুন।

**Auth, team, billing.** রক্ষণাবেক্ষণের খরচ আসল, portfolio-তে মূল্য শূন্য।
রিভিউয়ার অ্যাকাউন্ট খুলতে চাইবেন না।

**Cloud embedding API.** লোকাল MiniLM এমনিতেই 384-dim vector দিচ্ছে, প্রান্তিক
খরচ শূন্যে। আবার পেইড API-তে ফিরলে T5-এর খরচের গল্পটাই দুর্বল হয়ে যাবে।

---

## 5. সুপারিশকৃত ক্রম

Phase 1 → 2 → 3, তারপর Phase 4 — প্রতিটা ধাপ মেপে মেপে, এরপর ডেমোর জন্য Phase 5।
Phase 6 আর 7 হলো differentiator, ভিত্তি পাকা হওয়ার পর।

এই প্ল্যান থেকে সবচেয়ে শক্তিশালী যে জিনিসটা বেরোতে পারে: README-তে একটা টেবিল,
যেখানে Phase 4-এর প্রতিটা পরিবর্তনের আগে-পরে retrieval quality-র সংখ্যা থাকবে,
আর সংখ্যাগুলো আসবে Phase 3 থেকে। খুব কম portfolio প্রজেক্ট এটা দেখাতে পারে।
