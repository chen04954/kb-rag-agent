from uuid import uuid4

from fastapi.testclient import TestClient
from langchain_core.embeddings import Embeddings

from app.config import settings
from app.db.pgvector_store import search_chunks
from app.main import app


class FakeEmbeddings(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, float(len(text) % 7), 0.5] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return [1.0, float(len(text) % 7), 0.5]


def _auth(client: TestClient, email: str) -> dict[str, str]:
    credentials = {"email": email, "password": "correct-horse-123"}
    assert client.post("/api/v1/auth/signup", json=credentials).status_code == 201
    login = client.post("/api/v1/auth/login", json=credentials)
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _kb(client: TestClient, headers: dict[str, str], name: str) -> str:
    return client.post(
        "/api/v1/knowledge-bases/",
        json={"name": name, "description": ""},
        headers=headers,
    ).json()["id"]


def test_upload_indexes_metadata_and_hides_other_knowledge_bases(
    clean_database: None, monkeypatch
) -> None:
    from app.db import pgvector_store

    monkeypatch.setattr(pgvector_store, "get_embeddings", lambda: FakeEmbeddings())
    monkeypatch.setattr(
        settings, "pgvector_collection_name", f"test_documents_{uuid4().hex}"
    )

    with TestClient(app) as client:
        alice_headers = _auth(client, "alice-docs@example.com")
        bob_headers = _auth(client, "bob-docs@example.com")
        alice_kb = _kb(client, alice_headers, "Alice files")
        bob_kb = _kb(client, bob_headers, "Bob files")

        forbidden = client.post(
            f"/api/v1/documents/upload/{bob_kb}",
            headers=alice_headers,
            files={"file": ("stolen.txt", b"must not be indexed", "text/plain")},
        )
        assert forbidden.status_code == 404

        unsupported = client.post(
            f"/api/v1/documents/upload/{alice_kb}",
            headers=alice_headers,
            files={"file": ("payload.exe", b"no", "application/octet-stream")},
        )
        assert unsupported.status_code == 400
        assert ".pdf" in unsupported.json()["detail"]

        content = ("hello kb rag and employee handbook " * 80).encode()
        uploaded = client.post(
            f"/api/v1/documents/upload/{alice_kb}",
            headers=alice_headers,
            files={"file": ("handbook.txt", content, "text/plain")},
        )
        assert uploaded.status_code == 201
        document_id = uploaded.json()["id"]

        listed = client.get(
            f"/api/v1/documents/{alice_kb}", headers=alice_headers
        )
        assert listed.status_code == 200
        assert [item["file_name"] for item in listed.json()] == ["handbook.txt"]

        alice_id = client.get("/api/v1/users/me", headers=alice_headers).json()["id"]

    import asyncio

    chunks = asyncio.run(
        search_chunks(
            "employee handbook",
            user_id=alice_id,
            knowledge_base_id=alice_kb,
            k=5,
        )
    )
    assert chunks
    required = {"user_id", "knowledge_base_id", "document_id", "file_name"}
    assert required <= chunks[0].metadata.keys()
    assert chunks[0].metadata["document_id"] == document_id


def test_delete_document_removes_database_row(
    clean_database: None, monkeypatch
) -> None:
    from app.db import pgvector_store

    monkeypatch.setattr(pgvector_store, "get_embeddings", lambda: FakeEmbeddings())
    monkeypatch.setattr(
        settings, "pgvector_collection_name", f"test_delete_{uuid4().hex}"
    )

    with TestClient(app) as client:
        headers = _auth(client, "delete-docs@example.com")
        kb_id = _kb(client, headers, "Delete files")
        uploaded = client.post(
            f"/api/v1/documents/upload/{kb_id}",
            headers=headers,
            files={"file": ("delete.txt", b"delete this content", "text/plain")},
        )
        document_id = uploaded.json()["id"]

        assert (
            client.delete(
                f"/api/v1/documents/{document_id}", headers=headers
            ).status_code
            == 204
        )
        assert (
            client.get(
                f"/api/v1/documents/{kb_id}", headers=headers
            ).json()
            == []
        )
