"""Polaris API: thin HTTP surface over the orchestrator.

Runs execute in background tasks; the graph parks at human gates via the
Postgres checkpointer, so an approval arriving hours later (or after a
process restart) resumes exactly where the run paused. Endpoints return
whatever the audit trail recorded — the API never invents state.
"""

import json
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from pydantic import BaseModel

from src.config.settings import get_settings
from src.core.llm import chat_model
from src.core.orchestrator import build_graph, mark_run
from src.db.client import db_conn
from src.observability.logger import bind_run_context, configure_logging, get_logger

configure_logging()
log = get_logger(component="api")

app = FastAPI(title="Polaris", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

INBOX_DIR = Path(__file__).resolve().parents[2] / "data" / "inbox"
SAMPLES_DIR = Path(__file__).resolve().parents[2] / "data" / "generated_pdfs"

# Dev fallback only: without DATABASE_URL, interrupts still survive across
# requests inside one process. Production always uses Postgres.
_memory_saver = InMemorySaver()
_checkpointer_ready = False


@contextmanager
def graph_session():
    """Yield a compiled graph bound to a fresh checkpointer connection.

    A new PostgresSaver per request avoids stale long-lived connections
    through the Supavisor pooler (Render free instances sleep; idle
    connections die with them)."""
    global _checkpointer_ready
    settings = get_settings()
    if not settings.database_url:
        yield build_graph(_memory_saver)
        return
    from langgraph.checkpoint.postgres import PostgresSaver

    with PostgresSaver.from_conn_string(settings.database_url) as saver:
        if not _checkpointer_ready:
            saver.setup()
            _checkpointer_ready = True
        yield build_graph(saver)


def _config(run_id: str) -> dict:
    return {"configurable": {"thread_id": run_id}}


def _execute_run(run_id: str, storage_path: str) -> None:
    bind_run_context(run_id)
    try:
        with graph_session() as graph:
            graph.invoke(
                {"run_id": run_id, "storage_path": storage_path, "errors": []},
                _config(run_id),
            )
    except Exception as exc:  # noqa: BLE001 — background boundary
        log.error("run_crashed", run_id=run_id, error=str(exc))
        mark_run(run_id, "failed", error={"message": str(exc)})


def _resume_run(run_id: str, payload: dict) -> None:
    bind_run_context(run_id)
    try:
        with graph_session() as graph:
            graph.invoke(Command(resume=payload), _config(run_id))
    except Exception as exc:  # noqa: BLE001
        log.error("resume_crashed", run_id=run_id, error=str(exc))
        mark_run(run_id, "failed", error={"message": str(exc)})


# --- schemas ---------------------------------------------------------------


class StartRun(BaseModel):
    storage_path: str


class Approval(BaseModel):
    selected_entity_id: str | None = None


class Question(BaseModel):
    question: str


# --- endpoints -------------------------------------------------------------


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/documents/samples")
def list_samples() -> list[dict]:
    if not SAMPLES_DIR.exists():
        return []
    return [
        {"name": p.name, "storage_path": str(p)}
        for p in sorted(SAMPLES_DIR.glob("*.pdf"))
    ]


@app.post("/documents/upload")
def upload_document(file: UploadFile) -> dict:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "only PDF notices are accepted")
    dest = INBOX_DIR / f"{uuid.uuid4().hex[:8]}_{Path(file.filename).name}"
    dest.write_bytes(file.file.read())
    return {"storage_path": str(dest)}


@app.post("/runs", status_code=202)
def start_run(body: StartRun, background: BackgroundTasks) -> dict:
    with db_conn() as conn:
        row = conn.execute(
            "insert into workflow_runs (thread_id, status, current_node)"
            " values (%s, 'running', 'ingest') returning id",
            (uuid.uuid4().hex,),
        ).fetchone()
        run_id = str(row[0])
        conn.execute(
            "update workflow_runs set thread_id = %s where id = %s", (run_id, run_id)
        )
    background.add_task(_execute_run, run_id, body.storage_path)
    return {"run_id": run_id, "status": "running"}


