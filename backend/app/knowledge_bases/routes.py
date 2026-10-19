from uuid import UUID

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.auth.dependencies import CurrentUser, DatabaseSession
from app.db.models import KnowledgeBase
from app.db.pgvector_store import delete_chunks_for_knowledge_base
from app.knowledge_bases.schemas import (
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
)
from app.knowledge_bases.service import get_owned_knowledge_base


router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])


@router.post("/", response_model=KnowledgeBaseResponse, status_code=status.HTTP_201_CREATED)
async def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    user: CurrentUser,
    session: DatabaseSession,
) -> KnowledgeBaseResponse:
    knowledge_base = KnowledgeBase(
        user_id=user.id,
        name=payload.name,
        description=payload.description,
    )
    session.add(knowledge_base)
    await session.commit()
    await session.refresh(knowledge_base)
    return KnowledgeBaseResponse.model_validate(knowledge_base)


@router.get("/", response_model=list[KnowledgeBaseResponse])
async def list_knowledge_bases(
    user: CurrentUser,
    session: DatabaseSession,
) -> list[KnowledgeBaseResponse]:
    result = await session.scalars(
        select(KnowledgeBase)
        .where(KnowledgeBase.user_id == user.id)
        .order_by(KnowledgeBase.created_at.desc())
    )
    return [KnowledgeBaseResponse.model_validate(item) for item in result.all()]


@router.get("/{knowledge_base_id}", response_model=KnowledgeBaseResponse)
async def read_knowledge_base(
    knowledge_base_id: UUID,
    user: CurrentUser,
    session: DatabaseSession,
) -> KnowledgeBaseResponse:
    knowledge_base = await get_owned_knowledge_base(
        session, knowledge_base_id, user.id
    )
    return KnowledgeBaseResponse.model_validate(knowledge_base)


@router.patch("/{knowledge_base_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_base(
    knowledge_base_id: UUID,
    payload: KnowledgeBaseUpdate,
    user: CurrentUser,
    session: DatabaseSession,
) -> KnowledgeBaseResponse:
    knowledge_base = await get_owned_knowledge_base(
        session, knowledge_base_id, user.id
    )
    knowledge_base.name = payload.name
    knowledge_base.description = payload.description
    await session.commit()
    await session.refresh(knowledge_base)
    return KnowledgeBaseResponse.model_validate(knowledge_base)


@router.delete("/{knowledge_base_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_base(
    knowledge_base_id: UUID,
    request: Request,
    user: CurrentUser,
    session: DatabaseSession,
) -> Response:
    knowledge_base = await session.scalar(
        select(KnowledgeBase)
        .where(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.user_id == user.id,
        )
        .options(selectinload(KnowledgeBase.threads))
    )
    if knowledge_base is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )
    await delete_chunks_for_knowledge_base(str(knowledge_base.id))
    checkpointer = getattr(request.app.state, "checkpointer", None)
    if checkpointer is not None:
        for thread in knowledge_base.threads:
            await checkpointer.adelete_thread(str(thread.id))
    await session.delete(knowledge_base)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
