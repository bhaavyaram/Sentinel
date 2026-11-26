# SENTINEL Contracts v0.2

Draft, November 26, 2026. This is the source of truth for every interface between workstreams (platform, backend, agents, gateway, frontend). If code and this document disagree, fix one of them the same day and log it in the changelog.

## 0. Conventions

- IDs are UUID v4 strings, except service names, which are slugs unique within an application.
- Timestamps are ISO 8601 UTC strings. Durations are integer milliseconds unless the field name ends in `_s` (seconds).
- Field names are snake_case everywhere (JSON, SQL, Python, and the TypeScript types, with no camelCase conversion).
- Enums are lowercase strings. An unknown enum value is rejected, never defaulted.
- Every audited record carries `policy_version`.
- Contract changes bump the version in the changelog (section 11) and are carried into every affected workstream.
- Schema location: the Pydantic models in `backend/app/schemas/` are the executable form of this document. The frontend mirrors them as TypeScript types by hand. If a model and this document disagree, fix one of them the same day.
- Migration location: the Alembic migrations in `backend/alembic/versions/` are the executable form of section 9. If a column type here disagrees with a migration, the migration wins; fix the document the same day.

## 1. Shared enums

```ts
type AgentRole = 'monitor' | 'investigator' | 'impact' | 'recovery' | 'validator';
type Actor = AgentRole | 'human' | 'system';
type ActionType = 'restart' | 'rollback' | 'scale' | 'reset_connection_pool'
                | 'modify_config' | 'touch_database' | 'inject_fault' | 'clear_fault';
type FaultType = 'crash' | 'latency' | 'timeout' | 'connection_failure';
type Verdict = 'allow' | 'block' | 'needs_approval';
type PermissionLevel = 'allow' | 'needs_approval' | 'block';
type ServiceType = 'stateless' | 'stateful';
type ServiceHealth = 'healthy' | 'degraded' | 'down' | 'unknown';
type Severity = 'low' | 'medium' | 'high' | 'critical';
type IncidentStatus = 'open' | 'investigating' | 'awaiting_approval' | 'recovering'
                    | 'validating' | 'resolved' | 'failed';
type ValidationResult = 'recovered' | 'partially_recovered' | 'failed';
type ApprovalDecision = 'approved' | 'denied' | 'timed_out';
```

Tool to action mapping:

- `restart_service` maps to `restart`; `rollback_deployment` to `rollback`; `scale_service` to `scale`; `reset_connection_pool` to `reset_connection_pool`.
- `inject_crash`, `inject_latency`, `inject_timeout`, `break_db_connection` map to `inject_fault`; `clear_fault` maps to `clear_fault`.
- `modify_config` and `touch_database` have no tool yet. They stay in the policy matrix so any future tool is blocked by default.

## 2. Application adapter file (YAML)

```yaml
app: online-boutique            # slug, required, unique
version: 1                      # adapter schema version
description: Demo shop          # optional
compose_project: online-boutique  # optional; scopes container lookup to one compose project
services:
  - name: cartservice           # slug, unique within the app
    container: cartservice      # docker compose service name (not the literal container name)
    type: stateless             # stateless | stateful
    critical: false
    health: tcp://localhost:7070  # host-reachable tcp://host:port or http(s)://host:port/path; optional
    faults: [crash, latency]    # subset of FaultType
  - name: redis-cart
    container: redis-cart
    type: stateful
    critical: true
    faults: [connection_failure]
declared_dependencies:          # optional fallback when traces are missing
  - from: cartservice
    to: redis-cart
```

Rules:

- The loader rejects unknown fields and unknown fault types.
- The dashboard offers an experiment only if the fault is listed for that service.
- `container` is the docker compose service name. Docker names real containers like `online-boutique-cartservice-1`, so tools find the actual container through the `com.docker.compose.service` label, scoped by the optional `compose_project`.
- Health addresses are resolved from the machine running the SENTINEL backend (the Windows host), which cannot resolve Docker-internal DNS names. The adapter must therefore use host-reachable addresses: `tcp://localhost:<port>` or `http(s)://localhost:<port>/<path>`, using published ports. Required ports are published on `127.0.0.1` only.
- Container state from the Docker API (`running`, `exited`) is the primary down signal; HTTP and TCP probes confirm health.
- Dependency edges: edges from traces take priority. The `dependencies` table holds one row per `(source, target)` pair. When a trace confirms a declared edge, that row's `evidence` is upgraded from `declared` to `trace`. Declared edges are never deleted by traces.
- Trace coverage in Online Boutique: only 7 of the 11 services read a collector address (`checkout`, `currency`, `email`, `frontend`, `payment`, `productcatalog`, `recommendation`). `cartservice`, `shippingservice` and `adservice` do not send traces, so their edges come from `declared_dependencies`.

