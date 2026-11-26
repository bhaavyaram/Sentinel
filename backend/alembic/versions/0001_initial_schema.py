"""initial schema from Contracts v0.1 section 9

Revision ID: 0001
Revises:
Create Date: 2026-11-26
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    create table applications (
        id uuid primary key,
        name text unique not null,
        adapter jsonb not null,
        status text not null,
        created_at timestamptz not null default now()
    )
    """)

    op.execute("""
    create table services (
        id uuid primary key,
        application_id uuid references applications,
        name text not null,
        type text not null,
        critical boolean not null default false,
        health_endpoint text,
        unique (application_id, name)
    )
    """)

    op.execute("""
    create table dependencies (
        id uuid primary key,
        application_id uuid references applications,
        source text not null,
        target text not null,
        evidence text not null check (evidence in ('trace','declared')),
        unique (application_id, source, target)
    )
    """)

    op.execute("""
    create table experiments (
        id uuid primary key,
        application_id uuid references applications,
        service text not null,
        fault_type text not null,
        parameters jsonb not null default '{}',
        started_at timestamptz,
        ended_at timestamptz,
        initiated_by text not null
    )
    """)

    op.execute("""
    create table incidents (
        id uuid primary key,
        application_id uuid references applications,
        status text not null,
        severity text not null,
        opened_at timestamptz not null,
        closed_at timestamptz,
        root_cause_summary text
    )
    """)

    op.execute("""
    create table incident_events (
        id uuid primary key,
        incident_id uuid references incidents,
        ts timestamptz not null,
        actor text not null,
        type text not null,
        payload jsonb not null,
        policy_version int
    )
    """)

    op.execute("""
    create table policies (
        version serial primary key,
        body jsonb not null,
        created_by text not null,
        created_at timestamptz not null default now()
    )
    """)

    op.execute("""
    create table approvals (
        id uuid primary key,
        incident_id uuid references incidents,
        proposal jsonb not null,
        requested_at timestamptz not null,
        decided_by text,
        decision text,
        decided_at timestamptz
    )
    """)

    op.execute("""
    create table audit_log (
        id uuid primary key,
        ts timestamptz not null default now(),
        actor text not null,
        tool text,
        parameters jsonb,
        verdict text,
        reason_code text,
        reason text,
        policy_version int not null,
        dry_run boolean not null default false
    )
    """)

    op.execute("""
    create table postmortems (
        id uuid primary key,
        incident_id uuid references incidents unique,
        summary text not null,
        timeline jsonb not null,
        recovery_metrics jsonb not null
    )
    """)

    # Indexes for the queries the dashboard will run most often.
    op.execute("create index ix_incident_events_incident_ts on incident_events (incident_id, ts)")
    op.execute("create index ix_audit_log_ts on audit_log (ts)")

    # audit_log and policies are append-only (Contracts section 9, invariants 7 and 9).
    op.execute("""
    create function forbid_update_delete() returns trigger as $$
    begin
        raise exception '% is append-only: % is not allowed', tg_table_name, tg_op;
    end;
    $$ language plpgsql
    """)
    op.execute("""
    create trigger audit_log_append_only
    before update or delete on audit_log
    for each row execute function forbid_update_delete()
    """)
    op.execute("""
    create trigger policies_append_only
    before update or delete on policies
    for each row execute function forbid_update_delete()
    """)


def downgrade() -> None:
    op.execute("drop trigger if exists policies_append_only on policies")
    op.execute("drop trigger if exists audit_log_append_only on audit_log")
    op.execute("drop function if exists forbid_update_delete()")
    op.execute("drop table if exists postmortems")
    op.execute("drop table if exists audit_log")
    op.execute("drop table if exists approvals")
    op.execute("drop table if exists policies")
    op.execute("drop table if exists incident_events")
    op.execute("drop table if exists incidents")
    op.execute("drop table if exists experiments")
    op.execute("drop table if exists dependencies")
    op.execute("drop table if exists services")
    op.execute("drop table if exists applications")