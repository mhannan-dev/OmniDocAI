import os
import re
import uuid
import shutil
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from openai import AsyncOpenAI
import chromadb
from chromadb.config import Settings
from fastembed import TextEmbedding

# Document parsing
import pdfplumber
from docx import Document as DocxDocument
from docx.table import Table
from docx.text.paragraph import Paragraph

app = FastAPI(
    title="OmniDocAI API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "/app/storage"))
UPLOAD_DIR = STORAGE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
CHROMA_DIR = STORAGE_DIR / "chroma_db"
CHROMA_DIR.mkdir(parents=True, exist_ok=True)

DOCUMENTS_DB = STORAGE_DIR / "documents.json"

# DeepSeek client
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
deepseek_client = AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL) if DEEPSEEK_API_KEY else None

# ChromaDB client
chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR), settings=Settings(anonymized_telemetry=False))

# Embeddings run locally (all-MiniLM-L6-v2, 384-dim). DeepSeek exposes no /embeddings
# endpoint, so it is used for chat completion only.
# all-MiniLM-L6-v2 is English-only: on Bengali documents its similarities
# collapsed into a narrow band and recall@1 measured 0.000. This model covers
# 50+ languages at the same 384 dimensions.
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
# Bump to force every document to be re-indexed on the next startup.
INDEX_VERSION = 5  # 5: multilingual embedding model
_embedding_fn = None


def get_embedding_fn():
    """Return a callable that turns a list of strings into a list of vectors."""
    global _embedding_fn
    if _embedding_fn is None:
        model = TextEmbedding(EMBEDDING_MODEL)
        _embedding_fn = lambda texts: [v.tolist() for v in model.embed(list(texts))]
    return _embedding_fn

# asyncio keeps only weak references to tasks, so a fire-and-forget task can be
# garbage-collected mid-run. Hold a strong reference until it finishes.
_background_tasks = set()


def spawn(coro):
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


class Document(BaseModel):
    id: str
    name: str
    size: int
    type: str
    uploadedAt: str
    status: str
    path: str
    chunks: int = 0
    embeddingModel: Optional[str] = None
    indexVersion: int = 0
    error: Optional[str] = None


class ChatRequest(BaseModel):
    query: str
    document_id: str


class ChatResponse(BaseModel):
    content: str
    sources: List[dict] = []


def load_documents() -> List[Document]:
    if DOCUMENTS_DB.exists():
        with open(DOCUMENTS_DB) as f:
            return [Document(**d) for d in json.load(f)]
    return []


def save_documents(docs: List[Document]):
    with open(DOCUMENTS_DB, 'w') as f:
        json.dump([d.model_dump() for d in docs], f)


def get_collection_name(document_id: str) -> str:
    return f"doc_{document_id.replace('-', '_')}"


def extract_json_text(file_path: Path) -> str:
    """Flatten JSON into one `path: value` line per leaf.

    Indexing raw JSON buries the content in punctuation, and a chunk boundary
    can land mid-object. Flattening keeps every value on a line that still
    names where it came from, which both embeds and chunks cleanly.

    A .json file that does not parse is still text, so it is indexed as-is
    rather than rejected.
    """
    raw = file_path.read_text(encoding="utf-8", errors="ignore")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw

    lines = []

    def walk(node, path):
        if isinstance(node, dict):
            if not node:
                lines.append(f"{path}: (empty object)" if path else "(empty object)")
            for key, value in node.items():
                walk(value, f"{path}.{key}" if path else str(key))
        elif isinstance(node, list):
            if not node:
                lines.append(f"{path}: (empty list)" if path else "(empty list)")
            for i, value in enumerate(node):
                walk(value, f"{path}[{i}]")
        else:
            value = "null" if node is None else str(node)
            lines.append(f"{path}: {value}" if path else value)

    walk(data, "")
    return "\n".join(lines)

def extract_docx_text(file_path: Path) -> str:
    """Read a .docx in document order, tables included.

    Reading only `doc.paragraphs` silently drops every table. A 64-row district
    table went in as 10,464 characters and came out as the 157-character intro
    sentence above it, so the model was asked about content it had never seen.
    Each row becomes a pipe-delimited line, keeping a row's cells together.
    """
    document = DocxDocument(file_path)
    parts = []

    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            text = Paragraph(child, document).text.strip()
            if text:
                parts.append(text)
        elif child.tag.endswith("}tbl"):
            for row in Table(child, document).rows:
                cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                if any(cells):
                    parts.append(" | ".join(cells))

    return "\n".join(parts)


