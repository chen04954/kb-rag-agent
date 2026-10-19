"""Local dev entrypoint: Windows needs SelectorEventLoop before uvicorn starts."""
import asyncio
import socket
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn

from app.config import settings


def ensure_postgres_reachable() -> None:
    with socket.create_connection(
        (settings.postgres_host, settings.postgres_port), timeout=3
    ):
        pass


if __name__ == "__main__":
    try:
        ensure_postgres_reachable()
    except OSError as exc:
        print(
            f"\n[启动失败] 无法连接 PostgreSQL "
            f"{settings.postgres_host}:{settings.postgres_port}（{exc}）\n"
            "请先启动数据库，再运行本脚本。本机 PG17 示例：\n"
            "  D:\\PostgreSQL\\pg17\\start-postgres.bat\n"
            "启动后请确认 pg_ctl status 显示「server is running」，"
            "或 127.0.0.1:5432 可连接。\n"
            "确认 .env 中 POSTGRES_* 与真实账号、库名一致。\n",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_dirs=["app"],
    )
