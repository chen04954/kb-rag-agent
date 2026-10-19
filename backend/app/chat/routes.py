from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.auth.dependencies import CurrentUser, DatabaseSession
from app.chat.agent import build_agent
from app.chat.context import ChatContext
from app.chat.service import read_history, stream_agent
from app.config import settings
from app.threads.service import get_owned_thread


router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


@router.post("/{thread_id}")
async def chat(
    thread_id: UUID,
    payload: ChatRequest,
    request: Request,
    user: CurrentUser,
    session: DatabaseSession,
) -> StreamingResponse:
    thread = await get_owned_thread(session, thread_id, user.id)
    agent = build_agent(
        settings,
        request.app.state.checkpointer,
        settings.model_names[0],
    )
    context = ChatContext(
        user_id=str(user.id),
        thread_id=str(thread_id),
        knowledge_base_id=str(thread.knowledge_base_id),
    )
    return StreamingResponse(
        stream_agent(agent, payload.message, context, str(thread_id)),
        media_type="application/x-ndjson",
    )


@router.get("/{thread_id}")
async def chat_history(
    thread_id: UUID,
    request: Request,
    user: CurrentUser,
    session: DatabaseSession,
) -> dict[str, list[dict[str, str]]]:
    await get_owned_thread(session, thread_id, user.id)
    agent = build_agent(
        settings,
        request.app.state.checkpointer,
        settings.model_names[0],
    )
    return {"messages": await read_history(agent, str(thread_id))}
