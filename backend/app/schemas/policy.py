from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.base import ContractModel
from app.schemas.enums import ActionType, AgentRole, PermissionLevel, PolicyPreset


class ServiceRule(ContractModel):
    service: str
    tags: list[Literal["stateful", "critical"]] = Field(default_factory=list)
    overrides: dict[ActionType, PermissionLevel] = Field(default_factory=dict)


class Thresholds(ContractModel):
    max_affected_services: int = Field(ge=0)
    max_dependents: int = Field(ge=0)
    approval_risk_score: int = Field(ge=0, le=100)


class ProtectedPair(ContractModel):
    service: str
    action: ActionType


class Protected(ContractModel):
    services: list[str] = Field(default_factory=list)
    actions: list[ActionType] = Field(default_factory=list)
    pairs: list[ProtectedPair] = Field(default_factory=list)


class ApprovalSettings(ContractModel):
    approver_role: str = Field(min_length=1)
    timeout_seconds: int = Field(gt=0)
    on_timeout: Literal["deny"]  # can only be deny (invariant 6)


class PolicyBody(ContractModel):
    name: str = Field(min_length=1)
    preset: PolicyPreset
    # A missing matrix entry means block (invariant 3).
    matrix: dict[AgentRole, dict[ActionType, PermissionLevel]] = Field(default_factory=dict)
    service_rules: list[ServiceRule] = Field(default_factory=list)
    thresholds: Thresholds
    protected: Protected
    approval: ApprovalSettings


class Policy(PolicyBody):
    version: int = Field(ge=1)
    created_by: str
    created_at: datetime