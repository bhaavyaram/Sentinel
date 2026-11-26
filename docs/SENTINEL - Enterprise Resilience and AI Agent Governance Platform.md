# SENTINEL – Enterprise Resilience & AI Agent Governance Platform
 
Design document · Draft v1 · November 25, 2026
 
## 1. Overview
 
SENTINEL is a platform that does two things together: it **rehearses failures** in connected applications through controlled chaos experiments, and it **governs the AI agents** that detect, investigate and fix those failures, so they act only within human-defined limits.
 
Core idea: test how resilient an application is to failure, while proving that the AI agents responding to that failure operate safely, responsibly and within defined permissions.
 
## 2. Problem Statement
 
Modern enterprises depend on many interconnected services. When one fails, the result can be downtime, data inconsistency and business disruption.
 
AI agents can speed up detection, investigation and recovery, but they introduce a new risk: they may take incorrect, risky or unauthorized actions (restarting a database, rolling back every service, acting on instructions hidden in a log line) without proper control.
 
There is no single place where a team can (a) safely test how its systems behave under failure and (b) ensure AI responders cannot exceed their authority while doing so.
 
## 3. Proposed Solution
 
SENTINEL connects to an application, discovers its service architecture, lets users inject controlled failures, and uses AI agents to investigate and resolve the resulting incidents. Every action an agent attempts passes through a deterministic Guardrail Engine that allows it, blocks it, or sends it to a human for approval. Every step is recorded in an audit trail and summarized in a postmortem.
 
### 3.1 Module A – Failure Rehearsal
 
- Connects to an application through a small adapter and discovers services and dependencies.
 
- Builds an interactive service architecture map.
 
- Offers only the failure experiments that are relevant to the connected application.
 
- Injects controlled faults: service crash, latency spike, API timeout, database connection failure.
 
- Shows affected services, incident timeline, recovery time and system health in real time.
 
### 3.2 Module B – AI Agent Guardrails and Governance
 
- Specialized agents handle detection, investigation, impact analysis, recovery and validation.
 
- A central Guardrail Engine enforces per-agent permissions, blocks destructive operations, evaluates risk and blast radius, requests human approval for high-risk actions, and maintains the audit trail.
 
- Guardrail policy is created and edited entirely from the dashboard.
 
### 3.3 End-to-end workflow
 
1. An application is connected to SENTINEL through its adapter.
 
2. SENTINEL discovers architecture and capabilities and draws the service map.
 
3. The user selects a service and injects a fault.
 
4. The Monitor detects the anomaly and opens an incident.
 
5. The Investigator analyzes logs, metrics and traces to find a probable root cause.
 
6. Impact Analysis computes affected services and the blast radius of candidate fixes.
 
7. The Recovery Agent proposes an action.
 
8. The Guardrail Engine returns allow, block, or needs approval.
 
9. If allowed (or approved by a human), the action runs through an MCP recovery tool.
 
10. The Validator confirms recovery using health checks and metric comparison.
 
11. SENTINEL shows the full incident timeline and generates a postmortem.
 
## 4. Goals and Non-Goals
 
**Goals**
 
- Demonstrate realistic failure rehearsal on a real multi-service application.
 
- Show multi-agent investigation and recovery with visible reasoning.
 
- Make agent safety enforceable, configurable from the UI, and auditable.
 
- Produce measurable results (recovery time, unsafe actions blocked).
 
**Non-goals (for the first version)**
 
- Supporting arbitrary applications with zero configuration.
 
- Production-grade multi-tenancy, SSO or compliance certification.
 
- Kubernetes-native discovery, Prometheus/Grafana integration, advanced OPA policies (listed as stretch goals).
 
## 5. Architecture Decision Log
 
Each decision lists what was chosen, why, and what was rejected.
 
**D1. Support one real target application first, behind an adapter interface.** Generic “connect to anything” discovery is a hard problem. The MVP targets one open-source microservices application (for example Google’s Online Boutique or a docker-compose demo app). A small adapter format keeps the platform generic, so a second application needs only a new adapter, not platform changes. Rejected: building discovery for arbitrary applications up front.
 