@app.get("/runs")
def list_runs() -> list[dict]:
    with db_conn() as conn:
        rows = conn.execute(
            """
            select r.id, r.status, r.current_node, r.started_at, r.updated_at,
                   d.storage_path
            from workflow_runs r
            left join documents d on d.id = r.document_id
            order by r.started_at desc limit 50
            """
        ).fetchall()
    return [
        {"run_id": str(r[0]), "status": r[1], "current_node": r[2],
         "started_at": str(r[3]), "updated_at": str(r[4]), "document": r[5]}
        for r in rows
    ]


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    with db_conn() as conn:
        run = conn.execute(
            "select id, status, current_node, error, started_at, updated_at"
            " from workflow_runs where id = %s",
            (run_id,),
        ).fetchone()
        if not run:
            raise HTTPException(404, "run not found")
        timeline = conn.execute(
            "select ts, agent, event, level, payload from audit_log"
            " where run_id = %s order by ts, id",
            (run_id,),
        ).fetchall()
        report = conn.execute(
            "select markdown, citations from reports where run_id = %s"
            " order by created_at desc limit 1",
            (run_id,),
        ).fetchone()

    pending_gate: dict[str, Any] | None = None
    if run[1] == "awaiting_approval":
        with graph_session() as graph:
            snapshot = graph.get_state(_config(run_id))
        for task in snapshot.tasks:
            for intr in task.interrupts:
                pending_gate = intr.value

    return {
        "run_id": str(run[0]),
        "status": run[1],
        "current_node": run[2],
        "error": run[3],
        "started_at": str(run[4]),
        "updated_at": str(run[5]),
        "timeline": [
            {"ts": str(t[0]), "agent": t[1], "event": t[2], "level": t[3],
             "payload": t[4]}
            for t in timeline
        ],
        "pending_gate": pending_gate,
        "report": {"markdown": report[0], "citations": report[1]} if report else None,
    }


@app.post("/runs/{run_id}/approve", status_code=202)
def approve(run_id: str, body: Approval, background: BackgroundTasks) -> dict:
    _record_decision(run_id, "approved", body.selected_entity_id)
    background.add_task(
        _resume_run, run_id,
        {"decision": "approved", "selected_entity_id": body.selected_entity_id},
    )
    return {"run_id": run_id, "decision": "approved"}


@app.post("/runs/{run_id}/reject", status_code=202)
def reject(run_id: str, background: BackgroundTasks) -> dict:
    _record_decision(run_id, "rejected", None)
    background.add_task(_resume_run, run_id, {"decision": "rejected"})
    return {"run_id": run_id, "decision": "rejected"}


def _record_decision(run_id: str, decision: str, entity_id: str | None) -> None:
    with db_conn() as conn:
        run = conn.execute(
            "select status from workflow_runs where id = %s", (run_id,)
        ).fetchone()
        if not run:
            raise HTTPException(404, "run not found")
        if run[0] != "awaiting_approval":
            raise HTTPException(409, f"run is {run[0]}, not awaiting approval")
        conn.execute(
            """
            insert into approvals (run_id, question, context, decision,
                                   decided_by, decided_at)
            values (%s, 'human gate decision', %s, %s, 'dashboard', now())
            """,
            (run_id, json.dumps({"selected_entity_id": entity_id}), decision),
        )


ASK_SYSTEM_PROMPT = """You answer questions for a family-office analyst using ONLY \
the provided book snapshot and document excerpts. Cite excerpts as [n]. If the answer \
is not in the provided material, say exactly that — never guess numbers."""


@app.post("/ask")
def ask(body: Question) -> dict:
    from src.retrieval.retriever import search_chunks

    chunks = search_chunks(body.question, match_count=6)
    excerpts = "\n\n".join(
        f"[{i + 1}] {c['content']}" for i, c in enumerate(chunks)
    ) or "(no matching document excerpts)"

    with db_conn() as conn:
        nav = conn.execute(
            """
            select distinct on (f.entity_name) f.entity_name, f.position_value_usd
            from custodian_feed f order by f.entity_name, f.as_of desc
            """
        ).fetchall()
        exposure = conn.execute(
            """
            select c.name, sum(h.weight_pct), array_agg(f.name)
            from holdings h
            join entities c on c.id = h.company_entity_id
            join entities f on f.id = h.fund_entity_id
            group by c.name order by 2 desc
            """
        ).fetchall()
    book = {
        "positions": {r[0]: float(r[1]) for r in nav},
        "look_through_exposure_pct": {
            r[0]: {"pct_of_nav": float(r[1]), "via_funds": r[2]} for r in exposure
        },
    }

    response = chat_model().invoke([
        ("system", ASK_SYSTEM_PROMPT),
        ("human", f"Question: {body.question}\n\nBook snapshot:\n"
                  f"{json.dumps(book)}\n\nDocument excerpts:\n{excerpts}"),
    ])
    answer = response.content if isinstance(response.content, str) else str(response.content)
    return {"answer": answer, "sources": chunks}


@app.get("/custodian/feed")
def custodian_feed() -> list[dict]:
    """The mock custodian bank feed — exposed so the demo can show what the
    validator reconciles against."""
    with db_conn() as conn:
        rows = conn.execute(
            "select account_ref, entity_name, position_value_usd, as_of"
            " from custodian_feed order by as_of desc, entity_name"
        ).fetchall()
    return [
        {"account_ref": r[0], "entity_name": r[1],
         "position_value_usd": float(r[2]), "as_of": str(r[3])}
        for r in rows
    ]
