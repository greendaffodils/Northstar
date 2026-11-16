# Implementation plan and feature status

Status reflects code inspection on 2026-11-16. “Implemented” means a code path exists; end-to-end behavior is unverified unless explicitly tested.

| Area | Status | Evidence / gap |
|---|---|---|
| FastAPI modular starter, OpenAPI docs | Partial | Routes are in `app/main.py`; `/docs` is generated. Route module separation is not yet done. |
| Password login, short JWT, roles | Partial | Argon2 helper, JWT and admin/member roles exist. No refresh, lockout, lifecycle, org onboarding, fine-grained roles or revocation. |
| Organization data filtering | Partial | Core list/query/action paths filter by organization. No adversarial API integration tests, RLS, per-document ACL, or complete tenant audit. |
| PDF/DOCX/CSV/TXT extraction | Partial | Basic extraction functions exist; structure, MIME validation and parser limits remain limited. |
| Durable ingestion/version/deletion | Planned | Upload uses local storage and in-process BackgroundTasks; no persisted job table, retries, replacement, delete, cancellation or reindex. |
| Dense + BM25 + RRF | Partial | Qdrant and lexical code exists; no integration test, reranker, ACL filters, time/version/entity retrieval or relevance benchmark. |
| Grounded Gemini answer | Partial | Gemini call uses retrieved context; no citation verifier, contradiction policy, model timeout/cost tracking or tested abstention rate. |
| SQL analytics | Planned / disabled | The unsafe regex SQL executor has been removed. `/api/data/query` returns 503 pending industrial schema, AST parser, DB role and tenant enforcement. |
| Industrial dataset | Planned | No equipment, incidents, work orders, inventory or reproducible seed data exists. |
| Query router / LangGraph | Planned | Current endpoint always routes to RAG. No agent graph or workflow checkpointing exists. |
| Approval and external actions | Partial | Request and admin status approval exist; no reject, idempotency, execution adapter or confirmed external result. |
| Dashboard | Partial | One page covers docs, Q&A, evidence and action requests; no industrial workspaces or accessibility review. |
| CI / tests | Partial | One CI workflow and four unit tests. No type check, security scan, integration or reliability suite. |
| Docker / Alembic | Partial | Compose exists. Production table creation was disabled; one explicit initial migration now exists. Compose has local-only static DB credentials. |
| GCP / observability / evaluation | Planned | No Terraform, cloud deployment, OTel, load test, benchmark corpus or real measurement. |

## Phase gates

### Phase 1 — inspection, baseline, correctness and security (current)

- [x] Inspect source, README, migration/config/test and deployment files.
- [x] Document architecture, security, deployment, API, evaluation and ordered plan.
- [x] Disable unsafe SQL execution; prevent development table auto-creation in production.
- [x] Add basic content/signature validation for uploads; ensure failed documents are excluded from retrieval.
- [x] Replace dynamic metadata-based migration with an explicit initial migration.
- [x] Add API-level tenant tests for cross-organization list/action access, client-supplied org IDs and forged org claims.
- [ ] Run the tenant integration tests and all dependency-backed checks in a provisioned project environment; this workspace lacks PyJWT, pwdlib, Qdrant client and Ruff.

### Phase 2 — document lifecycle and retrieval correctness

Introduce document version/status/deleted state and persisted ingestion jobs. Design idempotent replacement and deletion across SQL and Qdrant, add ACL metadata and implement structure-aware extraction with page/heading provenance. Add hybrid retrieval tests and compare dense/BM25/RRF before adding reranking.

### Phase 3 — industrial data and safe analytics

Define organization-scoped industrial relational schema and deterministic synthetic-data generator. Build parameterized analytical operations first. Add an AST-based NL-to-SQL path only after table/column allowlists, tenant predicates, timeout and a dedicated read-only database role are tested.

### Phase 4 — investigations and actions

Implement deterministic multi-source investigation plans; add LangGraph only for workflows that benefit from conditional multi-hop steps. Add citation validation, numeric verification, work-order proposal/review/reject/execute states, idempotency and a simulated external adapter.

### Phase 5 — durable jobs and observability

Use a durable local/cloud queue, idempotent worker lifecycle, retry/dead-letter states and recovery tests. Add OpenTelemetry spans, redacted structured logs and baseline latency/cost metrics.

### Phase 6 — evaluation, cloud and product polish

Build reviewed benchmark data and reproducible retrieval/answer experiments. Set up GCP infrastructure, secrets, private networking, deployment migration job and dashboards. Expand UI around actual industrial records and validated workflows.

## Current completion evidence

Verification completed for this phase: Python bytecode compilation succeeded and `pytest` reported 5 passed, 1 skipped. The skipped module contains tenant API adversarial tests because PyJWT/pwdlib are absent here. Ruff could not run because it is not installed. Docker startup, Postgres/Qdrant integration, cloud deployment and a realistic end-to-end user journey remain unverified. No benchmark result or production-readiness claim is made.
