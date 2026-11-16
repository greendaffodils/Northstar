# ADR 0002: Disable the regex-only SQL executor

- Status: Accepted
- Date: 2026-11-16

## Context

The prior endpoint accepted arbitrary SQL text and used regex checks for a small set of blocked words and table names. It had no SQL AST policy, no tenant predicate or row-level security, no dedicated read-only credential, and the allow-listed `sales_records` table was absent from the schema. A `SELECT` can still invoke unsafe functions or bypass assumptions in regex filters.

## Decision

Remove the executor and return HTTP 503 from `/api/data/query` until the industrial schema, SQL AST validation, mandatory tenant scope, statement/resource limits and a separate read-only DB role are implemented and tested together. Preserve route discovery but document its temporary unavailable status.

## Consequences

The current SQL API contract no longer pretends to work, and the frontend does not offer structured analytics. Phase 3 can implement safe deterministic analytics first and add NL-to-SQL only behind a reviewed policy. The 503 is a deliberate safety/correctness trade-off.
