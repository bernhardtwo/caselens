import argparse
import glob
import os
import sys

from caselens.clients import MissingApiKeyError
from caselens.data.db import apply_schema as apply_data_schema

from .answer import answer, cited_sources
from .db import connect, init_db
from .ingest import ingest_documents

_CORPUS_GLOB = "data/corpus/*.md"


def _dispatch(args: argparse.Namespace) -> int:
    if args.command == "init-db":
        with connect() as conn:
            init_db(conn)
            apply_data_schema(conn)
        print("Esquema aplicado.")
        return 0

    if args.command == "ingest":
        paths = args.paths or sorted(glob.glob(_CORPUS_GLOB))
        if not paths:
            print("No se encontraron documentos para ingerir.", file=sys.stderr)
            return 1
        report = ingest_documents(paths)
        print(
            f"Ingeridos {report.documents_ingested} documentos "
            f"({report.chunks_written} chunks); {report.documents_skipped} sin cambios."
        )
        return 0

    result = answer(args.text, k=args.k, n=args.n)
    if not result.sources:
        print("No hay documentos ingeridos o la búsqueda no devolvió resultados.", file=sys.stderr)
        return 1
    print(result.text)
    print("\nFuentes:")
    for index, chunk in enumerate(result.sources):
        score = "" if chunk.rerank_score is None else f" (rerank {chunk.rerank_score:.3f})"
        print(f"  [{index}] {os.path.basename(chunk.source_path)} › {chunk.section}{score}")
    cited = cited_sources(result)
    print(f"\nCitas a: {', '.join(sorted(cited)) if cited else '(ninguna)'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="caselens-rag", description="RAG core CLI (spec-0001).")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db", help="Create the pgvector schema.")
    ingest_p = sub.add_parser("ingest", help="Ingest markdown documents (defaults to data/corpus).")
    ingest_p.add_argument("paths", nargs="*", help="Files to ingest; defaults to data/corpus/*.md.")
    query_p = sub.add_parser("query", help="Answer a question end to end.")
    query_p.add_argument("text", help="The question to answer.")
    query_p.add_argument("--k", type=int, default=None, help="Vector search top-k.")
    query_p.add_argument("--n", type=int, default=None, help="Rerank top-n.")
    args = parser.parse_args(argv)
    try:
        return _dispatch(args)
    except MissingApiKeyError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
