from uuid import UUID

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import select

from app.auth.dependencies import CurrentUser, DatabaseSession
from app.db.models import Thread
from app.knowledge_bases.service import get_owned_knowledge_base
from app.threads.schemas import ThreadCreate, ThreadResponse, ThreadUpdate
from app.threads.service import get_owned_thread


router = APIRouter(prefix="/threads", tags=["threads"])


@router.post("/", response_model=ThreadResponse, status_code=status.HTTP_201_CREATED)
async def create_thread(
    payload: ThreadCreate,
    user: CurrentUser,
    session: DatabaseSession,
) -> ThreadResponse:
    await get_owned_knowledge_base(session, payload.knowledge_base_id, user.id)
    thread = Thread(
        user_id=user.id,
        knowledge_base_id=payload.knowledge_base_id,
        title=payload.title,
    )
    session.add(thread)
    await session.commit()
    await session.refresh(thread)
    return ThreadResponse.model_validate(thread)


@router.get("/", response_model=list[ThreadResponse])
async def list_threads(
    user: CurrentUser,
    session: DatabaseSession,
    knowledge_base_id: UUID | None = None,
) -> list[ThreadResponse]:
    query = select(Thread).where(Thread.user_id == user.id)
    if knowledge_base_id is not None:
        await get_owned_knowledge_base(session, knowledge_base_id, user.id)
        query = query.where(Thread.knowledge_base_id == knowledge_base_id)
    result = await session.scalars(query.order_by(Thread.created_at.desc()))
    return [ThreadResponse.model_validate(item) for item in result.all()]


@router.get("/{thread_id}", response_model=ThreadResponse)
async def read_thread(
    thread_id: UUID,
    user: CurrentUser,
    session: DatabaseSession,
) -> ThreadResponse:
    thread = await get_owned_thread(session, thread_id, user.id)
    return ThreadResponse.model_validate(thread)


@router.patch("/{thread_id}", response_model=ThreadResponse)
async def update_thread(
    thread_id: UUID,
    payload: ThreadUpdate,
    user: CurrentUser,
    session: DatabaseSession,
) -> ThreadResponse:
    thread = await get_owned_thread(session, thread_id, user.id)
    thread.title = payload.title
    await session.commit()
    await session.refresh(thread)
    return ThreadResponse.model_validate(thread)


@router.delete("/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(
    thread_id: UUID,
    request: Request,
    user: CurrentUser,
    session: DatabaseSession,
) -> Response:
    thread = await get_owned_thread(session, thread_id, user.id)
    # Chat memory only; documents stay on the knowledge base.
    checkpointer = getattr(request.app.state, "checkpointer", None)
    if checkpointer is not None:
        await checkpointer.adelete_thread(str(thread.id))
    await session.delete(thread)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
