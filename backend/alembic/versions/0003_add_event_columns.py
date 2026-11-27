"""add application_id and seq to incident_events

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "alter table incident_events add column application_id uuid references applications (id)"
    )
    op.execute(
        "alter table incident_events add column seq bigint generated always as identity"
    )
    # The table is empty at this point (nothing writes to it yet), so NOT NULL is safe.
    op.execute("alter table incident_events alter column application_id set not null")
    op.execute("create unique index incident_events_seq_idx on incident_events (seq)")
    op.execute(
        "create index incident_events_app_seq_idx on incident_events (application_id, seq)"
    )


def downgrade() -> None:
    op.execute("drop index if exists incident_events_app_seq_idx")
    op.execute("drop index if exists incident_events_seq_idx")
    op.execute("alter table incident_events drop column if exists seq")
    op.execute("alter table incident_events drop column if exists application_id")