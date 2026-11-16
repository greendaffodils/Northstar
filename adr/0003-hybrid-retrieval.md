# ADR 0003: Use reciprocal-rank fusion for initial hybrid retrieval

- Status: Accepted, provisional pending benchmark
- Date: 2026-11-16

## Context

Industrial knowledge questions can contain exact equipment identifiers, part numbers and failure codes alongside semantic descriptions. Dense similarity is useful for paraphrase; lexical matching is useful for exact terms. Raw scores from separate retrievers are not directly comparable.

## Decision

The first retrieval implementation combines organization-filtered Qdrant candidates and SQL-backed BM25 candidates with reciprocal-rank fusion. Keep this provisional: the current app has no representative corpus or retrieval metrics.

## Consequences

The method avoids calibrating incomparable raw scores and provides both candidate types in one ranking. It currently rebuilds BM25 from all ready tenant chunks for each query, which will not scale. Phase 2 must benchmark it and add an indexed lexical backend or cached corpus representation if measurements justify it. Reranking and query expansion are deferred until a baseline exists.
