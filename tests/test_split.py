from langchain_core.documents import Document

from app.db.pgvector_store import split_documents


def test_split_documents_adds_start_index_and_overlap() -> None:
    text = "0123456789" * 250

    chunks = split_documents([Document(page_content=text)])

    assert len(chunks) > 1
    assert all("start_index" in chunk.metadata for chunk in chunks)
    assert chunks[1].metadata["start_index"] < 1000
    assert chunks[0].page_content[-200:] == chunks[1].page_content[:200]
