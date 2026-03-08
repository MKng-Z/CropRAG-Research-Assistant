from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from rag_mvp.config import DATA_DIR, DEFAULT_SOURCE_DIR, STATIC_DIR, STORAGE_DIR
from rag_mvp.graph_builder import GraphBuilder, GraphExtractionError
from rag_mvp.graph_store import GraphStore, GraphStoreError
from rag_mvp.index_store import IndexStore
from rag_mvp.kimi_client import KimiClient, KimiClientError
from rag_mvp.progress import ProgressTracker
from rag_mvp.schemas import (
    BuildGraphRequest,
    BuildIndexRequest,
    ChatRequest,
    ChatResponse,
    GraphSearchRequest,
    GraphSearchResponse,
    GraphStatusResponse,
    HealthResponse,
    IndexStatusResponse,
    ProgressResponse,
    UploadResponse,
)

app = FastAPI(title="Kimi RAG MVP", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for directory in (DATA_DIR, STORAGE_DIR, STATIC_DIR):
    directory.mkdir(parents=True, exist_ok=True)

index_store = IndexStore(STORAGE_DIR / "index.json")
kimi_client = KimiClient()
graph_store = GraphStore()
progress_tracker = ProgressTracker()
graph_builder = GraphBuilder(index_store=index_store, kimi_client=kimi_client, graph_store=graph_store)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


async def search_graph_with_fallback(question: str, top_k: int):
    facts = await run_in_threadpool(graph_store.search_graph, question, top_k)
    if facts or not kimi_client.is_configured:
        return facts

    try:
        expanded_query = await kimi_client.expand_query(question)
    except KimiClientError:
        return facts

    expanded_query = expanded_query.strip()
    if not expanded_query or expanded_query == question.strip():
        return facts

    return await run_in_threadpool(graph_store.search_graph, expanded_query, top_k)


@app.get("/", include_in_schema=False)
async def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    status = "ready" if index_store.has_index() else "needs_index"
    graph_status = graph_store.get_status()
    return HealthResponse(
        status=status,
        default_source_dir=str(DEFAULT_SOURCE_DIR),
        kimi_configured=kimi_client.is_configured,
        neo4j_configured=graph_status.configured,
        neo4j_driver_available=graph_status.driver_available,
    )


@app.get("/api/index/status", response_model=IndexStatusResponse)
async def index_status() -> IndexStatusResponse:
    return index_store.status()


@app.get("/api/index/progress", response_model=ProgressResponse)
async def index_progress() -> ProgressResponse:
    return progress_tracker.get("index")


@app.post("/api/index/build", response_model=IndexStatusResponse)
async def build_index(request: BuildIndexRequest) -> IndexStatusResponse:
    source_dir = request.source_dir.strip()
    if not source_dir:
        raise HTTPException(status_code=400, detail="source_dir is required")

    path = Path(source_dir)
    if not path.exists() or not path.is_dir():
        raise HTTPException(status_code=404, detail=f"Directory not found: {source_dir}")

    progress_tracker.start("index", total_steps=len(list(path.glob('*.pdf'))), message="Preparing to build index")
    try:
        status = await run_in_threadpool(
            index_store.build_from_directory,
            path,
            request.chunk_size,
            request.overlap,
            lambda **kwargs: progress_tracker.update("index", **kwargs),
        )
        progress_tracker.finish("index", f"Indexed {status.document_count} PDF files")
        return status
    except ValueError as exc:
        progress_tracker.fail("index", str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        progress_tracker.fail("index", str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/graph/status", response_model=GraphStatusResponse)
async def graph_status() -> GraphStatusResponse:
    return graph_store.get_status()


@app.get("/api/graph/progress", response_model=ProgressResponse)
async def graph_progress() -> ProgressResponse:
    return progress_tracker.get("graph")


@app.post("/api/graph/build", response_model=GraphStatusResponse)
async def build_graph(request: BuildGraphRequest) -> GraphStatusResponse:
    if not kimi_client.is_configured:
        raise HTTPException(status_code=500, detail="Kimi API credentials are not configured")

    progress_tracker.start("graph", total_steps=request.max_documents, message="Preparing graph extraction")
    try:
        status = await graph_builder.rebuild_from_index(
            max_chunks_per_document=request.max_chunks_per_document,
            max_documents=request.max_documents,
            progress_callback=lambda **kwargs: progress_tracker.update("graph", **kwargs),
        )
        progress_tracker.finish("graph", f"Graph built with {status.entity_count} entities")
        return status
    except (GraphStoreError, GraphExtractionError, KimiClientError) as exc:
        progress_tracker.fail("graph", str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        progress_tracker.fail("graph", str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/graph/search", response_model=GraphSearchResponse)
async def graph_search(request: GraphSearchRequest) -> GraphSearchResponse:
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="question is required")
    try:
        facts = await search_graph_with_fallback(request.question, request.top_k)
    except GraphStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return GraphSearchResponse(query=request.question, facts=facts)


@app.post("/api/upload", response_model=UploadResponse)
async def upload_files(files: list[UploadFile] = File(...)) -> UploadResponse:
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    upload_dir = DATA_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for file in files:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix != ".pdf":
            raise HTTPException(status_code=400, detail=f"Only PDF files are supported: {file.filename}")

        destination = upload_dir / Path(file.filename).name
        contents = await file.read()
        destination.write_bytes(contents)
        saved.append(str(destination))

    return UploadResponse(message=f"Saved {len(saved)} PDF files", files=saved)


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="question is required")
    if not index_store.has_index():
        raise HTTPException(status_code=400, detail="Index has not been built yet")
    if not kimi_client.is_configured:
        raise HTTPException(status_code=500, detail="Kimi API credentials are not configured")

    matches = index_store.search(request.question, top_k=request.top_k)
    if not matches:
        try:
            expanded_query = await kimi_client.expand_query(request.question)
        except KimiClientError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        matches = index_store.search(expanded_query, top_k=request.top_k)

    if not matches:
        raise HTTPException(status_code=404, detail="No relevant chunks found in the current index")

    graph_facts = []
    if request.use_graph:
        graph_status = graph_store.get_status()
        if graph_status.ready:
            try:
                graph_facts = await search_graph_with_fallback(request.question, 6)
            except GraphStoreError:
                graph_facts = []

    try:
        answer = await kimi_client.answer_question(request.question, matches, graph_facts=graph_facts)
    except KimiClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ChatResponse(answer=answer, sources=matches, graph_facts=graph_facts)


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8010, reload=False)