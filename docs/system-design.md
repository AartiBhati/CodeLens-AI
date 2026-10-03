# System Design — CodeLens AI

This document explains the reasoning behind the major architectural decisions in CodeLens AI, not just what was built.

## 1. Why event-driven indexing instead of a synchronous endpoint?

Cloning a repository, parsing potentially thousands of files, chunking, and generating embeddings can take anywhere from seconds to minutes depending on repo size. If `POST /repositories/{id}/index` did this work inline:

- The HTTP request would time out on large repos.
- One slow indexing job would tie up an API worker process, degrading throughput for every other user.
- There's no natural way to retry a failed step without re-running the whole request.

Instead, the endpoint does the minimum synchronous work (validate ownership, create an `IndexingJob` row, publish an event) and returns `202 Accepted` with a job ID in milliseconds. A separate worker process — decoupled from the API's request/response lifecycle — consumes the event and does the real work. This is the same pattern used for video transcoding, batch ML inference, and report generation at scale: **accept fast, process asynchronously, let the client poll or subscribe for status.**

Kafka specifically (over, say, a Redis list or Postgres-backed queue) was chosen because:
- It gives durable, replayable event logs — if a worker crashes mid-processing, the message isn't lost.
- Consumer groups let us scale workers horizontally for free (`docker compose up --scale worker=3`) with automatic partition rebalancing.
- It naturally models the domain as a sequence of events (`requested` → `completed`/`failed`), which is a good fit for a pipeline with multiple potential downstream consumers (notifications, analytics, webhooks) later.

## 2. Why a sync SQLAlchemy session in the worker but async in the API?

The FastAPI layer is async because it's I/O-bound and needs to serve many concurrent HTTP requests efficiently — async lets a single process handle hundreds of in-flight requests without threads.

The Kafka worker, by contrast, processes **one message at a time, sequentially**, by design — that's what gives us simple, easy-to-reason-about idempotency and retry semantics. `confluent-kafka`'s consumer is a synchronous C-backed client; fighting it into an asyncio event loop would add complexity without a real throughput benefit, since the worker's bottleneck is the LLM/embedding API calls and git clone, not Python-level concurrency. A plain synchronous script with `tenacity` retry decorators is easier to operate and debug.

## 3. Idempotency: why does IndexingJob exist as its own table?

Kafka gives **at-least-once** delivery, not exactly-once. A consumer crash after processing but before committing its offset will cause the same message to be redelivered. If indexing were driven purely off `Repository.index_status`, a redelivered message could re-trigger a duplicate clone/embed/upsert cycle.

Each `IndexingJob` row is created *before* the event is published, and its `id` is embedded in the event payload. The worker's very first step is: *if this job is already `COMPLETED`, skip.* This makes the handler idempotent regardless of how many times the same message is delivered — a classic "idempotency key" pattern borrowed from payment processing APIs.

## 4. Why delete-then-reinsert vectors on every index, instead of diffing?

A simpler, more robust invariant: after indexing completes, Qdrant's vectors for a repository always reflect exactly one commit. Diffing changed files between commits (to only re-embed what changed) is a real optimization opportunity — noted under Future Improvements — but it adds meaningful complexity (tracking per-file content hashes, handling renames/deletes) for a v1. Correctness first: delete stale vectors for the repository, then bulk-upsert the new commit's chunks. This also means a corrupted or partial previous index can never linger and pollute retrieval.

## 5. Why boundary-aware chunking instead of fixed-size windows?

Naive fixed-size chunking (e.g., every 500 characters) frequently splits a function or class definition in half, so a retrieved chunk might contain the back half of one function and the front half of the next — confusing context for the LLM and useless line-number/function-name metadata.

Instead, `chunk_file()` looks for language-specific boundary patterns (`def `, `class `, `function `, etc.) and splits *between* them, so each chunk is (ideally) one coherent function, class, or the file's leading imports/module docstring. This is a regex heuristic, not a full parser — deliberately, to avoid pulling in a per-language AST toolchain (tree-sitter grammars, etc.) for a v1 — but it captures the large majority of real-world code structure. Oversized blocks (e.g., a 2,000-line class) still fall back to the generic recursive splitter so no single chunk blows the embedding model's context window.

## 6. Why refuse to answer outside retrieved context?

