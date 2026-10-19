from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from tests.test_documents_api import FakeEmbeddings


def test_authenticated_api_smoke_flow(clean_database: None, monkeypatch) -> None:
    from app.db import pgvector_store

    monkeypatch.setattr(pgvector_store, "get_embeddings", lambda: FakeEmbeddings())
    monkeypatch.setattr(
        settings, "pgvector_collection_name", f"test_smoke_{uuid4().hex}"
    )
    credentials = {
        "email": "smoke@example.com",
        "password": "correct-horse-123",
    }

    with TestClient(app) as client:
        signup = client.post("/api/v1/auth/signup", json=credentials)
        assert signup.status_code == 201

        login = client.post("/api/v1/auth/login", json=credentials)
        assert login.status_code == 200
        headers = {
            "Authorization": f"Bearer {login.json()['access_token']}"
        }

        unauthorized_kb = client.post(
            "/api/v1/knowledge-bases/", json={"name": "Denied"}
        )
        assert unauthorized_kb.status_code == 401

        created_kb = client.post(
            "/api/v1/knowledge-bases/",
            json={"name": "Smoke KB", "description": ""},
            headers=headers,
        )
        assert created_kb.status_code == 201
        kb_id = created_kb.json()["id"]

        unauthorized_thread = client.post(
            "/api/v1/threads/",
            json={"title": "Denied", "knowledge_base_id": kb_id},
        )
        assert unauthorized_thread.status_code == 401

        created_thread = client.post(
            "/api/v1/threads/",
            json={"title": "Smoke test", "knowledge_base_id": kb_id},
            headers=headers,
        )
        assert created_thread.status_code == 201
        thread_id = created_thread.json()["id"]

        uploaded = client.post(
            f"/api/v1/documents/upload/{kb_id}",
            headers=headers,
            files={"file": ("notes.txt", b"Smoke test evidence.", "text/plain")},
        )
        assert uploaded.status_code == 201

        documents = client.get(
            f"/api/v1/documents/{kb_id}", headers=headers
        )
        assert documents.status_code == 200
        assert [item["file_name"] for item in documents.json()] == ["notes.txt"]

        unauthorized_chat = client.post(
            f"/api/v1/chat/{thread_id}",
            json={"message": "What is in my notes?"},
        )
        assert unauthorized_chat.status_code == 401
