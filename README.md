# CodeLens AI

**An AI-powered GitHub codebase intelligence platform.** Connect a repository, CodeLens indexes it asynchronously through an event-driven pipeline, and you can ask natural-language questions about the code — answered strictly from retrieved repository context (RAG), streamed token-by-token, with full conversation history.

This is a portfolio-grade backend/AI engineering project demonstrating clean architecture, event-driven design, RAG, caching, rate limiting, and DevOps automation end to end.

---

## Features

- 🔐 **JWT auth** — register/login/logout (Redis-backed token blacklist), bcrypt hashing, per-resource authorization
- 📁 **Projects & repositories** — connect GitHub repos, track indexing status, chunk counts, commit SHAs
- ⚡ **Event-driven indexing** — FastAPI publishes to Kafka and returns immediately with a job ID; a separate worker does the real work
- 🧠 **Smart code chunking** — splits around function/class boundaries, not arbitrary character windows
- 🟢 **Qdrant vector search** — metadata-filtered similarity search per repository, with lexical-overlap reranking
- 📚 **RAG pipeline** — LangChain LCEL chain; refuses to answer outside retrieved context
- 💬 **Persistent conversations** — history stored in Postgres, with automatic summarization once a thread gets long
- 🤖 **6 AI features** — Ask Codebase, Explain File, Generate Documentation, Architecture Analyzer, Bug Investigation, Related Files
- 🧰 **Agent tools** — `search_code`, `get_file`, `repository_tree`, `search_commit_history`, all repository-scoped
- 📡 **Streaming** — Server-Sent Events, token-by-token, persisted after completion even if the client disconnects
- 🔴 **Redis** — AI response cache (commit-scoped, invalidated on re-index) + per-user rate limiting (429 on excess)
- 🧪 **Tested** — auth, authorization, CRUD, Kafka publish, worker idempotency, RAG retrieval, cache, rate limiting
- 📦 **One-command startup** — `docker compose up --build` runs the entire stack
- ⚙️ **Jenkins CI/CD** — checkout → deps → tests → frontend build → docker build → compose validation

---

## Architecture

```text
                         React Frontend
                               │
                               ▼
                        FastAPI API Layer
                               │
         ┌──────────────┬──────────────┬──────────────┐
         ▼              ▼              ▼
    PostgreSQL        Redis         GitHub API
         │              │
         │         Rate Limiter
         │         Response Cache
         │
         ▼
        Kafka  ← Event Bus
         │
         ▼
   Repository Indexing Worker
         │
         ▼
     Chunking Engine → Embedding Generator → Qdrant Vector DB
         │
         ▼
     LangChain Retriever → LLM → Streaming AI Response
```

The API layer **never blocks** on indexing: `POST /repositories/{id}/index` publishes a `repository.index.requested` event to Kafka and returns `202 Accepted` with a job ID immediately. A dedicated worker process consumes that event, clones the repo, chunks and embeds the code, upserts vectors into Qdrant, and publishes `repository.index.completed` / `.failed`.

See [`docs/system-design.md`](docs/system-design.md) for the reasoning behind every major decision.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React (Vite), Tailwind CSS, React Router, Axios |
| Backend | Python 3.12, FastAPI, Pydantic, SQLAlchemy (async), Alembic |
| AI | LangChain, OpenAI / Gemini (configurable), custom RAG pipeline |
| Databases | PostgreSQL (transactional), Qdrant (vectors) |
| Events | Apache Kafka + Kafka consumer worker |
| Cache/Rate limit | Redis |
| DevOps | Docker, Docker Compose, Jenkins |
| Testing | Pytest, httpx `ASGITransport`, fakeredis |

---

## Database Schema

