# kb-rag-agent 设计说明

日期：2026-09-24  
状态：待实现  
目标：应聘「AI 应用技术开发」的作品集项目。产品骨架参考 [hosseinabadii/LangGraph-RAG-Agent](https://github.com/hosseinabadii/LangGraph-RAG-Agent)，技术栈升级到 **LangChain 1.2**，Agent 用 `create_agent` + middleware 重写。

本仓库是独立项目，不是对方仓库的 fork。README 会写明「产品形态受该项目启发」，不把他人代码当成自己的作品。

## 1. 目标与非目标

### 要做

- 通用企业知识库问答：上传 PDF / DOCX / TXT，按会话提问，回答尽量带来源。
- 完整可演示产品：注册登录、会话线程、文档管理、流式对话；数据库用本机 PostgreSQL 17。
- LangChain 1.2 主路径：`init_chat_model`、`init_embeddings`、`langchain.agents.create_agent`、自定义 middleware。
- 纠正型文档检索：打分 → 不相关则改写查询再检索一次 → 仍无依据则拒绝回答。
- 网页搜索先用 Tavily 垫着，后续可替换；缺 key 时不注册该工具，服务仍能启动。

### 第一版不做

- 混合检索（BM25 / 重排）、GraphRAG、多 Agent supervisor。
- 完整 RAGAS 评测台（可在第二版加 10～20 条问答集）。
- 本地 Ollama 作为默认运行时（保留 OpenAI 兼容 `base_url`，以后能接中转或本地网关）。
- Next.js 或其他非 Python 前端。
- 再用 Docker 起一套 Postgres 16。本机 PostgreSQL 17（`D:\PostgreSQL\pg17`）已安装并启用 pgvector **0.8.6**；项目库名建议用 `kb_rag_agent`。

## 2. 技术栈

| 层 | 选择 |
|---|---|
| 语言 | Python 3.12+ |
| Agent | `langchain>=1.2,<1.3`，`create_agent` |
| 编排 / 记忆 | `langgraph` + `langgraph-checkpoint-postgres` |
| 模型 / 向量 | `langchain-openai`，OpenAI 兼容 API；`init_chat_model` / `init_embeddings` |
| 向量库 | 本机 PostgreSQL 17 + pgvector，`langchain-postgres` |
| 后端 | FastAPI + SQLAlchemy 2 async + Pydantic v2 |
| 前端 | Streamlit |
| 搜索 | `TavilySearch`（可插拔，默认垫着） |
| 部署 | 默认连本机 Postgres 17。Compose 只起 `api` / `web`，不另起数据库容器 |

锁定 1.2.x，避免 0.3 的 `create_react_agent` 和已废弃 RAG chain。

## 3. 架构

```
Streamlit  ──JWT──►  FastAPI /api/v1
                         │
          ┌──────────────┼────────────────┐
          │              │                │
        auth/users    threads/docs     chat (SSE/NDJSON)
          │              │                │
          └──────── SQLAlchemy ───────────┤
                         │                │
                    本机 PostgreSQL 17    │
                    ├─ users/threads/docs │
                    ├─ pgvector chunks    │
                    └─ LangGraph checkpoints
                                      create_agent
                                      ├─ retrieve_user_documents
                                      ├─ web_search (Tavily，可选)
                                      └─ middleware: 打分 / 改写 / 拒绝
```

运行时身份不塞进 `config["configurable"]` 当业务字段。`thread_id` 仍给 checkpointer 用；`user_id` 和 `thread_id` 通过 `create_agent(..., context_schema=...)` 注入，工具和 middleware 从 `runtime.context` 读取。

## 4. 模块

后端按域拆包，每个包只做一件事：

| 包 | 职责 |
|---|---|
| `app/auth` | 注册、登录、刷新、登出；JWT |
| `app/users` | 当前用户资料 |
| `app/threads` | 会话 CRUD；删除时级联清理 checkpoint 和向量块 |
| `app/documents` | 上传、列表、删除；异步切块入库 |
| `app/chat` | 组装 agent、流式对话、历史读取 |
| `app/db` | 引擎、模型、pgvector、checkpointer |

`app/chat` 内部再拆：

- `agent.py`：`create_agent`，注入 model、tools、middleware、checkpointer、`context_schema`。
- `tools.py`：`retrieve_user_documents`、`web_search`。
- `middleware.py`：只纠正文档检索，不改写网页搜索。
- `prompts.py`：系统提示与打分/改写提示。
- `service.py` / `routes.py`：鉴权、组 context、把图事件映射成 NDJSON。

前端保持一个 Streamlit 应用：登录、会话列表、上传、流式聊天气泡。不在第一版做复杂设计系统。

## 5. 数据流

1. 用户注册 / 登录，拿到 access + refresh token。
2. 创建 thread。
3. 上传文件：校验扩展名 → 落盘临时文件 → loader（PDF 用 `PDFPlumberLoader`，DOCX / TXT 仍用对应 loader）→ `RecursiveCharacterTextSplitter`（chunk 1000 / overlap 200，`add_start_index=True`）→ embedding → pgvector。每块 metadata 必须含 `user_id`、`thread_id`、`document_id`、`file_name`。
4. 对话 `POST /api/v1/chat/{thread_id}`：
   - 校验 JWT，确认 thread 属于当前用户。
   - `create_agent` + checkpointer，`context={user_id, thread_id}`。
   - 模型先决定是否调用工具。
   - `retrieve_user_documents`：相似度检索，`k=3`，过滤 `user_id` **且** `thread_id`。
   - middleware：对检索结果打分；不相关则改写 query，最多再检索 **一次**；仍无依据则工具返回明确的「无相关文档」。
   - 文档不够、且问题需要外部事实时，模型可再调 `web_search`（Tavily）。
   - 文档与搜索都无可用依据时，最终回答必须拒绝，并说明缺了什么，禁止编造。
5. 流式输出 NDJSON，每行一个事件：
   - `llm_chunk`：增量文本
   - `tool_call`：工具名与参数
   - `tool_result`：工具返回摘要
   - `error`：可展示的失败信息
6. `GET /api/v1/chat/{thread_id}` 读 checkpoint 历史。

公开 `POST /api/v1/chat/`（无记忆、无工具）第一版不做，避免和主路径抢焦点。

## 6. Agent 与 middleware 约定

系统提示固定三条规则：

1. 先查当前会话已上传文档。
2. 文档不够且需要外部事实时才用 `web_search`。
3. 没有依据就拒绝，不编造；能引用文件名时要引用。

middleware 行为（只作用于 `retrieve_user_documents`）：

| 步骤 | 行为 |
|---|---|
| 调用工具 | `awrap_tool_call` 执行检索 |
| 打分 | 结构化输出：每条文档 `relevant: bool` + 一句理由 |
| 改写 | 全部不相关时改写 query，用改写后的 query 再 `handler` 一次 |
| 仍失败 | 返回「无相关文档」，并带上打分理由摘要 |
| 网页搜索 | 直接执行，不做改写；工具异常变成 ToolMessage，不把请求打成 500 |

`user_id` 必须参与过滤。只按 `thread_id` 过滤视为缺陷。

打分与改写使用较小、便宜的兼容模型（可由 `MODEL_NAMES` 里的第二个名字指定；只有一个名字时复用同一个）。

## 7. API

前缀：`/api/v1`

- 认证：`POST /auth/signup`、`POST /auth/login`、`GET /auth/logout`、`GET /auth/refresh-token`
- 用户：`GET /users/me`
- 会话：`POST/GET /threads/`，`GET/PATCH/DELETE /threads/{thread_id}`
- 文档：`GET /documents/{thread_id}`，`POST /documents/upload/{thread_id}`，`DELETE /documents/{document_id}`
- 对话：`POST /chat/{thread_id}`（流式），`GET /chat/{thread_id}`（历史）
- 健康检查：`GET /healthz`

除 signup / login / healthz 外，全部需要 JWT。

## 8. 错误处理

| 情况 | 处理 |
|---|---|
| 未登录或 token 过期 | 401 |
| 访问他人 thread / document | 404（不暴露是否存在） |
| 不支持的文件类型 | 400，列出允许扩展名 |
| 向量库或数据库失败 | 500 + `error` 事件，日志打完整堆栈 |
| LLM 提供商失败 | 流里发 `error`，连接正常结束 |
| 未配置 `TAVILY_API_KEY` | 不注册 `web_search`，服务照常启动 |
| 检索无依据且未搜索到可用结果 | 模型拒绝回答，不编造 |

## 9. 配置

项目根目录 `.env`（`env.example` 给出空模板，不提交真实密钥）：

- `OPENAI_API_KEY`、`MODEL_PROVIDER`、`MODEL_NAMES`、`MODEL_BASE_URL`
- `EMBEDDINGS_MODEL_NAME`、`EMBEDDINGS_BASE_URL`
- `TAVILY_API_KEY`（可选）
- `JWT_SECRET`、`JWT_ALGORITHM`、access / refresh 过期时间
- `POSTGRES_HOST`（默认 `127.0.0.1`）、`POSTGRES_PORT`（默认 `5432`）、`POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DATABASE`
- `PGVECTOR_COLLECTION_NAME`
- `BACKEND_BASE_URL`（前端用）

本机库启动后执行一次：`CREATE EXTENSION IF NOT EXISTS vector;`。不在 Docker 里再起一套 Postgres 16。Compose 里的 `api` / `web` 若需要访问宿主机数据库，Windows 上用 `host.docker.internal`。本地直接跑 uvicorn / streamlit 时连 `127.0.0.1`。

`MODEL_NAMES` 为 JSON 列表，例如 `["gpt-4o-mini","gpt-4o-mini"]`。第一个用于对话，第二个用于打分/改写。

## 10. 测试

第一版只保证这三块，都用 pytest：

1. **检索隔离**：同一 collection 里插入用户 A / B 的块，A 的检索不得返回 B 的内容；必须同时过滤 `user_id` 与 `thread_id`。
2. **middleware**：给定不相关文档，断言会改写并重试一次；第二次仍差则返回无相关文档。无依据路径断言最终不是编造答案（可用假模型）。
3. **接口冒烟**：注册登录、建会话、上传 txt、无 token 访问返回 401。LLM 与 Tavily 在测试中 mock。

不在第一版上浏览器 E2E。

## 11. 目录

```
kb-rag-agent/
  backend/app/{auth,users,threads,documents,chat,db}
  frontend/gui/
  tests/
  docs/superpowers/specs/
  docker-compose.yml
  env.example
  README.md
```

README 必须包含：一句话目标、和参考项目的差异（LangChain 1.2、`create_agent`、检索纠正、user 级隔离）、如何连本机 PostgreSQL 17、架构图、环境变量。

## 12. 本地参考项目（rag-pdf-streamlit-python）

路径：`D:\Projects\RAG-PDF-Streamlit-Python`。它是单文件 Streamlit 教程（源自 chat-with-pdf-RAG）：`PDFPlumberLoader` → 切块 1000/200 → `InMemoryVectorStore` → `prompt | OllamaLLM`。

**吸收进本项目的：**

- PDF 解析用 `PDFPlumberLoader`，比默认 PyPDF 更稳。
- 切块参数与「不知道就说不知道」的提示，和现有纠正/拒绝策略一致。
- 按函数测 load / split / index / retrieve 的写法，迁到 `tests/`。
- Streamlit 上传 + `st.chat_input` 的交互可作 UI 参考。

**不照搬的：**

- 内存向量库、全局 `vector_store`、Ollama 写死、无用户隔离。
- 把 RAG 写在 Streamlit 进程里（本项目 RAG 必须在 FastAPI + `create_agent`）。
- 旧式 LCEL 问答链，不作为 Agent 实现。

## 13. 实现顺序

1. 仓库骨架、依赖、连本机 PostgreSQL 17 的配置、健康检查。
2. 用户 / 会话 / 文档（含 pgvector 入库与删除）。
3. `create_agent` + 检索工具 + checkpointer + 流式接口。
4. 纠正 middleware + 拒绝策略。
5. Tavily 搜索工具（可关）。
6. Streamlit 最小可用界面。
7. 上述三类测试与 README。

每一步都要能独立运行或验证，不把 UI 作为后端正确性的前提。
