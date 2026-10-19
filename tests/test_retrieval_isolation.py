from pathlib import Path
from uuid import uuid4

import pytest
from langchain_core.embeddings import Embeddings

from app.config import settings
from app.db.pgvector_store import index_document, search_chunks


class ConstantEmbeddings(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0]


@pytest.mark.asyncio
async def test_search_does_not_cross_users_or_knowledge_bases(
    test_database: None, monkeypatch, tmp_path: Path
) -> None:
    from app.db import pgvector_store

    monkeypatch.setattr(
        pgvector_store, "get_embeddings", lambda: ConstantEmbeddings()
    )
    monkeypatch.setattr(
        settings, "pgvector_collection_name", f"test_isolation_{uuid4().hex}"
    )

    user_a, user_b = uuid4(), uuid4()
    kb_a, kb_b = uuid4(), uuid4()
    document_a, document_b = uuid4(), uuid4()
    file_a = tmp_path / "alice.txt"
    file_b = tmp_path / "bob.txt"
    file_a.write_text("shared secret phrase from alice", encoding="utf-8")
    file_b.write_text("shared secret phrase from bob", encoding="utf-8")

    await index_document(file_a, document_a, kb_a, user_a)
    await index_document(file_b, document_b, kb_b, user_b)

    bob_docs = await search_chunks(
        "shared secret phrase", str(user_b), str(kb_b), k=3
    )
    assert any(doc.metadata["document_id"] == str(document_b) for doc in bob_docs)

    alice_docs = await search_chunks(
        "shared secret phrase", str(user_a), str(kb_a), k=3
    )
    ids = {doc.metadata["document_id"] for doc in alice_docs}
    assert str(document_a) in ids
    assert str(document_b) not in ids
    assert all(doc.metadata["user_id"] == str(user_a) for doc in alice_docs)
    assert all(
        doc.metadata["knowledge_base_id"] == str(kb_a) for doc in alice_docs
    )

    crossed = await search_chunks(
        "shared secret phrase", str(user_a), str(kb_b), k=3
    )
    assert crossed == []
