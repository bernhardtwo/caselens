from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    section: str
    ordinal: int
    text: str


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: int
    document_id: int
    source_path: str
    title: str
    section: str
    ordinal: int
    text: str
    vector_distance: float
    vector_rank: int
    rerank_score: float | None = None
    rerank_rank: int | None = None


@dataclass(frozen=True)
class Citation:
    start: int
    end: int
    text: str
    sources: list[str]


@dataclass(frozen=True)
class GroundedAnswer:
    text: str
    citations: list[Citation]
    sources: list[RetrievedChunk]


@dataclass(frozen=True)
class IngestReport:
    documents_ingested: int
    documents_skipped: int
    chunks_written: int
