from openai import AsyncOpenAI

from app.config import Settings


def create_llm_client(settings: Settings):
    return AsyncOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key.get_secret_value(),
        timeout=settings.llm_timeout_seconds,
    )