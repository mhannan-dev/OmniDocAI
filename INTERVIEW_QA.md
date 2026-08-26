# OmniDocAI - Interview Questions & Answers

## System Architecture

### Q: Describe the overall architecture of this application.
**A:** OmniDocAI is a document intelligence platform with a **RAG (Retrieval-Augmented Generation)** architecture:

- **Frontend**: SvelteKit + Tailwind CSS (TypeScript) - served on port 5173
- **Backend**: FastAPI (Python) - REST API on port 8000
- **Vector Store**: ChromaDB (local, persistent) for document embeddings
- **LLM**: DeepSeek API (chat completions) + local sentence-transformers (embeddings)
- **Document Processing**: pdfplumber (PDF), python-docx (DOCX), native (TXT/MD)
- **Deployment**: Docker Compose with live-reload for development

Data flow: Upload → Text Extraction → Chunking → Embedding → ChromaDB → Query → Vector Search → Context + DeepSeek → Streaming Response

---

### Q: Why use ChromaDB instead of a traditional database?
**A:** ChromaDB is purpose-built for vector similarity search:
- Native HNSW index for fast ANN (Approximate Nearest Neighbor) search
- Stores embeddings + metadata + documents in one place
- No need for pgvector extension or separate vector infrastructure
- Persistent local storage with zero config
- Handles 100K+ vectors efficiently on modest hardware

---

