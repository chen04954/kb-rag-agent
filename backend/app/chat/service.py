import json
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from app.chat.context import ChatContext


def _line(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str) + "\n"


def _message_content(message: BaseMessage) -> str:
    content = message.content
    return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)


async def stream_agent(
    agent,
    message: str,
    context: ChatContext,
    thread_id: str,
) -> AsyncIterator[str]:
    emitted_model_text = False
    config = {"configurable": {"thread_id": thread_id}}
    try:
        async for event in agent.astream_events(
            {"messages": [{"role": "user", "content": message}]},
            config=config,
            context=context,
            version="v2",
        ):
            event_name = event["event"]
            data = event.get("data", {})
            if event_name == "on_tool_start":
                yield _line(
                    {
                        "type": "tool_call",
                        "name": event.get("name", ""),
                        "args": data.get("input", {}),
                    }
                )
            elif event_name == "on_tool_end":
                output = data.get("output")
                content = (
                    _message_content(output)
                    if isinstance(output, BaseMessage)
                    else str(output)
                )
                yield _line(
                    {
                        "type": "tool_result",
                        "name": event.get("name", ""),
                        "content": content,
                    }
                )
            elif event_name == "on_chat_model_stream":
                chunk = data.get("chunk")
                content = getattr(chunk, "content", "")
                if isinstance(content, str) and content:
                    emitted_model_text = True
                    yield _line({"type": "llm_chunk", "content": content})
            elif event_name == "on_chat_model_end" and not emitted_model_text:
                output = data.get("output")
                if isinstance(output, AIMessage) and output.content:
                    yield _line(
                        {
                            "type": "llm_chunk",
                            "content": _message_content(output),
                        }
                    )
    except Exception as exc:
        yield _line({"type": "error", "content": str(exc)})


async def read_history(agent, thread_id: str) -> list[dict[str, str]]:
    snapshot = await agent.aget_state({"configurable": {"thread_id": thread_id}})
    history: list[dict[str, str]] = []
    for message in snapshot.values.get("messages", []):
        if isinstance(message, ToolMessage):
            role = "tool"
        elif isinstance(message, AIMessage):
            role = "assistant"
        else:
            role = "user"
        history.append({"role": role, "content": _message_content(message)})
    return history
