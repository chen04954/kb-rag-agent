import json
from typing import Any, Sequence
from uuid import uuid4

from fastapi.testclient import TestClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda

from app.chat.middleware import (
    DocumentGrade,
    RelevanceAssessment,
    RewrittenQuery,
)
from app.config import settings
from app.main import app
from tests.test_documents_api import FakeEmbeddings


class ToolCallingFakeModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "tool-calling-fake"

    def bind_tools(
        self,
        tools: Sequence[Any],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> "ToolCallingFakeModel":
        return self

    def with_structured_output(self, schema, **kwargs: Any):
        async def respond(_: Any):
            if schema is RelevanceAssessment:
                return RelevanceAssessment(
                    grades=[DocumentGrade(relevant=True, reason="contains evidence")]
                )
            if schema is RewrittenQuery:
                return RewrittenQuery(query="rewritten leave policy")
            raise AssertionError(f"Unexpected schema: {schema}")

        return RunnableLambda(respond)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        tool_messages = [
            message for message in messages if isinstance(message, ToolMessage)
        ]
        if tool_messages:
            if str(tool_messages[-1].content).startswith("无相关文档"):
                response = AIMessage(content="无法根据现有资料回答。")
            else:
                response = AIMessage(
                    content="According to handbook.txt, leave is documented."
                )
        else:
            response = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "retrieve_user_documents",
                        "args": {"query": "leave policy"},
                        "id": "call-retrieve-1",
                        "type": "tool_call",
                    }
                ],
            )
        return ChatResult(generations=[ChatGeneration(message=response)])


def _login(client: TestClient) -> tuple[dict[str, str], str]:
    credentials = {"email": "chat@example.com", "password": "correct-horse-123"}
    client.post("/api/v1/auth/signup", json=credentials)
    login = client.post("/api/v1/auth/login", json=credentials).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    user_id = client.get("/api/v1/users/me", headers=headers).json()["id"]
    return headers, user_id


def _create_kb_and_thread(
    client: TestClient, headers: dict[str, str], title: str
) -> tuple[str, str]:
    kb_id = client.post(
        "/api/v1/knowledge-bases/",
        json={"name": "Chat KB", "description": ""},
        headers=headers,
    ).json()["id"]
    thread_id = client.post(
        "/api/v1/threads/",
        json={"title": title, "knowledge_base_id": kb_id},
        headers=headers,
    ).json()["id"]
    return kb_id, thread_id


def test_chat_streams_tool_events_and_persists_history(
    clean_database: None, monkeypatch
) -> None:
    from app.chat import agent as agent_module
    from app.chat import tools as tools_module
    from app.db import pgvector_store

    monkeypatch.setattr(pgvector_store, "get_embeddings", lambda: FakeEmbeddings())
    monkeypatch.setattr(
        settings, "pgvector_collection_name", f"test_chat_{uuid4().hex}"
    )
    monkeypatch.setattr(
        agent_module, "create_model", lambda settings, model_name: ToolCallingFakeModel()
    )
    observed: dict[str, str] = {}
    original_search = tools_module.search_chunks

    async def search_spy(
        query: str, user_id: str, knowledge_base_id: str, k: int = 3
    ):
        observed.update(user_id=user_id, knowledge_base_id=knowledge_base_id)
        return await original_search(query, user_id, knowledge_base_id, k)

    monkeypatch.setattr(tools_module, "search_chunks", search_spy)

    with TestClient(app) as client:
        headers, user_id = _login(client)
        kb_id, thread_id = _create_kb_and_thread(client, headers, "Chat")
        uploaded = client.post(
            f"/api/v1/documents/upload/{kb_id}",
            headers=headers,
            files={
                "file": (
                    "handbook.txt",
                    b"The leave policy grants ten days.",
                    "text/plain",
                )
            },
        )
        assert uploaded.status_code == 201

        response = client.post(
            f"/api/v1/chat/{thread_id}",
            headers=headers,
            json={"message": "What is the leave policy?", "user_id": "spoofed"},
        )
        assert response.status_code == 200
        events = [json.loads(line) for line in response.text.splitlines() if line]
        assert any(event["type"] == "tool_call" for event in events)
        assert any(event["type"] == "tool_result" for event in events)
        assert any(event["type"] == "llm_chunk" for event in events)
        assert observed == {"user_id": user_id, "knowledge_base_id": kb_id}

        history = client.get(f"/api/v1/chat/{thread_id}", headers=headers)
        assert history.status_code == 200
        assert any(
            "leave policy" in message["content"].lower()
            for message in history.json()["messages"]
        )


def test_chat_refuses_when_retrieval_has_no_evidence(
    clean_database: None, monkeypatch
) -> None:
    from app.chat import agent as agent_module
    from app.db import pgvector_store

    monkeypatch.setattr(pgvector_store, "get_embeddings", lambda: FakeEmbeddings())
    monkeypatch.setattr(
        settings, "pgvector_collection_name", f"test_empty_chat_{uuid4().hex}"
    )
    monkeypatch.setattr(
        agent_module, "create_model", lambda settings, model_name: ToolCallingFakeModel()
    )

    with TestClient(app) as client:
        headers, _ = _login(client)
        _, thread_id = _create_kb_and_thread(client, headers, "Empty chat")
        response = client.post(
            f"/api/v1/chat/{thread_id}",
            headers=headers,
            json={"message": "Tell me FABRICATED_FACT_42"},
        )

    events = [json.loads(line) for line in response.text.splitlines() if line]
    answer = "".join(
        event["content"]
        for event in events
        if event["type"] == "llm_chunk"
    )
    assert "FABRICATED_FACT_42" not in answer
    assert "无法" in answer
