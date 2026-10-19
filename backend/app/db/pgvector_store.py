import asyncio
from pathlib import Path
from uuid import UUID, uuid4

from langchain.embeddings import init_embeddings
from langchain_community.document_loaders import (
    Docx2txtLoader,
    PDFPlumberLoader,
    TextLoader,
)
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_postgres import PGVector
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import text

from app.config import settings
from app.db.main import engine


text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200,
    add_start_index=True,
)


def split_documents(documents: list[Document]) -> list[Document]:
    return text_splitter.split_documents(documents)


LOADERS = {
    ".pdf": PDFPlumberLoader,
    ".docx": Docx2txtLoader,
    ".txt": TextLoader,
}
ALLOWED_EXTENSIONS = tuple(LOADERS)


def get_embeddings() -> Embeddings:
    kwargs: dict[str, str | bool] = {
        "api_key": settings.openai_api_key,
        # 百炼等 OpenAI 兼容网关不接受 tiktoken 数组，必须传原文。
        "check_embedding_ctx_length": False,
    }
    if settings.embeddings_base_url:
        kwargs["base_url"] = settings.embeddings_base_url
    return init_embeddings(
        settings.embeddings_model_name,
        provider=settings.model_provider,
        **kwargs,
    )


def get_vector_store(embeddings: Embeddings | None = None) -> PGVector:
    return PGVector(
        embeddings=embeddings or get_embeddings(),
        connection=settings.psycopg_url,
        collection_name=settings.pgvector_collection_name,
        use_jsonb=True,
        async_mode=True,
    )


async def load_documents(file_path: Path) -> list[Document]:
    suffix = file_path.suffix.lower()
    loader_type = LOADERS.get(suffix)
    if loader_type is None:
        raise ValueError(
            f"Unsupported file type {suffix}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    loader = loader_type(str(file_path))
    return await asyncio.to_thread(loader.load)


async def index_document(
    file_path: Path,
    document_id: UUID,
    knowledge_base_id: UUID,
    user_id: UUID,
) -> list[str]:
    documents = await load_documents(file_path)
    chunks = split_documents(documents)
    ids: list[str] = []
    for chunk in chunks:
        chunk_id = str(uuid4())
        ids.append(chunk_id)
        chunk.metadata.update(
            {
                "chunk_id": chunk_id,
                "user_id": str(user_id),
                "knowledge_base_id": str(knowledge_base_id),
                "document_id": str(document_id),
                "file_name": file_path.name,
            }
        )
    if not chunks:
        return []
    return await get_vector_store().aadd_documents(chunks, ids=ids)


async def search_chunks(
    query: str,
    user_id: str,
    knowledge_base_id: str,
    k: int = 3,
) -> list[Document]:
    return await get_vector_store().asimilarity_search(
        query,
        k=k,
        filter={"user_id": user_id, "knowledge_base_id": knowledge_base_id},
    )


async def _delete_chunks(metadata_key: str, metadata_value: str) -> None:
    async with engine.begin() as connection:
        tables_exist = await connection.scalar(
            text("SELECT to_regclass('public.langchain_pg_embedding')")
        )
        if tables_exist is None:
            return
        await connection.execute(
            text(
                """
                DELETE FROM langchain_pg_embedding AS embedding
                USING langchain_pg_collection AS collection
                WHERE embedding.collection_id = collection.uuid
                  AND collection.name = :collection_name
                  AND embedding.cmetadata ->> :metadata_key = :metadata_value
                """
            ),
            {
                "collection_name": settings.pgvector_collection_name,
                "metadata_key": metadata_key,
                "metadata_value": metadata_value,
            },
        )


async def delete_chunks_for_document(document_id: str) -> None:
    await _delete_chunks("document_id", document_id)


async def delete_chunks_for_knowledge_base(knowledge_base_id: str) -> None:
    await _delete_chunks("knowledge_base_id", knowledge_base_id)
