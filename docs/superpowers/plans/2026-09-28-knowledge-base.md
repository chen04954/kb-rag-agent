# Knowledge Base Implementation Plan

> **For agentic workers:** Implement task-by-task. Chat memory stays per `thread_id`.

**Goal:** Upload documents once to a knowledge base; open multiple chat sessions against that base without re-uploading. Sessions do not share chat memory.

**Architecture:** `User → KnowledgeBase → Document` and `User → KnowledgeBase → Thread`. Vector metadata uses `user_id` + `knowledge_base_id`. Checkpointer remains keyed by `thread_id`.

**Tech Stack:** FastAPI, SQLAlchemy, pgvector, LangChain create_agent, Streamlit

## Global Constraints

- Chat history not shared across threads
- Retrieval filter: `user_id` AND `knowledge_base_id`
- First version: whole-KB retrieval (no per-doc session subset)
- Local schema: drop/recreate via `RESET_SCHEMA` or test fixtures

## Tasks

1. Models + cascade tests
2. Knowledge base CRUD API
3. Documents upload/list under KB
4. Threads create/list under KB
5. ChatContext + tools + indexing metadata
6. Frontend navigation
7. Full pytest + schema reset note
