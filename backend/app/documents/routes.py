from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status
from sqlalchemy import select

from app.auth.dependencies import CurrentUser, DatabaseSession
from app.config import settings
from app.db.models import Document
from app.db.pgvector_store import ALLOWED_EXTENSIONS, delete_chunks_for_document
from app.documents.schemas import DocumentResponse
from app.documents.service import create_document
from app.knowledge_bases.service import get_owned_knowledge_base


router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "/upload/{knowledge_base_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    knowledge_base_id: UUID,
    user: CurrentUser,
    session: DatabaseSession,
    file: UploadFile = File(...),
) -> DocumentResponse:
    await get_owned_knowledge_base(session, knowledge_base_id, user.id)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Allowed file types: {', '.join(ALLOWED_EXTENSIONS)}",
        )
    if not settings.testing and not settings.openai_api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "未配置 OPENAI_API_KEY，无法解析文档向量。"
                "请在项目根目录 .env 中填写密钥并重启后端。"
            ),
        )
    try:
        document = await create_document(
            session, file, knowledge_base_id, user.id
        )
    except Exception as exc:
        message = str(exc).strip() or exc.__class__.__name__
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"文档入库失败：{message}",
        ) from exc
    return DocumentResponse.model_validate(document)


@router.get("/{knowledge_base_id}", response_model=list[DocumentResponse])
async def list_documents(
    knowledge_base_id: UUID,
    user: CurrentUser,
    session: DatabaseSession,
) -> list[DocumentResponse]:
    await get_owned_knowledge_base(session, knowledge_base_id, user.id)
    result = await session.scalars(
        select(Document)
        .where(
            Document.knowledge_base_id == knowledge_base_id,
            Document.user_id == user.id,
        )
        .order_by(Document.created_at)
    )
    return [DocumentResponse.model_validate(item) for item in result.all()]


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    user: CurrentUser,
    session: DatabaseSession,
) -> Response:
    document = await session.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.user_id == user.id,
        )
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    await delete_chunks_for_document(str(document.id))
    await session.delete(document)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
