import hashlib
import json
import os

import cohere
import psycopg

from caselens.clients import get_cohere_client
from caselens.config.settings import Settings, get_settings

from .chunking import chunk_markdown, load_document
from .db import connect, to_vector_literal
from .embed import embed_passages
from .models import IngestReport


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ingest_documents(
    paths: list[str],
    *,
    settings: Settings | None = None,
    co: cohere.ClientV2 | None = None,
    conn: psycopg.Connection | None = None,
) -> IngestReport:
    settings = settings or get_settings()
    co = co or get_cohere_client(settings)
    own = conn is None
    conn = conn or connect(settings)
    ingested = skipped = written = 0
    try:
        for path in paths:
            title, text = load_document(path)
            digest = _hash(text)
            source = str(path)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, content_hash FROM documents WHERE source_path = %s", (source,)
                )
                row = cur.fetchone()
                if row and row[1] == digest:
                    skipped += 1
                    continue
                if row:
                    cur.execute("DELETE FROM documents WHERE id = %s", (row[0],))
                chunks = chunk_markdown(
                    text, chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap
                )
                if not chunks:
                    continue
                embeddings = embed_passages([c.text for c in chunks], settings=settings, co=co)
                cur.execute(
                    "INSERT INTO documents (source_path, title, content_hash) "
                    "VALUES (%s, %s, %s) RETURNING id",
                    (source, title, digest),
                )
                document_id = cur.fetchone()[0]
                cur.executemany(
                    "INSERT INTO chunks (document_id, section, ordinal, text, embedding, metadata) "
                    "VALUES (%s, %s, %s, %s, %s::vector, %s::jsonb)",
                    [
                        (
                            document_id,
                            chunk.section,
                            chunk.ordinal,
                            chunk.text,
                            to_vector_literal(embedding),
                            json.dumps(
                                {
                                    "source": os.path.basename(source),
                                    "title": title,
                                    "section": chunk.section,
                                }
                            ),
                        )
                        for chunk, embedding in zip(chunks, embeddings, strict=True)
                    ],
                )
                written += len(chunks)
                ingested += 1
            conn.commit()
        return IngestReport(ingested, skipped, written)
    finally:
        if own:
            conn.close()
