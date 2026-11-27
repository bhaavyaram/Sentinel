"""Starting-point policies. The dashboard edits copies of these; nothing here is special at runtime."""

from app.schemas import PolicyBody, PolicyPreset

DEFAULT_PRESET = PolicyPreset.balanced

# What the recovery agent may do, per preset. Missing agents and missing actions mean block.
_RECOVERY = {
    PolicyPreset.strict: {
        "restart": "needs_approval",
        "rollback": "block",
        "scale": "block",
        "reset_connection_pool": "needs_approval",
        "modify_config": "block",
        "touch_database": "block",
        "inject_fault": "block",
        "clear_fault": "block",
    },
    PolicyPreset.balanced: {
        "restart": "allow",
        "rollback": "needs_approval",
        "scale": "allow",
        "reset_connection_pool": "allow",
        "modify_config": "block",
        "touch_database": "block",
        "inject_fault": "block",
        "clear_fault": "block",
    },
    PolicyPreset.permissive: {
        "restart": "allow",
        "rollback": "allow",
        "scale": "allow",
        "reset_connection_pool": "allow",
        "modify_config": "block",
        "touch_database": "block",
        "inject_fault": "block",
        "clear_fault": "block",
    },
}

_THRESHOLDS = {
    PolicyPreset.strict: {"max_affected_services": 1, "max_dependents": 1, "approval_risk_score": 30},
    PolicyPreset.balanced: {"max_affected_services": 3, "max_dependents": 3, "approval_risk_score": 50},
    PolicyPreset.permissive: {"max_affected_services": 6, "max_dependents": 6, "approval_risk_score": 80},
}


def preset_body(preset: PolicyPreset) -> PolicyBody:
    if preset not in _RECOVERY:
        raise ValueError(f"'{preset.value}' is not a built-in preset")
    return PolicyBody.model_validate(
        {
            "name": f"{preset.value.capitalize()} (default)",
            "preset": preset.value,
            "matrix": {"recovery": _RECOVERY[preset]},
            "service_rules": [],
            "thresholds": _THRESHOLDS[preset],
            "protected": {
                "services": [],
                "actions": ["modify_config", "touch_database"],
                "pairs": [],
            },
            "approval": {"approver_role": "approver", "timeout_seconds": 300, "on_timeout": "deny"},
        }
    )