**D2. Platform owns generic fault types; adapters declare which apply.** Faults act at the infrastructure and network level (container stop, network delay or drop via a proxy such as Toxiproxy, database connection break), so they work on any application. Each adapter declares its services, health endpoints, stateful or stateless type, and the faults that make sense for each service. The dashboard shows only those experiments. Rejected: hardcoding chaos experiments per application.
 
**D3. Service discovery from real signals.** Services come from Docker/compose metadata and the declared adapter; dependency edges come from OpenTelemetry distributed traces. Rejected: manually drawn maps (not credible) and LLM-guessed architecture (unreliable).
 
**D4. Five agent roles, but only two truly need an LLM.**
 
| Role | Implementation | Reason |
| --- | --- | --- |
| Monitor | Deterministic rules (health checks, thresholds) | Faster and more reliable than an LLM |
| Investigator | LLM agent | Real reasoning over logs, metrics, traces |
| Impact Analysis | Graph traversal plus LLM summary | The dependency graph already answers who is affected |
| Recovery | LLM agent | Chooses and proposes actions |
| Validator | Health checks and metric comparison plus LLM summary | Verification should be objective |
 
This keeps the five-agent story while reducing latency, cost, flakiness and LLM rate-limit exposure. Merging Investigator and Impact Analysis into one agent is an acceptable simplification if time is short.
 
**D5. The Guardrail Engine is deterministic code, not an LLM.** If an LLM judged safety, an agent could be persuaded to bypass it. The engine evaluates structured rules and live facts, and returns a verdict. Rejected: LLM-as-judge for permission decisions (it may still be used to *explain* a verdict in plain language).
 
**D6. Guardrails sit at the tool boundary as a gateway in front of MCP servers.** All agent tool calls go through one choke point, so no agent can reach a recovery or chaos tool without being checked. This is also where audit records are written.
 
**D7. Use MCP for tool access.** MCP is not strictly required, but it gives a standard interface, swappable tools per adapter, and a natural single point for the gateway. Three MCP servers: Diagnostics (read-only), Recovery (state-changing), Chaos (fault injection). Policy checks are strict on Recovery and Chaos; Diagnostics is low-risk and read-only.
 
**D8. Guardrail policy is set from the UI alone.** An admin edits policy through the dashboard; it is stored as structured JSON in PostgreSQL; the engine reads it on every call so changes apply immediately without redeploying. Every policy change is audit-logged. Import/export of policy as JSON supports version control and resetting demos.
 
**D9. Deny by default.** An action with no matching allow rule is blocked. A missing rule never means permission.
 
**D10. Human approval uses LangGraph interrupts.** High-risk actions pause the workflow until an approver responds. If nobody responds before the timeout, the default outcome is deny.
 
**D11. Real-time dashboard via WebSockets; PostgreSQL as the single source of truth.** Redis is optional and used only if pub/sub or caching is actually needed. Rejected: adding Redis by default.
 
**D12. Deterministic demo scenarios.** LLM behavior is not perfectly repeatable, so 3 to 4 seeded scenarios are tested end to end, with a recorded fallback run in case an LLM API is slow or rate-limited during a presentation.
 
## 6. System Architecture
 
### 6.1 Layers
 
Dashboard (React + TypeScript + Tailwind, React Flow, Recharts)
        |  REST + WebSocket
Backend API (FastAPI)
        |
Orchestration (LangGraph: Monitor -> Investigator -> Impact -> Recovery -> Validator)
        |  all tool calls
Guardrail Gateway (policy engine, risk scoring, approvals, audit)
        |
MCP servers: Diagnostics | Recovery | Chaos
        |
Target application (Docker) + OpenTelemetry collector + fault proxy
 
PostgreSQL: apps, services, policies, incidents, audit
 
### 6.2 Components
 
- **Dashboard:** service map (React Flow), chaos control panel, live incident timeline, agent workflow view, charts (Recharts), policy editor, approval inbox, postmortem viewer.
 
- **Backend API (FastAPI):** application registry, adapter loading, experiment control, incident and policy CRUD, WebSocket event stream.
 
- **Orchestrator (LangGraph):** runs the incident workflow as a graph, holds state, and supports pause and resume for approvals.
 