An AI codebase assistant that occasionally hallucinates a function that doesn't exist is worse than useless — it actively misleads developers making real decisions. The RAG chain enforces this two ways:
1. **Prompt-level**: the system prompt explicitly instructs the model to answer only from `CONTEXT` and to emit a fixed refusal string otherwise.
2. **Pipeline-level (belt and suspenders)**: before even calling the LLM, retrieval results below `MIN_RELEVANCE_SCORE` are filtered out; if nothing survives, the pipeline **short-circuits and never calls the LLM at all**, returning the refusal message directly. This is both a correctness guarantee (the model literally isn't given a chance to freelance) and a cost optimization (no wasted LLM call on a query we already know has no evidential basis).

## 7. Why cache on `(repository_id, commit_sha, question)` rather than just `question`?

Caching purely on the question text would serve a stale answer after a repository is re-indexed against a new commit — e.g., "what does `parse_config` do?" might have a completely different correct answer after a refactor. Including `commit_sha` in the cache key means a new commit produces a cache miss automatically, without needing to actively invalidate every possible cached question for that repo. The worker *additionally* proactively clears all cache entries for a repository after a successful re-index, as defense in depth (and to free Redis memory promptly rather than waiting on TTL).

## 8. Why store `source_references` on the Message row?

Beyond satisfying the "Source References" feature, persisting the file paths used as evidence alongside the assistant's message means:
- The frontend can render "Sources: ..." for historical messages without re-running retrieval.
- If a user disputes an answer later, there's an audit trail of exactly what code the model saw.
- It's a cheap way to measure retrieval quality over time (e.g., "are we citing the same 3 files for every question, suggesting a chunking or indexing gap?").

## 9. Why history summarization instead of always sending full history?

Prompt size grows linearly with conversation length, which increases both cost and latency, and eventually risks exceeding the model's context window entirely. Once a conversation crosses `HISTORY_SUMMARY_TRIGGER` messages, older messages are collapsed into a single rolling summary (itself generated by an LLM call) and only the most recent `MAX_HISTORY_MESSAGES` are sent verbatim. This bounds prompt size regardless of how long a conversation runs, while still preserving long-range context that would otherwise be lost by simply truncating history.

## 10. Why 404 instead of 403 for cross-user access?

Every data-access method that scopes by ownership (`get_owned`) returns `None` — and therefore a `404 Not Found` — rather than a `403 Forbidden` when a user requests a resource that exists but belongs to someone else. Returning `403` would confirm to an attacker that the resource *exists*, just that they can't access it — a minor but real information leak (resource enumeration). `404` is indistinguishable from "this ID doesn't exist at all."

## 11. Why Redis `INCR`-based fixed-window rate limiting instead of a token bucket?

A fixed window (`rate_limit:{user}:{minute}`, `INCR` + `EXPIRE 60`) is one round-trip per request and trivially correct under concurrent access (Redis `INCR` is atomic). Its known weakness is burst behavior at window boundaries (a user could in theory send `2x limit` requests within a couple seconds spanning a window edge). For a `/chat/ask` endpoint gating relatively expensive LLM calls, this tradeoff is acceptable for v1; a sliding-window or token-bucket algorithm (e.g., via a Lua script) is a drop-in replacement if burst abuse becomes a real problem in practice.

## 12. Why LangChain without LangGraph?

LangGraph is built for complex, stateful multi-agent orchestration with branching control flow. CodeLens's actual AI logic — retrieve, build a prompt from one of six templates, stream from a chat model, optionally let the model call one of four well-scoped tools — is a fundamentally linear pipeline. Expressing it as plain LCEL (`prompt | model`) plus straightforward Python functions keeps the control flow readable in a single file (`rag/chain.py`) rather than distributed across graph node definitions, which matters for a project meant to be legible to someone reviewing it as a portfolio piece.

## 13. Why does the worker use `python-jose`/bcrypt-style layering only in the API, not the worker?

The worker never handles user credentials or issues tokens — it only ever reads `Repository`/`IndexingJob` rows by ID from trusted, internally-generated Kafka payloads. Authentication and authorization are enforced entirely at the API boundary (JWT verification, ownership checks) before an event is ever published; the worker operates on already-authorized work items and doesn't need its own auth stack. This keeps the worker's dependency footprint smaller and its trust boundary simple: **the worker trusts the API, and the API is the only thing that talks to Kafka producers on the write path.**
