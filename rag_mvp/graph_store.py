import contextlib
import importlib
import io
import json
from datetime import datetime
from pathlib import Path

from rag_mvp.config import (
    GRAPH_BUILD_METADATA,
    NEO4J_AUTH_ENABLED,
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USERNAME,
)
from rag_mvp.index_store import normalize_text, tokenize
from rag_mvp.schemas import GraphFact, GraphStatusResponse

_GRAPH_DATABASE = None
_GRAPH_IMPORT_ATTEMPTED = False


def _load_graph_database():
    global _GRAPH_DATABASE, _GRAPH_IMPORT_ATTEMPTED
    if _GRAPH_IMPORT_ATTEMPTED:
        return _GRAPH_DATABASE

    _GRAPH_IMPORT_ATTEMPTED = True
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            module = importlib.import_module("neo4j")
        _GRAPH_DATABASE = module.GraphDatabase
    except Exception:
        _GRAPH_DATABASE = None
    return _GRAPH_DATABASE


class GraphStoreError(RuntimeError):
    """Raised when graph operations fail."""


class GraphStore:
    def __init__(self) -> None:
        self.uri = NEO4J_URI
        self.auth_enabled = NEO4J_AUTH_ENABLED
        self.username = NEO4J_USERNAME
        self.password = NEO4J_PASSWORD
        self.metadata_path = GRAPH_BUILD_METADATA

    @property
    def driver_available(self) -> bool:
        return _load_graph_database() is not None

    @property
    def configured(self) -> bool:
        return bool(self.uri and ((self.username and self.password) or not self.auth_enabled))

    def get_status(self) -> GraphStatusResponse:
        metadata = self._load_metadata()
        errors = metadata.get("errors", [])
        if not self.driver_available:
            errors = errors + ["Python package 'neo4j' is not installed or cannot be imported cleanly"]

        connected = False
        document_count = metadata.get("document_count", 0)
        entity_count = metadata.get("entity_count", 0)
        relation_count = metadata.get("relation_count", 0)

        if self.driver_available and self.configured:
            try:
                with self._get_driver() as driver:
                    driver.verify_connectivity()
                    connected = True
                    with driver.session() as session:
                        counts = session.run(
                            """
                            OPTIONAL MATCH (d:Document:PortfolioGraph)
                            WITH count(d) AS docs
                            OPTIONAL MATCH (e:Entity:PortfolioGraph)
                            WITH docs, count(e) AS entities
                            OPTIONAL MATCH (:Entity:PortfolioGraph)-[r:RELATED_TO]-(:Entity:PortfolioGraph)
                            RETURN docs, entities, count(r) AS relations
                            """
                        ).single()
                        if counts is not None:
                            document_count = counts["docs"]
                            entity_count = counts["entities"]
                            relation_count = counts["relations"]
            except Exception as exc:
                errors = errors + [f"Neo4j connection failed: {exc}"]

        ready = connected and entity_count > 0
        return GraphStatusResponse(
            configured=self.configured,
            driver_available=self.driver_available,
            connected=connected,
            ready=ready,
            uri=self.uri,
            document_count=document_count,
            entity_count=entity_count,
            relation_count=relation_count,
            last_built_at=metadata.get("last_built_at"),
            errors=errors,
        )

    def rebuild_graph(self, documents: list[dict], progress_callback=None) -> GraphStatusResponse:
        if not self.driver_available:
            raise GraphStoreError("Python package 'neo4j' is not installed or cannot be imported cleanly")
        if not self.configured:
            raise GraphStoreError("Neo4j connection variables are not configured")

        errors: list[str] = []
        total_documents = len(documents)
        with self._get_driver() as driver:
            driver.verify_connectivity()
            with driver.session() as session:
                if progress_callback:
                    progress_callback(
                        stage="resetting_graph",
                        progress=0.84,
                        current_item="PortfolioGraph",
                        completed_steps=0,
                        total_steps=total_documents,
                        message="Clearing old graph snapshot",
                    )
                session.run("MATCH (n:PortfolioGraph) DETACH DELETE n")
                self._initialize_schema(session)
                for index, document in enumerate(documents, start=1):
                    if progress_callback:
                        progress_callback(
                            stage="writing_graph",
                            progress=0.84 + (index / max(total_documents, 1)) * 0.14,
                            current_item=document["file_name"],
                            completed_steps=index,
                            total_steps=total_documents,
                            message=f"Writing {document['file_name']} to Neo4j",
                        )
                    try:
                        self._write_document(session, document)
                    except Exception as exc:
                        errors.append(f"{document['file_name']}: {exc}")

                counts = session.run(
                    """
                    MATCH (d:Document:PortfolioGraph) WITH count(d) AS docs
                    MATCH (e:Entity:PortfolioGraph) WITH docs, count(e) AS entities
                    MATCH (:Entity:PortfolioGraph)-[r:RELATED_TO]-(:Entity:PortfolioGraph)
                    RETURN docs, entities, count(r) AS relations
                    """
                ).single()

        metadata = {
            "last_built_at": datetime.now().isoformat(timespec="seconds"),
            "document_count": counts["docs"] if counts is not None else 0,
            "entity_count": counts["entities"] if counts is not None else 0,
            "relation_count": counts["relations"] if counts is not None else 0,
            "errors": errors,
        }
        self._save_metadata(metadata)
        return self.get_status()

    def search_graph(self, question: str, top_k: int) -> list[GraphFact]:
        status = self.get_status()
        if not status.connected:
            raise GraphStoreError("Neo4j is not connected")

        terms = [term for term in tokenize(normalize_text(question)) if len(term) >= 2][:8]
        if not terms:
            return []

        with self._get_driver() as driver:
            with driver.session() as session:
                rows = session.run(
                    """
                    WITH $terms AS terms
                    MATCH (e:Entity:PortfolioGraph)
                    WHERE any(term IN terms WHERE toLower(e.name) CONTAINS term)
                    MATCH (d:Document:PortfolioGraph)-[:MENTIONS]->(e)
                    OPTIONAL MATCH (e)-[r:RELATED_TO]-(other:Entity:PortfolioGraph)
                    WITH e, d, r, other,
                         size([term IN terms WHERE toLower(e.name) CONTAINS term]) AS entity_score,
                         CASE WHEN other IS NULL THEN 0 ELSE size([term IN terms WHERE toLower(other.name) CONTAINS term]) END AS neighbor_score
                    RETURN e.name AS source,
                           e.type AS source_type,
                           coalesce(r.type, 'MENTIONS') AS relation,
                           coalesce(other.name, d.file_name) AS target,
                           coalesce(other.type, 'Document') AS target_type,
                           d.file_name AS document,
                           coalesce(r.evidence, '') AS evidence,
                           (entity_score * 1.0 + neighbor_score * 0.35) AS score
                    ORDER BY score DESC, document ASC
                    LIMIT $limit
                    """,
                    terms=terms,
                    limit=top_k,
                ).data()

        facts: list[GraphFact] = []
        for index, row in enumerate(rows, start=1):
            facts.append(
                GraphFact(
                    rank=index,
                    score=round(float(row.get("score", 0.0)), 4),
                    source=row.get("source", ""),
                    source_type=row.get("source_type", "Entity"),
                    relation=row.get("relation", "RELATED_TO"),
                    target=row.get("target", ""),
                    target_type=row.get("target_type", "Entity"),
                    document=row.get("document", ""),
                    evidence=row.get("evidence", ""),
                )
            )
        return facts

    def _initialize_schema(self, session) -> None:
        session.run("CREATE CONSTRAINT document_file IF NOT EXISTS FOR (d:Document) REQUIRE d.file_name IS UNIQUE")
        session.run("CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.name)")

    def _write_document(self, session, document: dict) -> None:
        session.run(
            """
            MERGE (d:Document:PortfolioGraph {file_name: $file_name})
            SET d.source_path = $source_path,
                d.summary = $summary,
                d.updated_at = datetime()
            """,
            file_name=document["file_name"],
            source_path=document["source_path"],
            summary=document.get("summary", ""),
        )

        for entity in document.get("entities", []):
            session.run(
                """
                MATCH (d:Document:PortfolioGraph {file_name: $file_name})
                MERGE (e:Entity:PortfolioGraph {name: $name, type: $type})
                MERGE (d)-[:MENTIONS]->(e)
                """,
                file_name=document["file_name"],
                name=entity["name"],
                type=entity["type"],
            )

        for relation in document.get("relationships", []):
            session.run(
                """
                MATCH (source:Entity:PortfolioGraph {name: $source})
                MATCH (target:Entity:PortfolioGraph {name: $target})
                MERGE (source)-[r:RELATED_TO {type: $type, document: $document}]->(target)
                SET r.evidence = $evidence,
                    r.updated_at = datetime()
                """,
                source=relation["source"],
                target=relation["target"],
                type=relation["type"],
                document=document["file_name"],
                evidence=relation.get("evidence", ""),
            )

    def _get_driver(self):
        graph_database = _load_graph_database()
        if graph_database is None:
            raise GraphStoreError("Python package 'neo4j' is not installed or cannot be imported cleanly")
        if self.auth_enabled:
            return graph_database.driver(self.uri, auth=(self.username, self.password))
        return graph_database.driver(self.uri)

    def _load_metadata(self) -> dict:
        if not self.metadata_path.exists():
            return {}
        return json.loads(self.metadata_path.read_text(encoding="utf-8"))

    def _save_metadata(self, metadata: dict) -> None:
        Path(self.metadata_path).parent.mkdir(parents=True, exist_ok=True)
        self.metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")