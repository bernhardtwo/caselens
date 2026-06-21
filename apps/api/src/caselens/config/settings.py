from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute so the .env loads regardless of the process CWD (e.g. the repo root).
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    co_api_key: str | None = None

    database_url: str = "postgresql://caselens:caselens@localhost:5432/caselens"

    embed_model: str = "embed-v4.0"
    rerank_model: str = "rerank-v3.5"
    chat_model: str = "command-a-03-2025"

    embedding_dim: int = 1536
    embed_batch_size: int = 96

    chunk_size: int = 900
    chunk_overlap: int = 100

    retrieval_k: int = 20
    rerank_n: int = 5

    agent_max_iterations: int = 6
    agent_temperature: float = 0.2


@lru_cache
def get_settings() -> Settings:
    return Settings()
