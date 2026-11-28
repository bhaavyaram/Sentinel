# SENTINEL Contracts v0.3

Draft, November 27, 2026. This is the source of truth for every interface between workstreams (platform, backend, agents, gateway, frontend). If code and this document disagree, fix one of them the same day and log it in the changelog (section 11).

Status tags used in this document:

- **[live]**: implemented in the backend and verified on the developer machine.
- **[planned]**: agreed but not built yet. Code against the contract and a fake.
- **[proposed]**: a suggestion made while writing v0.3. The workstream that owns it must confirm it before anyone depends on it.

## 0. Conventions

- IDs are UUID v4 strings, except service names, which are slugs unique within an application.
- Timestamps are ISO 8601 UTC strings (for example `2026-11-26T19:28:51.289825Z`). Durations are integer milliseconds unless the field name ends in `_s` (seconds).
- Field names are snake_case everywhere (JSON, SQL, Python, and the TypeScript types, with no camelCase conversion).
- Enums are lowercase strings. An unknown enum value is rejected, never defaulted.
- Every audited record carries `policy_version`.
- All REST routes are under `/api/v1`. There is no authentication yet [live]; admin and approver roles arrive in Backend Step 8c.
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
type PolicyPreset = 'strict' | 'balanced' | 'permissive' | 'custom';
```

Tool to action mapping:

- `restart_service` maps to `restart`; `rollback_deployment` to `rollback`; `scale_service` to `scale`; `reset_connection_pool` to `reset_connection_pool`.
- `inject_crash`, `inject_latency`, `inject_timeout`, `break_db_connection` map to `inject_fault`; `clear_fault` maps to `clear_fault`.
- `modify_config` and `touch_database` have no tool yet. They stay in the policy matrix so any future tool is blocked by default.
- Executable form: `TOOL_ACTION_MAP` and `CHAOS_TOOLS` in `app/schemas/enums.py`.

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
    health: tcp://localhost:22001  # host-reachable tcp://host:port or http(s)://host:port/path; optional
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

- The loader rejects unknown fields and unknown fault types. [live]
- The dashboard offers an experiment only if the fault is listed for that service. [live]
- `container` is the docker compose service name. Docker names real containers like `online-boutique-cartservice-1`, so tools find the actual container through the `com.docker.compose.service` label, scoped by the optional `compose_project`.
- Health addresses are resolved from the machine running the SENTINEL backend (the Windows host), which cannot resolve Docker-internal DNS names. The adapter must therefore use host-reachable addresses: `tcp://localhost:<port>` or `http(s)://localhost:<port>/<path>`, using published ports. Required ports are published on `127.0.0.1` only. The probe rewrites `localhost` to `127.0.0.1` before connecting, because on Windows `localhost` tries IPv6 first and costs about a second per probe. [live]
- A health value that is a bare path (for example `/healthz`) is accepted by the loader but cannot be probed. Such a service counts as healthy while its container runs. [live]
- Container state from the Docker API (`running`, `exited`) is the primary down signal; HTTP and TCP probes confirm health.
- Faults other than `crash` are applied through Toxiproxy proxies. The proxy name must equal the adapter service `name`. [live]
- Dependency edges: edges from traces take priority. The `dependencies` table holds one row per `(source, target)` pair. When a trace confirms a declared edge, that row's `evidence` is upgraded from `declared` to `trace`. Declared edges are never deleted by traces.
- Trace coverage in Online Boutique: only 7 of the 11 services read a collector address (`checkout`, `currency`, `email`, `frontend`, `payment`, `productcatalog`, `recommendation`). `cartservice`, `shippingservice` and `adservice` do not send traces, so their edges come from `declared_dependencies`.
- Re-registering an application requires deleting its rows by hand, because there is no delete endpoint yet.
- Shipped adapters (repo folder `adapters/`): `online-boutique.yaml` (the real target) and `sample-shop.yaml` (a tiny test adapter). Do not register both: service names collide with the real shop's containers.

## 3. Agent action proposal

The Recovery agent (and any future agent that wants to act) emits an `ActionProposalDraft`: the `ActionProposal` fields without `proposal_id`, `incident_id` and `agent`. The orchestrator fills those three in (`draft.finalize(incident_id, agent)`), so the model never invents IDs. `evidence_refs` may only contain `incident_event` ids that were shown to the model in its prompt. Draft output that fails schema validation is retried once, then escalated to a human. The same rule applies to `RootCauseReport` and `ImpactReport`: the model returns everything except `incident_id`, which the orchestrator adds.

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

