import json
import math
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Callable

from pypdf import PdfReader

from rag_mvp.schemas import IndexStatusResponse, SourceHit

WORD_RE = re.compile(r"[a-zA-Z0-9_]+")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
SPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    return SPACE_RE.sub(" ", text or "").strip()


def tokenize(text: str) -> list[str]:
    lowered = (text or "").lower()
    english_words = WORD_RE.findall(lowered)
    chinese_chars = CJK_RE.findall(lowered)
    chinese_bigrams = [
        chinese_chars[index] + chinese_chars[index + 1]
        for index in range(len(chinese_chars) - 1)
    ]
    return english_words + chinese_chars + chinese_bigrams


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    chunks: list[str] = []
    start = 0
    text = text.strip()
    while start < len(text):
        end = min(len(text), start + chunk_size)
        if end < len(text):
            window = text[start:end]
            split_markers = [window.rfind(marker) for marker in ("。", "！", "？", ".", ";", "；")]
            split_at = max(split_markers)
            if split_at > int(chunk_size * 0.6):
                end = start + split_at + 1

        chunk = text[start:end].strip()
        if len(chunk) >= 80:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


class IndexStore:
    def __init__(self, index_path: Path):
        self.index_path = index_path
        self.state = self._load_state()

    def has_index(self) -> bool:
        return bool(self.state.get("chunks"))

    def status(self) -> IndexStatusResponse:
        metadata = self.state.get("metadata", {})
        return IndexStatusResponse(
            ready=self.has_index(),
            built_at=metadata.get("built_at"),
            source_dir=metadata.get("source_dir"),
            document_count=len(self.state.get("documents", [])),
            chunk_count=len(self.state.get("chunks", [])),
            chunk_size=metadata.get("chunk_size", 0),
            overlap=metadata.get("overlap", 0),
            files=[document["file_name"] for document in self.state.get("documents", [])],
            errors=metadata.get("errors", []),
        )

    def build_from_directory(
        self,
        source_dir: Path,
        chunk_size: int,
        overlap: int,
        progress_callback: Callable[..., None] | None = None,
    ) -> IndexStatusResponse:
        pdf_files = sorted(source_dir.glob("*.pdf"))
        if not pdf_files:
            raise ValueError(f"No PDF files found in {source_dir}")

        chunks: list[dict] = []
        documents: list[dict] = []
        errors: list[str] = []
        document_frequency: Counter[str] = Counter()
        total_files = len(pdf_files)

        for file_index, pdf_file in enumerate(pdf_files, start=1):
            if progress_callback:
                progress_callback(
                    stage="extracting",
                    progress=(file_index - 1) / max(total_files, 1) * 0.75,
                    current_item=pdf_file.name,
                    completed_steps=file_index - 1,
                    total_steps=total_files,
                    message=f"Extracting text from {pdf_file.name}",
                )
            try:
                reader = PdfReader(str(pdf_file))
                page_count = len(reader.pages)
                total_chars = 0

                for page_index, page in enumerate(reader.pages, start=1):
                    text = normalize_text(page.extract_text() or "")
                    if not text:
                        continue

                    page_chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
                    total_chars += len(text)

                    for chunk_index, chunk in enumerate(page_chunks, start=1):
                        tokens = tokenize(chunk)
                        if not tokens:
                            continue
                        term_counts = Counter(tokens)
                        chunk_id = f"{pdf_file.stem}-p{page_index}-c{chunk_index}"
                        chunks.append(
                            {
                                "chunk_id": chunk_id,
                                "file_name": pdf_file.name,
                                "source_path": str(pdf_file),
                                "page_number": page_index,
                                "chunk_index": chunk_index,
                                "text": chunk,
                                "term_counts": dict(term_counts),
                            }
                        )
                        document_frequency.update(term_counts.keys())

                documents.append(
                    {
                        "file_name": pdf_file.name,
                        "source_path": str(pdf_file),
                        "page_count": page_count,
                        "character_count": total_chars,
                    }
                )
            except Exception as exc:
                errors.append(f"{pdf_file.name}: {exc}")

        total_chunks = len(chunks)
        if total_chunks == 0:
            raise ValueError("No readable text was extracted from the provided PDFs")

        if progress_callback:
            progress_callback(
                stage="vectorizing",
                progress=0.82,
                current_item="idf-build",
                completed_steps=total_files,
                total_steps=total_files,
                message="Building sparse retrieval index",
            )

        idf = {
            token: math.log((1 + total_chunks) / (1 + frequency)) + 1.0
            for token, frequency in document_frequency.items()
        }

        for chunk in chunks:
            term_counts = chunk.pop("term_counts")
            token_total = sum(term_counts.values())
            weights: dict[str, float] = {}
            for token, count in term_counts.items():
                tf = count / token_total
                weights[token] = tf * idf[token]
            norm = math.sqrt(sum(weight * weight for weight in weights.values())) or 1.0
            chunk["weights"] = weights
            chunk["norm"] = norm

        if progress_callback:
            progress_callback(
                stage="persisting",
                progress=0.94,
                current_item=self.index_path.name,
                completed_steps=total_files,
                total_steps=total_files,
                message="Saving index to disk",
            )

        self.state = {
            "metadata": {
                "built_at": datetime.now().isoformat(timespec="seconds"),
                "source_dir": str(source_dir),
                "chunk_size": chunk_size,
                "overlap": overlap,
                "errors": errors,
            },
            "documents": documents,
            "idf": idf,
            "chunks": chunks,
        }
        self._persist_state()
        return self.status()

    def search(self, query: str, top_k: int) -> list[SourceHit]:
        query = normalize_text(query)
        if not query:
            return []

        idf: dict[str, float] = self.state.get("idf", {})
        query_counts = Counter(tokenize(query))
        if not query_counts:
            return []

        query_total = sum(query_counts.values())
        query_weights = {
            token: (count / query_total) * idf.get(token, 0.0)
            for token, count in query_counts.items()
            if idf.get(token, 0.0) > 0
        }
        if not query_weights:
            return []

        query_norm = math.sqrt(sum(weight * weight for weight in query_weights.values())) or 1.0
        scored_hits: list[tuple[float, dict]] = []

        for chunk in self.state.get("chunks", []):
            dot_product = 0.0
            for token, query_weight in query_weights.items():
                dot_product += query_weight * chunk["weights"].get(token, 0.0)
            if dot_product <= 0:
                continue
            score = dot_product / (query_norm * chunk["norm"])
            scored_hits.append((score, chunk))

        scored_hits.sort(key=lambda item: item[0], reverse=True)
        results: list[SourceHit] = []
        for rank, (score, chunk) in enumerate(scored_hits[:top_k], start=1):
            results.append(
                SourceHit(
                    rank=rank,
                    score=round(score, 4),
                    chunk_id=chunk["chunk_id"],
                    file_name=chunk["file_name"],
                    source_path=chunk["source_path"],
                    page_number=chunk["page_number"],
                    preview=chunk["text"][:360],
                )
            )
        return results

    def get_document_packets(self, max_chunks_per_document: int, max_documents: int) -> list[dict]:
        packets: list[dict] = []
        chunks = sorted(
            self.state.get("chunks", []),
            key=lambda item: (item["file_name"], item["page_number"], item.get("chunk_index", 0)),
        )
        grouped: dict[str, list[dict]] = {}
        for chunk in chunks:
            grouped.setdefault(chunk["file_name"], []).append(chunk)

        documents = self.state.get("documents", [])[:max_documents]
        for document in documents:
            file_name = document["file_name"]
            selected_chunks = grouped.get(file_name, [])[:max_chunks_per_document]
            if not selected_chunks:
                continue
            packets.append(
                {
                    "file_name": file_name,
                    "source_path": document["source_path"],
                    "text": "\n\n".join(chunk["text"] for chunk in selected_chunks),
                    "pages": sorted({chunk["page_number"] for chunk in selected_chunks}),
                }
            )
        return packets

    def _load_state(self) -> dict:
        if not self.index_path.exists():
            return {"metadata": {}, "documents": [], "idf": {}, "chunks": []}
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def _persist_state(self) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
