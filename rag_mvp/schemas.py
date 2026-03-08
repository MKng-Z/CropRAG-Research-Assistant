from typing import List

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    default_source_dir: str
    kimi_configured: bool
    neo4j_configured: bool
    neo4j_driver_available: bool


class BuildIndexRequest(BaseModel):
    source_dir: str
    chunk_size: int = Field(default=1200, ge=400, le=3000)
    overlap: int = Field(default=200, ge=0, le=800)


class SourceHit(BaseModel):
    rank: int
    score: float
    chunk_id: str
    file_name: str
    source_path: str
    page_number: int
    preview: str


class GraphEntity(BaseModel):
    name: str
    type: str


class GraphRelation(BaseModel):
    source: str
    target: str
    type: str
    evidence: str = ""


class GraphFact(BaseModel):
    rank: int
    score: float
    source: str
    source_type: str
    relation: str
    target: str
    target_type: str
    document: str
    evidence: str


class IndexStatusResponse(BaseModel):
    ready: bool
    built_at: str | None = None
    source_dir: str | None = None
    document_count: int = 0
    chunk_count: int = 0
    chunk_size: int = 0
    overlap: int = 0
    files: List[str] = []
    errors: List[str] = []


class ProgressResponse(BaseModel):
    operation: str
    status: str
    stage: str
    progress: float
    current_item: str | None = None
    completed_steps: int = 0
    total_steps: int = 0
    message: str = ""
    started_at: str | None = None
    updated_at: str | None = None
    error: str | None = None


class GraphStatusResponse(BaseModel):
    configured: bool
    driver_available: bool
    connected: bool
    ready: bool
    uri: str
    document_count: int = 0
    entity_count: int = 0
    relation_count: int = 0
    last_built_at: str | None = None
    errors: List[str] = []


class BuildGraphRequest(BaseModel):
    max_chunks_per_document: int = Field(default=6, ge=2, le=12)
    max_documents: int = Field(default=17, ge=1, le=50)


class GraphSearchRequest(BaseModel):
    question: str
    top_k: int = Field(default=8, ge=1, le=20)


class GraphSearchResponse(BaseModel):
    query: str
    facts: List[GraphFact]


class ChatRequest(BaseModel):
    question: str
    top_k: int = Field(default=5, ge=1, le=8)
    use_graph: bool = True


class ChatResponse(BaseModel):
    answer: str
    sources: List[SourceHit]
    graph_facts: List[GraphFact] = []


class UploadResponse(BaseModel):
    message: str
    files: List[str]