## 3. Agent action proposal

The Recovery agent (and any future agent that wants to act) emits an `ActionProposalDraft`: the `ActionProposal` fields without `proposal_id`, `incident_id` and `agent`. The orchestrator fills those three in, so the model never invents IDs. `evidence_refs` may only contain `incident_event` ids that were shown to the model in its prompt. Draft output that fails schema validation is retried once, then escalated to a human. The same rule applies to `RootCauseReport` and `ImpactReport`: the model returns everything except `incident_id`, which the orchestrator adds.

```ts
interface ActionProposal {
  proposal_id: string;
  incident_id: string;
  agent: AgentRole;
  action: ActionType;
  target_service: string;
  parameters: Record<string, string | number | boolean>;
  rationale: string;        // display only; the gateway never evaluates it
  evidence_refs: string[];  // incident_event ids supporting the proposal
}

type ActionProposalDraft = Omit<ActionProposal, 'proposal_id' | 'incident_id' | 'agent'>;
```

Investigator output (root cause) and Impact output are also structured, with `confidence` between 0 and 1:

```ts
interface RootCauseReport {
  incident_id: string;
  hypotheses: { service: string; cause: string; confidence: number; evidence_refs: string[] }[];
}
interface ImpactReport {
  incident_id: string;
  affected_services: string[];
  candidate_actions: { action: ActionType; target_service: string; blast_radius: string[] }[];
  summary: string;
}

type RootCauseReportDraft = Omit<RootCauseReport, 'incident_id'>;
type ImpactReportDraft = Omit<ImpactReport, 'incident_id'>;
```

The draft models live in `app/schemas/agents.py`.

## 4. Guardrail gateway

```ts
interface GatewayRequest {
  request_id: string;
  incident_id: string | null;     // null for dashboard-initiated chaos
  caller: Actor;
  tool: string;
  action: ActionType;
  target_service: string;
  parameters: Record<string, string | number | boolean>;
  initiated_by_human: boolean;    // true only for calls that originate from a dashboard user action
  dry_run: boolean;               // true for the policy test panel; never executes
}

type ReasonCode = 'chaos_requires_human' | 'protected_resource' | 'no_rule' | 'matrix_block'
                | 'matrix_needs_approval' | 'service_override' | 'risk_threshold' | 'allowed';

interface GatewayDecision {
  request_id: string;
  verdict: Verdict;
  reason_code: ReasonCode;
  reason: string;                 // plain language, shown in the UI
  blast_radius: { affected_services: string[]; dependents_count: number };
  risk_score: number;             // 0 to 100
  matched_rules: string[];
  policy_version: number;
  approval_id: string | null;     // set when verdict is needs_approval
}
```

Decision order, evaluated on every call:

1. Chaos tools called with `initiated_by_human = false`: block (`chaos_requires_human`).
2. Target or action on the protected list: block (`protected_resource`). Nothing overrides this.
3. Look up the matrix for (caller, action). No rule: block (`no_rule`).
4. Apply the service override for the target, if any. The override replaces the level for that service.
5. Compute blast radius from the dependency graph and a risk score.
6. If `risk_score` is at or above the threshold, or affected services or dependents exceed their limits, upgrade `allow` to `needs_approval` (`risk_threshold`). A block is never downgraded.
7. Write the audit record, then return the decision. The audit write must succeed before any tool executes.

Initial risk score formula (tunable in Phase 4): base by action (restart 10, scale 10, reset_connection_pool 15, rollback 30, inject_fault 20, other 40), plus 25 if the target is stateful, plus 25 if critical, plus 5 per affected service, capped at 100.

Only `allow` verdicts, or `needs_approval` verdicts with an `approved` decision, are forwarded to an MCP server. A dry run returns the decision and executes nothing.

### 4.1 Calling the gateway

