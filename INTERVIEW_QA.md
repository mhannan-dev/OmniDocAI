# OmniDocAI — Interview Questions & Answers

প্রশ্নগুলো ইংরেজিতেই রাখা, কারণ ইন্টারভিউয়ার ওভাবেই জিজ্ঞেস করবেন। ব্যাখ্যা
বাংলায়, technical term ইংরেজিতে — যাতে বোঝাটা সহজ হয় কিন্তু বলার সময় শব্দগুলো
হাতের কাছেই থাকে।

---

## System Architecture

### Q: What is Retrieval-Augmented Generation (RAG)?

**A:** একটা LLM শুধু ততটুকুই জানে যতটুকু তার training data-তে ছিল। আপনার
কোম্পানির handbook, গতকালের incident report, বা আপনার আপলোড করা PDF — এসবের
কিছুই সে জানে না। জিজ্ঞেস করলে হয় "জানি না" বলবে, নয়তো আত্মবিশ্বাসের সাথে বানিয়ে
বলবে।

**RAG** সেই ফাঁকটা ভরে — মডেলকে নতুন করে শেখানোর বদলে, প্রশ্নের সাথে প্রাসঙ্গিক
অংশটুকু **খুঁজে এনে prompt-এর সাথে জুড়ে দিয়ে**। নামটার দুটো ভাগ:

- **Retrieval** — প্রশ্নের সাথে মিলে যায় এমন কয়েকটা টুকরো ডকুমেন্ট থেকে বের করা
- **Augmented Generation** — সেই টুকরোগুলো prompt-এ যোগ (augment) করে মডেলকে
  দিয়ে উত্তর লেখানো

মূল কথাটা: **মডেল বদলায় না, prompt বদলায়।**

**কীভাবে কাজ করে** (দুটো পর্যায়):

*Indexing — আগে, একবার:*
ডকুমেন্ট → টেক্সট বের করা → chunk-এ ভাঙা → প্রতিটা chunk-কে **embedding**
(অর্থ বহনকারী সংখ্যার তালিকা, এখানে 384টা সংখ্যা) বানানো → vector database-এ রাখা

*Query — প্রতিবার প্রশ্নে:*
প্রশ্নকেও embedding বানানো → যে chunk-গুলোর embedding প্রশ্নের সবচেয়ে কাছাকাছি
সেগুলো তোলা → prompt-এ বসানো → মডেল শুধু ওই টুকু পড়ে উত্তর দেয়

**কেন embedding, শুধু keyword খোঁজা নয়?** কারণ "চা বাগানের জন্য বিখ্যাত জেলা
কোনটি?" প্রশ্নে "সিলেট" শব্দটা নেই। Embedding অর্থ ধরে, তাই শব্দ না মিললেও
প্রাসঙ্গিক অংশ পাওয়া যায়। (উল্টো দিকে, হুবহু কোড বা ID খুঁজতে embedding দুর্বল —
সেজন্যই hybrid search দরকার, যেটা এই প্রজেক্টের পরের কাজ।)

**এই প্রজেক্টে বাস্তবে:**

```
Upload → Text Extraction → Chunking → Embedding → ChromaDB
                                                      ↓
প্রশ্ন → Embedding → Vector Search (top_k=5) → Context + DeepSeek → উত্তর
```

---

### Q: Why RAG instead of fine-tuning, or just pasting the whole document?

**A:** তিনটে পথই সম্ভব, কিন্তু কাজ আলাদা:

| | সমস্যা |
|---|---|
| **Fine-tuning** | ব্যয়বহুল ও ধীর; নতুন ডকুমেন্ট যোগ হলেই আবার train করতে হয়। আর fine-tuning মডেলকে *ভঙ্গি* শেখাতে ভালো, *তথ্য* মনে রাখাতে দুর্বল — ভুল তথ্য দিলে কোথা থেকে এল সেটাও দেখানো যায় না |
| **পুরো ডকুমেন্ট prompt-এ** | context window-এ সীমা আছে; ১০০টা ডকুমেন্ট আঁটবে না। আঁটলেও প্রতিটা প্রশ্নে পুরোটার টোকেন খরচ হবে, আর অপ্রাসঙ্গিক লেখা উত্তরের মান কমায় |
| **RAG** | নতুন ডকুমেন্ট মানে শুধু নতুন index; মডেল অপরিবর্তিত। প্রতি প্রশ্নে শুধু প্রাসঙ্গিক ~৫টা chunk যায়, তাই খরচ কম। **আর কোন অংশ থেকে উত্তর এল সেটা দেখানো যায়** — citation |

শেষ পয়েন্টটা এই অ্যাপে গুরুত্বপূর্ণ: প্রতিটা উত্তরের সাথে source আর relevance
score ফেরত যায়, তাই ব্যবহারকারী নিজে যাচাই করতে পারেন।

**যে follow-up আসতে পারে** — *"context window তো এখন অনেক বড়, RAG কি অপ্রয়োজনীয়
হয়ে যাচ্ছে?"* বড় window কিছু কেস সহজ করেছে ঠিকই, কিন্তু খরচ, latency, আর
"অপ্রাসঙ্গিক লেখা ঢুকলে উত্তর খারাপ হয়" — এই তিনটে রয়ে গেছে। আর citation দেখানোর
ক্ষমতা RAG-এর নিজস্ব, window বড় হলেও সেটা আসে না।

