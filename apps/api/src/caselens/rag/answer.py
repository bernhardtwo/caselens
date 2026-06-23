import os
from collections.abc import Sequence

import cohere

from caselens.clients import get_cohere_client
from caselens.config.settings import Settings, get_settings

from .models import Citation, GroundedAnswer, RetrievedChunk
from .retrieve import retrieve


class CitationError(RuntimeError):
    """Raised when an answer over documents carries no citations (ADR-0002)."""


def document(index: int, chunk: RetrievedChunk) -> dict:
    return {
        "id": str(index),
        "data": {
            "title": f"{chunk.title} — {chunk.section}",
            "text": chunk.text,
            "source": os.path.basename(chunk.source_path),
        },
    }


def _leading_int(value: str) -> int | None:
    digits = ""
    for char in value:
        if char.isdigit():
            digits += char
        else:
            break
    return int(digits) if digits else None


def citations(raw: list | None) -> list[Citation]:
    citations: list[Citation] = []
    for item in raw or []:
        ids: list[str] = []
        for source in getattr(item, "sources", None) or []:
            sid = getattr(source, "id", None)
            if sid is None:
                document = getattr(source, "document", None)
                sid = getattr(document, "id", None) if document is not None else None
            if sid is not None:
                ids.append(str(sid))
        citations.append(Citation(start=item.start, end=item.end, text=item.text, sources=ids))
    return citations


def build_answer(
    query: str, chunks: Sequence[RetrievedChunk], *, co: cohere.ClientV2, settings: Settings
) -> GroundedAnswer:
    documents = [document(i, chunk) for i, chunk in enumerate(chunks)]
    resp = co.chat(
        model=settings.chat_model,
        messages=[{"role": "user", "content": query}],
        documents=documents,
    )
    text = resp.message.content[0].text if resp.message.content else ""
    parsed = citations(resp.message.citations)
    if documents and not parsed:
        raise CitationError("La respuesta no cita ninguna fuente sobre los documentos (ADR-0002).")
    return GroundedAnswer(text=text, citations=parsed, sources=list(chunks))


def cited_sources(answer: GroundedAnswer) -> set[str]:
    sources: set[str] = set()
    for citation in answer.citations:
        for sid in citation.sources:
            index = _leading_int(sid)
            if index is not None and 0 <= index < len(answer.sources):
                sources.add(os.path.basename(answer.sources[index].source_path))
    return sources


def answer(
    query: str, *, k: int | None = None, n: int | None = None, settings: Settings | None = None
) -> GroundedAnswer:
    settings = settings or get_settings()
    co = get_cohere_client(settings)
    chunks = retrieve(query, k=k, n=n, co=co, settings=settings)
    if not chunks:
        return GroundedAnswer(text="", citations=[], sources=[])
    return build_answer(query, chunks, co=co, settings=settings)