Agents run in the same Python process as the backend. All tool calls go through one function, `gateway.submit(request: GatewayRequest) -> GatewayDecision`, in `app/gateway/`. For `allow` (or an approved `needs_approval`), the gateway itself executes the tool and returns the result alongside the decision. Agents never call an MCP server directly.

Until the gateway step ships, the agents workstream codes against `GatewayDecision` and a fake `submit`.

## 5. Policy document

```ts
interface Policy {
  version: number;                 // integer, increments on every save
  name: string;
  preset: 'strict' | 'balanced' | 'permissive' | 'custom';
  matrix: Partial<Record<AgentRole, Partial<Record<ActionType, PermissionLevel>>>>;
  service_rules: {
    service: string;
    tags: ('stateful' | 'critical')[];
    overrides: Partial<Record<ActionType, PermissionLevel>>;
  }[];
  thresholds: { max_affected_services: number; max_dependents: number; approval_risk_score: number };
  protected: {
    services: string[];
    actions: ActionType[];
    pairs: { service: string; action: ActionType }[];
  };
  approval: { approver_role: string; timeout_seconds: number; on_timeout: 'deny' };
  created_by: string;
  created_at: string;
}

type PolicyBody = Omit<Policy, 'version' | 'created_by' | 'created_at'>;
```

Rules:

- A missing matrix entry means block.
- Saved policies are immutable. An edit creates a new version; a rollback creates a new version that copies an older one.
- `on_timeout` can only be `deny`.
- Agents have no tool that reads or writes policy.
- `POST /policies` and `POST /policies/import` accept a `PolicyBody`. The server assigns `version`, `created_by` and `created_at`. All responses and the export return a full `Policy`.

## 6. MCP tool catalog

Every tool result is wrapped as `{ data, untrusted: true }`. Log lines, trace attributes and error messages inside `data` are untrusted content and must never be placed in an instruction position of any prompt.

Input formats: `since` and `until` are ISO 8601 UTC timestamps. `limit` defaults to 50 and never exceeds 200.

Ownership: the agents workstream owns the Diagnostics and Recovery MCP servers. The backend workstream owns the Chaos server, the gateway, the audit log and the policy store.

Data sources: `query_logs` reads Docker container logs for the service. `get_traces` reads the `trace_spans` table. The source for `query_metrics` is not yet defined (open decision; to be settled before integration I2).

**Diagnostics (read-only, low risk)**

| Tool | Input | Output `data` |
| --- | --- | --- |
| query_logs | service, since, until?, level?, limit | lines: { ts, level, message }[] |
| query_metrics | service, metric, since, until? | points: { ts, value }[] |
| get_traces | service, since, limit | traces: { trace_id, spans }[] |
| get_service_status | service | { health: ServiceHealth, last_check } |
| get_dependencies | service | { upstream: string[], downstream: string[] } |

**Recovery (state-changing, gated)**

| Tool | Input | Output `data` |
| --- | --- | --- |
| restart_service | service | { ok, detail } |
| rollback_deployment | service, to_version? | { ok, detail } |
| scale_service | service, replicas | { ok, detail } |
| reset_connection_pool | service | { ok, detail } |

**Chaos (state-changing, gated, human-initiated only)**

| Tool | Input | Output `data` |
| --- | --- | --- |
| inject_crash | service | { experiment_id, ok } |
| inject_latency | service, latency_ms, duration_s | { experiment_id, ok } |
| inject_timeout | service, duration_s | { experiment_id, ok } |
| break_db_connection | service, duration_s | { experiment_id, ok } |
| clear_fault | experiment_id | { ok } |

## 7. Events (WebSocket and persistence)

```ts
interface SentinelEvent {
  event_id: string;
  ts: string;
  application_id: string;
  incident_id: string | null;
  actor: Actor;
  type: EventType;
  payload: Record<string, unknown>;
  policy_version: number | null;
}

type EventType = 'experiment_started' | 'experiment_ended' | 'service_health_changed'
  | 'incident_opened' | 'incident_status_changed' | 'agent_step' | 'proposal_created'
  | 'gateway_decision' | 'approval_requested' | 'approval_decided' | 'action_executed'
  | 'validation_completed' | 'postmortem_ready' | 'policy_changed';
```

Payload keys by type:

- `experiment_started` / `experiment_ended`: experiment_id, service, fault_type
- `service_health_changed`: service, from, to
- `incident_opened`: severity, trigger_service
- `incident_status_changed`: from, to
- `agent_step`: agent, summary, detail_ref
- `proposal_created`: ActionProposal
- `gateway_decision`: GatewayDecision
- `approval_requested` / `approval_decided`: approval_id, proposal_id, decision (when decided), decided_by
- `action_executed`: tool, result_ok, detail
- `validation_completed`: result (ValidationResult), metrics_before, metrics_after
- `postmortem_ready`: postmortem_id
- `policy_changed`: from_version, to_version, changed_by

Transport: `GET /ws/applications/{application_id}/events` (server to client only). A reconnecting client passes `?after_event_id=` to receive missed events. Every event is stored and replayable, including events with `incident_id = null` (experiment and health events). `gateway_decision` and `policy_changed` are additionally written to `audit_log`.

### 7.1 Publishing events (in-process)

All code inside the backend process publishes events through one function in `app/events.py`:

```python
publish(application_id: UUID, type: EventType, actor: Actor, payload: dict,
        incident_id: UUID | None = None, policy_version: int | None = None) -> SentinelEvent
```

Rules:

- The function is synchronous and safe to call from agent code. It assigns `event_id` and `ts`, checks `type` and that `payload` contains the keys listed above for that type, stores the event, and then pushes it to the WebSocket subscribers of that application.
- It returns the stored `SentinelEvent`. Agents use the returned `event_id` as an `evidence_refs` value.
- Storage comes first. If storing fails, `publish` raises `EventPublishError` and nothing is sent. A failed push to a WebSocket client never raises.
- Every event is stored and replayable through `?after_event_id=`, including events with `incident_id = null`. The backend adds an `application_id` column to the events table in Step 7, and the table note in section 9 is updated at that point (v0.3 entry).
- Until Step 7 ships, the agents workstream codes against `publish` and a fake one that keeps events in memory and returns a `SentinelEvent` with a real UUID.

## 8. REST API surface

All paths are prefixed `/api/v1`. Admin-only routes require an authenticated admin; approval decisions require the approver role.

- `POST /applications` (upload adapter), `GET /applications`, `GET /applications/{id}/map`, `GET /applications/{id}/experiments/available`
- `POST /experiments` (service, fault_type, parameters), `POST /experiments/{id}/clear`
- `GET /incidents`, `GET /incidents/{id}`, `GET /incidents/{id}/events`, `GET /incidents/{id}/postmortem`
- `GET /approvals?status=pending`, `POST /approvals/{id}/decision` (approver role)
- `GET /policies/current`, `GET /policies`, `POST /policies` (admin, creates a new version), `POST /policies/{version}/restore` (admin), `GET /policies/export`, `POST /policies/import` (admin)
- `POST /policy-test` (admin; agent, action, service; returns GatewayDecision; stored with dry_run true)
- `GET /audit` (filters: incident, actor, verdict, time range), `GET /metrics/summary`
- `POST /ingest/traces` (collector ingest, see 8.2)

### 8.1 Application endpoints

| Method and path | Request | Response | Notes |
| --- | --- | --- | --- |
| `POST /applications` | Raw adapter YAML (`Content-Type: application/x-yaml`) | `{ id, name, status, created_at, service_count }` | `status` is `connected` |
| `GET /applications/{id}/map` | none | `{ application_id, nodes: [{ name, type, critical, health_endpoint, health }], edges: [{ source, target, evidence }] }` | node `health` is `unknown` until health monitoring ships (Backend Step 7) |
| `GET /applications/{id}/experiments/available` | none | `{ application_id, experiments: [{ service, fault_type }] }` | |

### 8.2 Trace ingest

`POST /api/v1/ingest/traces` receives OTLP/JSON from the OpenTelemetry collector. It requires the header `X-Sentinel-App: <application name>`. It is unauthenticated in the MVP, so run it on localhost only.

### 8.3 Error shape and codes

Error shape for all non-2xx responses: `{ error: { code: string, message: string } }`.

| Error code | HTTP status | Description |
| --- | --- | --- |
| `application_not_found` | 404 | Target application does not exist |
| `application_exists` | 409 | Application already registered |
| `invalid_adapter` | 422 | Adapter YAML failed validation |
| `adapter_too_large` | 413 | Adapter payload exceeds size limit |
| `invalid_encoding` | 400 | Request body encoding is invalid |
| `validation_error` | 422 | General request validation error |
| `http_<status>` | `<status>` | Fallback format for other HTTP errors |