---

### Q: Describe the overall architecture of this application.

**A:** OmniDocAI একটা document intelligence platform, **RAG
(Retrieval-Augmented Generation)** স্থাপত্যে বানানো:

- **Frontend**: SvelteKit + Tailwind CSS (TypeScript), port 5173
- **Backend**: FastAPI (Python), REST API port 8000
- **Vector Store**: ChromaDB (local, persistent)
- **LLM**: chat completion-এ DeepSeek API; embedding লোকালি, fastembed দিয়ে
- **Document Processing**: pdfplumber (PDF), python-docx টেবিলসহ (DOCX),
  flatten করা JSON, native (TXT/MD)
- **Deployment**: Docker Compose, development-এ live reload

ডেটার পথ: Upload → Text Extraction → Chunking → Embedding → ChromaDB → Query →
Vector Search → Context + DeepSeek → Streaming Response

---

### Q: Why use ChromaDB instead of a traditional database?

**A:** ChromaDB বিশেষভাবে vector similarity search-এর জন্য বানানো:

- ANN search-এর জন্য native HNSW index
- embedding, metadata আর মূল টেক্সট — সব এক জায়গায়
- pgvector extension বা আলাদা vector infrastructure লাগে না
- শূন্য কনফিগে persistent local storage

সৎ সীমাবদ্ধতা: single-node, তাই HA নেই। Multi-tenancy দরকার হলে বা স্কেলে গেলে
pgvector ভালো পছন্দ — আর তখন এখানকার per-document collection ডিজাইনটাই সবার আগে
বদলাতে হবে।

---

### Q: How does the embedding pipeline work?

**A:**
1. **Extract**: pdfplumber / python-docx / JSON flatten / raw text → plain text
2. **Chunk**: structure-aware — আগে markdown heading ধরে, তারপর paragraph,
   sentence, word; শব্দ কখনো মাঝখানে কাটে না। প্রতি chunk তার heading path বহন করে
3. **Embed**: `paraphrase-multilingual-MiniLM-L12-v2` (384-dim, ONNX, লোকাল)
4. **Store**: প্রতি ডকুমেন্টে আলাদা ChromaDB collection (`doc_{uuid}`), cosine distance
5. **Query**: প্রশ্ন embed → vector search (top_k=5) → chunk ও score ফেরত

---

### Q: Why use local embeddings instead of DeepSeek/OpenAI embeddings?

**A:** প্রথম কারণটা বাধ্যবাধকতা: **DeepSeek-এ embeddings endpoint নেই** (এই নিয়ে
নিচে একটা bug story আছে)। এরপর যা যা পাওয়া গেল:

- **খরচ**: embedding-এ শূন্য API কল, DeepSeek শুধু chat-এ
- **Latency**: লোকাল inference, নেটওয়ার্ক round-trip নেই
- **Privacy**: embed করতে ডকুমেন্টের লেখা সার্ভারের বাইরে যায় না
- **Reliability**: core retrieval কোনো বাইরের সেবার উপর নির্ভর করে না

কোন মডেল, সেই সিদ্ধান্তটা মেপে নেওয়া — নিচে "Decisions I measured" দেখুন।

---

## Backend (FastAPI)

### Q: How do you handle long-running document indexing without blocking the API?

**A:** Background task, তবে reference ধরে রেখে:

```python
_background_tasks = set()

def spawn(coro):
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task

spawn(index_document(doc))   # সাথে সাথে ফেরত, indexing পেছনে চলে
```

**কেন set-টা জরুরি:** asyncio task-এর শুধু **weak reference** রাখে। খালি
`asyncio.create_task()` লিখে ছেড়ে দিলে কাজ শেষ হওয়ার আগেই garbage collector
সেটা মুছে দিতে পারে। এই বাগটা এখানে সত্যিই হয়েছিল।

Status: `processing` → `ready` | `error`, আর সেটা লেখে indexing কোড নিজেই।

---

### Q: How is streaming chat implemented?

**A:** `StreamingResponse` দিয়ে Server-Sent Events (SSE):

```python
async def generate_chat_response(query, doc_id):
    stream = await deepseek_client.chat.completions.create(
        model="deepseek-chat", messages=[...], stream=True
    )
    async for chunk in stream:
        if chunk.choices[0].delta.content:
            yield f"data: {json.dumps({'content': piece})}\n\n"
    yield f"data: {json.dumps({'sources': preview_sources(sources)})}\n\n"
    yield "data: [DONE]\n\n"
```

`Cache-Control: no-cache` আর `X-Accel-Buffering: no` header দুটো জরুরি — নাহলে
proxy পুরো response জমিয়ে একবারে পাঠাবে, streaming-এর মানেই থাকবে না।

Frontend `ReadableStream` + `TextDecoder` দিয়ে SSE পার্স করে।

---

### Q: How do you handle file uploads and validation?

**A:**
- FormData পার্স করতে `python-multipart`
- Extension আগে যাচাই, তারপর MIME type (`application/octet-stream` হলে extension
  থেকে অনুমান — ব্রাউজার প্রায়ই ওটাই পাঠায়)
- অনুমোদিত: PDF, TXT, MD, MARKDOWN, DOCX, JSON
- সর্বোচ্চ 10MB
- UUID ফাইলনাম, তাই একই নামের দুটো ফাইল সংঘর্ষ করে না

