-- RAG layer: pgvector chunks + hybrid (vector + full-text) retrieval with
-- Reciprocal Rank Fusion, all in SQL. No external vector DB needed.

create extension if not exists vector;

create table if not exists doc_chunks (
    id          bigserial primary key,
    document_id uuid not null references documents(id) on delete cascade,
    chunk_index int not null,
    content     text not null,
    embedding   vector(768),
    tsv         tsvector generated always as (to_tsvector('english', content)) stored,
    unique (document_id, chunk_index)
);

create index if not exists idx_chunks_tsv on doc_chunks using gin (tsv);
create index if not exists idx_chunks_embedding on doc_chunks
    using hnsw (embedding vector_cosine_ops);

-- Hybrid search: rank chunks by semantic similarity AND keyword match,
-- fuse with RRF (1 / (k + rank)). Chunks found by both channels win.
create or replace function hybrid_search(
    query_text      text,
    query_embedding vector(768),
    match_count     int default 8,
    rrf_k           int default 50
)
returns table (
    chunk_id    bigint,
    document_id uuid,
    content     text,
    score       numeric
)
language sql stable as $$
with fts as (
    select id, row_number() over (
        order by ts_rank_cd(tsv, websearch_to_tsquery('english', query_text)) desc
    ) as rank
    from doc_chunks
    where tsv @@ websearch_to_tsquery('english', query_text)
    limit 40
),
vec as (
    select id, row_number() over (
        order by embedding <=> query_embedding
    ) as rank
    from doc_chunks
    where embedding is not null
    limit 40
)
select
    c.id,
    c.document_id,
    c.content,
    round(
        coalesce(1.0 / (rrf_k + fts.rank), 0) +
        coalesce(1.0 / (rrf_k + vec.rank), 0), 6
    ) as score
from doc_chunks c
left join fts on fts.id = c.id
left join vec on vec.id = c.id
where fts.id is not null or vec.id is not null
order by score desc
limit match_count;
$$;
