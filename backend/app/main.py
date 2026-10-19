import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.auth.routes import router as auth_router
from app.chat.routes import router as chat_router
from app.db.checkpointer import open_checkpointer
from app.db.main import init_db
from app.documents.routes import router as documents_router
from app.knowledge_bases.routes import router as knowledge_bases_router
from app.threads.routes import router as threads_router
from app.users.routes import router as users_router



@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    await init_db()
    async with open_checkpointer() as checkpointer:
        application.state.checkpointer = checkpointer
        yield


app = FastAPI(title="kb-rag-agent", version="0.1.0", lifespan=lifespan)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(knowledge_bases_router, prefix="/api/v1")
app.include_router(threads_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")


@app.get("/api/v1/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