- **Guardrail Gateway:** the only path from agents to tools.
 
- **MCP servers:** expose tools to agents through a standard protocol.
 
- **Telemetry:** OpenTelemetry collects logs, metrics and traces from the target application.
 
- **Target application:** an open-source microservices demo running in Docker, fronted by a fault-injection proxy.
 
## 7. Application Adapter
 
An adapter is a small declarative file that describes one application to SENTINEL.
 
app: online-boutique
services:
  - name: cartservice
    type: stateless
    critical: false
    health: /healthz
    faults: [crash, latency]
  - name: redis-cart
    type: stateful
    critical: true
    faults: [connection_failure]
 
SENTINEL reads the adapter, combines it with discovered traces, builds the map, and shows only the experiments that apply. The MVP ships one real adapter; a second tiny one is an optional proof of generality.
 
## 8. Agents
 
- **Monitor Agent:** polls health checks and metrics against thresholds, opens an incident and publishes the first event.
 
- **Investigator Agent (LLM):** queries logs, metrics and traces through Diagnostics tools, forms hypotheses, tests them against data, and reports a ranked root cause with evidence.
 
- **Impact Analysis Agent:** traverses the dependency graph to list affected services and computes the blast radius of each candidate fix; an LLM writes the summary.
 
- **Recovery Agent (LLM):** proposes one or more actions (restart, rollback, scale, reroute) and requests them through the gateway.
 
- **Validator Agent:** re-runs health checks, compares metrics before and after, and declares recovered, partially recovered or failed; an LLM writes the summary.
 
Agent outputs must be structured (for example JSON with fields for action, target, rationale) so the gateway can evaluate them without parsing free text.
 
## 9. Guardrail Engine
 
### 9.1 Responsibilities
 
- Enforce per-agent permissions.
 
- Block unauthorized or destructive operations.
 
- Evaluate risk and blast radius.
 
- Request human approval for high-risk operations.
 
- Maintain an audit trail of every decision and action.
 
### 9.2 Policy model (all editable in the UI)
 
- **Permission matrix:** agents by action types (restart, rollback, scale, modify config, touch database, inject fault), each set to Allow, Needs approval, or Block.
 
- **Service rules:** per service tags (stateful, critical) and overrides, for example payment service: everything needs approval.
 
- **Risk thresholds:** require approval if an action affects more than N services or a service with more than N dependents.
 
- **Protected resources:** hard blocks that no other rule can override.
 
- **Approval settings:** approver role, timeout, default-deny on timeout.
 
- **Presets:** Strict, Balanced, Permissive as starting points.
 
### 9.3 Decision logic (evaluated on every tool call)
 
1. Identify the calling agent, action, target service and parameters.
 
2. If the target or action is on the protected list, **block**.
 
3. Look up the permission matrix for this agent and action; if no rule exists, **block**.
 
4. Apply any service-specific override.
 
5. Compute blast radius from the dependency graph and a risk score from service tags.
 
6. If risk exceeds the threshold, upgrade the verdict to **needs approval**.
 
7. Return the verdict with a plain-language reason; write the audit record.
 
### 9.4 Safeguards for the guardrails themselves
 
- Agents have no tool that can read or modify policy.
 
- The policy editor requires an authenticated admin.
 
- Policy changes are versioned and auditable, with rollback.
 
- Tool outputs (logs, traces) are treated as untrusted data, never as instructions. This is the defense against prompt injection planted in logs.
 
### 9.5 Policy test panel
 
A dashboard panel lets an admin pick an agent, action and service and see the verdict and reasoning without executing anything. It supports policy debugging and live demos.
 
## 10. MCP Tool Catalog
 
| Server | Tools | Risk |
| --- | --- | --- |
| Diagnostics | query_logs, query_metrics, get_traces, get_service_status, get_dependencies | Read-only, low |
| Recovery | restart_service, rollback_deployment, scale_service, reset_connection_pool | State-changing, gated |
| Chaos | inject_crash, inject_latency, inject_timeout, break_db_connection, clear_fault | State-changing, gated |
 
The Chaos server is also gated, so that fault injection requires explicit user intent from the dashboard and agents cannot trigger it.
 