def extract_text_from_file(file_path: Path, content_type: str) -> str:
    """Extract text from various file types."""
    try:
        if content_type == 'application/pdf':
            text = ""
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            return text.strip()
        elif content_type == 'application/json':
            return extract_json_text(file_path)
        elif content_type == 'text/plain' or content_type == 'text/markdown':
            return file_path.read_text(encoding='utf-8', errors='ignore')
        elif content_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
            return extract_docx_text(file_path)
        else:
            return file_path.read_text(encoding='utf-8', errors='ignore')
    except Exception as e:
        print(f"Error extracting text: {e}")
        return ""


HEADING_RE = re.compile(r'^(#{1,6})\s+(.*\S)\s*$')
SENTENCE_RE = re.compile(r'(?<=[.!?])\s+')


def _sections(text: str):
    """Split markdown into (heading_path, body) pairs.

    The heading path carries the document title down into every section, so a
    chunk about rate limits still says which API it belongs to.
    """
    sections, stack, buffer, path = [], [], [], ""

    def flush():
        body = "\n".join(buffer).strip()
        if body:
            sections.append((path, body))
        buffer.clear()

    for line in text.split("\n"):
        match = HEADING_RE.match(line)
        if match:
            flush()
            level = len(match.group(1))
            del stack[level - 1:]
            stack.append(match.group(2))
            path = " > ".join(stack)
        else:
            buffer.append(line)
    flush()

    return sections or [("", text.strip())]


def _hard_split(text: str, budget: int):
    return [text[i:i + budget] for i in range(0, len(text), budget)]


def _split_to_budget(text: str, budget: int, level: int = 0):
    """Break text into pieces of at most `budget` characters.

    Tries progressively finer separators — paragraphs, then sentences, then
    words — and only falls back to a hard character cut when a single word is
    itself longer than the budget. That ordering is what keeps chunks from
    starting mid-word.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= budget:
        return [text]

    separators = [("\n\n", lambda t: t.split("\n\n")),
                  (" ", lambda t: SENTENCE_RE.split(t)),
                  (" ", lambda t: t.split(" "))]
    if level >= len(separators):
        return _hard_split(text, budget)

    joiner, split = separators[level]
    units = [u for u in split(text) if u.strip()]
    if len(units) <= 1:
        return _split_to_budget(text, budget, level + 1)

    packed, current = [], ""
    for unit in units:
        candidate = f"{current}{joiner}{unit}" if current else unit
        if len(candidate) <= budget:
            current = candidate
        else:
            if current:
                packed.append(current)
            current = unit
    if current:
        packed.append(current)

    pieces = []
    for piece in packed:
        if len(piece) <= budget:
            pieces.append(piece)
        else:
            pieces.extend(_split_to_budget(piece, budget, level + 1))
    return pieces


def _add_overlap(pieces, overlap: int, budget: int):
    """Carry a word-aligned tail of each piece into the next one."""
    if overlap <= 0 or len(pieces) < 2:
        return pieces

    out = [pieces[0]]
    for previous, current in zip(pieces, pieces[1:]):
        tail = previous[-overlap:]
        space = tail.find(" ")
        tail = tail[space + 1:] if space != -1 else ""
        merged = f"{tail} {current}".strip() if tail else current
        out.append(merged if len(merged) <= budget else current)
    return out


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """Split text into chunks that follow the document's own structure.

    Fixed-size windows used to cut through words and headings — chunk 1 of a
    test document began "ny:** Alphabet Inc.", having sliced "Parent Company"
    in half. Sections are now kept whole where they fit, and each chunk is
    labelled with its heading path so retrieval sees the context too.
    """
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    for path, body in _sections(text):
        prefix = f"[{path}]\n" if path else ""
        # A heading path should never crowd out the text it labels.
        if len(prefix) > chunk_size // 4:
            prefix = ""

        budget = chunk_size - len(prefix)
        pieces = _add_overlap(_split_to_budget(body, budget), overlap, budget)
        chunks.extend(f"{prefix}{piece}".strip() for piece in pieces)

    return [c for c in chunks if c]


async def get_embeddings(texts: List[str]) -> List[List[float]]:
    """Embed text locally. Raises on failure so callers can mark the document failed."""
    def _embed():
        return [list(map(float, v)) for v in get_embedding_fn()(texts)]

    return await asyncio.to_thread(_embed)


def update_document(doc_id: str, **fields):
    """Patch one document's record in place."""
    docs = load_documents()
    for d in docs:
        if d.id == doc_id:
            for key, value in fields.items():
                setattr(d, key, value)
            break
    else:
        return
    save_documents(docs)