**যেটা এখনো দুর্বল:** size check হয় ডিস্কে **সেভ করার পরে**। 500MB ফাইল দিলে
পুরোটা লেখা হবে, তারপর মুছে ফেলা হবে। streaming-এ গুনে গুনে থামানো উচিত।

---

### Q: How do you manage document metadata persistence?

**A:** একটা সাধারণ JSON ফাইল (`/app/storage/documents.json`), Pydantic model দিয়ে
validate করা। Field: id, name, size, type, uploadedAt, status, path, chunks,
embeddingModel, indexVersion, error।

**এখানে একটা আসল bug আছে, নিজে থেকে বলবেন:** প্রতিটা লেখা হলো
load → mutate → save। দুজন একসাথে upload করলে একজনের entry নীরবে হারিয়ে যাবে —
ক্লাসিক read-modify-write race। SQLite-ই এর সমাধান, আর সেটাই roadmap-এর প্রথম কাজ।

---

## Frontend (SvelteKit)

### Q: How does the sidebar communicate with the chat area?

**A:** Custom DOM event দিয়ে:

```typescript
// Sidebar
window.dispatchEvent(new CustomEvent('doc-select', { detail: doc.id }))
window.dispatchEvent(new CustomEvent('docs-changed'))

// Page
window.addEventListener('doc-select', onSelect)
window.addEventListener('docs-changed', onChanged)
```

Svelte store বা prop দিয়েও হতো; event বেছেছি কারণ shared state ছাড়াই component
সীমানা পেরিয়ে কাজ করে।

**একটা সূক্ষ্ম বাগ এখানে ছিল:** `removeEventListener`-এ নতুন করে arrow function
বানানো হচ্ছিল, তাই reference মিলত না আর listener কখনোই সরত না। এখন একটাই
reference দুই জায়গায় ব্যবহার হয়।

---

### Q: How is the streaming response rendered incrementally?

**A:**

```svelte
const reader = res.body?.getReader()
const decoder = new TextDecoder()
let fullContent = ''

while (true) {
    const { done, value } = await reader.read()
    if (done) break
    for (const line of decoder.decode(value).split('\n')) {
        if (line.startsWith('data: ')) {
            const parsed = JSON.parse(line.slice(6))
            if (parsed.content) {
                fullContent += parsed.content
                messages = messages.map((m, i) =>
                    i === messages.length - 1 ? { ...m, content: fullContent } : m
                )
            }
        }
    }
    await tick()
}
```

`tick()` না দিলে DOM প্রতি chunk-এ আপডেট হয় না। Streaming চলাকালে `▌` cursor
`animate-pulse` দিয়ে, আর stream শেষে source গুলো `<details>`-এ।

---

### Q: How do you handle SSR vs client-only code?

**A:** `onMount`-এর ভেতরে রাখি — ওটা শুধু ব্রাউজারে চলে, server-side rendering-এ
কখনো নয়:

```typescript
onMount(() => {
    chatEnd = document.getElementById('chat-end')
})
```

---

## DevOps / Docker

### Q: Why does the API container use `--reload` in development but not production?

**A:**
- Dev-এ `--reload` mounted `/app` দেখে, পরিবর্তন হলেই restart
- Prod-এ বাদ, কারণ: double startup (reloader + worker), বাড়তি মেমরি, আর বড়
  codebase-এ WatchFiles-এর খরচ

**বাস্তব অভিজ্ঞতা:** একটা memory-heavy bug-এর পর watchfiles
`Cannot allocate memory` দিয়ে মরে গিয়েছিল আর নিজে থেকে ফেরেনি — তখন থেকে কোড
বদলালে `docker compose restart api` দিতে হচ্ছিল। dev tooling নিজেই একটা failure
point।

---

### Q: How do you persist data across container recreates?

**A:** Named volume আর bind mount:

```yaml
volumes:
  - ./apps/api:/app                       # কোড (live reload)
  - ./storage:/app/storage                # ডকুমেন্ট, ChromaDB, documents.json
  - embedding_cache:/tmp/fastembed_cache  # মডেল ক্যাশ
```

`./storage` হোস্টেই থাকে, তাই সেটাই source of truth।

**একটা ফাঁদ ধরা পড়েছিল:** volume-টা প্রথমে `/root/.cache/chroma`-তে mount করা
ছিল, কারণ তখন ChromaDB-র নিজস্ব embedding function ব্যবহার হচ্ছিল। fastembed-এ
সরার পর ক্যাশের জায়গা বদলে `/tmp/fastembed_cache` হয়েছে, কিন্তু volume আগেরটাই
ছিল — অর্থাৎ ক্যাশ আর সংরক্ষিত হচ্ছিল না। মডেলটা Dockerfile-এ বিল্ড টাইমেও bake
করা, যাতে runtime-এ কোনো ডাউনলোড না লাগে।

---

### Q: How do you handle environment-specific configuration?

**A:** `.env` (git-এ নেই) + `.env.example` (template):

```env
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com
STORAGE_DIR=/app/storage
VITE_API_URL=http://localhost:8000
```

- API: `python-dotenv` → `os.getenv()`, runtime-এ পড়ে
- Frontend: `import.meta.env.VITE_*`, Vite build টাইমে বসিয়ে দেয় — তাই
  **VITE_ প্রিফিক্সের কিছু গোপন রাখা যায় না**, ওগুলো bundle-এ চলে যায়

