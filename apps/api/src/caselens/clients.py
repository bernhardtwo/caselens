import cohere

from caselens.config.settings import Settings, get_settings


class MissingApiKeyError(RuntimeError):
    """Raised when a Cohere call is attempted without CO_API_KEY set."""


def get_cohere_client(settings: Settings | None = None) -> cohere.ClientV2:
    settings = settings or get_settings()
    if not settings.co_api_key:
        raise MissingApiKeyError(
            "CO_API_KEY no está definida. Expórtala o cópiala en apps/api/.env (ver .env.example)."
        )
    return cohere.ClientV2(api_key=settings.co_api_key)