def index_is_healthy(document: Document) -> bool:
    """True only if this document's vectors are actually present in ChromaDB.

    Guards against a wiped or partially written chroma_db: without this the
    registry would still say "ready" and every question would retrieve nothing.
    """
    expected = getattr(document, "chunks", 0)
    if expected <= 0:
        return False
    try:
        collection = chroma_client.get_collection(name=get_collection_name(document.id))
        return collection.count() == expected
    except Exception:
        return False


async def index_document(document: Document):
    """Extract text, chunk, embed, and store in ChromaDB.

    Status only becomes "ready" once the chunks are actually in ChromaDB.
    """
    try:
        text = extract_text_from_file(Path(document.path), document.type)
        if not text:
            raise ValueError("No text could be extracted from this file")

        chunks = chunk_text(text)
        if not chunks:
            raise ValueError("Document produced no text chunks")

        embeddings = await get_embeddings(chunks)

        # Rebuild from scratch so re-indexing never leaves stale or
        # wrong-dimension vectors behind.
        name = get_collection_name(document.id)
        try:
            chroma_client.delete_collection(name=name)
        except Exception:
            pass
        collection = chroma_client.create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )

        collection.add(
            ids=[f"{document.id}_chunk_{i}" for i in range(len(chunks))],
            documents=chunks,
            embeddings=embeddings,
            metadatas=[
                {"document_id": document.id, "document_name": document.name, "chunk_index": i}
                for i in range(len(chunks))
            ],
        )

        update_document(
            document.id,
            status="ready",
            chunks=len(chunks),
            embeddingModel=EMBEDDING_MODEL,
            indexVersion=INDEX_VERSION,
            error=None,
        )
        print(f"Indexed {document.name}: {len(chunks)} chunks")
    except Exception as e:
        print(f"Indexing failed for {document.name}: {e}")
        update_document(document.id, status="error", error=str(e))


async def search_document(document_id: str, query: str, top_k: int = 5) -> List[dict]:
    """Search for relevant chunks in a document."""
    collection = chroma_client.get_or_create_collection(name=get_collection_name(document_id))
    
    query_embedding = await get_embeddings([query])
    
    results = collection.query(
        query_embeddings=query_embedding,
        n_results=top_k,
        include=["documents", "metadatas", "distances"]
    )
    
    sources = []
    if results['documents'] and results['documents'][0]:
        for i, doc in enumerate(results['documents'][0]):
            metadata = results['metadatas'][0][i]
            distance = results['distances'][0][i] if results['distances'] else 0
            # Convert distance to similarity score (0-1)
            score = max(0, 1 - distance)
            sources.append({
                "document_id": metadata.get("document_id", document_id),
                "document_name": metadata.get("document_name", "Unknown"),
                "content": doc,
                "score": score
            })
    return sources


def preview_sources(sources: List[dict], limit: int = 500) -> List[dict]:
    """Shorten chunks for display only - never for the model context."""
    return [
        {**s, "content": s["content"][:limit] + "..." if len(s["content"]) > limit else s["content"]}
        for s in sources
    ]