## 11. Data Model (PostgreSQL)
 
- **applications:** id, name, adapter reference, status.
 
- **services:** id, application, name, type, critical flag, health endpoint.
 
- **dependencies:** source service, target service, source of evidence (trace or declared).
 
- **experiments:** id, service, fault type, parameters, started and ended times, initiated by.
 
- **incidents:** id, application, status, severity, opened and closed times, root cause summary.
 
- **incident_events:** incident, timestamp, actor (agent or human), event type, payload.
 
- **policies:** version, matrix, service rules, thresholds, protected list, created by, created at.
 
- **approvals:** id, incident, proposed action, requested at, decided by, decision, decided at.
 
- **audit_log:** timestamp, actor, tool, parameters, verdict, reason, policy version.
 
- **postmortems:** incident, generated summary, timeline, recovery metrics.
 
## 12. Technology Stack
 
**Core**
 
| Technology | Purpose |
| --- | --- |
| React, TypeScript, Tailwind CSS | Dashboard |
| React Flow | Service map and agent workflow view |
| Recharts | Metrics and incident charts |
| Python, FastAPI | Backend, APIs and agent hosting |
| LangGraph | Multi-agent orchestration, interrupts for approvals |
| MCP | Standard tool access for diagnostics, recovery and chaos |
| LLM API (Groq or compatible) | Reasoning for Investigator and Recovery, summaries |
| PostgreSQL | Registry, policies, incidents, audit |
| WebSockets | Real-time dashboard updates |
| OpenTelemetry | Logs, metrics and distributed traces |
| Docker | Target application and isolated simulation |
| Toxiproxy (or tc netem) | Latency, timeout and connection faults |
 
**Deferred or optional:** Redis (only if needed), Open Policy Agent (advanced policies), Kubernetes, Prometheus and Grafana.
 
## 13. Demo Scenarios
 
1. **Happy path:** inject a crash in a stateless service; agents detect, diagnose, restart it (allowed), validate, and a postmortem is generated.
 
2. **Blocked action:** the Recovery Agent proposes touching the database or a mass rollback; the guardrail blocks it or pauses for approval, with the reason shown.
 
3. **Human approval:** a high blast-radius fix is paused; the approver reviews evidence and approves; the action runs and is validated.
 
4. **Prompt injection:** a malicious instruction planted in a log line tries to trigger a destructive command; the gateway blocks it and the audit trail records the attempt.
 
5. **Live policy edit:** change a rule in the UI and show the next agent action being treated differently.
 
## 14. Success Metrics
 
- Time to recovery with agents versus manual baseline.
 
- Number of unsafe actions attempted versus blocked.
 
- False blocks: safe actions wrongly stopped.
 
- Approval turnaround time.
 
- Percentage of incidents correctly diagnosed in the seeded scenarios.
 
## 15. Risks and Mitigations
 
| Risk | Mitigation |
| --- | --- |
| Scope too large | One target app, four fault types, build in phases (section 16) |
| LLM nondeterminism and rate limits | Deterministic components where possible, seeded scenarios, recorded fallback run |
| Unrealistic simulation | Use a real open-source microservices app, not scripted animation |
| Guardrails bypassed | Gateway at the only tool path, deterministic engine, no policy tools for agents |
| Prompt injection via logs | Treat tool output as data, structured agent outputs, gateway enforcement independent of the LLM |
| Policy UI misused | Admin authentication, versioned changes, audit log |
 
## 16. Suggested Build Order
 
1. Target application running; adapter loaded; discovery builds the service map.
 
2. Fault injection from the dashboard (crash, then latency).
 
3. Diagnostics MCP server, Investigator, and one Recovery action.
 
4. Guardrail gateway with a handful of policies and the audit log.
 
5. Policy editor UI, approval flow, Validator and postmortem generation.
 
6. Prompt-injection demo, metrics, and polish.
 
## 17. Open Questions
 
- Which target application will be used for the MVP?
 
- Which LLM provider and model will be used, given rate limits and latency?
 
- Will approvals be single-user for the demo, or role-based?
 
- Is a second adapter in scope to prove generality?
 
- What time frame and team size apply to the build?