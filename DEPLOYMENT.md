# Deployment guide and status

## Local development

From this directory, copy `.env.example` to `.env`, replace the local JWT/password values, then run:

```powershell
docker compose up --build
```

The UI/API serves at `http://localhost:8000`; OpenAPI is available at `/docs`. Compose starts PostgreSQL and Qdrant and mounts `./data` for local document files. Do not expose these ports or the example database credentials to a network. With `APP_ENV=development`, app startup creates the demo schema and first local admin. That bootstrap path is not a production account lifecycle.

For a standalone local migration run after installing the project, use `alembic upgrade head` from the project directory. Production mode skips ORM `create_all`; apply migrations as a separate controlled deployment step before starting the API. Verify the migration state and application health after deploy.

## Current deployment state

Only local Compose configuration exists. No GCP resources, Terraform, deployed URL, Cloud SQL instance, Cloud Storage bucket, Pub/Sub topic, Cloud Run service or billed-cost evidence exists. The current API still uses in-process background tasks and local filesystem storage, so the current Compose layout is not a template for a horizontally scaled production deployment.

## GCP target topology (planned)

Cloud Run API → Cloud SQL (private IP) and authenticated Qdrant; API stores originals in a private Cloud Storage bucket and emits an ingestion job to Pub/Sub/Cloud Tasks. A separate Cloud Run worker consumes jobs and updates PostgreSQL/Qdrant idempotently. Secret Manager supplies credentials. Cloud Logging/Monitoring and OpenTelemetry collect redacted traces and metrics. Use dedicated service accounts, least privilege, TLS, private networking and Cloud SQL backups.

Use a deployment job to apply Alembic migrations once per release; do not let every Cloud Run replica mutate schema at startup. Configure min/max instances, concurrency, timeouts, CPU/memory and queue retry/dead-letter policy from measured workload. Add a private Qdrant deployment with backups, access policy and capacity monitoring before production.

## Cost estimation method

No current cost estimate is included because region, traffic, document volume, embedding volume, model tokens and Qdrant sizing have not been measured. Estimate monthly totals from measured query/document rates and selected GCP region using current provider calculators; list assumptions, model/API prices and resource sizing date. Keep estimated and billed costs separate in reports.
