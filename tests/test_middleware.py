from dataclasses import dataclass, replace
from typing import Any

import pytest
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableLambda

from app.chat.middleware import (
    DocumentGrade,
    RetrievalCorrectionMiddleware,
    RelevanceAssessment,
    RewrittenQuery,
)


class FakeStructuredModel:
    def __init__(self, grades: list[RelevanceAssessment], rewrite: str = "better query"):
        self.grades = list(grades)
        self.rewrite = rewrite

    def with_structured_output(self, schema):
        async def respond(_: Any):
            if schema is RelevanceAssessment:
                return self.grades.pop(0)
            if schema is RewrittenQuery:
                return RewrittenQuery(query=self.rewrite)
            raise AssertionError(f"Unexpected schema: {schema}")

        return RunnableLambda(respond)


@dataclass(frozen=True)
class FakeRequest:
    tool_call: dict[str, Any]

    def override(self, **overrides: Any) -> "FakeRequest":
        return replace(self, **overrides)


def assessment(relevant: bool, reason: str = "reason") -> RelevanceAssessment:
    return RelevanceAssessment(
        grades=[DocumentGrade(relevant=relevant, reason=reason)]
    )


@pytest.mark.asyncio
async def test_irrelevant_results_rewrite_once_then_refuse() -> None:
    model = FakeStructuredModel(
        [assessment(False, "off topic"), assessment(False, "still off topic")],
        rewrite="rewritten leave policy",
    )
    middleware = RetrievalCorrectionMiddleware(model)
    request = FakeRequest(
        {
            "name": "retrieve_user_documents",
            "args": {"query": "leave"},
            "id": "call-1",
        }
    )
    queries: list[str] = []

    async def handler(current: FakeRequest) -> ToolMessage:
        queries.append(current.tool_call["args"]["query"])
        return ToolMessage(
            content="[source: handbook.txt]\nunrelated content",
            tool_call_id="call-1",
        )

    result = await middleware.awrap_tool_call(request, handler)

    assert queries == ["leave", "rewritten leave policy"]
    assert isinstance(result, ToolMessage)
    assert str(result.content).startswith("无相关文档")
    assert "still off topic" in str(result.content)


@pytest.mark.asyncio
async def test_relevant_first_result_does_not_retry() -> None:
    middleware = RetrievalCorrectionMiddleware(
        FakeStructuredModel([assessment(True)])
    )
    request = FakeRequest(
        {
            "name": "retrieve_user_documents",
            "args": {"query": "leave"},
            "id": "call-2",
        }
    )
    calls = 0

    async def handler(_: FakeRequest) -> ToolMessage:
        nonlocal calls
        calls += 1
        return ToolMessage(
            content="[source: handbook.txt]\nten days leave",
            tool_call_id="call-2",
        )

    result = await middleware.awrap_tool_call(request, handler)

    assert calls == 1
    assert "ten days leave" in str(result.content)


@pytest.mark.asyncio
async def test_web_search_is_not_graded_or_rewritten() -> None:
    middleware = RetrievalCorrectionMiddleware(FakeStructuredModel([]))
    request = FakeRequest(
        {"name": "web_search", "args": {"query": "news"}, "id": "call-3"}
    )
    calls = 0

    async def handler(_: FakeRequest) -> ToolMessage:
        nonlocal calls
        calls += 1
        return ToolMessage(content="web result", tool_call_id="call-3")

    result = await middleware.awrap_tool_call(request, handler)

    assert calls == 1
    assert result.content == "web result"


@pytest.mark.asyncio
async def test_tool_exception_becomes_tool_message() -> None:
    middleware = RetrievalCorrectionMiddleware(FakeStructuredModel([]))
    request = FakeRequest(
        {"name": "web_search", "args": {"query": "news"}, "id": "call-4"}
    )

    async def handler(_: FakeRequest) -> ToolMessage:
        raise RuntimeError("tool unavailable")

    result = await middleware.awrap_tool_call(request, handler)

    assert isinstance(result, ToolMessage)
    assert "tool unavailable" in str(result.content)
