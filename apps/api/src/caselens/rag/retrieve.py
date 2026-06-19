from dataclasses import replace

import cohere
import psycopg

from caselens.clients import get_cohere_client
from caselens.config.settings import Settings, get_settings

from .db import connect, to_vector_literal
from .embed import embed_query
from .models import RetrievedChunk


def build_vector_search_sql() -> str:
    return (
        "SELECT c.id, c.document_id, d.source_path, d.title, c.section, c.ordinal, c.text, "
        "c.embedding <=> %(qvec)s::vector AS distance "
        "FROM chunks c JOIN documents d ON d.id = c.document_id "
        "ORDER BY c.embedding <=> %(qvec)s::vector, c.id "
        "LIMIT %(k)s"
    )


def vector_search(
    conn: psycopg.Connection, query_vector: list[float], k: int
) -> list[RetrievedChunk]:
    with conn.cursor() as cur:
        cur.execute(build_vector_search_sql(), {"qvec": to_vector_literal(query_vector), "k": k})
        rows = cur.fetchall()
    return [
        RetrievedChunk(
            chunk_id=row[0],
            document_id=row[1],
            source_path=row[2],
            title=row[3],
            section=row[4],
            ordinal=row[5],
            text=row[6],
            vector_distance=float(row[7]),
            vector_rank=rank,
        )
        for rank, row in enumerate(rows, start=1)
    ]


def apply_rerank(
    candidates: list[RetrievedChunk], ranked: list[tuple[int, float]], n: int
) -> list[RetrievedChunk]:
    out: list[RetrievedChunk] = []
    for rank, (index, score) in enumerate(ranked[:n], start=1):
        out.append(replace(candidates[index], rerank_score=score, rerank_rank=rank))
    return out


def rerank_chunks(
    co: cohere.ClientV2, query: str, candidates: list[RetrievedChunk], model: str, n: int
) -> list[RetrievedChunk]:
    resp = co.rerank(model=model, query=query, documents=[c.text for c in candidates], top_n=n)
    ranked = [(result.index, result.relevance_score) for result in resp.results]
    return apply_rerank(candidates, ranked, n)


def retrieve(
    query: str,
    *,
    k: int | None = None,
    n: int | None = None,
    conn: psycopg.Connection | None = None,
    co: cohere.ClientV2 | None = None,
    settings: Settings | None = None,
) -> list[RetrievedChunk]:
    settings = settings or get_settings()
    k = k or settings.retrieval_k
    n = n or settings.rerank_n
    co = co or get_cohere_client(settings)
    own = conn is None
    conn = conn or connect(settings)
    try:
        candidates = vector_search(conn, embed_query(query, settings=settings, co=co), k)
        if not candidates:
            return []
        return rerank_chunks(co, query, candidates, settings.rerank_model, n)
    finally:
        if own:
            conn.close()
