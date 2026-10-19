from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Thread


async def get_owned_thread(
    session: AsyncSession,
    thread_id: UUID,
    user_id: UUID,
) -> Thread:
    thread = await session.scalar(
        select(Thread).where(Thread.id == thread_id, Thread.user_id == user_id)
    )
    if thread is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found",
        )
    return thread
