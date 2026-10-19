import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document
from app.db.pgvector_store import delete_chunks_for_document, index_document


async def create_document(
    session: AsyncSession,
    file: UploadFile,
    knowledge_base_id: UUID,
    user_id: UUID,
) -> Document:
    document_id = uuid4()
    safe_name = Path(file.filename or "upload").name
    with TemporaryDirectory() as temp_directory:
        file_path = Path(temp_directory) / safe_name
        contents = await file.read()
        await asyncio.to_thread(file_path.write_bytes, contents)
        await index_document(file_path, document_id, knowledge_base_id, user_id)

    document = Document(
        id=document_id,
        knowledge_base_id=knowledge_base_id,
        user_id=user_id,
        file_name=safe_name,
    )
    session.add(document)
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        await delete_chunks_for_document(str(document_id))
        raise
    await session.refresh(document)
    return document
