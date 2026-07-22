# Architecture

## The problem

A family office holds 50–200 private investments. Capital calls and distribution
notices arrive as PDFs. Processing them by hand produces the expensive failure
modes this system is built around: calls booked to the wrong (sub-)fund, unreconciled
positions, missed funding deadlines with penalty interest, and hidden look-through
concentration that no single fund report reveals.

## System overview

```
                         ┌──────────────────────────────────────────────┐
   PDF notice ──────────►│                 ORCHESTRATOR                  │
   (inbox)               │        LangGraph StateGraph, Postgres         │
                         │      checkpointing after every node           │
                         └──────────────────────────────────────────────┘
                              │ conditional, validation-gated edges
      ┌───────────┬──────────┼───────────┬─────────────┬──────────┬──────────┐
      ▼           ▼          ▼           ▼             ▼          ▼          ▼
 ┌─────────┐ ┌─────────┐ ┌────────┐ ┌──────────┐ ┌──────────┐ ┌───────┐ ┌────────┐
 │ ingest  │ │ input   │ │ parse  │ │ resolve  │ │ validate │ │analyze│ │ risk / │
 │ (pdf →  │ │ guard   │ │ (LLM   │ │ (fuzzy + │ │ (recon + │ │ (NAV, │ │ report │
 │ text,   │ │ (regex  │ │ struct │ │ threshold│ │ dedup +  │ │ no    │ │        │
 │ sha256) │ │ redact) │ │ + a    │ │ refusal) │ │ deadline)│ │ LLM)  │ │        │
 └─────────┘ └─────────┘ │ ground │ └──────────┘ └──────────┘ └───────┘ └────────┘
                         │ check) │      │             │
                         └────────┘      ▼             ▼
                                   [entity_gate] [exception_gate]   ← interrupt()
                                    human picks   human overrides     runs park in
                                    the entity    or rejects          the checkpointer

 State: Supabase Postgres (entities, transactions, positions, custodian_feed,
        holdings, workflow_runs, approvals, audit_log, doc_chunks/pgvector)
 LLM:   Gemini 2.5 Flash (+ Flash-Lite), gemini-embedding-001 @ 768d
 Cache: Upstash Redis (embedding cache, best-effort)
 Obs:   structlog JSON + audit_log table + LangSmith tracing
```

## Load-bearing design decisions

**Contracts at every boundary** (`src/core/contracts.py`). Agents exchange
JSON-serializable dicts validated through Pydantic models in
`BaseAgent._validate_output`. A malformed output is stopped at the boundary that
produced it. Amount bounds (`0 < amount < $1B`) are hallucination tripwires.

**Well-formed is not true** (`src/guardrails/output_guard.py`). Schema validation
cannot catch a model that extracts $975,000 from a document that says $850,000.
The grounding check requires the extracted amount and fund name to literally
appear in the source text.

**Resolution refuses to guess** (`src/agents/entity_resolver.py`). Matching is
deterministic (exact → alias → RapidFuzz), not an LLM call, because entity
resolution must be explainable and reproducible. Three refusal rules route to a
human: top candidate below the auto-accept threshold (0.93), runner-up within
the ambiguity margin (0.05), or a parent-fund notice that allocates across
sub-funds. Thresholds are pinned by the adversarial eval suite.

**Failures are data, not exceptions** (`src/agents/base.py`). Agents classify
failures (transient / permanent / contract), retry only transient ones with
full-jitter backoff, and trip a per-agent circuit breaker after repeated
exhaustion. A failed agent appends a structured `AgentError` to state; the graph
routes to `error_handler` and downstream agents are never invoked on a poisoned
state.

**Checkpoint everything** (`src/core/orchestrator.py`). The Postgres checkpointer
persists full state after every node. Human gates use `interrupt()` — a run
waiting for approval is parked state, not a blocked process, and survives
restarts and deploys. `sha256` uniqueness on documents makes replays idempotent.

**Hybrid RAG in SQL** (`src/db/migrations/002_rag.sql`). Dense (pgvector HNSW)
and full-text rankings are fused with Reciprocal Rank Fusion inside a single
`hybrid_search()` SQL function. Finance queries are exact-token-heavy
("Fund IV-A", "NGV9-2026-044"); pure vector search blurs precisely those tokens.

## Trade-offs made deliberately

| Decision | Trade-off |
|---|---|
| pymupdf + Gemini structured output instead of Docling | Docling's layout models exceed the 512MB RAM of the free hosting tier. Text-layer extraction + LLM parsing covers digital-native notices; scanned PDFs would need OCR (out of scope, documented). |
| No cross-encoder re-ranker | Same RAM constraint. RRF over two strong signals ranks well at this corpus size; the retriever interface isolates the swap if one is added. |
| Deterministic NAV math, zero LLM | Numbers an LLM "computed" cannot be audited. The analyst agent is arithmetic over sourced values, persisted as `calculated` positions. |
| Single mock custodian feed | Real custodial integrations are credentialed and proprietary. The feed table reproduces the property that matters: an independent source that disagrees with documents. |
| Best-effort audit writes | An audit INSERT failing must never take down the pipeline it describes; failures are logged and the run continues. |

## Free-tier deployment shape

Vercel (dashboard) → Render free (FastAPI + LangGraph) → Supabase (Postgres +
pgvector + Storage) with Upstash Redis and LangSmith free. One operational
constraint is encoded in code rather than docs: checkpointer connections are
opened per-request (`graph_session()`), because free-tier instances sleep and
long-lived pooler connections die with them. The Supabase connection must use
the session-mode pooler (port 5432) — the direct host is IPv6-only and
unreachable from Render.
