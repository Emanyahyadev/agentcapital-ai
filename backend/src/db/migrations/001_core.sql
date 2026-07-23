-- AgentCapital AI core schema: entities, documents, transactions, positions,
-- custodian feed (mock), look-through holdings, workflow runs, audit log.

create table if not exists entities (
    id          uuid primary key default gen_random_uuid(),
    name        text not null unique,
    kind        text not null check (kind in ('fund', 'sub_fund', 'company', 'custodian')),
    parent_id   uuid references entities(id),
    aliases     text[] not null default '{}',
    sector      text,
    created_at  timestamptz not null default now()
);

create table if not exists documents (
    id           uuid primary key default gen_random_uuid(),
    storage_path text not null,
    doc_type     text check (doc_type in ('capital_call', 'distribution', 'quarterly_report')),
    status       text not null default 'received'
                 check (status in ('received', 'parsed', 'failed')),
    sha256       text not null unique,  -- idempotency: same file never processed twice
    raw_text     text,
    parsed       jsonb,
    received_at  timestamptz not null default now(),
    parsed_at    timestamptz
);

create table if not exists transactions (
    id             uuid primary key default gen_random_uuid(),
    entity_id      uuid not null references entities(id),
    document_id    uuid references documents(id),
    txn_type       text not null check (txn_type in ('capital_call', 'distribution')),
    amount_usd     numeric(14, 2) not null,
    due_date       date,
    effective_date date,
    status         text not null default 'pending_review'
                   check (status in ('pending_review', 'confirmed', 'rejected')),
    confidence     real,
    created_at     timestamptz not null default now()
);

create table if not exists positions (
    id               uuid primary key default gen_random_uuid(),
    entity_id        uuid not null references entities(id),
    as_of            date not null,
    market_value_usd numeric(14, 2) not null,
    source           text not null check (source in ('custodian', 'calculated')),
    unique (entity_id, as_of, source)
);

-- Mock custodian bank feed. Deliberately keyed by *name*, not entity id:
-- real feeds arrive unlinked, which is why entity resolution exists.
create table if not exists custodian_feed (
    id                 bigserial primary key,
    account_ref        text not null,
    entity_name        text not null,
    position_value_usd numeric(14, 2) not null,
    as_of              date not null,
    unique (account_ref, as_of)
);

-- Look-through holdings: which portfolio companies each fund holds.
create table if not exists holdings (
    id                bigserial primary key,
    fund_entity_id    uuid not null references entities(id),
    company_entity_id uuid not null references entities(id),
    weight_pct        numeric(5, 2) not null,  -- % of TOTAL portfolio NAV via this fund
    as_of             date not null,
    unique (fund_entity_id, company_entity_id, as_of)
);

create table if not exists workflow_runs (
    id           uuid primary key default gen_random_uuid(),
    thread_id    text not null unique,  -- LangGraph checkpointer thread
    document_id  uuid references documents(id),
    status       text not null default 'running'
                 check (status in ('running', 'awaiting_approval', 'completed',
                                   'failed', 'rejected')),
    current_node text,
    error        jsonb,
    started_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);

create table if not exists approvals (
    id          uuid primary key default gen_random_uuid(),
    run_id      uuid not null references workflow_runs(id),
    question    text not null,
    context     jsonb not null default '{}',  -- candidates, confidences, excerpts
    decision    text check (decision in ('approved', 'rejected')),
    decided_by  text,
    created_at  timestamptz not null default now(),
    decided_at  timestamptz
);

create table if not exists reports (
    id         uuid primary key default gen_random_uuid(),
    run_id     uuid not null references workflow_runs(id),
    markdown   text not null,
    citations  jsonb not null default '[]',
    created_at timestamptz not null default now()
);

-- Every agent event lands here: the reconstructible trail for 3 AM debugging.
create table if not exists audit_log (
    id      bigserial primary key,
    run_id  uuid references workflow_runs(id),
    ts      timestamptz not null default now(),
    agent   text not null,
    event   text not null,
    level   text not null default 'info',
    payload jsonb not null default '{}'
);

create index if not exists idx_audit_run on audit_log (run_id, ts);
create index if not exists idx_txn_entity on transactions (entity_id);
create index if not exists idx_runs_status on workflow_runs (status);
