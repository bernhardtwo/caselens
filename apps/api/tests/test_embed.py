from types import SimpleNamespace
from unittest.mock import MagicMock

from caselens.config.settings import Settings
from caselens.rag.embed import embed_passages, embed_query


def _fake_cohere(dim: int) -> MagicMock:
    def _embed(**kwargs):
        return SimpleNamespace(
            embeddings=SimpleNamespace(float_=[[0.0] * dim for _ in kwargs["texts"]])
        )

    co = MagicMock()
    co.embed.side_effect = _embed
    return co


def test_embed_passages_batches_by_size():
    settings = Settings(embed_batch_size=96, embedding_dim=4)
    co = _fake_cohere(4)
    out = embed_passages([f"t{i}" for i in range(200)], settings=settings, co=co)
    assert len(out) == 200
    assert co.embed.call_count == 3
    first = co.embed.call_args_list[0].kwargs
    assert first["input_type"] == "search_document"
    assert first["output_dimension"] == 4
    assert len(first["texts"]) == 96


def test_embed_query_uses_search_query_and_returns_one_vector():
    settings = Settings(embed_batch_size=96, embedding_dim=4)
    co = _fake_cohere(4)
    vec = embed_query("hello", settings=settings, co=co)
    assert len(vec) == 4
    assert co.embed.call_count == 1
    assert co.embed.call_args.kwargs["input_type"] == "search_query"
