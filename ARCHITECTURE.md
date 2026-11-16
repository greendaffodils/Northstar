# Northstar architecture baseline

## Current shape

Northstar is currently a small FastAPI modular monolith. `app/main.py` owns HTTP routes and startup; `app/core` contains settings, SQLAlchemy setup and JWT/password helpers; `app/models.py` defines the relational metadata; `app/services` contains extraction, retrieval, answer generation and (previously) SQL validation; the single HTML page in `app/templates` is plain browser JavaScript. Alembic, Compose and GitHub Actions files are present.

The request path is browser → FastAPI → SQLAlchemy/PostgreSQL metadata and audit records. Uploads are stored to a local mounted directory, then FastAPI `BackgroundTasks` invokes extraction/chunking. Sentence Transformers embeds chunks into Qdrant. Queries combine Qdrant dense ranks with a BM25 ranking over tenant-scoped ready chunks, then optionally call Gemini. Action requests are persisted and can be marked approved; no external action is run. The current release has no conversation persistence, agent graph, work-order domain, or industrial data schema.

## Trust boundaries

- Browser input is untrusted. Bearer tokens are verified and user state is reloaded from PostgreSQL. Authorization uses the current database role and organization.
- The document upload path is tenant/id scoped and the extension plus a basic content signature is checked. File parsing and uncompressed archive limits are not yet hardened for hostile large documents.
- PostgreSQL and Qdrant are separate stores. SQL queries for lexical retrieval are scoped by organization and document status; vector queries filter by organization and their IDs are intersected with ready SQL chunks.
- Gemini receives the question, supplied conversation context and retrieved chunks. There is no validated citation entailment check and no prompt isolation beyond a natural-language instruction.
- The former client SQL executor was removed because regex filtering is not a safe SQL boundary and the referenced table did not exist. `/api/data/query` now returns 503 until a schema-aware read-only implementation is introduced.
- Approval currently means only that an admin changed a database status. It does not mean an industrial work order was executed.

## Current deployment topology

Docker Compose defines one API container, PostgreSQL and Qdrant. Document storage is a local volume. There is no queue, Redis, object store, separate worker, tracing collector or cloud infrastructure. The API health route checks database connectivity only; it does not prove Qdrant, Gemini, embedding model or migration readiness.

## Main architectural risks

1. In-process background work is lost on process termination and upload bytes are also retained in task memory.
2. Chunk creation and vector upsert are not a single transaction; partial states can occur. Retry/reconciliation and deletion/version semantics are missing.
3. Authorization is organization-wide for documents; per-document ACLs and RLS are absent.
4. The token is a short-lived JWT with no refresh/revocation flow. Provisioning an initial production organization/admin is not implemented.
5. Relational schema is still a generic knowledge/action schema. Industrial facts and safe analytics do not exist.
6. Evaluation is four small unit tests and does not measure retrieval or answer quality.

## Target direction

Keep a modular monolith initially. Add explicit domain modules for industrial records, jobs, retrieval and actions. Use a durable queue and isolated worker for ingestion; Cloud Storage for originals; Cloud SQL for relational state; tenant-scoped Qdrant deployment; and a managed secret source for a GCP deployment. Add LangGraph only when the multi-source investigation workflow demonstrates value over direct retrieval plus deterministic SQL. See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for gates.
