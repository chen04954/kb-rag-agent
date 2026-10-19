from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.db.main import engine, init_db, session_factory
from app.db.models import Base, Document, KnowledgeBase, Thread, User


@pytest.mark.asyncio
async def test_deleting_knowledge_base_cascades_to_documents(
    test_database: None,
) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await init_db()

    user_id = uuid4()
    kb_id = uuid4()
    thread_id = uuid4()
    document_id = uuid4()

    async with session_factory() as session:
        session.add(
            User(id=user_id, email="owner@example.com", password_hash="hash")
        )
        session.add(
            KnowledgeBase(id=kb_id, user_id=user_id, name="Handbook KB")
        )
        session.add(
            Thread(
                id=thread_id,
                user_id=user_id,
                knowledge_base_id=kb_id,
                title="Chat 1",
            )
        )
        session.add(
            Document(
                id=document_id,
                knowledge_base_id=kb_id,
                user_id=user_id,
                file_name="handbook.txt",
            )
        )
        await session.commit()

        await session.execute(
            delete(KnowledgeBase).where(KnowledgeBase.id == kb_id)
        )
        await session.commit()

        document_count = await session.scalar(
            select(func.count()).select_from(Document)
        )
        thread_count = await session.scalar(
            select(func.count()).select_from(Thread)
        )

    assert document_count == 0
    assert thread_count == 0


@pytest.mark.asyncio
async def test_deleting_thread_keeps_documents(test_database: None) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await init_db()

    user_id = uuid4()
    kb_id = uuid4()
    thread_id = uuid4()
    document_id = uuid4()

    async with session_factory() as session:
        session.add(
            User(id=user_id, email="keep@example.com", password_hash="hash")
        )
        session.add(KnowledgeBase(id=kb_id, user_id=user_id, name="Shared"))
        session.add(
            Thread(
                id=thread_id,
                user_id=user_id,
                knowledge_base_id=kb_id,
                title="Temp chat",
            )
        )
        session.add(
            Document(
                id=document_id,
                knowledge_base_id=kb_id,
                user_id=user_id,
                file_name="keep.txt",
            )
        )
        await session.commit()

        await session.execute(delete(Thread).where(Thread.id == thread_id))
        await session.commit()

        document_count = await session.scalar(
            select(func.count()).select_from(Document)
        )

    assert document_count == 1