The draft models live in `app/schemas/agents.py`. [live]

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

Decision order, evaluated on every call [planned, Backend Step 8b]:

1. Chaos tools called with `initiated_by_human = false`: block (`chaos_requires_human`).
2. Target or action on the protected list: block (`protected_resource`). Nothing overrides this.
3. Look up the matrix for (caller, action). No rule: block (`no_rule`). See open decision Q2 for how human callers are handled.
4. Apply the service override for the target, if any. The override replaces the level for that service.
5. Compute blast radius from the dependency graph and a risk score.
6. If `risk_score` is at or above the threshold, or affected services or dependents exceed their limits, upgrade `allow` to `needs_approval` (`risk_threshold`). A block is never downgraded.
7. Write the audit record, then return the decision. The audit write must succeed before any tool executes.

Initial risk score formula (tunable in Phase 4): base by action (restart 10, scale 10, reset_connection_pool 15, rollback 30, inject_fault 20, other 40), plus 25 if the target is stateful, plus 25 if critical, plus 5 per affected service, capped at 100.

Only `allow` verdicts, or `needs_approval` verdicts with an `approved` decision, are forwarded to a tool. A dry run returns the decision and executes nothing.

### 4.0 Current state: placeholder gateway [live]

Until Backend Step 8b, `gateway.submit(request) -> GatewayDecision` in `app/gateway/placeholder.py` does only this:

- a chaos tool with `initiated_by_human = false`: block, `chaos_requires_human`;
- a chaos tool with `initiated_by_human = true`: allow, `allowed`;
- any other tool: block, `no_rule`;
- `risk_score` is 0, `blast_radius` holds only the target service, `approval_id` is null, `policy_version` is the constant 1;
- it writes the `audit_log` row before returning (actor, tool, parameters including `target_service`, verdict, reason code, reason, policy version, dry_run);
- it does not execute any tool. The experiments route applies the fault itself after an `allow`.

So any Recovery proposal sent to the placeholder is blocked with `no_rule`. Agent code uses a fake `submit` until 8b.

### 4.1 Calling the gateway

Agents run in the same Python process as the backend. All tool calls go through one function, `gateway.submit(request: GatewayRequest) -> GatewayDecision`, in `app/gateway/`. For `allow` (or an approved `needs_approval`), the gateway itself executes the tool and returns the result alongside the decision. Agents never call a tool server directly. The return type for the "result alongside the decision" case is open decision Q3.

Until the gateway step ships, the agents workstream codes against `GatewayDecision` and a fake `submit`.

### 4.2 Tool execution [proposed, Backend Step 8b]

- `app/gateway/tools.py` holds a registry: `register_tool(tool: str, handler)`, where `handler(request: GatewayRequest) -> dict` returns the tool's `data`.
- The gateway wraps the handler's return value as `{ data, untrusted: true }` and returns it with the decision.
- The agents workstream registers handlers for the Diagnostics and Recovery tools. The backend registers the Chaos handlers.
- Open decision Q4 covers whether these handlers are plain in-process functions or an MCP client.

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
- Saved policies are immutable. An edit creates a new version; a rollback (restore) creates a new version that copies an older one. [live]
- `on_timeout` can only be `deny`.
- Agents have no tool that reads or writes policy.
- `POST /policies` and `POST /policies/import` accept a `PolicyBody`. The server assigns `version`, `created_by` and `created_at`. All responses and the export return a full `Policy`.
- `POST /policies/import` also accepts a full exported `Policy`: it ignores `version`, `created_by` and `created_at` if present and still rejects every other unknown field, so an export can be imported again. [live]
- `created_by` is `admin` for every dashboard save until roles exist (8c), and `system` for the automatically created first policy.
- The first call to `GET /policies/current` on an empty store saves the Balanced preset as version 1. [live]

Built-in presets [live] (`app/policy/presets.py`). Only the `recovery` row is filled; every other agent has no entries and is therefore blocked by default. Every preset blocks `modify_config`, `touch_database`, `inject_fault` and `clear_fault` for agents, lists `modify_config` and `touch_database` as protected actions, and uses approver role `approver`, timeout 300 seconds, `on_timeout = deny`.