```
users
 ├── id (uuid, pk), email (unique), hashed_password, full_name, is_active
 └── created_at, updated_at

projects
 ├── id (uuid, pk), owner_id (fk → users), name, description
 └── created_at, updated_at

repositories
 ├── id (uuid, pk), project_id (fk → projects), github_url, branch, commit_sha
 ├── primary_language, index_status (enum), chunk_count, last_indexed_at
 └── created_at, updated_at

indexing_jobs
 ├── id (uuid, pk), repository_id (fk → repositories), status (enum)
 ├── requested_commit_sha, chunks_indexed, error_message, duration_ms
 └── created_at, updated_at        -- id doubles as the Kafka idempotency key

conversations
 ├── id (uuid, pk), repository_id (fk), user_id (fk), title, summary
 └── created_at, updated_at

messages
 ├── id (uuid, pk), conversation_id (fk → conversations), role (enum)
 ├── content, source_references (string[]), token_usage (jsonb)
 └── created_at, updated_at
```

Every table uses UUID primary keys, foreign keys with `ON DELETE CASCADE`, indexes on FK/lookup columns, and `created_at`/`updated_at` timestamps. See `backend/alembic/versions/0001_initial_schema.py`.

---

## RAG Pipeline

1. **User question** arrives via `POST /chat/ask`
2. **Query embedding** — the question is embedded with the same model used to index the repo
3. **Qdrant similarity search** — cosine similarity, filtered by `repository_id` (and optionally `file_path`)
4. **Reranking** — vector score + a small lexical-overlap boost so exact identifier matches outrank near-misses
5. **Relevance threshold** — if nothing clears the bar, the pipeline short-circuits to *"I couldn't find evidence in this repository."* without calling the LLM
6. **Prompt construction** — mode-specific LangChain prompt template (ask/explain/docs/architecture/bug/related), with conversation history and rolling summary injected
7. **LLM streaming** — tokens streamed to the client over SSE as they're generated
8. **Source references** — every file path used as evidence is returned with the answer and persisted alongside the message

---

## Kafka Event Flow

| Topic | Producer | Consumer | Purpose |
|---|---|---|---|
| `repository.index.requested` | FastAPI | Worker | Kick off indexing without blocking the API |
| `repository.index.completed` | Worker | (future consumers, e.g. notifications) | Signal successful indexing |
| `repository.index.failed` | Worker | (future consumers) | Signal indexing failure with error detail |
| `repository.updated` | (reserved) | (reserved) | Future: incremental re-index on webhook push events |