---

## RAG Specific

### Q: What happens if the document is too large for the context window?

**A:** Chunking প্রতিটা টুকরো ~1000 অক্ষরে রাখে, `top_k=5` মানে সর্বোচ্চ ~5000
অক্ষর context। DeepSeek-এর window তার চেয়ে অনেক বড়, তাই এখানে চাপ নেই।

সীমাবদ্ধতাটা উল্টো দিকে: পুরো ডকুমেন্ট জুড়ে সারাংশ চাইলে ৫টা chunk যথেষ্ট নয়।
তখন hierarchical summarization বা map-reduce লাগবে।

---

### Q: How do you handle hallucination / answers not in the document?

**A:** System prompt মডেলকে context-এর মধ্যেই বেঁধে রাখে — "Use only the
information from the context... If the answer isn't in the context, say so."

প্রতিটা উত্তরের সাথে source ফেরত যায়, UI-তে relevance score সহ দেখানো হয়।

**একটা গুরুত্বপূর্ণ পাঠ:** একবার অ্যাপ বলেছিল "the document does not specify who
founded Google" — অথচ ডকুমেন্টে স্পষ্ট লেখা ছিল। মডেল hallucinate করেনি, **সত্যি
কথাই বলেছিল**; ডেটাই তার কাছে পৌঁছায়নি (নিচের truncation bug)। তাই "context-এ
নেই" উত্তর দেখলে আগে retrieval আর ingestion সন্দেহ করা উচিত, মডেলকে নয়।

---

### Q: How would you improve retrieval quality?

**A:** অগ্রাধিকার অনুসারে, আর প্রতিটার প্রভাব eval harness দিয়ে মাপা যাবে:

1. **Hybrid search**: BM25 + vector, reciprocal rank fusion — এখনকার দুটো
   ব্যর্থতাই lexical, তাই এটাই সবার আগে
2. **Re-ranking**: cross-encoder দিয়ে top-20 → top-5
3. **Query rewriting**: multi-turn follow-up কাজ করানোর জন্য
4. **Metadata filtering**: multi-document scoping-এর পূর্বশর্ত
5. **Chunk size sweep**: 1000/200 সংখ্যা দুটো উত্তরাধিকারসূত্রে পাওয়া, মাপা নয়

---

## Scaling Considerations

### Q: How would you scale this to 1000+ concurrent users?

**A:**
- **API**: load balancer-এর পেছনে একাধিক FastAPI worker
- **ChromaDB**: single-node থেকে Qdrant/Weaviate বা pgvector-এ
- **Embeddings**: GPU worker + batch queue (Redis + Celery)
- **Frontend**: static build → CDN
- **Sessions**: chat history আর rate limiting-এর জন্য Redis

তার আগে একটা কাঠামোগত পরিবর্তন লাগবে: এখন **প্রতি ডকুমেন্টে একটা করে
collection**, আর HNSW প্রতিটার জন্য আগেই জায়গা বরাদ্দ করে — তাই ১ KB ফাইলও
~1.6 MB ডিস্ক নেয়। হাজার ডকুমেন্ট মানে ~1.6 GB। একটাই collection + metadata
filtering-এ যেতে হবে।

---

### Q: What are the bottlenecks in the current architecture?

**A:**
1. **CPU-bound embedding** — `asyncio.to_thread`-এ চলে, কিন্তু CPU-ই সীমা
2. **ChromaDB single-node** — HA নেই
3. **কোনো auth বা rate limiting নেই**
4. **`documents.json`-এ write race** — concurrent upload-এ entry হারায়
5. **প্রতি collection-এ ~1.6 MB নির্দিষ্ট খরচ**
6. **Observability নেই** — শুধু log, কোনো metric বা trace নেই

---

## Security

### Q: What security issues exist in the current implementation?

**A:** স্বীকার করে নেওয়াই ভালো — এগুলো জানা এবং ইচ্ছাকৃত:

- **CORS**: `allow_origins=["*"]` — production-এ frontend domain-এ সীমিত করতে হবে
- **কোনো authentication নেই**: যে কেউ upload, delete, chat করতে পারে
- **Rate limiting নেই**: upload বা chat দিয়ে DoS সম্ভব
- **File upload**: virus scan নেই
- **HTTPS নেই**: dev only, prod-এ TLS termination লাগবে

Portfolio প্রজেক্টে auth ইচ্ছে করেই বাদ — রিভিউয়ার অ্যাকাউন্ট খুলতে চাইবেন না।

---

### Q: How would you add multi-tenancy?

**A:** Document model-এ `tenant_id`, collection-এ tenant প্রিফিক্স, tenant-প্রতি
scoped API key, আর metadata filter-এ row-level security।

বাস্তবে এই পর্যায়ে ChromaDB থেকে pgvector-এ সরে যাওয়াই যুক্তিযুক্ত — tenant
isolation, backup আর query-তে join, সবই তখন সহজ হয়।

---

## Testing

### Q: How do you test the RAG pipeline?

**A:** রেপোতে এখন দুটো স্তর আছে।

**Unit ও API test** (`apps/api/tests/`, ৩৫টা):
- `test_chunking.py` — যে লুপ কখনো থামত না, তার edge case
- `test_sources.py` — মডেল পুরো chunk পায়, কাটাকাটি শুধু display-এ
- `test_upload.py` — file type, 10 MB সীমা, listing, delete
- `test_json_extraction.py` — flatten, unicode, ভাঙা JSON