| Action (recovery agent) | strict | balanced | permissive |
| --- | --- | --- | --- |
| restart | needs_approval | allow | allow |
| scale | block | allow | allow |
| reset_connection_pool | needs_approval | allow | allow |
| rollback | block | needs_approval | allow |
| max_affected_services / max_dependents / approval_risk_score | 1 / 1 / 30 | 3 / 3 / 50 | 6 / 6 / 80 |

## 6. MCP tool catalog

Every tool result is wrapped as `{ data, untrusted: true }`. Log lines, trace attributes and error messages inside `data` are untrusted content and must never be placed in an instruction position of any prompt.

Input formats: `since` and `until` are ISO 8601 UTC timestamps. `limit` defaults to 50 and never exceeds 200.

Ownership: the agents workstream owns the Diagnostics and Recovery tools. The backend workstream owns the Chaos tools, the gateway, the audit log and the policy store.

Data sources:

- `query_logs` reads Docker container logs for the service, found through the compose label. Logs of an exited container remain readable.
- `get_traces` reads the `trace_spans` table. Services without traces (cartservice, shippingservice, adservice) return nothing.
- `get_service_status` reads the live health state (`app.monitoring.state.tracker`). `last_check` is not tracked yet; ask the backend workstream if it is needed.
- `get_dependencies` reads the `dependencies` table.
- `query_metrics`: source not yet settled, see open decision Q1.

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

Docker Compose has no rollout history or replicas. `rollback_deployment` and `scale_service` are therefore simulated: they return `ok: true` with a detail such as "simulated: compose has no rollout", and still pass through the gateway and the audit. [proposed]

**Chaos (state-changing, gated, human-initiated only)**

| Tool | Input | Output `data` |
| --- | --- | --- |
| inject_crash | service | { experiment_id, ok } |
| inject_latency | service, latency_ms, duration_s | { experiment_id, ok } |
| inject_timeout | service, duration_s | { experiment_id, ok } |
| break_db_connection | service, duration_s | { experiment_id, ok } |
| clear_fault | experiment_id | { ok } |

Today the experiments API calls these actions directly after an `allow` from the gateway. The tool names above are the names used in the gateway and the audit log [live].

How each fault is applied [live] (`app/chaos/`):

- `crash`: `docker kill` on the container found by compose label (it exits with code 137). Clearing runs `docker start`.
- `latency`: a Toxiproxy toxic of type `latency` (downstream, jitter 0, `latency` = `latency_ms`) on the service's proxy.
- `timeout`: a Toxiproxy toxic of type `timeout` with value 0 (connections are held open and no data is sent).
- `connection_failure`: the service's Toxiproxy proxy is disabled. Clearing re-enables it.
- Toxics are named `sentinel-<experiment_id>`. Toxiproxy rejects browser-like User-Agent headers, so every call sends a custom one.
- Known gap: health probes go directly to the service's host port and bypass Toxiproxy, so only `crash` changes the health state. Latency, timeout and connection faults are visible only in logs and traces.

The Chaos server is also gated, so that fault injection requires explicit user intent from the dashboard and agents cannot trigger it.

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

Required payload keys by type (`publish` rejects an event that lacks them; extra keys are allowed):

- `experiment_started` / `experiment_ended`: experiment_id, service, fault_type. An `experiment_ended` caused by `duration_s` expiring also carries `reason: "duration_expired"`.
- `service_health_changed`: service, from, to
- `incident_opened`: severity, trigger_service
- `incident_status_changed`: from, to
- `agent_step`: agent, summary, detail_ref
- `proposal_created`: proposal_id, action, target_service (the full ActionProposal is recommended)
- `gateway_decision`: request_id, verdict, reason_code (the full GatewayDecision is recommended)
- `approval_requested`: approval_id, proposal_id
- `approval_decided`: approval_id, proposal_id, decision, decided_by
- `action_executed`: tool, result_ok, detail
- `validation_completed`: result (ValidationResult), metrics_before, metrics_after
- `postmortem_ready`: postmortem_id
- `policy_changed`: from_version, to_version (from_version is null for the first policy), changed_by

Event catalog:

| Type | Actor | Published by | Status |
| --- | --- | --- | --- |
| experiment_started | human | experiments API | live |
| experiment_ended | human, or system when `duration_s` expires | experiments API and expiry worker | live |
| service_health_changed | system | health monitor | live |
| policy_changed | human (or system) | policy API, once per registered application | live |
| gateway_decision | the caller | gateway | planned (8b) |
| approval_requested / approval_decided | system / human | approvals | planned (8c) |
| incident_opened, incident_status_changed | monitor / system | incident lifecycle | planned |
| agent_step, proposal_created, action_executed, validation_completed | the agent | agents workstream | planned |
| postmortem_ready | system | postmortem generator | planned |