### Q: How does the embedding pipeline work?
**A:**
1. **Extract**: pdfplumber / python-docx / raw text → plain text
2. **Chunk**: 1000-char windows with 200-char overlap (sentence-boundary aware)
3. **Embed**: `sentence-transformers/all-MiniLM-L6-v2` (384-dim, runs locally via ChromaDB's DefaultEmbeddingFunction)
4. **Store**: ChromaDB collection per document (`doc_{uuid}`) with IDs, documents, embeddings, metadata
5. **Query**: Embed user question → vector search (top-k=5) → return chunks + scores

---

### Q: Why use local embeddings instead of DeepSeek/OpenAI embeddings?
**A:**
- **Cost**: Zero API calls for embeddings (only chat uses DeepSeek)
- **Latency**: Local inference ~10-50ms vs 200-500ms network round-trip
- **Privacy**: Document text never leaves the server for embedding
- **Reliability**: No external dependency for core retrieval
- **all-MiniLM-L6-v2** is 384-dim, fast, and strong for semantic search

---

## Backend (FastAPI)

### Q: How do you handle long-running document indexing without blocking the API?
**A:** Fire-and-forget with task tracking:
```python
_background_tasks = set()

def spawn(coro):
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task

# In upload endpoint:
spawn(index_document(doc))  # Returns immediately, indexing runs in background
```
- Document status: `processing` → `ready` | `error`
- Startup re-indexing runs as background task via `asyncio.create_task()`

---

### Q: How is streaming chat implemented?
**A:** Server-Sent Events (SSE) via `StreamingResponse`:
```python
async def generate_chat_response(query, doc_id):
    stream = await deepseek_client.chat.completions.create(
        model="deepseek-chat",
        messages=[...],
        stream=True
    )
    async for chunk in stream:
        if chunk.choices[0].delta.content:
            yield f"data: {json.dumps({'content': piece})}\n\n"
    yield f"data: {json.dumps({'sources': sources})}\n\n"
    yield "data: [DONE]\n\n"

@app.post("/chat")
async def chat(request: ChatRequest):
    return StreamingResponse(
        generate_chat_response(...),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )
```
Frontend uses `ReadableStream` + `TextDecoder` to parse SSE chunks.

---

### Q: How do you handle file uploads and validation?
**A:**
- `python-multipart` for FormData parsing
- MIME type inferred from extension if `application/octet-stream`
- Allowed: PDF, TXT, MD, DOCX
- Max 10MB (checked after save)
- UUID filename prevents collisions
- Files stored in `/app/storage/uploads/{uuid}.ext`

---

### Q: How do you manage document metadata persistence?
**A:** Simple JSON file (`/app/storage/documents.json`):
```python
def load_documents() -> List[Document]:
    if DOCUMENTS_DB.exists():
        return [Document(**d) for d in json.load(f)]
    return []

def save_documents(docs: List[Document]):
    json.dump([d.model_dump() for d in docs], f)
```
- Pydantic models for validation
- Atomic write (replace file)
- Fields: id, name, size, type, uploadedAt, status, path, chunks, embeddingModel, error

---

## Frontend (SvelteKit)

### Q: How does the sidebar communicate with the chat area?
**A:** Custom DOM events:
```typescript
// Sidebar - dispatch
window.dispatchEvent(new CustomEvent('doc-select', { detail: doc.id }))

// Page - listen
onMount(() => {
    window.addEventListener('doc-select', ((e: CustomEvent) => handleDocSelect(e.detail)) as EventListener)
})
```
Alternative: Svelte stores or props, but events work across component boundaries without shared state.

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
    const chunk = decoder.decode(value)
    for (const line of chunk.split('\n')) {
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
    await tick()  // Force Svelte update
}
```
- `tick()` ensures DOM updates between chunks
- Cursor `▌` animated via `animate-pulse` during streaming
- Sources rendered in `<details>` after stream ends

---

### Q: How do you handle SSR vs client-only code (e.g., `document.getElementById`)?
**A:** Guard with `onMount`:
```typescript
let chatEnd: HTMLElement | null = null

onMount(() => {
    chatEnd = document.getElementById('chat-end')
})

function scrollToBottom() {
    chatEnd?.scrollIntoView({ behavior: 'smooth' })
}
```
Runs only in browser, never during server-side rendering.

---

## DevOps / Docker

### Q: Why does the API container use `--reload` in development but not production?
**A:** 
- Dev: `--reload` watches `/app` (mounted volume) for changes → instant restart
- Prod: Removed `--reload` to avoid:
  - Double startup (reloader + worker)
  - Memory overhead
  - WatchFiles blocking on large codebases
- Controlled via `docker-compose.yml` command override

---

### Q: How do you persist data across container recreates?
**A:** Named volumes + bind mounts:
```yaml
volumes:
  - ./apps/api:/app              # Code (live reload)
  - ./storage:/app/storage       # Documents, ChromaDB, documents.json
  - embedding_cache:/root/.cache/chroma  # Model cache (survives rebuild)
```
- `./storage` on host = source of truth
- `embedding_cache` avoids re-downloading sentence-transformers model

---

### Q: How do you handle environment-specific configuration?
**A:** `.env` file (not committed) + `.env.example` (template):
```env
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com
STORAGE_DIR=/app/storage
VITE_API_URL=http://localhost:8000
```
- `python-dotenv` loads into `os.getenv()`
- Frontend: `import.meta.env.VITE_*` (Vite injects at build time)
- API: `os.getenv()` at runtime

---

## RAG Specific

### Q: What happens if the document is too large for the context window?
**A:** 
- Chunking limits each piece to ~1000 chars
- Top-k=5 retrieval → max ~5000 chars context
- DeepSeek context window: 32K+ tokens (plenty of headroom)
- If needed: implement hierarchical summarization or sliding window

---

### Q: How do you handle hallucination / answers not in the document?
**A:** System prompt constrains behavior:
```
"You are a helpful assistant that answers questions based on the provided document context.
Use only the information from the context to answer. If the answer isn't in the context, say so.
Cite sources using [Source: document_name] format."
```
- Sources returned with every response
- UI shows expandable source citations with relevance scores
- Low similarity scores (distance → 1-score) flagged in UI

---

### Q: How would you improve retrieval quality?
**A:**
1. **Hybrid search**: BM25 (keyword) + vector (semantic) → reciprocal rank fusion
2. **Re-ranking**: Cross-encoder (e.g., `ms-marco-MiniLM-L-6-v2`) on top-20 → top-5
3. **Query expansion**: LLM rewrites query → multiple sub-queries
4. **Metadata filtering**: Filter by doc type, date, tags before vector search
5. **Better chunking**: Semantic chunking (by heading/section) vs fixed-size

---

## Scaling Considerations

### Q: How would you scale this to 1000+ concurrent users?
**A:**
- **API**: Horizontal scaling (multiple FastAPI workers behind load balancer)
- **ChromaDB**: Single-node → ChromaDB cluster or migrate to Pinecone/Weaviate/Qdrant
- **Embeddings**: GPU workers + batch inference queue (Redis + Celery)
- **LLM**: Dedicated inference server (vLLM, TGI) or managed API
- **Frontend**: Static build → CDN (Cloudflare, Vercel)
- **Sessions**: Redis for chat history, rate limiting

---

### Q: What are the bottlenecks in the current architecture?
**A:**
1. **Single-threaded embedding** (CPU-bound, blocks event loop via `to_thread`)
2. **ChromaDB single-node** (no HA, limited write throughput)
3. **No auth/rate limiting** (open API)
4. **In-memory task tracking** (`_background_tasks` lost on restart)
5. **JSON file locking** (concurrent writes corrupt `documents.json`)
6. **No observability** (logs only, no metrics/tracing)

---

## Security

### Q: What security issues exist in the current implementation?
**A:**
- **CORS**: `allow_origins=["*"]` - should restrict to frontend domain
- **No authentication**: Anyone can upload/delete/chat
- **No rate limiting**: DoS via upload or chat endpoints
- **File upload**: No virus scanning, path traversal possible if filename not sanitized
- **API key in env**: Should use secrets manager in production
- **No HTTPS**: Dev only, needs TLS termination in prod

---

### Q: How would you add multi-tenancy?
**A:**
- Add `user_id` / `tenant_id` to Document model
- ChromaDB collections per tenant: `tenant_{id}_doc_{uuid}`
- API keys per tenant with scoped permissions
- Row-level security in metadata filters
- Separate embedding caches per tenant (optional)

---

## Testing

### Q: How would you test the RAG pipeline?
**A:**
- **Unit**: `extract_text_from_file`, `chunk_text`, `get_embeddings` with fixtures
- **Integration**: Upload → index → query → assert relevant chunks returned
- **Golden set**: Curated Q&A pairs per document, measure recall@k, MRR
- **Regression**: Embedding model version pinning + re-index on change
- **Load**: Locust/k6 for concurrent upload + chat

---

## Behavioral / Design

### Q: Walk me through a design decision you made and its trade-off.
**A:** **Local embeddings vs API embeddings**
- Decision: Use `all-MiniLM-L6-v2` locally via ChromaDB
- Trade-off: 
  - ✅ Zero cost, low latency, privacy, offline-capable
  - ❌ 384-dim (vs 1536/3072), slightly lower quality than `text-embedding-3-large`
  - ❌ CPU-bound, needs `to_thread` to not block event loop
- Mitigation: Warm-up on startup, batch embeddings, GPU offload later

---

### Q: How would you add support for a new file type (e.g., PPTX)?
**A:**
1. Add MIME type to `allowed_types` and `mime_from_ext`
2. Add extraction in `extract_text_from_file`:
   ```python
   elif content_type == 'application/vnd.openxmlformats-officedocument.presentationml.presentation':
       from pptx import Presentation
       prs = Presentation(file_path)
       return "\n".join([shape.text for slide in prs.slides for shape in slide.shapes if hasattr(shape, "text")])
   ```
3. Add dependency: `python-pptx` to requirements.txt
4. Test with sample PPTX

---

### Q: What monitoring would you add for production?
**A:**
- **Metrics (Prometheus)**: Request latency (p50/p95/p99), error rate, queue depth, active indexing tasks
- **Logs (Loki/ELK)**: Structured JSON logs with trace IDs
- **Traces (Jaeger)**: End-to-end: upload → extract → embed → store → query → LLM
- **Alerts**: Indexing failure rate > 5%, p99 latency > 10s, disk usage > 80%
- **Health checks**: `/health` + `/ready` (checks ChromaDB connectivity)

---

## Quick Reference

| Component | Technology | Key Config |
|-----------|------------|------------|
| API Framework | FastAPI 0.115 | `--reload` dev only |
| Frontend | SvelteKit 2 + TS | Vite + Tailwind 4 |
| Vector DB | ChromaDB 0.6 | PersistentClient |
| Embeddings | all-MiniLM-L6-v2 | 384-dim, local |
| LLM | DeepSeek Chat | SSE streaming |
| PDF | pdfplumber | Page-by-page |
| DOCX | python-docx | Paragraph extraction |
| Container | Docker Compose | Named volumes |