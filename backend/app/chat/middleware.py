import re
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langchain.tools.tool_node import ToolCallRequest
from langgraph.types import Command
from pydantic import BaseModel, Field

from app.chat.prompts import GRADE_PROMPT, REWRITE_PROMPT


class DocumentGrade(BaseModel):
    relevant: bool
    reason: str


class RelevanceAssessment(BaseModel):
    grades: list[DocumentGrade] = Field(default_factory=list)


class RewrittenQuery(BaseModel):
    query: str


class RetrievalCorrectionMiddleware(AgentMiddleware):
    def __init__(self, grading_model: Any) -> None:
        self.grading_model = grading_model

    @staticmethod
    def _content(result: ToolMessage) -> str:
        return result.content if isinstance(result.content, str) else str(result.content)

    @staticmethod
    def _blocks(content: str) -> list[str]:
        blocks = [
            block.strip()
            for block in re.split(r"\n\n(?=\[source:)", content)
            if block.strip()
        ]
        return blocks or [content]

    async def _grade(
        self, query: str, blocks: list[str]
    ) -> RelevanceAssessment:
        if all(block.strip() == "无相关文档" for block in blocks):
            return RelevanceAssessment(
                grades=[
                    DocumentGrade(relevant=False, reason="检索没有返回文档")
                    for _ in blocks
                ]
            )
        numbered = "\n\n".join(
            f"Document {index + 1}:\n{block}"
            for index, block in enumerate(blocks)
        )
        grader = self.grading_model.with_structured_output(RelevanceAssessment)
        return await grader.ainvoke(
            [
                {"role": "system", "content": GRADE_PROMPT},
                {
                    "role": "user",
                    "content": f"Query: {query}\n\n{numbered}",
                },
            ]
        )

    async def _rewrite(self, query: str) -> str:
        rewriter = self.grading_model.with_structured_output(RewrittenQuery)
        result = await rewriter.ainvoke(
            [
                {"role": "system", "content": REWRITE_PROMPT},
                {"role": "user", "content": query},
            ]
        )
        return result.query

    @staticmethod
    def _tool_message(request: ToolCallRequest, content: str) -> ToolMessage:
        return ToolMessage(
            content=content,
            tool_call_id=request.tool_call["id"],
            name=request.tool_call["name"],
        )

    async def _evaluate_result(
        self,
        request: ToolCallRequest,
        query: str,
        result: ToolMessage,
    ) -> tuple[ToolMessage | None, list[str]]:
        blocks = self._blocks(self._content(result))
        assessment = await self._grade(query, blocks)
        if len(assessment.grades) != len(blocks):
            return None, ["打分结果与文档数量不一致"]
        relevant_blocks = [
            block
            for block, grade in zip(blocks, assessment.grades, strict=True)
            if grade.relevant
        ]
        if relevant_blocks:
            return self._tool_message(request, "\n\n".join(relevant_blocks)), []
        return None, [grade.reason for grade in assessment.grades]

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[
            [ToolCallRequest], Awaitable[ToolMessage | Command[Any]]
        ],
    ) -> ToolMessage | Command[Any]:
        try:
            first_result = await handler(request)
            if request.tool_call["name"] != "retrieve_user_documents":
                return first_result
            if not isinstance(first_result, ToolMessage):
                return first_result

            original_query = str(request.tool_call["args"].get("query", ""))
            relevant, first_reasons = await self._evaluate_result(
                request, original_query, first_result
            )
            if relevant is not None:
                return relevant

            rewritten_query = await self._rewrite(original_query)
            rewritten_call = {
                **request.tool_call,
                "args": {
                    **request.tool_call["args"],
                    "query": rewritten_query,
                },
            }
            rewritten_request = request.override(tool_call=rewritten_call)
            second_result = await handler(rewritten_request)
            if not isinstance(second_result, ToolMessage):
                return second_result
            relevant, second_reasons = await self._evaluate_result(
                request, rewritten_query, second_result
            )
            if relevant is not None:
                return relevant

            reasons = second_reasons or first_reasons
            reason_summary = "；".join(reason for reason in reasons if reason)
            return self._tool_message(
                request,
                f"无相关文档；原因：{reason_summary or '检索结果不相关'}",
            )
        except Exception as exc:
            return self._tool_message(request, f"工具执行失败：{exc}")