Transport [live]: `GET /api/v1/ws/applications/{application_id}/events` (server to client only; the path includes the `/api/v1` prefix).

- Each message is one JSON `SentinelEvent`. The server never expects messages from the client.
- Without `after_event_id`, the stream carries live events only.
- With `?after_event_id=<event_id>`, the server first sends every stored event of that application that came after it, in storage order, then continues live without duplicates.
- A reconnecting client remembers the last `event_id` it processed and passes it. Clients should still ignore an `event_id` they have already seen.
- An unknown application or an unknown `after_event_id` closes the socket with code `4404`.
- No authentication yet.
- Every event is stored and replayable, including events with `incident_id = null` (experiment, health and policy events). `gateway_decision` and `policy_changed` are additionally written to `audit_log`.
- Events carry no sequence number. The server orders replay by a private `seq` column.

### 7.1 Publishing events (in-process) [live]

All code inside the backend process publishes events through one function in `app/events.py`:

```python
publish(application_id: UUID, type: EventType, actor: Actor, payload: dict,
        incident_id: UUID | None = None, policy_version: int | None = None) -> SentinelEvent
```

Rules:

- The function is synchronous and safe to call from agent code. It assigns `event_id` and `ts`, checks `type` and that `payload` contains the keys listed above for that type, stores the event, and then pushes it to the WebSocket subscribers of that application.
- It returns the stored `SentinelEvent`. Agents use the returned `event_id` as an `evidence_refs` value.
- Storage comes first. If storing or validating fails, `publish` raises `EventPublishError` and nothing is sent. A failed push to a WebSocket client never raises.
- Payload values are converted through JSON (UUIDs, datetimes and enums become strings) before storage.
- The in-memory fan-out (`app/event_hub.py`) delivers to async WebSocket handlers. Synchronous agent code that wants to read events reads storage instead: `app.repository.events.list_after(application_id, after_seq, limit)` returns `(seq, SentinelEvent)` pairs.

## 8. REST API surface

All paths are prefixed `/api/v1`. Admin-only routes will require an authenticated admin and approval decisions will require the approver role (8c). Today every route is open.

Live:

- `POST /applications` (upload adapter), `GET /applications`, `GET /applications/{id}/map`, `GET /applications/{id}/experiments/available`
- `POST /experiments`, `POST /experiments/{id}/clear`
- `GET /policies/current`, `GET /policies`, `POST /policies`, `POST /policies/{version}/restore`, `GET /policies/export`, `POST /policies/import`
- `POST /ingest/traces`
- WebSocket `/ws/applications/{id}/events` (section 7)
- a health route in `app/api/health.py`

Planned:

- `GET /experiments?application_id=&active=true` [proposed, see Q5]
- `GET /incidents`, `GET /incidents/{id}`, `GET /incidents/{id}/events`, `GET /incidents/{id}/postmortem`
- `GET /approvals?status=pending`, `POST /approvals/{id}/decision` (approver role)
- `POST /policy-test` (admin; agent, action, service; returns GatewayDecision; stored with dry_run true)
- `GET /audit` (filters: incident, actor, verdict, time range), `GET /metrics/summary`

### 8.1 Application endpoints [live]

| Method and path | Request | Response | Notes |
| --- | --- | --- | --- |
| `POST /applications` | Raw adapter YAML (`Content-Type: application/x-yaml`) | `{ id, name, status, created_at, service_count }` | `status` is `connected`; HTTP 201 |
| `GET /applications` | none | `ApplicationSummary[]` | |
| `GET /applications/{id}/map` | none | `{ application_id, nodes: [{ name, type, critical, health_endpoint, health }], edges: [{ source, target, evidence }] }` | node `health` is live (see below) |
| `GET /applications/{id}/experiments/available` | none | `{ application_id, experiments: [{ service, fault_type }] }` | |

The application `id` is generated at registration and changes if the application is deleted and registered again. Clients must read it from `GET /applications`, never hardcode it.

Map `health` is produced by the health monitor (`app/monitoring/`), which sweeps every 3 seconds:

- A container that is not running (`exited`, `dead`, `created`, `paused`) is `down`. It is reported immediately and is not probed.
- A container that is `restarting` is `degraded`.
- A running container whose probe passes, or which has no probe address, is `healthy`.
- A running container whose probe fails is `degraded`, but only after 2 consecutive failures, so a single slow probe does not create an event.
- A service with no matching container is `unknown`.
- After a backend restart every service is `unknown` for about 3 seconds, until the first sweep.
- `service_health_changed` events are published on changes only. A service first seen as `healthy` produces no event; first seen in any other state produces `unknown -> <state>`.

### 8.2 Trace ingest [live]

`POST /api/v1/ingest/traces` receives OTLP/JSON from the OpenTelemetry collector. It requires the header `X-Sentinel-App: <application name>`. It is unauthenticated in the MVP, so run it on localhost only.

### 8.3 Error shape and codes

Error shape for all non-2xx responses: `{ error: { code: string, message: string } }`.

| Error code | HTTP status | Description |
| --- | --- | --- |
| `application_not_found` | 404 | Target application does not exist |
| `application_exists` | 409 | Application already registered |
| `invalid_adapter` | 422 | Adapter YAML failed validation |
| `adapter_too_large` | 413 | Adapter payload exceeds size limit (1 MB) |
| `invalid_encoding` | 400 | Request body encoding is invalid |
| `validation_error` | 422 | General request validation error (also: unknown service or bad parameter in an experiment request) |
| `fault_not_available` | 422 | The adapter does not list this fault for this service |
| `experiment_not_found` | 404 | No experiment with that id |
| `experiment_already_cleared` | 409 | The experiment was already cleared |
| `action_blocked` | 403 | The gateway did not allow the action; `message` is the gateway's reason |
| `chaos_failed` | 502 | Docker or Toxiproxy could not apply or revert the fault |
| `policy_not_found` | 404 | No policy with that version |
| `invalid_policy` | 422 | Imported policy failed validation |
| `invalid_json` | 400 | Request body is not valid JSON |
| `http_<status>` | `<status>` | Fallback format for other HTTP errors |

### 8.4 Experiments [live]

```ts
interface ExperimentCreate {
  application_id: string;
  service: string;
  fault_type: FaultType;
  parameters: Record<string, string | number | boolean>;
}
interface ExperimentRecord {
  id: string;
  application_id: string;
  service: string;
  fault_type: FaultType;
  parameters: Record<string, string | number | boolean>;
  started_at: string | null;
  ended_at: string | null;      // null while the experiment is active
  initiated_by: string;         // 'dashboard'
}
```

| Method and path | Request | Response | Errors |
| --- | --- | --- | --- |
| `POST /experiments` | `ExperimentCreate` | 201 `ExperimentRecord` | 404 `application_not_found`, 422 `validation_error`, 422 `fault_not_available`, 403 `action_blocked`, 502 `chaos_failed` |
| `POST /experiments/{id}/clear` | none | 200 `ExperimentRecord` with `ended_at` set | 404 `experiment_not_found`, 409 `experiment_already_cleared`, 403 `action_blocked`, 502 `chaos_failed` |

Parameters: `latency_ms` (positive integer, latency only, default 1000) and `duration_s` (optional positive integer, any fault). The server stores only these two keys and ignores any other. When `duration_s` is set, a background worker clears the experiment automatically once `started_at + duration_s` has passed.

Automatic clearing goes through the gateway as caller `system` with `initiated_by_human = true` and the parameter `reason = "duration_expired"`: the person who started the experiment asked for that duration, so expiry completes the original request. It publishes `experiment_ended` with `actor = system`. If a clear fails, the worker retries after 30 seconds.

Each start or clear writes one `audit_log` row (actor `human` or `system`, tool `inject_*` or `clear_fault`) and one event.

### 8.5 Policy endpoints [live]

| Method and path | Request | Response | Errors |
| --- | --- | --- | --- |
| `GET /policies/current` | none | `Policy` | |
| `GET /policies` | none | `Policy[]`, newest first | |
| `POST /policies` | `PolicyBody` | 201 `Policy` (new version) | 422 `validation_error` |
| `POST /policies/{version}/restore` | none | 201 `Policy` (new version copying `{version}`) | 404 `policy_not_found` |
| `GET /policies/export` | none | `Policy` (the current one) | |
| `POST /policies/import` | JSON object (`PolicyBody`, or an exported `Policy`) | 201 `Policy` | 400 `invalid_json`, 422 `invalid_policy` |