## 9. Database schema (PostgreSQL)

```sql
create table applications (id uuid primary key, name text unique not null, adapter jsonb not null, status text not null, created_at timestamptz not null default now());
create table services (id uuid primary key, application_id uuid references applications, name text not null, type text not null, critical boolean not null default false, health_endpoint text, unique (application_id, name));
create table dependencies (id uuid primary key, application_id uuid references applications, source text not null, target text not null, evidence text not null check (evidence in ('trace','declared')), unique (application_id, source, target));
create table trace_spans (application_id uuid references applications, trace_id text not null, span_id text not null, parent_span_id text, service text not null, name text not null, start_ts timestamptz not null, end_ts timestamptz not null, status text not null, primary key (application_id, trace_id, span_id));
create table experiments (id uuid primary key, application_id uuid references applications, service text not null, fault_type text not null, parameters jsonb not null default '{}', started_at timestamptz, ended_at timestamptz, initiated_by text not null);
create table incidents (id uuid primary key, application_id uuid references applications, status text not null, severity text not null, opened_at timestamptz not null, closed_at timestamptz, root_cause_summary text);
create table incident_events (id uuid primary key, incident_id uuid references incidents, ts timestamptz not null, actor text not null, type text not null, payload jsonb not null, policy_version int);
create table policies (version serial primary key, body jsonb not null, created_by text not null, created_at timestamptz not null default now());
create table approvals (id uuid primary key, incident_id uuid references incidents, proposal jsonb not null, requested_at timestamptz not null, decided_by text, decision text, decided_at timestamptz);
create table audit_log (id uuid primary key, ts timestamptz not null default now(), actor text not null, tool text, parameters jsonb, verdict text, reason_code text, reason text, policy_version int not null, dry_run boolean not null default false);
create table postmortems (id uuid primary key, incident_id uuid references incidents unique, summary text not null, timeline jsonb not null, recovery_metrics jsonb not null);
```

Notes:

- `trace_spans` is fed by the collector through the ingest endpoint and read by the `get_traces` tool. `parent_span_id` is nullable. `status` is one of `ok`, `error` or `unset`.
- `audit_log` and `policies` are append-only: no updates or deletes from application code.
- Planned for Backend Step 7 (v0.3 entry): an `application_id` column on the events table, so events without an incident (experiment and health events) can be stored and replayed.

## 10. Safety invariants (each must have an automated test)

1. Agents reach Recovery and Chaos MCP servers only through the gateway.
2. No tool exposes policy read or write to an agent.
3. A missing rule results in block.
4. A chaos call with `initiated_by_human = false` is blocked.
5. Tool output is passed to an LLM only as labeled data, never as instructions.
6. An approval that times out results in deny.
7. The audit record is written before the tool executes.
8. A protected resource is blocked regardless of matrix, override or approval.
9. Policy changes create a new version and an audit entry.

## 11. Changelog

- v0.2 (2026-11-26): agent drafts without IDs (section 3); gateway call interface (4.1); policy body vs. policy (5); health address forms (host-reachable tcp:// or http(s)://), container lookup and compose_project (2); trace edge upgrade rule (2); applications and ingest endpoints and error codes (8); trace_spans table (9); Diagnostics input formats and ownership (6); events.publish and replay of all events (7.1); integration milestones (12); schema and migration locations (0).
- v0.1 (2026-11-25): initial draft from design document v1.

## 12. Integration milestones

| # | Who | Ready when | Pass test |
| --- | --- | --- | --- |
| I1 | Frontend + Backend | Backend Steps 4, 6, 7 | The map shows live node health; the chaos panel offers only the experiments from `experiments/available`; starting and clearing an experiment works. |
| I2 | Agents + Backend | Backend Step 6; Diagnostics tools and Investigator done | Inject a crash. The Investigator returns a valid `RootCauseReport` from real container logs and `trace_spans`. |
| I3 | Agents + Backend + Frontend | Backend Step 7 (`events.publish`); the happy path works with a fake gateway | Crash, incident, Investigator, Impact, Recovery proposal, fake gateway, restart, Validator, every step emitted as a `SentinelEvent`. Then the frontend replaces its fake feed with the real WebSocket and the timeline fills live. |
| I4 | All | Backend Step 8 | I3 again with the real `gateway.submit`, plus blocked-action, approval and prompt-injection scenarios. |