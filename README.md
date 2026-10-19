# KB RAG Agent

一个可演示的企业知识库问答应用：用户登录后按会话上传 PDF、DOCX 或 TXT 文档并提问，系统会流式回答，没有可靠文档依据时明确拒绝作答。

## 项目特点与参考说明

产品形态受
[hosseinabadii/LangGraph-RAG-Agent](https://github.com/hosseinabadii/LangGraph-RAG-Agent)
启发，但本项目是独立实现，不是 fork，也没有复制其代码。主要差异：

- 使用 LangChain 1.2 的 `create_agent`，不使用旧版 `create_react_agent`。
- 自定义 middleware 对文档检索结果打分；不相关时只改写查询并重试一次，仍无依据则拒绝。
- pgvector 检索同时使用 `user_id` 和 `thread_id` 过滤，隔离不同用户及会话的数据。
- PDF 使用 `PDFPlumberLoader`，并支持 DOCX、TXT。
- 使用 PostgreSQL checkpointer 保存会话历史；Tavily 联网搜索可选，失败不会导致聊天接口 500。

## 架构

```text
Streamlit  ── JWT ──►  FastAPI /api/v1
                          │
           ┌──────────────┼────────────────┐
           │              │                │
       auth/users     threads/docs     chat (NDJSON)
           │              │                │
           └──────── SQLAlchemy ───────────┤
                          │                │
                   PostgreSQL 17       LangChain Agent
                    + pgvector         + middleware
                                           │
                                  OpenAI-compatible API
                                  + optional Tavily
```

Streamlit 只负责界面和 API 调用；文档解析、切块、向量检索、模型调用均在 FastAPI 后端。

## 本机 PostgreSQL 17

本项目默认使用已经安装在 `D:\PostgreSQL\pg17` 的 PostgreSQL 17。先启动数据库：

```powershell
D:\PostgreSQL\pg17\start-postgres.bat
```

默认数据库名是 `kb_rag_agent`，`vector` 扩展已启用。本地运行后端时连接
`127.0.0.1:5432`。

**PowerShell 里若直接运行 `.bat` 可能没有任何输出**，请任选一种方式启动并确认出现
`server is running`：

```powershell
cmd /c D:\PostgreSQL\pg17\start-postgres.bat
# 或（推荐）
D:\Projects\kb-rag-agent\scripts\start-postgres.ps1
```

如在其他机器运行，请先创建数据库并执行：

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

## 环境变量

复制 `env.example` 为 `.env`，填写自己的密钥和数据库密码。`.env` 已被 Git 忽略。

| 变量 | 用途 | 是否可空 |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI 或兼容服务的 API Key | 否 |
| `MODEL_PROVIDER` | LangChain 模型提供方，默认 `openai` | 否 |
| `MODEL_NAMES` | 对话及打分模型名 JSON 数组 | 否 |
| `MODEL_BASE_URL` | OpenAI 兼容接口地址 | 使用官方接口时可空 |
| `EMBEDDINGS_MODEL_NAME` | Embedding 模型名 | 否 |
| `EMBEDDINGS_BASE_URL` | Embedding 兼容接口地址 | 可空 |
| `TAVILY_API_KEY` | 可选网页搜索 | 可空 |
| `JWT_SECRET` | JWT 签名密钥，建议至少 32 字节 | 否 |
| `JWT_ALGORITHM` | JWT 算法，默认 `HS256` | 否 |
| `ACCESS_TOKEN_EXPIRY_MINS` | Access Token 有效分钟数 | 否 |
| `REFRESH_TOKEN_EXPIRY_DAYS` | Refresh Token 有效天数 | 否 |
| `POSTGRES_HOST` | PostgreSQL 地址 | 否 |
| `POSTGRES_PORT` | PostgreSQL 端口 | 否 |
| `POSTGRES_USER` | PostgreSQL 用户 | 否 |
| `POSTGRES_PASSWORD` | PostgreSQL 密码 | 否 |
| `POSTGRES_DATABASE` | 数据库名，默认 `kb_rag_agent` | 否 |
| `PGVECTOR_COLLECTION_NAME` | pgvector 集合名 | 否 |
| `BACKEND_BASE_URL` | Streamlit 访问的 API 根地址 | 否 |

## 本地启动

创建虚拟环境并安装依赖：

```powershell
cd D:\Projects\kb-rag-agent
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
pip install -r frontend\requirements.txt
```

启动后端：

```powershell
cd D:\Projects\kb-rag-agent\backend
..\.venv\Scripts\Activate.ps1
python run_dev.py
```

Windows 上请用 `run_dev.py`（内部已处理 asyncio 与 psycopg 兼容）。Linux/macOS 仍可直接：

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

另开终端启动前端：

```powershell
cd D:\Projects\kb-rag-agent\frontend
streamlit run gui/main.py
```

浏览器访问 `http://127.0.0.1:8501`。健康检查地址为
`http://127.0.0.1:8000/healthz`。

## 测试

测试使用独立数据库 `kb_rag_agent_test`，模型、Embedding 和 Tavily 均由假实现替代，不需要真实 API Key：

```powershell
cd D:\Projects\kb-rag-agent
.\.venv\Scripts\python.exe -m pytest -v
```

## Docker Compose（可选）

Compose 只启动 API 和 Streamlit，不启动数据库；容器通过
`host.docker.internal` 访问本机 PostgreSQL 17：

```powershell
docker compose up --build
```