Every save inserts one `policies` row and one `audit_log` row in the same transaction (`tool = 'policy_change'`, `verdict` null, `reason` like "Policy version 4 saved (edit)", `parameters` with from_version, to_version, name, preset, source = edit | restore | import | seed, and restored_from for restores). After the commit, a `policy_changed` event is published once for every registered application.

### 8.6 Incident lifecycle (in-process) [proposed, Backend Step 9]

The backend provides these functions in `app/repository/incidents.py` for the orchestrator. Each one stores the change and publishes the matching event itself, so agents do not publish `incident_opened` or `incident_status_changed` by hand:

```python
def open_incident(application_id: UUID, severity: Severity, trigger_service: str) -> UUID
def set_status(incident_id: UUID, status: IncidentStatus) -> None
def close_incident(incident_id: UUID, status: IncidentStatus,  # resolved or failed
                   root_cause_summary: str | None) -> None
```

Until Step 9 ships, the agents workstream codes against a fake with the same signatures.

## 9. Database schema (PostgreSQL)

```sql
create table applications (id uuid primary key, name text unique not null, adapter jsonb not null, status text not null, created_at timestamptz not null default now());
create table services (id uuid primary key, application_id uuid references applications, name text not null, type text not null, critical boolean not null default false, health_endpoint text, unique (application_id, name));
create table dependencies (id uuid primary key, application_id uuid references applications, source text not null, target text not null, evidence text not null check (evidence in ('trace','declared')), unique (application_id, source, target));
create table trace_spans (application_id uuid references applications, trace_id text not null, span_id text not null, parent_span_id text, service text not null, name text not null, start_ts timestamptz not null, end_ts timestamptz not null, status text not null, primary key (application_id, trace_id, span_id));
create table experiments (id uuid primary key, application_id uuid references applications, service text not null, fault_type text not null, parameters jsonb not null default '{}', started_at timestamptz, ended_at timestamptz, initiated_by text not null);
create table incidents (id uuid primary key, application_id uuid references applications, status text not null, severity text not null, opened_at timestamptz not null, closed_at timestamptz, root_cause_summary text);
create table incident_events (id uuid primary key, incident_id uuid references incidents, application_id uuid not null references applications, ts timestamptz not null, actor text not null, type text not null, payload jsonb not null, policy_version int, seq bigint generated always as identity);
create unique index incident_events_seq_idx on incident_events (seq);
create index incident_events_app_seq_idx on incident_events (application_id, seq);
create table policies (version serial primary key, body jsonb not null, created_by text not null, created_at timestamptz not null default now());
create table approvals (id uuid primary key, incident_id uuid references incidents, proposal jsonb not null, requested_at timestamptz not null, decided_by text, decision text, decided_at timestamptz);
create table audit_log (id uuid primary key, ts timestamptz not null default now(), actor text not null, tool text, parameters jsonb, verdict text, reason_code text, reason text, policy_version int not null, dry_run boolean not null default false);
create table postmortems (id uuid primary key, incident_id uuid references incidents unique, summary text not null, timeline jsonb not null, recovery_metrics jsonb not null);
```

Notes:

- Migrations: `0001` (this schema except `trace_spans`, plus append-only triggers on `audit_log` and `policies`), `0002` (`trace_spans`), `0003` (`application_id` and `seq` on `incident_events`). They are written by hand: the project has no `script.py.mako`, so `alembic revision` fails. Create each new migration file manually with `revision` and `down_revision` set.
- `trace_spans` is fed by the collector through the ingest endpoint and read by the `get_traces` tool. `parent_span_id` is nullable. `status` is one of `ok`, `error` or `unset`.
- `audit_log` and `policies` are append-only: no updates or deletes from application code, and database triggers enforce it.
- `incident_events` stores every event, including events without an incident. `seq` is server-only, used to order replay, and is not part of `SentinelEvent`.
- Policy audit rows have `verdict` and `reason_code` null; the details are in `parameters`.
- `experiments` rows are kept after clearing (`ended_at` is set).

## 10. Safety invariants (each must have an automated test)

1. Agents reach Recovery and Chaos tools only through the gateway.
2. No tool exposes policy read or write to an agent.
3. A missing rule results in block.
4. A chaos call with `initiated_by_human = false` is blocked.
5. Tool output is passed to an LLM only as labeled data, never as instructions.
6. An approval that times out results in deny.
7. The audit record is written before the tool executes.
8. A protected resource is blocked regardless of matrix, override or approval.
9. Policy changes create a new version and an audit entry.

