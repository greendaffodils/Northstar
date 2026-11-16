# Evaluation plan and current evidence

## Current evidence

There is no retrieval benchmark, answer-quality dataset, measured latency/cost result or load test. The five executed unit checks cover chunk overlap/content, CSV dimensions, upload signature mismatch and production-secret validation. Tenant API adversarial tests are present but were skipped in this environment because PyJWT and pwdlib are not installed. No scores are reported here because no reproducible benchmark has been run.

## Benchmark design

Build a versioned synthetic corpus with answerable, unanswerable, temporal, conflicting, equipment-specific, multi-document, structured-data and tenant-adversarial questions. For every question, reviewers record expected facts, acceptable source passages, answerability, tenant, equipment/time entities and whether a refusal is expected. Store data provenance: all records must be labeled generated, use deterministic seeds, and avoid representing them as observed industrial facts.

For each retriever configuration, freeze corpus, embedding model/revision, chunking config, Qdrant snapshot, top-k and reranker version. Compare dense-only, BM25-only, RRF and RRF+rereank/filter. Report Recall@5/10, Precision@K, MRR and nDCG@10, with latency distributions and failed-query counts.

For generated answers, independently label factual correctness, claim-level citation precision, support/faithfulness, contradiction handling and abstention. Report sample size and confidence intervals. Review a human-checked sample; automated LLM judges alone are not ground truth. Track token counts and provider pricing assumptions with timestamped model configuration; do not infer costs from unmeasured tokens.

For routing/agents, compare direct RAG, deterministic SQL/analysis, a simple multi-source orchestration and LangGraph. Record task success, unsupported claims, citations, tool correctness, execution steps, p50/p95 latency and cost. Keep multi-agent orchestration only where it improves a defined metric enough to justify added failure modes.

## Regression requirements

Store benchmark JSONL and environment/config manifests under `experiments/`. CI should run a small deterministic retrieval suite on every change and a larger scheduled suite for model changes. Use explicit tolerances and fail on regressions in tenant isolation, citation validity and SQL policy. Keep model-generated output snapshots limited to deterministic/mock integration tests; quality evaluation should use a versioned run artifact rather than brittle exact strings.

## Metrics definitions

- Recall@K: fraction of labeled relevant passages present in the top K.
- Precision@K: relevant passages among the top K, divided by K (also report result-count-adjusted precision where fewer than K are returned).
- MRR: reciprocal rank of the first relevant passage, averaged across questions.
- nDCG@10: normalized discounted cumulative gain using graded passage relevance.
- Citation precision: answer claims with valid, supporting cited passages divided by all cited factual claims.
- Faithfulness: supported answer claims divided by factual answer claims; score via a reviewed protocol, not only an LLM judge.
- Abstention quality: correct abstentions on unanswerable cases plus answer rate on answerable cases, reported separately.

No target metric should be described as achieved until a result artifact and dataset version are committed.
