"""Manual smoke test: round-trips Command, Embed 4, and Rerank 4 on the live Cohere API.

Run from apps/api with CO_API_KEY set (environment or .env):

    uv run python scripts/smoke_cohere.py

Not wired into CI: it needs a real API key and makes network calls.
"""

import sys

import cohere

from caselens.config.settings import get_settings

CHAT_MODEL = "command-a-03-2025"
EMBED_MODEL = "embed-v4.0"
RERANK_MODEL = "rerank-v4.0-pro"


def main() -> int:
    api_key = get_settings().co_api_key
    if not api_key:
        print(
            "CO_API_KEY no está definida. Expórtala o cópiala en apps/api/.env "
            "(ver .env.example) antes de correr el smoke test.",
            file=sys.stderr,
        )
        return 1

    co = cohere.ClientV2(api_key=api_key)

    chat = co.chat(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": "Reply with the single word: pong."}],
    )
    print(f"[chat]   {CHAT_MODEL}: {chat.message.content[0].text!r}")

    embed = co.embed(
        model=EMBED_MODEL,
        input_type="search_document",
        texts=["caselens smoke test"],
        embedding_types=["float"],
    )
    dims = len(embed.embeddings.float_[0])
    print(f"[embed]  {EMBED_MODEL}: 1 vector, {dims} dims")

    rerank = co.rerank(
        model=RERANK_MODEL,
        query="What is the capital of France?",
        documents=["Paris is the capital of France.", "Bananas are yellow."],
        top_n=1,
    )
    top = rerank.results[0]
    print(f"[rerank] {RERANK_MODEL}: top index {top.index}, score {top.relevance_score:.4f}")

    print("OK: round-trip de Command + Embed 4 + Rerank 4 correcto.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