async def generate_chat_response(query: str, document_id: str):
    docs = load_documents()
    doc = next((d for d in docs if d.id == document_id), None)

    if not doc:
        yield f"data: {json.dumps({'error': 'Document not found'})}\n\n"
        yield "data: [DONE]\n\n"
        return

    if not deepseek_client:
        content = "DeepSeek API key not configured. Please add DEEPSEEK_API_KEY to your .env file."
        words = content.split()
        for word in words:
            yield f"data: {json.dumps({'content': word + ' '})}\n\n"
            await asyncio.sleep(0.02)
        yield "data: [DONE]\n\n"
        return

    # Search for relevant context
    sources = await search_document(document_id, query)
    
    # Build context from sources
    context = "\n\n".join([f"[Source: {s['document_name']}]\n{s['content']}" for s in sources])
    
    system_prompt = """You are a helpful assistant that answers questions based on the provided document context. 
    Use only the information from the context to answer. If the answer isn't in the context, say so.
    Cite sources using [Source: document_name] format."""
    
    user_prompt = f"Context:\n{context}\n\nQuestion: {query}"
    
    try:
        stream = await deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            stream=True,
            temperature=0.3
        )
        
        full_content = ""
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                content_piece = chunk.choices[0].delta.content
                full_content += content_piece
                yield f"data: {json.dumps({'content': content_piece})}\n\n"
        
        # Send sources at the end
        if sources:
            yield f"data: {json.dumps({'sources': preview_sources(sources)})}\n\n"
        yield "data: [DONE]\n\n"
        
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        yield f"data: {json.dumps({'content': error_msg})}\n\n"
        yield "data: [DONE]\n\n"


@app.get("/")
async def home():
    return {"status": "ok", "message": "OmniDocAI API is running smoothly"}


@app.get("/documents")
async def list_documents():
    docs = load_documents()
    return {"documents": [d.model_dump() for d in docs]}


@app.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    ext = Path(file.filename).suffix.lower()
    supported_extensions = {'.pdf', '.txt', '.md', '.markdown', '.docx', '.json'}

    if ext not in supported_extensions:
        raise HTTPException(
            400,
            f"Unsupported file extension: '{ext}'. Supported: {', '.join(sorted(supported_extensions))}"
        )

    mime_from_ext = {
        '.pdf': 'application/pdf',
        '.txt': 'text/plain',
        '.md': 'text/markdown',
        '.markdown': 'text/markdown',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.json': 'application/json',
    }
    content_type = file.content_type
    if not content_type or content_type == 'application/octet-stream':
        content_type = mime_from_ext.get(ext, 'application/octet-stream')

    allowed_types = {
        'application/pdf',
        'text/plain',
        'text/markdown',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/json',
    }
    if content_type not in allowed_types:
        raise HTTPException(400, f"Unsupported file type: {content_type}")

    doc_id = str(uuid.uuid4())
    save_path = UPLOAD_DIR / f"{doc_id}{ext}"

    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    size = save_path.stat().st_size
    if size > 10 * 1024 * 1024:
        save_path.unlink()
        raise HTTPException(400, "File too large (max 10MB)")

    doc = Document(
        id=doc_id,
        name=file.filename,
        size=size,
        type=content_type,
        uploadedAt=datetime.utcnow().isoformat(),
        status="processing",
        path=str(save_path)
    )

    docs = load_documents()
    docs.append(doc)
    save_documents(docs)

    # index_document flips the status to "ready" or "error" when it actually finishes.
    spawn(index_document(doc))

    return {"document": doc.model_dump()}


@app.on_event("startup")
async def reindex_stale_documents():
    """Re-index anything left unfinished or embedded with an older model."""
    # Run re-indexing in background without blocking startup
    async def _reindex():
        stale = [
            d for d in load_documents()
            if d.status != "ready"
            or getattr(d, 'embeddingModel', None) != EMBEDDING_MODEL
            or getattr(d, 'indexVersion', 0) != INDEX_VERSION
            or not index_is_healthy(d)
        ]
        for doc in stale:
            if not Path(doc.path).exists():
                update_document(doc.id, status="error", error="Source file is missing")
                continue
            update_document(doc.id, status="processing")
            spawn(index_document(doc))
        if stale:
            print(f"Re-indexing {len(stale)} document(s)")
    
    spawn(_reindex())


@app.delete("/documents/{document_id}")
async def delete_document(document_id: str):
    docs = load_documents()
    doc = next((d for d in docs if d.id == document_id), None)
    
    if not doc:
        raise HTTPException(404, "Document not found")
    
    # Delete file
    file_path = Path(doc.path)
    if file_path.exists():
        file_path.unlink()
    
    # Delete from ChromaDB
    try:
        chroma_client.delete_collection(name=get_collection_name(document_id))
    except Exception:
        pass
    
    # Remove from documents list
    docs = [d for d in docs if d.id != document_id]
    save_documents(docs)
    
    return {"status": "deleted"}


@app.post("/chat")
async def chat(request: ChatRequest):
    return StreamingResponse(
        generate_chat_response(request.query, request.document_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )