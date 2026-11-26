"""trace_spans table for ingested OpenTelemetry spans

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-26
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    create table trace_spans (
        application_id uuid not null references applications,
        trace_id text not null,
        span_id text not null,
        parent_span_id text,
        service text not null,
        name text not null,
        start_ts timestamptz not null,
        end_ts timestamptz not null,
        status text not null,
        primary key (application_id, trace_id, span_id)
    )
    """)
    op.execute("create index ix_trace_spans_service_start on trace_spans (application_id, service, start_ts)")


def downgrade() -> None:
    op.execute("drop table if exists trace_spans")