Where each stands today:

| # | Enforced today | Automated test |
| --- | --- | --- |
| 1 | The experiments route calls the gateway. No agent tools exist yet. | planned (8b, I4) |
| 2 | By construction: no policy tool exists. | planned (8b) |
| 3 | Placeholder only | yes (`test_gateway_placeholder.py`); engine version in 8b |
| 4 | Placeholder | yes (`test_gateway_placeholder.py`) |
| 5 | Not yet | planned (agents) |
| 6 | Policy schema allows only `deny`; the approval flow does not exist yet. | planned (8c) |
| 7 | Yes for chaos: the audit row is written before the fault is applied. | planned (8b) |
| 8 | The protected list is stored in the policy; the engine does not read it yet. | planned (8b) |
| 9 | Yes (verified by hand; database triggers block updates) | planned (8b) |

## 11. Changelog

- v0.3 (2026-11-27), covering Backend Steps 6, 7a, 7b and 8a:
  - Experiments API: `ExperimentCreate` includes `application_id`; `ExperimentRecord`; parameters (`latency_ms`, `duration_s`); how each fault is applied; new error codes `fault_not_available`, `experiment_not_found`, `experiment_already_cleared`, `action_blocked`, `chaos_failed` (8.3, 8.4, 6).
  - `duration_s` is enforced by a background worker; the auto-clear goes through the gateway as `system` with `initiated_by_human = true` and `reason = duration_expired`; the `experiment_ended` event carries `reason` (8.4, 7).
  - Placeholder gateway documented (4.0); tool registry and incident lifecycle interfaces proposed (4.2, 8.6).
  - Events: WebSocket path is `/api/v1/ws/applications/{id}/events`; close code 4404; replay by `after_event_id` and storage order; `publish` implemented with required payload keys; event catalog with status (7, 7.1).
  - `incident_events` gained `application_id` (not null) and a server-only `seq`; migration 0003; migrations are hand-written (9).
  - Health monitor: live map health, debounce rule, parallel probes, IPv4 loopback probing, health events with `actor = system` (8.1, 2).
  - Policy API implemented with presets, restore, export and import; import also accepts an exported `Policy`; `policy_changed` published once per application; policy saves are audited; new error codes `policy_not_found`, `invalid_policy`, `invalid_json` (5, 8.5, 8.3).
  - Adapter notes: bare-path health, proxy names, shipped adapters, re-registration (2).
  - Known gap documented: Toxiproxy faults do not change health (6).
  - Added sections 13 (runtime facts) and 14 (open decisions); status tags and invariant status table (10).
