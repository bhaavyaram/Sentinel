import pytest

from app.errors import AppError
from app.policy import presets
from app.policy.io import parse_policy_body
from app.schemas import ActionType, PermissionLevel, PolicyPreset

BUILT_IN = (PolicyPreset.strict, PolicyPreset.balanced, PolicyPreset.permissive)


def test_every_preset_is_a_valid_policy_that_denies_on_timeout():
    for preset in BUILT_IN:
        body = presets.preset_body(preset)
        assert body.preset == preset
        assert body.approval.on_timeout == "deny"


def test_agents_can_never_inject_or_clear_faults_in_any_preset():
    for preset in BUILT_IN:
        for agent_matrix in presets.preset_body(preset).matrix.values():
            assert agent_matrix.get(ActionType.inject_fault, PermissionLevel.block) == PermissionLevel.block
            assert agent_matrix.get(ActionType.clear_fault, PermissionLevel.block) == PermissionLevel.block


def test_database_and_config_changes_are_protected_in_every_preset():
    for preset in BUILT_IN:
        protected = presets.preset_body(preset).protected.actions
        assert ActionType.touch_database in protected
        assert ActionType.modify_config in protected


def test_thresholds_loosen_from_strict_to_permissive():
    strict, balanced, permissive = (presets.preset_body(p).thresholds for p in BUILT_IN)
    assert strict.max_affected_services < balanced.max_affected_services < permissive.max_affected_services
    assert strict.approval_risk_score < balanced.approval_risk_score < permissive.approval_risk_score


def test_import_accepts_an_exported_policy():
    body = presets.preset_body(PolicyPreset.balanced)
    exported = {
        **body.model_dump(mode="json"),
        "version": 3,
        "created_by": "admin",
        "created_at": "2026-11-27T10:00:00Z",
    }
    assert parse_policy_body(exported) == body


def test_import_rejects_unknown_fields():
    with pytest.raises(AppError) as exc:
        parse_policy_body({"name": "x", "bogus": 1})
    assert exc.value.code == "invalid_policy"