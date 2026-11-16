# Security baseline

## Data classification and trust

Treat uploaded manuals, work reports, query text and action payloads as confidential organization data and as untrusted input. The synthetic/demo content must not contain real plant, employee or customer information. Gemini is an external processor when configured; obtain the applicable organizational approval before sending sensitive data.

## Controls currently present

- Password hashes use `pwdlib`'s recommended Argon2 configuration.
- JWTs are signed with HS256, expire, and are checked against the active user row and current organization membership. The database role, rather than the role claim, gates admin routes.
- Production settings reject the known development JWT secret and bootstrap password.
- Most data routes filter by the authenticated organization's ID. Document list/reindex/version access also honors role/user allowlists. Qdrant filters by organization, current version and only SQL-derived document IDs the user can read.
- Upload length is bounded and extension/content checks cover common format mismatches. Stored paths use generated IDs, not the supplied filename.
- Action approval is admin-only and action IDs are looked up within the caller's organization. Approval does not claim execution.
- Client-provided SQL no longer reaches a database. The endpoint responds with 503 until a safe analytics implementation exists.
- Production startup does not call `Base.metadata.create_all`; schema changes use Alembic.

## Known security gaps (do not deploy as a production service yet)

1. No SSO, refresh/revocation, login throttling, password reset, invitation flow, or production first-admin provisioning.
2. No PostgreSQL RLS or tenant-scoped foreign keys on all records. Document ACLs are application-enforced and still need executed adversarial integration coverage.
3. No separate read-only database role because the analytics schema and safe SQL path are not implemented.
4. File type checks are basic. PDF parser resource limits, archive expansion limits, malware scanning, encrypted-file policy and external storage access controls are absent.
5. No durable job isolation, cancellation or worker-level authorization context. Upload originals currently use local filesystem storage.
6. Prompt-injection defenses rely on prompt instructions. Citation markers are not independently validated for claim support. Retrieved snippets are sent to Gemini when configured.
7. No rate limiting, CORS policy, global request timeout, token budget, API key rotation workflow, or secrets manager integration.
8. Audit details contain portions of user query and action metadata. Define retention, redaction and access controls before production.
9. Qdrant is not secured by Compose authentication or private networking; Compose ports and static Postgres credentials are local development only.

## Production deployment requirements

Use unique high-entropy secrets from Secret Manager, TLS, private service networking, least-privilege service accounts, authenticated/private Qdrant, Cloud SQL backups, object-level access policy, edge rate/body limits, log redaction, dependency/image scanning and an incident/retention policy. Create a dedicated organization provisioning path and test tenant isolation at the API and database layers. Do not enable SQL generation until an AST policy and database grants jointly enforce its read-only scope.

## Security verification status

No penetration test, dependency scan, container scan, abuse/load test or adversarial tenant integration test has been run. Current unit tests do not establish system security.