সবগুলো temp `STORAGE_DIR`-এ চলে, আসল ডেটা ছোঁয় না।

**সবচেয়ে জরুরি অংশ:** টেস্টগুলো সত্যিই বাগ ধরে কিনা যাচাই করেছি — **পুরনো ভাঙা
কোডের বিরুদ্ধে** একই assertion চালিয়ে। তিনটা regression test ওখানে fail করে,
ঠিক কোডে pass করে। যে টেস্ট ভাঙা কোডেও pass করে, সেটা অকেজো।

**Retrieval evaluation** (`apps/api/eval/`): ৪টা ডকুমেন্টে ৪৮টা প্রশ্ন,
recall@1/3/5 আর MRR দিয়ে স্কোর। কোনো LLM নেই, তাই ফ্রি ও নির্ধারিত।
`--fail-under` দিয়ে CI gate, `--compare` দিয়ে before/after ডেল্টা ও কোন প্রশ্ন
পিছিয়েছে তার নাম।

এখনো নেই: load test, আর generation-quality metric (RAGAS) — ওগুলো LLM-judged,
তাই খরচ আছে ও ফল অস্থির; CI-তে নয়, রাতের job-এ মানায়।

---

## Behavioral / Design

### Q: Walk me through a design decision you made and its trade-off.

**A:** **গড় স্কোর কমতে দিয়ে একটা সক্ষমতা কেনা।**

`all-MiniLM-L6-v2` ইংরেজি-only। বাংলা ডকুমেন্টে মেপে দেখা গেল **recall@1 =
0.000** — ১২টা প্রশ্নের একটাও সঠিক chunk-কে এক নম্বরে আনতে পারেনি।
`paraphrase-multilingual-MiniLM-L12-v2`-এ সরালে বাংলা recall@1 হলো 0.250, কিন্তু
ইংরেজিতে খরচ হলো (একটা ডকুমেন্টে 0.941 → 0.765) — আর corpus-এর তিন-চতুর্থাংশ
ইংরেজি হওয়ায় প্রতিটা headline metric নামল।

তবু multilingual রেখেছি। যে store বাংলা ফাইল থেকে কিছুই তুলতে পারে না, সেটা
দ্বিভাষিক ব্যবহারকারীর জন্য **ভাঙা**; ইংরেজির অবনতিতে retrieval কম নিখুঁত হয়,
কিন্তু অচল হয় না। এই বাণিজ্যটা রক্ষা করা যায় **শুধু কারণ এটা মাপা** —
`eval/results/03_english_model.json` আর `04_multilingual.json`।

যে খরচগুলো মেনে নিয়েছি: embedding CPU-bound, তাই `asyncio.to_thread`-এ চলে যাতে
event loop আটকে না যায়; আর ONNX মডেল ইমেজে bake করা, যাতে container runtime-এ
কিছু ডাউনলোড না করে।

---

### Q: How would you add support for a new file type (e.g., PPTX)?

**A:**
1. `supported_extensions` আর `mime_from_ext`-এ যোগ
2. `extract_text_from_file`-এ শাখা:
   ```python
   elif content_type == '...presentationml.presentation':
       from pptx import Presentation
       prs = Presentation(file_path)
       return "\n".join(shape.text for slide in prs.slides
                        for shape in slide.shapes if hasattr(shape, "text"))
   ```
3. `requirements.txt`-এ `python-pptx`
4. Extraction-এর unit test
5. `INDEX_VERSION` বাড়ানো, যাতে পুরনো ডকুমেন্ট নিজে থেকে re-index হয়

**৫ নম্বরটা ভুলে যাওয়া সহজ, আর সেটাই সবচেয়ে বেশি কামড়ায়** — extraction ঠিক করার
পরেও আগের ডকুমেন্ট পুরনো chunk নিয়েই বসে থাকবে। এই ভুলটা এখানে হয়েছিল।

---

### Q: What monitoring would you add for production?

**A:**
- **Metrics**: request latency (p50/p95/p99), error rate, active indexing task
- **Logs**: trace ID সহ structured JSON
- **Traces**: upload → extract → embed → store → query → LLM
- **Alerts**: indexing failure rate, p99 latency, disk usage
- **Domain-specific**: extract করা অক্ষর বনাম ফাইল সাইজের অনুপাত — ৩২ KB ফাইল
  থেকে ১৫৭ অক্ষর বেরোলে সেটা নীরবে পাশ করা উচিত নয় (এটা এখানে ঘটেছিল)

---

## Quick Reference

| Component | Technology | Key Config |
|-----------|------------|------------|
| API Framework | FastAPI 0.115 | `--reload` dev only |
| Frontend | SvelteKit 2 + TS | Vite + Tailwind 4 |
| Vector DB | ChromaDB 0.6 | PersistentClient, cosine |
| Embeddings | paraphrase-multilingual-MiniLM-L12-v2 | 384-dim, ONNX via fastembed |
| LLM | DeepSeek Chat | SSE streaming |
| PDF | pdfplumber | Page-by-page |
| DOCX | python-docx | Paragraph **ও table**, document order |
| JSON | stdlib | `path: value` লাইনে flatten |
| Container | Docker Compose | Named volumes |

