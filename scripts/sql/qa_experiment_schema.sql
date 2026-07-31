-- Milestone 7B.1d: disposable, publication-decoupled Q&A retrieval-chunk
-- experiment schema.
--
-- Deliberately NOT an Alembic migration under migrations_app/ -- this schema
-- does not go through PublicationBuilder, has no BUILDING/VALIDATING/READY
-- lifecycle, carries no app_readonly grants, and is never read by the
-- Next.js app in this milestone. It is safe to drop and rebuild at any time
-- (see build_chunks.py --reset) without touching app/app_internal, the
-- active publication, or canonical passage embeddings.
--
-- Every table still references app.* rows by real FK (reports/companies/
-- passages/passage_comparisons/report_comparisons) so chunk->canonical
-- lineage is enforced by the database, not just convention -- but qa_experiment
-- rows cascade only from app.* deletes, never the reverse, and are never
-- referenced by app_internal.publications, so this schema has no bearing on
-- publication cleanup/retention.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS qa_experiment;

CREATE TABLE IF NOT EXISTS qa_experiment.retrieval_chunks (
    id UUID PRIMARY KEY,
    publication_version VARCHAR(64) NOT NULL,
    report_id UUID NOT NULL REFERENCES app.reports(id) ON DELETE CASCADE,
    company_id UUID NOT NULL REFERENCES app.companies(id) ON DELETE CASCADE,
    anchor_passage_id UUID NOT NULL REFERENCES app.passages(id) ON DELETE CASCADE,
    chunk_strategy VARCHAR(64) NOT NULL,
    chunk_text TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    word_count INTEGER NOT NULL,
    page_start INTEGER NOT NULL,
    page_end INTEGER NOT NULL,
    text_hash VARCHAR(64) NOT NULL,
    embedding_model VARCHAR(255) NOT NULL,
    embedding_model_revision VARCHAR(64) NOT NULL,
    dimensions INTEGER NOT NULL,
    embedding VECTOR(384) NOT NULL,
    truncation_policy VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Chunk id is deterministic from (publication_version, chunk_strategy,
    -- text_hash) -- see qa_experiment/labels.py -- so this constraint is a
    -- belt-and-suspenders re-check, never expected to fire.
    CONSTRAINT uq_qa_chunk_identity UNIQUE (publication_version, chunk_strategy, text_hash)
);

CREATE INDEX IF NOT EXISTS ix_qa_retrieval_chunks_publication_version
    ON qa_experiment.retrieval_chunks (publication_version);
CREATE INDEX IF NOT EXISTS ix_qa_retrieval_chunks_report_id
    ON qa_experiment.retrieval_chunks (report_id);
CREATE INDEX IF NOT EXISTS ix_qa_retrieval_chunks_anchor_passage_id
    ON qa_experiment.retrieval_chunks (anchor_passage_id);
CREATE INDEX IF NOT EXISTS ix_qa_retrieval_chunks_strategy
    ON qa_experiment.retrieval_chunks (chunk_strategy);
CREATE INDEX IF NOT EXISTS ix_qa_retrieval_chunks_hnsw_cosine
    ON qa_experiment.retrieval_chunks USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS qa_experiment.retrieval_chunk_passages (
    chunk_id UUID NOT NULL REFERENCES qa_experiment.retrieval_chunks(id) ON DELETE CASCADE,
    passage_id UUID NOT NULL REFERENCES app.passages(id) ON DELETE CASCADE,
    passage_order INTEGER NOT NULL,
    role VARCHAR(32) NOT NULL CHECK (
        role IN ('PREVIOUS', 'ANCHOR', 'NEXT', 'EARLIER_SIDE', 'LATER_SIDE', 'HEADING_CONTEXT', 'TOKEN_MEMBER')
    ),
    PRIMARY KEY (chunk_id, passage_id, role)
);
CREATE INDEX IF NOT EXISTS ix_qa_chunk_passages_passage_id
    ON qa_experiment.retrieval_chunk_passages (passage_id);

CREATE TABLE IF NOT EXISTS qa_experiment.retrieval_chunk_contexts (
    chunk_id UUID NOT NULL REFERENCES qa_experiment.retrieval_chunks(id) ON DELETE CASCADE,
    report_comparison_id UUID NOT NULL REFERENCES app.report_comparisons(id) ON DELETE CASCADE,
    passage_comparison_id UUID NOT NULL REFERENCES app.passage_comparisons(id) ON DELETE CASCADE,
    report_side VARCHAR(16) NOT NULL CHECK (report_side IN ('EARLIER', 'LATER')),
    alignment_status VARCHAR(32) NOT NULL,
    earlier_period_end DATE,
    later_period_end DATE,
    PRIMARY KEY (chunk_id, passage_comparison_id, report_side)
);
CREATE INDEX IF NOT EXISTS ix_qa_chunk_contexts_passage_comparison_id
    ON qa_experiment.retrieval_chunk_contexts (passage_comparison_id);
