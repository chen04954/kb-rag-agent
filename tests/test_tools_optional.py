import json
from typing import Any

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.config import settings
from app.main import app
from tests.test_chat_stream import ToolCallingFakeModel, _login


class FailingTavily:
    async def ainvoke(self, payload: dict[str, str]) -> Any:
        raise RuntimeError("tavily down")


class WebSearchFakeModel(ToolCallingFakeModel):
    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        if any(isinstance(message, ToolMessage) for message in messages):
            response = AIMessage(content="Search failed safely.")
        else:
            response = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "web_search",
                        "args": {"query": "latest news"},
                        "id": "call-web-1",
                        "type": "tool_call",
                    }
                ],
            )
        return ChatResult(generations=[ChatGeneration(message=response)])


def test_empty_tavily_key_registers_only_document_retrieval(monkeypatch) -> None:
    from app.chat import tools as tools_module

    monkeypatch.setattr(settings, "tavily_api_key", "")
    tool_names = {item.name for item in tools_module.build_tools(settings)}

    assert tool_names == {"retrieve_user_documents"}


def test_tavily_failure_streams_tool_result_without_http_500(
    clean_database: None, monkeypatch
) -> None:
    from app.chat import agent as agent_module
    from app.chat import tools as tools_module

    monkeypatch.setattr(settings, "tavily_api_key", "test-key")
    monkeypatch.setattr(
        tools_module, "create_tavily_client", lambda _: FailingTavily()
    )
    monkeypatch.setattr(
        agent_module, "create_model", lambda settings, model_name: WebSearchFakeModel()
    )

    with TestClient(app) as client:
        headers, _ = _login(client)
        kb_id = client.post(
            "/api/v1/knowledge-bases/",
            json={"name": "Web KB", "description": ""},
            headers=headers,
        ).json()["id"]
        thread_id = client.post(
            "/api/v1/threads/",
            json={"title": "Web search", "knowledge_base_id": kb_id},
            headers=headers,
        ).json()["id"]
        response = client.post(
            f"/api/v1/chat/{thread_id}",
            headers=headers,
            json={"message": "Search the web"},
        )

    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines() if line]
    tool_results = [
        event["content"] for event in events if event["type"] == "tool_result"
    ]
    assert any("tavily down" in content for content in tool_results)