---

## Bugs I found and fixed

সাধারণ RAG উত্তর মুখস্থ করা সহজ; এগুলো নয়। প্রতিটা এই রেপোতে reproduce করা যায়,
আর প্রতিটার সাথে সংখ্যা আছে। শুধু একটা অংশ প্রস্তুত করলে **এটাই করুন**।

### The chunker that never terminated

**লক্ষণ.** ২ KB-র একটা markdown আপলোডের পর পুরো API সাড়া দেওয়া বন্ধ করল — এমনকি
`/health`-ও খালি পেজ ফেরত দিল।

**নির্ণয়.** `docker stats` দেখাল ২,১১২ বাইটের ডকুমেন্টের জন্য কন্টেইনার
**6.08 GiB** মেমরি আর ১০৭% CPU খাচ্ছে। Chunking লুপের শেষে ছিল
`start = end - overlap`, যেটা **শেষ chunk-এর পরেও** চলত। `end` টেক্সটের শেষে
পৌঁছে গেলে `start` চিরকাল `len(text) - overlap`-এ আটকে যেত, `start < len(text)`
সত্যি থাকত, আর একই tail chunk যোগ হতে থাকত যতক্ষণ না মেমরি শেষ। `chunk_text`
synchronous এবং event loop-এ চলে বলে পুরো সার্ভার জমে যেত — `/health` ঝুলে
থাকার আসল কারণ এটাই।

**কেন লুকিয়ে ছিল.** ১০০০ অক্ষরের কম ফাইল প্রথম লাইনেই return করে, তাই সব ছোট
টেস্ট ফাইল পাশ করত।

**সমাধান.** tail শেষ হলে বেরিয়ে যাওয়া, আর সামনে এগোনোর নিশ্চয়তা:
`if end >= len(text): break` তারপর `start = max(end - overlap, start + 1)`।

**যে follow-up আসবে** — *"How do you know it is fixed?"* `test_chunking.py`
chunk সংখ্যার একটা সীমা assert করে, তাই অসীম লুপ মেশিন ঝুলিয়ে দেওয়ার বদলে
assertion fail করে। টেস্টটা সত্যিই ধরে কিনা যাচাই করেছি — পুরনো implementation-এ
একই assertion চালিয়ে।

### Half of every retrieved chunk never reached the model

**লক্ষণ.** যে ডকুমেন্টে হুবহু লেখা "Founded: 1998 by Larry Page and Sergey
Brin", সেখানে "Who founded Google?" জিজ্ঞেস করলে উত্তর এল "the document does not
specify who"।

**নির্ণয়.** `search_document` প্রতিটা chunk ৫০০ অক্ষরে কাটত, আর মডেলের context
বানানো হতো সেই **কাটা** টেক্সট থেকে। Chunk ১০০০ অক্ষর পর্যন্ত হয়, তাই মডেল
retrieval-এর অর্ধেকও দেখত না। প্রতিষ্ঠাতাদের লাইনটা ছিল chunk-এর ৫৯২ নম্বর
অক্ষরে — কাটের ঠিক পরে।

**সমাধান.** মডেল পায় পুরো chunk; কাটাকাটি সরিয়ে `preview_sources`-এ, যেটা শুধু
ব্রাউজারে দেখানোর জন্য।

**সাধারণ পাঠ** — display-এর জন্য কাটা আর মডেলের জন্য কাটা আলাদা দুটো ব্যাপার,
যারা ভুলবশত একই ভেরিয়েবল ভাগ করছিল।

### 98.5% of a Word document silently discarded

**লক্ষণ.** বাংলাদেশের জেলার ইতিহাসের একটা `.docx` মাত্র একটা chunk হিসেবে index
হলো, আর সব প্রশ্নের উত্তর এল "context-এ নেই"।

**নির্ণয়.** `extract_text_from_file` শুধু `doc.paragraphs` পড়ত। ডকুমেন্টে
paragraph-এ ছিল ১৫৫ অক্ষর আর **table-এ ১০,৪৬৪ অক্ষর**, তাই extraction দিল ১৫৭
অক্ষর — শুধু ভূমিকার বাক্যটা। মডেলকে এমন বিষয়ে প্রশ্ন করা হচ্ছিল যা সে কখনো
দেখেইনি।

**সমাধান.** `document.element.body` ধরে document order-এ হাঁটা, আর table row-কে
`cell | cell` লাইনে বের করা। ফল: **১ chunk → ১১ chunk**।

**Follow-up** — *"How would you catch this class of bug earlier?"* extract করা
অক্ষরসংখ্যা আর ফাইল সাইজের অনুপাত দেখা; ৩২ KB ফাইল থেকে ১৫৭ অক্ষর কখনো নীরবে
পাশ করা উচিত নয়।

### DeepSeek has no embeddings endpoint

**লক্ষণ.** Retrieval "কাজ করছিল", কিন্তু বড় ডকুমেন্টে এলোমেলো অংশ ফেরত দিত।

**নির্ণয়.** কোড DeepSeek-কে
`client.embeddings.create(model="text-embedding-ada-002")` ডাকছিল। DeepSeek chat
completion দেয়, embedding নয় — তাই প্রতিটা কল **404**। এরপর একটা `try/except`
fallback-এ চলে যেত `[0.0] * 1536`-এ, অর্থাৎ প্রতিটা chunk-এর জন্য শূন্য vector।
সব vector এক হলে similarity search কার্যত এলোমেলো ফল দেয়, আর লগে এর কোনো ইঙ্গিত
ছিল না।