The worker uses **manual offset commits** (commits only after successful processing) and an **`IndexingJob` row as an idempotency key** — if the same message is redelivered (Kafka's at-least-once guarantee), a job already marked `COMPLETED` is skipped rather than re-processed.

---

## Redis Cache Strategy

- **AI response cache**: keyed on `(repository_id, commit_sha, sha256(normalized question))`, TTL-based, explicitly invalidated by the worker after every successful re-index (a new commit can change the correct answer).
- **Rate limiting**: fixed-window `INCR` + `EXPIRE` per user per minute on `/chat/ask`; returns `429` with `Retry-After` when exceeded.
- **Token blacklist**: `POST /auth/logout` blacklists the JWT's `jti` in Redis for its remaining lifetime — a stateless-JWT-compatible logout strategy that self-cleans via TTL.

---

## Getting Started

### 1. Configure environment

```bash
cp .env.example .env
# then set JWT_SECRET_KEY and HF_TOKEN (free: https://huggingface.co/settings/tokens)
# Default provider is Hugging Face (free). To use OpenAI/Gemini instead, set LLM_PROVIDER
# and the matching EMBEDDING_DIM (see .env.example).
```

### 2. Start the full stack

```bash
docker compose up --build
```

This starts: `postgres`, `redis`, `zookeeper`, `kafka`, `qdrant`, `backend` (runs Alembic migrations on boot), `worker`, `frontend`.

- Frontend: http://localhost:5173
- API docs (Swagger): http://localhost:8000/api/v1/docs
- Health: http://localhost:8000/api/v1/health · Readiness: http://localhost:8000/api/v1/ready

### 3. Scale the worker horizontally

```bash
docker compose up --scale worker=3
```

Kafka consumer groups automatically balance partitions across worker replicas.

### 4. Run tests

Tests need a real Postgres (the schema uses native `UUID`/`JSONB`/`ARRAY` types) and use `fakeredis` for Redis:

```bash
docker compose up -d postgres redis
cd backend
pip install -r requirements.txt
export TEST_DATABASE_URL=postgresql+asyncpg://codelens:codelens@localhost:5432/codelens_test
pytest --cov=app
```

---

## API Overview

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/auth/register` | Create an account |
| POST | `/api/v1/auth/login` | Get access/refresh tokens |
| GET | `/api/v1/auth/me` | Current user |
| POST | `/api/v1/auth/logout` | Blacklist current token |
| POST | `/api/v1/projects` | Create a project |
| GET | `/api/v1/projects` | List your projects |
| POST | `/api/v1/projects/{id}/repositories` | Connect a GitHub repo |
| POST | `/api/v1/repositories/{id}/index` | Trigger async indexing → `202` + job ID |
| GET | `/api/v1/indexing-jobs/{id}` | Poll indexing job status |
| POST | `/api/v1/chat/ask` | Streaming RAG Q&A (SSE) — rate limited |
| GET | `/api/v1/conversations/{id}` | Fetch conversation + message history |
| GET | `/api/v1/health` / `/api/v1/ready` | Liveness / readiness probes |

Full interactive schema at `/api/v1/docs` once running.

---

## Performance Optimizations

- **Redis caching** of repeated AI answers, scoped to the exact commit indexed
- **Postgres indexes** on every foreign key and status/lookup column
- **Connection pooling** (`pool_size`/`max_overflow` on the async engine, `pool_pre_ping` to avoid stale-connection errors)
- **Async FastAPI** end to end — no blocking I/O in the request path
- **Kafka asynchronous workers** — indexing never blocks the API, and workers scale horizontally
- **Metadata-filtered vector search** — Qdrant payload indexes on `repository_id`/`file_path`/`language` keep filtered queries fast as the collection grows
- **Top-K retrieval + reranking** — over-fetch 3x, rerank, truncate — balances recall and prompt size
- **History summarization** — bounds prompt size on long conversations instead of sending the full transcript

---

## Security

- JWT access/refresh tokens, bcrypt password hashing, Redis-backed logout blacklist
- Every DB query for a project/repository/conversation is scoped to `owner_id`/`user_id` — cross-user access returns `404`, not `403`, to avoid leaking existence
- GitHub tokens are only ever used server-side (worker container) and never returned to the frontend
- CORS restricted via `CORS_ORIGINS` env var
- Path-traversal guard on the `get_file` agent tool (can't escape the cloned repo root)
- All secrets sourced from `.env` / Jenkins credentials — nothing hard-coded

---

## Project Structure

```
CodeLens-AI/
├── frontend/              React (Vite) SPA
├── backend/
│   └── app/
│       ├── api/routes/    HTTP endpoints
│       ├── core/          config, security, logging
│       ├── db/            engine/session, declarative base
│       ├── models/        SQLAlchemy ORM models
│       ├── schemas/       Pydantic request/response models
│       ├── repositories/  data-access layer
│       ├── services/      business logic (auth, cache, rate limit, indexing)
│       ├── rag/           chunking, embeddings, vector store, retriever,
│       │                  prompts, LCEL chain, tools, summarizer
│       ├── workers/       Kafka producer + standalone consumer worker
│       ├── middleware/    request logging, rate-limit dependency
│       ├── utils/         GitHub parsing, language detection
│       └── tests/         pytest suite
├── docker/worker.Dockerfile
├── docker-compose.yml
├── Jenkinsfile
├── .github/workflows/ci.yml
└── docs/system-design.md
```

---

## Future Improvements

- Incremental indexing via GitHub webhooks (`repository.updated` topic is reserved for this)
- LLM-based reranking (currently a cheap lexical-overlap heuristic on top of vector score)
- Multi-tenant team/organization support beyond per-user ownership
- Dead-letter topic for indexing jobs that exhaust retries
- WebSocket fallback for streaming where SSE is proxied/blocked

---

## Screenshots

*(placeholders — add screenshots of the dashboard, repository indexing status, and streaming chat UI here)*
