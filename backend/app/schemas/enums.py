from enum import Enum


class AgentRole(str, Enum):
    monitor = "monitor"
    investigator = "investigator"
    impact = "impact"
    recovery = "recovery"
    validator = "validator"


class Actor(str, Enum):
    monitor = "monitor"
    investigator = "investigator"
    impact = "impact"
    recovery = "recovery"
    validator = "validator"
    human = "human"
    system = "system"


class ActionType(str, Enum):
    restart = "restart"
    rollback = "rollback"
    scale = "scale"
    reset_connection_pool = "reset_connection_pool"
    modify_config = "modify_config"
    touch_database = "touch_database"
    inject_fault = "inject_fault"
    clear_fault = "clear_fault"


class FaultType(str, Enum):
    crash = "crash"
    latency = "latency"
    timeout = "timeout"
    connection_failure = "connection_failure"


class Verdict(str, Enum):
    allow = "allow"
    block = "block"
    needs_approval = "needs_approval"


class PermissionLevel(str, Enum):
    allow = "allow"
    needs_approval = "needs_approval"
    block = "block"


class ServiceType(str, Enum):
    stateless = "stateless"
    stateful = "stateful"


class ServiceHealth(str, Enum):
    healthy = "healthy"
    degraded = "degraded"
    down = "down"
    unknown = "unknown"


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class IncidentStatus(str, Enum):
    open = "open"
    investigating = "investigating"
    awaiting_approval = "awaiting_approval"
    recovering = "recovering"
    validating = "validating"
    resolved = "resolved"
    failed = "failed"


class ValidationResult(str, Enum):
    recovered = "recovered"
    partially_recovered = "partially_recovered"
    failed = "failed"


class ApprovalDecision(str, Enum):
    approved = "approved"
    denied = "denied"
    timed_out = "timed_out"


class ReasonCode(str, Enum):
    chaos_requires_human = "chaos_requires_human"
    protected_resource = "protected_resource"
    no_rule = "no_rule"
    matrix_block = "matrix_block"
    matrix_needs_approval = "matrix_needs_approval"
    service_override = "service_override"
    risk_threshold = "risk_threshold"
    allowed = "allowed"


class PolicyPreset(str, Enum):
    strict = "strict"
    balanced = "balanced"
    permissive = "permissive"
    custom = "custom"


class EventType(str, Enum):
    experiment_started = "experiment_started"
    experiment_ended = "experiment_ended"
    service_health_changed = "service_health_changed"
    incident_opened = "incident_opened"
    incident_status_changed = "incident_status_changed"
    agent_step = "agent_step"
    proposal_created = "proposal_created"
    gateway_decision = "gateway_decision"
    approval_requested = "approval_requested"
    approval_decided = "approval_decided"
    action_executed = "action_executed"
    validation_completed = "validation_completed"
    postmortem_ready = "postmortem_ready"
    policy_changed = "policy_changed"


# Contracts section 1: tool -> action mapping.
# modify_config and touch_database have no tool yet, so any future tool is blocked by default.
TOOL_ACTION_MAP: dict[str, ActionType] = {
    "restart_service": ActionType.restart,
    "rollback_deployment": ActionType.rollback,
    "scale_service": ActionType.scale,
    "reset_connection_pool": ActionType.reset_connection_pool,
    "inject_crash": ActionType.inject_fault,
    "inject_latency": ActionType.inject_fault,
    "inject_timeout": ActionType.inject_fault,
    "break_db_connection": ActionType.inject_fault,
    "clear_fault": ActionType.clear_fault,
}

# Contracts section 6: chaos tools may only be called with initiated_by_human = true.
CHAOS_TOOLS: frozenset[str] = frozenset(
    {
        "inject_crash",
        "inject_latency",
        "inject_timeout",
        "break_db_connection",
        "clear_fault",
    }
)