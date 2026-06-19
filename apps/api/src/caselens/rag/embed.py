from collections.abc import Iterable, Sequence

import cohere

from caselens.config.settings import Settings


def _batched(items: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _embed(
    texts: Sequence[str], input_type: str, *, settings: Settings, co: cohere.ClientV2
) -> list[list[float]]:
    out: list[list[float]] = []
    for batch in _batched(list(texts), settings.embed_batch_size):
        resp = co.embed(
            model=settings.embed_model,
            input_type=input_type,
            texts=list(batch),
            embedding_types=["float"],
            output_dimension=settings.embedding_dim,
        )
        out.extend(resp.embeddings.float_)
    return out


def embed_passages(
    texts: Sequence[str], *, settings: Settings, co: cohere.ClientV2
) -> list[list[float]]:
    return _embed(texts, "search_document", settings=settings, co=co)


def embed_queries(
    queries: Sequence[str], *, settings: Settings, co: cohere.ClientV2
) -> list[list[float]]:
    return _embed(queries, "search_query", settings=settings, co=co)


def embed_query(query: str, *, settings: Settings, co: cohere.ClientV2) -> list[float]:
    return _embed([query], "search_query", settings=settings, co=co)[0]