**কেন লুকিয়ে ছিল.** এক-chunk-এর ডকুমেন্টে প্রার্থী একটাই, তাই সঠিকটাই আসে।
সমস্যা শুধু স্কেলে দেখা দেয়।

**সমাধান.** Embedding লোকালি চলে। নীরব fallback বাদ — ব্যর্থ হলে ডকুমেন্ট
`error` চিহ্নিত হয়, চুপচাপ ভুল উত্তর দেয় না।

**সাধারণ পাঠ** — যে fallback দেখতে-সঠিক আবর্জনা ফেরত দেয়, সেটা crash-এর চেয়েও
খারাপ। হয় জোরে fail করো, নয়তো একেবারেই না।

### "ready" that meant nothing

Indexing status সেট হতো `await asyncio.sleep(2)` করে তারপর `ready` লিখে —
indexing শেষ হলো কিনা বা ব্যর্থ হলো কিনা না দেখেই। দুটো fire-and-forget
`asyncio.create_task()` কলও কোনো reference রাখত না, আর asyncio task-এর শুধু weak
reference রাখে — তাই task মাঝপথে garbage-collect হয়ে যেতে পারত।

এখন status লেখে indexing কোড নিজেই (`ready` — chunk সংখ্যা ও মডেলসহ, অথবা
`error` — কারণসহ), আর background task module-স্তরের একটা set-এ ধরা থাকে।

---

## Decisions I measured — including two I reverted

এই রেপোর সবচেয়ে দরকারি জিনিসটা কোনো feature নয়। সেটা `eval/run_eval.py` —
৪টা ডকুমেন্টে ৪৮টা প্রশ্ন, recall@k আর MRR দিয়ে স্কোর। কোনো LLM নেই, তাই ফ্রি,
নির্ধারিত, আর প্রতি commit-এ চালানো নিরাপদ। Snapshot থাকে `eval/results/`-এ।

**Relevance চিহ্নিত evidence snippet দিয়ে, chunk index দিয়ে নয়** — chunking
বদলালেই index অচল হয়ে যেত, অর্থাৎ golden set ঠিক তখনই ভাঙত যখন সবচেয়ে বেশি
দরকার।

**Corpus এক collection-এ pool করা.** ডকুমেন্টভিত্তিক করলে `recall@5` গঠনগতভাবেই
1.0 হয়ে যেত — ৪ chunk-এর ডকুমেন্ট থেকে ৫টা চাইলে পুরোটাই ফেরত আসে। Pool করায়
retriever-কে সঠিক ডকুমেন্ট **আর** সঠিক chunk দুটোই বাছতে হয়।

### Structure-aware chunking: headline সংখ্যা কমা সত্ত্বেও রাখা

| | recall@1 | recall@3 | recall@5 | MRR |
|---|---|---|---|---|
| Fixed-size | **0.722** | 0.861 | 0.944 | **0.793** |
| Structure-aware | 0.639 | **0.917** | **0.972** | 0.772 |

Retrieval `top_k=5` পাঠায় আর **পাঁচটা chunk-ই** prompt-এ যায়, তাই মডেল আদৌ উত্তর
দিতে পারবে কিনা সেটা ঠিক করে recall@5। recall@1 তখনই গুরুত্বপূর্ণ হতো যদি
একটামাত্র chunk দেখাতাম বা ব্যবহার করতাম। Ablation-এ heading-path prefix-এর
উপযোগিতাও নিশ্চিত হয়েছে: সেটা সরালে recall@5 নেমে 0.917।

### Multilingual embeddings: জেনেশুনে নেওয়া বাণিজ্য

উপরে "Behavioral / Design"-এ বিস্তারিত। সংক্ষেপে: বাংলা recall@1 0.000 → 0.250,
ইংরেজিতে খরচ, আর corpus ইংরেজি-ভারী হওয়ায় গড় নেমেছে — তবু রাখা।

### Two experiments I ran and threw away

ভেবেছিলাম টেবিলের প্রতি সারিকে আলাদা chunk করলে সেই কেসটা সারবে যেখানে উত্তর
১১-এর মধ্যে ১১ নম্বরে ছিল। মেপে দেখা গেল বাংলা recall@5 নামল **1.000 → 0.500**।
এরপর অনুমান করলাম heading prefix ছোট সারিগুলোকে চাপা দিচ্ছে, তাই সেটা বন্ধ করলাম
— আরও খারাপ, recall@1 **0.250 → 0.083**। দুটোই ফিরিয়ে নেওয়া হয়েছে, আর eval
নিশ্চিত করেছে revert-এর পর সংখ্যা হুবহু আগের জায়গায় ফিরেছে।

**Eval harness নিয়ে প্রশ্ন এলে এই উত্তরটাই দেবেন।** দুটো যুক্তিসঙ্গত অনুমান,
দুটোই ভুল, দুটোই শিপ হওয়ার আগে ধরা। মাপার ব্যবস্থা না থাকলে আমি একটা regression
শিপ করে সেটাকে "উন্নতি" বলতাম।

---

## What I know is still wrong

নিজে থেকে বলা ধরা পড়ার চেয়ে অনেক শক্তিশালী।

