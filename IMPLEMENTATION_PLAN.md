# Implementation plan and feature status

Status reflects code inspection on 2026-11-16. “Implemented” means a code path exists; end-to-end behavior is unverified unless explicitly tested.

| Area | Status | Evidence / gap |
|---|---|---|
| FastAPI modular starter, OpenAPI docs | Partial | Routes are in `app/main.py`; `/docs` is generated. Route module separation is not yet done. |
| Password login, short JWT, roles | Partial | Argon2 helper, JWT and admin/member roles exist. No refresh, lockout, lifecycle, org onboarding, fine-grained roles or revocation. |
| Organization data filtering | Partial | Core endpoints and retrieval filter by organization; document reads add role/user allowlists. No executed adversarial API suite, RLS, or complete tenant audit. |
| PDF/DOCX/CSV/TXT extraction | Partial | Basic format checks plus page/heading/table/paragraph metadata and equipment-ID enrichment exist. Parser resource limits and author/effective-date extraction remain. |
| Durable ingestion/version/deletion | Partial | Same-name versions, soft delete, manual reindex, persisted jobs, bounded retry/backoff, deletion cleanup job and local polling worker exist. Cloud queue, reconciliation and user-triggered cancellation remain. |
| Dense + BM25 + RRF | Partial | Current/non-deleted, equipment and document ACL filtering, org-scoped Qdrant filter, SQL intersection and optional cross-encoder reranking exist; a dry-run/apply vector reconciliation CLI is available. No executed Qdrant integration test, historical-version query mode or relevance benchmark. |
| Grounded Gemini answer | Partial | Gemini call uses retrieved context; numeric digit values and citation indices are checked against retrieved passages. No semantic citation-support or contradiction verifier, model timeout/cost tracking or tested abstention rate. |
| SQL analytics | Partial | `/api/data/query` routes three supported question families to fixed parameterized SQLAlchemy queries with organization predicates; raw SQL is rejected. Unsupported requests do not execute. No AST-based NL-to-SQL, database read-only role, query timeout or broad analytics set. |
| Industrial dataset | Partial | Explicit industrial schema and deterministic, provenance-marked synthetic generator exist. Seed and analytics tests cover M-204, compatible inventory and tenant scoping. Data review, import pipeline and production schema evolution remain. |
| Query router / LangGraph | Partial | `/api/investigations` combines fixed structured analytics and ACL-filtered retrieval in a deterministic plan. `/api/query` fails closed on invalid citation indices or digit-form numbers absent from the question/passages. No LangGraph, checkpointing, semantic support verifier or cross-source claim verifier. |
| Approval and external actions | Partial | Approval/rejection plus a repeat-safe local simulated adapter exist; work-order proposals create internal rows. No live external connector, credential management or verified external result. |
| Dashboard | Partial | One page covers docs, Q&A, evidence and action requests; no industrial workspaces or accessibility review. |
| CI / tests | Partial | One CI workflow, unit tests and tenant API tests. Tenant API module remains skipped locally due missing PyJWT/pwdlib; no type check, security scan, Qdrant integration or load suite. |
| Docker / Alembic | Partial | Compose includes one-shot migrations and separate API/worker. SQLite migration up/down and worker unit tests passed; Docker startup remains unverified. Compose has local-only static DB credentials. |
| GCP / observability / evaluation | Partial | Optional OTLP tracing, request/worker timing logs, admin tenant queue summary and a ten-case deterministic analytics smoke evaluation exist. No Terraform/cloud deployment, collector verification, broad reviewed benchmark corpus, retrieval/answer-quality measurements or load test. |

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
- [x] Add tenant-scoped vector reconciliation with read-only preview and opt-in missing-vector repair/orphan deletion.
- [ ] Add executed Qdrant integration tests; finish tenant API tests with runtime dependencies.

### Phase 3 — industrial data and safe analytics (in progress)

Define organization-scoped industrial relational schema and deterministic synthetic-data generator. Build parameterized analytical operations first. Add an AST-based NL-to-SQL path only after table/column allowlists, tenant predicates, timeout and a dedicated read-only database role are tested.

- [x] Add organization-scoped facility, equipment, failure, maintenance, work order, spare part, inventory, metric and safety incident tables plus migration 0003.
- [x] Add deterministic synthetic records with manifest/provenance, stable IDs and duplicate/mixed-data safeguards.
- [x] Add fixed parameterized analytics for tagged equipment failure history, compatible parts inventory and rolling 90-day downtime by category; reject raw SQL and audit supported requests.
- [x] Test deterministic/idempotent seeding, M-204 case records, compatible parts and tenant isolation using SQLite.
- [ ] Add broader analytics and measured query plans; validate against PostgreSQL and operationally reviewed data before any AST-based NL-to-SQL work.

### Phase 4 — investigations and actions (in progress)

Implement deterministic multi-source investigation plans; add LangGraph only for workflows that benefit from conditional multi-hop steps. Add citation validation, numeric verification, work-order proposal/review/reject/execute states, idempotency and a simulated external adapter.

- [x] Combine safe structured analytics and ACL-filtered document retrieval in a deterministic investigation response.
- [x] Add work-order proposal validation, admin approval/rejection, simulated execution and idempotent repeat handling; persist execution result and audit transitions.
- [x] Reject generated RAG synthesis with unknown citation indices or unsupported digit-form numeric values; expose the deterministic validation result.
- [ ] Verify semantic citation support and cross-source numerical claims before generated investigation synthesis; execute a live external adapter only after integration, access controls and result validation are in place.

### Phase 5 — durable jobs and observability (in progress)

Use a durable local/cloud queue, idempotent worker lifecycle, retry/dead-letter states and recovery tests. Add OpenTelemetry spans, redacted structured logs and baseline latency/cost metrics.

- [x] Expose tenant-scoped queued/running/retrying/failed job counts and oldest queued age to organization admins; terminal `failed` jobs are reported as dead letters.
- [x] Add optional FastAPI OTLP tracing, request duration/status logs and worker job spans/duration logs without logging request bodies or credentials; tracing exporter is not yet exercised with a collector.
- [ ] Verify collector export and PostgreSQL worker claiming under concurrency; add queue reconciliation, cancellation and alert thresholds.

### Phase 6 — evaluation, cloud and product polish

Build reviewed benchmark data and reproducible retrieval/answer experiments. Set up GCP infrastructure, secrets, private networking, deployment migration job and dashboards. Expand UI around actual industrial records and validated workflows.

- [x] Add a versioned ten-case deterministic analytics routing/value regression set and a runnable JSON evaluation report.
- [ ] Build the manually reviewed benchmark corpus and retrieval/answer evaluation requested in the original plan; current smoke set is not representative enough for quality claims.
- [ ] Add and validate GCP infrastructure, deployment configuration, UI industrial workspaces and accessibility review.

## Current completion evidence

Verification: `python -m compileall -q app migrations tests` succeeded; `python -m pytest -q` reports 19 passed, 1 skipped after the latest changes. The skipped module contains API tenant adversarial tests because PyJWT/pwdlib are absent here. The ten-case analytics evaluation is asserted by the seeded SQLite test. SQLite Alembic upgraded through 0004 and downgraded/upgraded through 0004 successfully. Ruff is not installed. OTLP collector export, PostgreSQL/Docker startup, Qdrant integration, cloud deployment and a realistic end-to-end user journey remain unverified. No broad benchmark result or production-readiness claim is made.
