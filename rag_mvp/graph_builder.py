from rag_mvp.schemas import GraphEntity, GraphRelation


class GraphExtractionError(RuntimeError):
    """Raised when graph extraction fails."""


class GraphBuilder:
    def __init__(self, index_store, kimi_client, graph_store) -> None:
        self.index_store = index_store
        self.kimi_client = kimi_client
        self.graph_store = graph_store

    async def rebuild_from_index(
        self,
        max_chunks_per_document: int,
        max_documents: int,
        progress_callback=None,
    ):
        if not self.index_store.has_index():
            raise GraphExtractionError("Index has not been built yet")

        packets = self.index_store.get_document_packets(max_chunks_per_document, max_documents)
        if not packets:
            raise GraphExtractionError("No document packets are available for graph extraction")

        total_documents = len(packets)
        extracted_documents = []
        for index, packet in enumerate(packets, start=1):
            if progress_callback:
                progress_callback(
                    stage="extracting_entities",
                    progress=(index - 1) / max(total_documents, 1) * 0.72,
                    current_item=packet["file_name"],
                    completed_steps=index - 1,
                    total_steps=total_documents,
                    message=f"Extracting entities from {packet['file_name']}",
                )
            graph_json = await self.kimi_client.extract_document_graph(packet["file_name"], packet["text"])
            entities = []
            seen_entities = set()
            for item in graph_json.get("entities", []):
                name = str(item.get("name", "")).strip()
                entity_type = str(item.get("type", "")).strip() or "Concept"
                key = (name.lower(), entity_type.lower())
                if not name or key in seen_entities:
                    continue
                seen_entities.add(key)
                entities.append(GraphEntity(name=name, type=entity_type).model_dump())

            relationships = []
            seen_relations = set()
            valid_names = {entity["name"] for entity in entities}
            for item in graph_json.get("relationships", []):
                source = str(item.get("source", "")).strip()
                target = str(item.get("target", "")).strip()
                relation_type = str(item.get("type", "")).strip() or "RELATED_TO"
                evidence = str(item.get("evidence", "")).strip()
                key = (source.lower(), target.lower(), relation_type.lower())
                if not source or not target or source == target:
                    continue
                if source not in valid_names or target not in valid_names:
                    continue
                if key in seen_relations:
                    continue
                seen_relations.add(key)
                relationships.append(
                    GraphRelation(
                        source=source,
                        target=target,
                        type=relation_type,
                        evidence=evidence,
                    ).model_dump()
                )

            extracted_documents.append(
                {
                    "file_name": packet["file_name"],
                    "source_path": packet["source_path"],
                    "summary": graph_json.get("summary", ""),
                    "entities": entities,
                    "relationships": relationships,
                }
            )

        if progress_callback:
            progress_callback(
                stage="writing_graph",
                progress=0.8,
                current_item="Neo4j",
                completed_steps=total_documents,
                total_steps=total_documents,
                message="Writing graph nodes and edges to Neo4j",
            )

        return self.graph_store.rebuild_graph(extracted_documents, progress_callback=progress_callback)
