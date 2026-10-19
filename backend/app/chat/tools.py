from typing import Any

from langchain.tools import ToolRuntime, tool

from app.chat.context import ChatContext
from app.config import Settings
from app.db.pgvector_store import search_chunks


@tool
async def retrieve_user_documents(
    query: str,
    runtime: ToolRuntime[ChatContext],
) -> str:
    """Search documents uploaded by the current user to the current conversation."""
    documents = await search_chunks(
        query,
        user_id=runtime.context.user_id,
        knowledge_base_id=runtime.context.knowledge_base_id,
        k=3,
    )
    if not documents:
        return "无相关文档"
    return "\n\n".join(
        f"[source: {document.metadata.get('file_name', 'unknown')}]\n"
        f"{document.page_content}"
        for document in documents
    )


def create_tavily_client(settings: Settings):
    from langchain_tavily import TavilySearch
    from langchain_tavily._utilities import TavilySearchAPIWrapper

    return TavilySearch(
        name="web_search",
        max_results=3,
        api_wrapper=TavilySearchAPIWrapper(
            tavily_api_key=settings.tavily_api_key
        ),
    )


def build_tools(settings: Settings, *, tavily_client=None) -> list:
    tools = [retrieve_user_documents]
    if not settings.tavily_api_key:
        return tools

    client = tavily_client or create_tavily_client(settings)

    @tool("web_search")
    async def web_search(query: str) -> Any:
        """Search the public web for current external information."""
        try:
            return await client.ainvoke({"query": query})
        except Exception as exc:
            return f"工具执行失败：{exc}"

    tools.append(web_search)
    return tools
