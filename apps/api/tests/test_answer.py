from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from caselens.config.settings import Settings
from caselens.rag.answer import CitationError, build_answer, cited_sources
from caselens.rag.models import RetrievedChunk


def _chunk(i: int, source: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=i,
        document_id=1,
        source_path=f"data/corpus/{source}",
        title="T",
        section="Sec",
        ordinal=i,
        text=f"text {i}",
        vector_distance=0.1,
        vector_rank=i + 1,
        rerank_score=0.9,
        rerank_rank=i + 1,
    )


def _chat_response(text: str, citations: list) -> SimpleNamespace:
    return SimpleNamespace(
        message=SimpleNamespace(content=[SimpleNamespace(text=text)], citations=citations)
    )


def test_build_answer_returns_citations_mapped_to_sources():
    co = MagicMock()
    citation = SimpleNamespace(start=0, end=4, text="text", sources=[SimpleNamespace(id="1")])
    co.chat.return_value = _chat_response("Body.", [citation])
    chunks = [_chunk(0, "a.md"), _chunk(1, "b.md")]
    result = build_answer("q", chunks, co=co, settings=Settings())
    assert result.text == "Body."
    assert result.citations[0].sources == ["1"]
    assert cited_sources(result) == {"b.md"}


def test_build_answer_without_citations_is_a_defect():
    co = MagicMock()
    co.chat.return_value = _chat_response("Body.", [])
    with pytest.raises(CitationError):
        build_answer("q", [_chunk(0, "a.md")], co=co, settings=Settings())
