# API reference (current)

Interactive OpenAPI is generated at `/docs` when the service is running. JSON schema is available at `/openapi.json`.

All `/api/*` routes except the token endpoint require `Authorization: Bearer <access_token>`. Errors use FastAPI's `detail` response shape; unexpected exceptions include a request ID. IDs are opaque UUID strings. Current login tokens expire after `ACCESS_TOKEN_MINUTES`.

| Method and path | Access | Behavior |
|---|---|---|
| `POST /api/auth/token` | Public | OAuth2 form fields `username` (email) and `password`; returns `access_token`, `token_type`, `role`. |
| `GET /api/me` | Authenticated | Current account and organization IDs. |
| `POST /api/admin/users` | Org admin | JSON `{ "email": "...", "password": "at-least-12-chars", "role": "member|engineer|analyst|reader|admin" }`; creates an account inside the admin's organization. |
| `POST /api/documents` | Authenticated | Multipart `file` plus optional `access_roles` (`inherit`, `*`, or comma-separated roles); returns 202 with document and persisted job IDs. Same-name changed uploads create a new version and inherit permissions by default. |
| `GET /api/documents?include_history=false` | Authenticated | Current organization's non-deleted documents; set `include_history=true` to include superseded versions. No pagination yet. |
| `GET /api/documents/{id}/versions` | Authenticated | Lists versions for a family after checking tenant ownership. |
| `PUT /api/documents/{id}/access` | Org admin | JSON `allowed_roles` and same-organization `allowed_user_ids`; sets document-level read access. |
| `POST /api/documents/{id}/reindex` | Authenticated | Queues reprocessing of the current version; requires the original local file. |
| `DELETE /api/documents/{id}` | Org admin | Returns 202 after soft-deleting all versions and queuing vector/original-file cleanup. SQL chunks are removed immediately; the cleanup job retries failures. |
| `GET /api/ingestion-jobs/{id}` | Authenticated | Tenant-scoped job status, progress, attempts and error. |
| `POST /api/query` | Authenticated | JSON `{ "question": "...", "history": [] }`; returns answer, citations, retrieval evidence and workflow display steps. |
| `POST /api/data/query` | Analyst, engineer, org admin | JSON `{ "question": "Show failure history for M-204" }`; supports tagged equipment failure history, compatible spare-part inventory and 90-day downtime by category. A legacy `sql` field is rejected; arbitrary SQL is never executed. |
| `POST /api/actions` | Authenticated | JSON `{ "kind": "support_ticket|draft_email|report", "payload": {...} }`; creates a pending approval request only. |
| `GET /api/actions` | Authenticated | Lists current organization's requests. |
| `POST /api/actions/{action_id}/approve` | Org admin | Marks a pending request approved; does not execute an external system operation. |
| `GET /api/dashboard` | Authenticated | Basic document, query and pending-action counts for the current organization. |
| `GET /health` | Public | Checks API process and PostgreSQL connection only. It does not check all dependencies. |

Pagination, a stable versioned response envelope, cancellation endpoint, richer status codes and conversation endpoints are future API work. Do not infer execution success from `approved` action status.
