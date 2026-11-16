# API reference (current)

Interactive OpenAPI is generated at `/docs` when the service is running. JSON schema is available at `/openapi.json`.

All `/api/*` routes except the token endpoint require `Authorization: Bearer <access_token>`. Errors use FastAPI's `detail` response shape; unexpected exceptions include a request ID. IDs are opaque UUID strings. Current login tokens expire after `ACCESS_TOKEN_MINUTES`.

| Method and path | Access | Behavior |
|---|---|---|
| `POST /api/auth/token` | Public | OAuth2 form fields `username` (email) and `password`; returns `access_token`, `token_type`, `role`. |
| `GET /api/me` | Authenticated | Current account and organization IDs. |
| `POST /api/admin/users` | Org admin | JSON `{ "email": "...", "password": "at-least-12-chars", "role": "member" }`; creates an account inside the admin's organization. |
| `POST /api/documents` | Authenticated | Multipart `file`; supported filename extensions PDF/DOCX/CSV/TXT; configured byte limit; returns 202 with ID/status. Processing is in-process and not durable. |
| `GET /api/documents` | Authenticated | Current organization's documents. No pagination yet. |
| `POST /api/query` | Authenticated | JSON `{ "question": "...", "history": [] }`; returns answer, citations, retrieval evidence and workflow display steps. |
| `POST /api/data/query` | Authenticated | Currently returns 503; raw SQL execution is intentionally disabled until schema-aware validation and tenant isolation are implemented. |
| `POST /api/actions` | Authenticated | JSON `{ "kind": "support_ticket|draft_email|report", "payload": {...} }`; creates a pending approval request only. |
| `GET /api/actions` | Authenticated | Lists current organization's requests. |
| `POST /api/actions/{action_id}/approve` | Org admin | Marks a pending request approved; does not execute an external system operation. |
| `GET /api/dashboard` | Authenticated | Basic document, query and pending-action counts for the current organization. |
| `GET /health` | Public | Checks API process and PostgreSQL connection only. It does not check all dependencies. |

Pagination, a stable versioned response envelope, document deletion, richer status codes and conversation endpoints are future API work. Do not infer execution success from `approved` action status.
