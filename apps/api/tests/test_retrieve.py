from caselens.rag.db import to_vector_literal
from caselens.rag.models import RetrievedChunk
from caselens.rag.retrieve import apply_rerank, build_vector_search_sql


def _chunk(i: int) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=i,
        document_id=1,
        source_path=f"data/corpus/doc{i}.md",
        title="T",
        section=f"S{i}",
        ordinal=i,
        text=f"text {i}",
        vector_distance=0.1 * i,
        vector_rank=i + 1,
    )


def test_to_vector_literal_formats_pgvector():
    assert to_vector_literal([1, 2.5, -3.0]) == "[1.0,2.5,-3.0]"


def test_build_vector_search_sql_uses_cosine_and_deterministic_order():
    sql = build_vector_search_sql()
    assert "<=>" in sql
    assert "::vector" in sql
    assert "JOIN documents" in sql
    assert "ORDER BY" in sql and "c.id" in sql
    assert "LIMIT %(k)s" in sql


def test_apply_rerank_reorders_truncates_and_scores():
    candidates = [_chunk(0), _chunk(1), _chunk(2)]
    out = apply_rerank(candidates, [(2, 0.9), (0, 0.5)], n=5)
    assert [c.chunk_id for c in out] == [2, 0]
    assert [c.rerank_rank for c in out] == [1, 2]
    assert out[0].rerank_score == 0.9
    assert out[0].section == "S2"


def test_apply_rerank_respects_n():
    candidates = [_chunk(i) for i in range(5)]
    ranked = [(i, 1.0 - i * 0.1) for i in range(5)]
    assert len(apply_rerank(candidates, ranked, n=2)) == 2