- **Exact identifier retrieve হয় না.** `X-Request-Id` আর `sk_test_` আসে না;
  dense vector কোড ও ID-তে দুর্বল। BM25 দিয়ে hybrid search-ই পরিকল্পিত সমাধান,
  আর সেটা ভাষা চেনে না বলে বাংলাতেও কাজে দেবে।
- **`documents.json`-এ write race.** load → mutate → save, তাই concurrent upload-এ
  entry হারায়। SQLite সমাধান।
- **ChromaDB ডিস্ক ফেরত দেয় না.** ডকুমেন্ট delete করলে SQLite row বা HNSW ফাইল
  কিছুই মুক্ত হয় না — এই বিল্ডে 1.6 MB live-এর বিপরীতে 15.2 MB orphaned জমেছিল।
  `scripts/rebuild_index.py` সাফ করে, কিন্তু সেটা ম্যানুয়াল।
- **প্রতি ডকুমেন্টে ~1.6 MB**, আকার নির্বিশেষে — প্রতিটার আলাদা collection আর
  HNSW-র আগাম বরাদ্দের কারণে।
- **কোনো auth বা multi-tenancy নেই.** ইচ্ছাকৃত।
- **Conversation সংরক্ষিত হয় না**, প্রতিটা প্রশ্ন স্বাধীন — তাই "ওটা আরেকটু
  বুঝাও" ধরনের follow-up কাজ করে না।

---

## Talking about how this was built

আপনি AI সহায়তা ব্যাপকভাবে ব্যবহার করেছেন। এখন ইন্ডাস্ট্রির বড় অংশই তাই করে, আর
লুকানোটা একই সাথে ঝুঁকিপূর্ণ ও অপ্রয়োজনীয় — লাইনগুলো কে টাইপ করেছে সেটা কখনোই
আকর্ষণীয় অংশ ছিল না।

**সোজা বলে দিয়ে সিদ্ধান্তের দিকে চলে যান.** যেমন:

> *"I built this with heavy AI assistance. What I own is the diagnosis and the
> decisions — the measurement harness, and which changes I kept."*

এটা টেকে কারণ সত্যি, আর প্রমাণ রেপোতেই আছে: `eval/results/`-এ snapshot, পুরনো
implementation-এ fail করা টেস্ট, আর দুটো বাতিল করা পরীক্ষা।

**আসল probe-এর জন্য তৈরি থাকুন**, যেটা "AI ব্যবহার করেছেন কিনা" নয়, বরং
*"what happens if I change X?"* নোট ছাড়াই উত্তর দিতে পারা চাই:

- কেন `top_k=5` থাকায় recall@5-ই আসল metric
- কেন golden set-এ chunk index নয়, evidence snippet
- কেন zero-vector fallback exception-এর চেয়ে খারাপ
- কেন গড় নামা সত্ত্বেও multilingual মডেল রাখা হলো

**যা করবেন না:** প্রতিটা লাইন নিজে লিখেছেন দাবি করা, আর উপরের উত্তরগুলো
শব্দে-শব্দে মুখস্থ করা — মুখস্থ ভাষা সহজে ধরা পড়ে এবং প্রথম follow-up-এই ভেঙে
পড়ে। প্রতিটা গল্পের পেছনের কোডটা একবার পড়ে নিন, যাতে আবৃত্তি নয় — মনে করে বলেন।

**সবচেয়ে জোরালো চাল** হলো `eval/results/` খুলে সংখ্যাগুলো ধরে হাঁটা। খুব কম
portfolio প্রজেক্ট প্রতিটা পরিবর্তনের মাপা before/after দেখাতে পারে — বাতিল করা
পরিবর্তনগুলো সহ।

---

## Quick answers

**Why DeepSeek and not OpenAI?** খরচ, আর এটা OpenAI-compatible বলে client কোড
বদলাতে হয় না। পাশাপাশি এটা `prompt_cache_hit_tokens` আলাদা করে দেয়, যা cost
tracking-কে আরও আকর্ষণীয় করে।

**Why ChromaDB and not pgvector?** এই আকারের প্রজেক্টে আলাদা কোনো সার্ভিস চালাতে
হয় না। স্কেলে বা multi-tenancy-তে গেলে pgvector ভালো — আর তখন per-document
collection ডিজাইনটাই সবার আগে বাদ যাবে।

**Why 1000/200 for chunk size and overlap?** উত্তরাধিকারসূত্রে পাওয়া default,
মাপা নয়। সৎ উত্তর: eval harness-টা ঠিক এই প্রশ্ন মীমাংসা করার জন্যই আছে, কিন্তু
ওই sweep-টা এখনো চালাইনি।

**How would you make retrieval better tomorrow?** আগে hybrid search — দুই ভাষার
অবশিষ্ট ব্যর্থতাই lexical। তারপর cross-encoder reranking, একই golden set দিয়ে
মেপে।

**What was the hardest bug?** Chunker-এর লুপ। কারণ লক্ষণ (`/health` খালি পেজ)
আঙুল তুলছিল web layer-এর দিকে, অথচ কারণ ছিল একটা synchronous লুপ event loop-কে
অনাহারে রাখা। ২ KB ফাইলের জন্য `docker stats`-এ 6 GB দেখাটাই মোড় ঘুরিয়ে দিয়েছিল।
