from typing import Any

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from app.chat.context import ChatContext
from app.chat.middleware import RetrievalCorrectionMiddleware
from app.chat.prompts import SYSTEM_PROMPT
from app.chat.tools import build_tools
from app.config import Settings


def create_model(settings: Settings, model_name: str) -> BaseChatModel:
    kwargs: dict[str, Any] = {
        "model": model_name,
        "model_provider": settings.model_provider,
        "api_key": settings.openai_api_key,
    }
    if settings.model_base_url:
        kwargs["base_url"] = settings.model_base_url
    return init_chat_model(**kwargs)


def build_agent(settings: Settings, checkpointer, model_name: str):
    grading_model_name = (
        settings.model_names[1]
        if len(settings.model_names) > 1
        else settings.model_names[0]
    )
    return create_agent(
        model=create_model(settings, model_name),
        tools=build_tools(settings),
        system_prompt=SYSTEM_PROMPT,
        middleware=[
            RetrievalCorrectionMiddleware(
                create_model(settings, grading_model_name)
            )
        ],
        checkpointer=checkpointer,
        context_schema=ChatContext,
    )
