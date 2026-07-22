# Polaris

Autonomous capital-call processing for family offices — a production-style multi-agent system.

Family offices receive capital calls and distribution notices as PDFs attached to emails. Processing them
by hand is slow and error-prone: mis-allocated calls, unreconciled positions, missed deadlines with real
penalty interest. Polaris automates the pipeline with six cooperating agents — document ingestion, entity
resolution, data validation/reconciliation, portfolio analysis, risk monitoring, and report generation —
orchestrated by LangGraph with Postgres checkpointing, human-in-the-loop approval gates, hybrid RAG over
filings, and structured observability.

> Full architecture, failure modes, and design trade-offs: see [`docs/`](docs/).

## Stack

- **Orchestration:** LangGraph (Python 3.12) — conditional routing, interrupts, Postgres checkpointer
- **Data:** Supabase (Postgres + pgvector + Storage), Upstash Redis (idempotency + cache)
- **LLM:** Gemini 2.5 Flash / Flash-Lite, `gemini-embedding-001` (768d)
- **API:** FastAPI · **UI:** Next.js · **Tracing:** LangSmith · **CI:** GitHub Actions

## Quickstart

```bash
cd backend
uv sync --all-groups
cp ../.env.example .env   # fill in Supabase / Gemini / Upstash keys
uv run python scripts/setup_db.py      # apply migrations
uv run python src/db/seed.py           # seed entities, positions, custodian feed
uv run python scripts/generate_pdfs.py # synthetic capital-call PDFs
uv run uvicorn src.api.main:app --reload
```

Run tests and evals:

```bash
uv run pytest -q
uv run python scripts/run_evals.py
```