- v0.2 (2026-11-26): agent drafts without IDs (section 3); gateway call interface (4.1); policy body vs. policy (5); health address forms (host-reachable tcp:// or http(s)://), container lookup and compose_project (2); trace edge upgrade rule (2); applications and ingest endpoints and error codes (8); trace_spans table (9); Diagnostics input formats and ownership (6); events.publish and replay of all events (7.1); integration milestones (12); schema and migration locations (0).
- v0.1 (2026-11-25): initial draft from design document v1.

## 12. Integration milestones

| # | Who | Ready when | Pass test | Status |
| --- | --- | --- | --- | --- |
| I1 | Frontend + Backend | Backend Steps 4, 6, 7 | The map shows live node health; the chaos panel offers only the experiments from `experiments/available`; starting and clearing an experiment works. | Backend side ready. Reloading the page loses active experiments until `GET /experiments` exists (Q5). |
| I2 | Agents + Backend | Backend Step 6; Diagnostics tools and Investigator done | Inject a crash. The Investigator returns a valid `RootCauseReport` from real container logs and `trace_spans`. | Backend side ready. Needs decision Q1 for `query_metrics`. |
| I3 | Agents + Backend + Frontend | Backend Step 7 (`events.publish`); the happy path works with a fake gateway | Crash, incident, Investigator, Impact, Recovery proposal, fake gateway, restart, Validator, every step emitted as a `SentinelEvent`. Then the frontend replaces its fake feed with the real WebSocket and the timeline fills live. | Backend side ready (`publish` and the WebSocket are live). Incident functions are faked until Step 9. |
| I4 | All | Backend Step 8 | I3 again with the real `gateway.submit`, plus blocked-action, approval and prompt-injection scenarios. | Waiting for 8b and 8c. |

## 13. Runtime facts

Repository layout (`C:\Users\ADMIN\Documents\SENTINEL`, branch `main`): `docker-compose.yml` and `.env` at the root (`.env` is not committed); `adapters/`; `target-apps/online-boutique/` (its own compose project); `backend/` with `app/`, `alembic/`, `tests/`, `scripts/` and `requirements.txt`.

Ports:

| Port | What |
| --- | --- |
| 5432 | PostgreSQL (container `sentinel-postgres`, user, password and database all `sentinel`, development only) |
| 8000 | SENTINEL backend (uvicorn) |
| 5173 | Frontend dev server (the only origin allowed by CORS, `CORS_ORIGINS` in `.env`) |
| 8081 | The shop in a browser (enters through the Toxiproxy proxy `frontend`) |
| 8474 | Toxiproxy API (127.0.0.1) |
| 22000 to 22010 | Direct host ports (127.0.0.1) used for probes: 22000 frontend (http, `/_healthz`), 22001 cartservice, 22002 productcatalogservice, 22003 currencyservice, 22004 paymentservice, 22005 shippingservice, 22006 emailservice, 22007 checkoutservice, 22008 recommendationservice, 22009 adservice, 22010 redis-cart |
| 21000 to 21010 | Toxiproxy proxy ports inside the Docker network (services call `toxiproxy:<port>`; 21010 is redis) |

Starting everything (details in the Development Instructions): Docker Desktop running; `docker compose up -d` at the repo root (Postgres) and in `target-apps\online-boutique` (the shop); then `uvicorn app.main:app --reload --port 8000` from `backend` with the venv active. The collector sends spans to the backend through `host.docker.internal:8000`.

Backend conventions: synchronous SQLAlchemy 2 with psycopg 3 and raw SQL through `text()` (no ORM models); one repository module per area in `app/repository`; routers in `app/api`; errors raised as `AppError(status, code, message)`. Do not use async psycopg: it fails on the Windows default event loop.

Background workers (health monitor, experiment expiry) start in the FastAPI lifespan through `app/workers.py` (`PeriodicWorker`) and are switched off by the setting `BACKGROUND_WORKERS=false` (the test suite sets it). Any new worker should respect the same setting.

Tests: `pytest` from `backend` with the venv active. 70 tests pass after Step 8a.

## 14. Open decisions

- **Q1. `query_metrics` source.** [proposed] Derive points from `trace_spans`, per 10-second bucket: `span_count`, `error_count`, `error_rate`, `p95_latency_ms`. Services without traces return empty series, and the Investigator must handle that. Owner: agents.
- **Q2. Human callers and the permission matrix.** The matrix is keyed by agent role, so a human-initiated chaos call has no row and would hit `no_rule`. Recommendation: human-initiated chaos skips the matrix (step 3) but still goes through steps 2, 5, 6 and 7. Decide in Backend Step 8b.
- **Q3. Return type of `submit`.** [proposed] A wrapper `GatewayOutcome { decision: GatewayDecision, tool_result: { data, untrusted } | null }`. The alternative is an optional field on `GatewayDecision`. Decide before 8b; the agents fake should use the same shape.
- **Q4. How the gateway reaches tools.** An in-process handler registry (4.2), or an MCP client talking to separate MCP servers. The registry is simpler for the MVP. Owners: backend and agents, in 8b.
- **Q5. `GET /experiments?application_id=&active=true`.** [proposed] Needed by the dashboard to show and clear experiments that are active after a reload. Small; suggested before 8b.
- **Q6. Approval resume.** How a paused workflow continues after a decision (an LangGraph interrupt plus a gateway call such as "execute approved"). Defined in Backend Step 8c.
- **Q7. Experiments after agent recovery.** When an agent restarts a crashed service, the experiment record stays active until a human clears it or `duration_s` expires (clearing a crash is safe because starting a running container does nothing). Decide later whether the backend closes the experiment automatically when the service recovers.
- **Q8. Health blind spot.** Toxiproxy faults do not change health. A second probe through the proxy would need a new optional adapter field. Deferred.
- **Q9. Roles.** How admin and approver are identified (Step 8c).
- **Q10. Agents infrastructure.** LLM provider and model (Groq or compatible), LangGraph checkpointing (an in-memory saver is enough unless a paused approval must survive a restart), and whether to merge Investigator and Impact. Owner: agents.
- **Q11. Adapter loader warning.** Warn when a health address host is not `localhost` or `127.0.0.1`. Low priority.