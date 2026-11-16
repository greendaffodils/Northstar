# ADR 0001: Keep the first release a modular monolith

- Status: Accepted
- Date: 2026-11-16

## Context

Northstar is a small first-slice application with one API process, one relational store and one vector store. Splitting it into services now would add deployment and operational cost before durable ingestion, analytics or a measured throughput bottleneck exists.

## Decision

Keep FastAPI as a modular monolith. Separate domain and infrastructure logic into Python modules. When ingestion needs crash recovery and independent scaling, introduce a worker boundary with a durable queue; do not split unrelated API modules into network services without evidence.

## Consequences

The local demo is straightforward to run and trace. In-process `BackgroundTasks` remain a known limitation and must be replaced before multi-replica production deployment. Module boundaries need improvement as routes grow.
