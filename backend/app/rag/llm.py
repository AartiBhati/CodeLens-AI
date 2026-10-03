from functools import lru_cache

from langchain_core.language_models.chat_models import BaseChatModel

from app.core.config import settings


@lru_cache
def get_chat_model(streaming: bool = True) -> BaseChatModel:
    if settings.LLM_PROVIDER == "huggingface":
        if not settings.HF_TOKEN:
            raise ValueError(
                "HF_TOKEN is not set. Create a free token at "
                "https://huggingface.co/settings/tokens and add it to .env"
            )
        # Hugging Face Inference Providers expose an OpenAI-compatible
        # endpoint, so no extra dependency is needed for chat.
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.HF_CHAT_MODEL,
            api_key=settings.HF_TOKEN,
            base_url=settings.HF_CHAT_BASE_URL,
            streaming=streaming,
            temperature=0.1,
            max_tokens=settings.HF_CHAT_MAX_TOKENS,
            max_retries=3,
        )
    if settings.LLM_PROVIDER == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.OPENAI_CHAT_MODEL,
            api_key=settings.OPENAI_API_KEY,
            streaming=streaming,
            temperature=0.1,
        )
    if settings.LLM_PROVIDER == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=settings.GEMINI_CHAT_MODEL,
            google_api_key=settings.GEMINI_API_KEY,
            streaming=streaming,
            temperature=0.1,
        )
    raise ValueError(f"Unsupported LLM_PROVIDER: {settings.LLM_PROVIDER}")
