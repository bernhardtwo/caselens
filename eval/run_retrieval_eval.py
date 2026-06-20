"""Retrieval eval (spec-0001): recall@k, rerank lift, and a grounded-answer citation check.

Run from the repo root with CO_API_KEY set and the corpus already ingested:

    uv run --project apps/api python eval/run_retrieval_eval.py [--answers] [--k K] [--n N]

Not wired into CI yet (ADR-0006): it needs a live key and a populated database.
"""

import argparse
import json
import os
import time
from pathlib import Path

from caselens.clients import get_cohere_client
from caselens.config.settings import get_settings
from caselens.rag.answer import build_answer, cited_sources
from caselens.rag.db import connect
from caselens.rag.embed import embed_queries
from caselens.rag.models import RetrievedChunk
from caselens.rag.retrieve import rerank_chunks, vector_search

_GOLDEN = Path(__file__).parent / "golden" / "retrieval.jsonl"


def _load_cases() -> list[dict]:
    with _GOLDEN.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _matches(chunk: RetrievedChunk, case: dict) -> bool:
    return (
        os.path.basename(chunk.source_path) == case["expected_source"]
        and chunk.section == case["expected_section"]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="retrieval-eval")
    parser.add_argument("--k", type=int, default=None)
    parser.add_argument("--n", type=int, default=None)
    parser.add_argument(
        "--answers",
        action="store_true",
        help="Also run the grounded-answer citation check (uses Command calls).",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=6.5,
        help="Seconds between cases to respect Cohere's trial limit (10/min per endpoint).",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    k = args.k or settings.retrieval_k
    n = args.n or settings.rerank_n
    co = get_cohere_client(settings)
    cases = _load_cases()
    query_vectors = embed_queries([case["query"] for case in cases], settings=settings, co=co)

    recall_hits = 0
    lifts: list[int] = []
    answer_hits = answer_total = 0

    with connect(settings) as conn:
        for index, (case, query_vector) in enumerate(zip(cases, query_vectors, strict=True)):
            if index:
                # Trial cap is 10/min per endpoint; one rerank (and one Command) call per case.
                time.sleep(args.sleep)
            candidates = vector_search(conn, query_vector, k)
            vector_rank = next((c.vector_rank for c in candidates if _matches(c, case)), None)
            reranked = rerank_chunks(co, case["query"], candidates, settings.rerank_model, n)
            rerank_rank = next((c.rerank_rank for c in reranked if _matches(c, case)), None)
            if vector_rank is not None:
                recall_hits += 1
            if vector_rank is not None and rerank_rank is not None:
                lifts.append(vector_rank - rerank_rank)
            note = f"vec#{vector_rank or '-'} -> rerank#{rerank_rank or '-'}"
            if args.answers:
                grounded = build_answer(case["query"], reranked, co=co, settings=settings)
                answer_total += 1
                ok = case["expected_source"] in cited_sources(grounded)
                answer_hits += int(ok)
                note += f" | cites expected: {'yes' if ok else 'no'}"
            print(f"- {case['query'][:58]:58s} {note}")

    total = len(cases)
    print()
    print(f"recall@{k}: {recall_hits}/{total} = {recall_hits / total:.2f}")
    if lifts:
        print(f"rerank lift (mean vec_rank - rerank_rank over {len(lifts)} hits): "
              f"{sum(lifts) / len(lifts):+.2f}")
    if args.answers:
        print(f"answers citing an expected source: {answer_hits}/{answer_total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
