# Implementation plan and feature status

Status reflects code inspection on 2026-11-16. “Implemented” means a code path exists; end-to-end behavior is unverified unless explicitly tested.

| Area | Status | Evidence / gap |
|---|---|---|
| FastAPI modular starter, OpenAPI docs | Partial | Routes are in `app/main.py`; `/docs` is generated. Route module separation is not yet done. |
| Password login, short JWT, roles | Partial | Argon2 helper, JWT and admin/member roles exist. No refresh, lockout, lifecycle, org onboarding, fine-grained roles or revocation. |
| Organization data filtering | Partial | Core endpoints and retrieval filter by organization; document reads add role/user allowlists. No executed adversarial API suite, RLS, or complete tenant audit. |
| PDF/DOCX/CSV/TXT extraction | Partial | Basic format checks plus page/heading/table/paragraph metadata and equipment-ID enrichment exist. Parser resource limits and author/effective-date extraction remain. |
| Durable ingestion/version/deletion | Partial | Same-name versions, soft delete, manual reindex, persisted jobs, bounded retry/backoff, deletion cleanup job and local polling worker exist. Cloud queue, reconciliation and user-triggered cancellation remain. |
| Dense + BM25 + RRF | Partial | Current/non-deleted, equipment and document ACL filtering, org-scoped Qdrant filter, SQL intersection and optional cross-encoder reranking exist; no vector integration test, historical-version query mode or relevance benchmark. |
| Grounded Gemini answer | Partial | Gemini call uses retrieved context; no citation verifier, contradiction policy, model timeout/cost tracking or tested abstention rate. |
| SQL analytics | Planned / disabled | The unsafe regex SQL executor has been removed. `/api/data/query` returns 503 pending industrial schema, AST parser, DB role and tenant enforcement. |
| Industrial dataset | Planned | No equipment, incidents, work orders, inventory or reproducible seed data exists. |
| Query router / LangGraph | Planned | Current endpoint always routes to RAG. No agent graph or workflow checkpointing exists. |
| Approval and external actions | Partial | Request and admin status approval exist; no reject, idempotency, execution adapter or confirmed external result. |
| Dashboard | Partial | One page covers docs, Q&A, evidence and action requests; no industrial workspaces or accessibility review. |
| CI / tests | Partial | One CI workflow, unit tests and tenant API tests. Tenant API module remains skipped locally due missing PyJWT/pwdlib; no type check, security scan, Qdrant integration or load suite. |
| Docker / Alembic | Partial | Compose includes one-shot migrations and separate API/worker. SQLite migration up/down and worker unit tests passed; Docker startup remains unverified. Compose has local-only static DB credentials. |
| GCP / observability / evaluation | Planned | No Terraform, cloud deployment, OTel, load test, benchmark corpus or real measurement. |

## Phase gates

### Phase 1 — inspection, baseline, correctness and security (completed with verification gaps)

- [x] Inspect source, README, migration/config/test and deployment files.
- [x] Document architecture, security, deployment, API, evaluation and ordered plan.
- [x] Disable unsafe SQL execution; prevent development table auto-creation in production.
- [x] Add basic content/signature validation for uploads; ensure failed documents are excluded from retrieval.
- [x] Replace dynamic metadata-based migration with an explicit initial migration.
- [x] Add API-level tenant tests for cross-organization list/action access, client-supplied org IDs and forged org claims.
- [ ] Run the tenant integration tests and Ruff in a provisioned project environment; this workspace lacks PyJWT, pwdlib and Ruff.

### Phase 2 — document lifecycle and retrieval correctness (in progress)

- [x] Add same-name immutable versions and keep the previous current version until replacement indexing succeeds.
- [x] Persist jobs, retries, backoff, progress, cancellation on delete and stale-running-job recovery in a separate local worker.
- [x] Add soft deletion, version history, reindex, and current/non-deleted retrieval filtering.
- [x] Add migration 0002 and verify upgrade/downgrade against SQLite.
- [x] Add deletion cleanup jobs with persisted retry state; SQL visibility is removed before vector cleanup completes.
- [x] Add page/heading/table/paragraph chunk metadata and equipment-ID enrichment.
- [x] Add role/user document allowlists to list, version, reindex and retrieval paths; filter Qdrant by SQL-derived accessible document IDs.
- [ ] Add vector-store integration tests and reconciliation; finish tenant API tests with runtime dependencies.

### Phase 3 — industrial data and safe analytics

Define organization-scoped industrial relational schema and deterministic synthetic-data generator. Build parameterized analytical operations first. Add an AST-based NL-to-SQL path only after table/column allowlists, tenant predicates, timeout and a dedicated read-only database role are tested.

### Phase 4 — investigations and actions

Implement deterministic multi-source investigation plans; add LangGraph only for workflows that benefit from conditional multi-hop steps. Add citation validation, numeric verification, work-order proposal/review/reject/execute states, idempotency and a simulated external adapter.

### Phase 5 — durable jobs and observability

Use a durable local/cloud queue, idempotent worker lifecycle, retry/dead-letter states and recovery tests. Add OpenTelemetry spans, redacted structured logs and baseline latency/cost metrics.

### Phase 6 — evaluation, cloud and product polish

Build reviewed benchmark data and reproducible retrieval/answer experiments. Set up GCP infrastructure, secrets, private networking, deployment migration job and dashboards. Expand UI around actual industrial records and validated workflows.

## Current completion evidence

Phase 1 verification: compilation succeeded; the latest Phase 2 suite reported 12 passed, 1 skipped. The skipped module contains API tenant adversarial tests because PyJWT/pwdlib are absent here. Ruff could not run because it is not installed. SQLite migrations upgraded and downgraded successfully. Docker startup, Postgres/Qdrant integration, cloud deployment and a realistic end-to-end user journey remain unverified. No benchmark result or production-readiness claim is made.
