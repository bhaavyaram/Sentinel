from datetime import datetime
from typing import Literal
from uuid import UUID

from app.schemas.base import ContractModel
from app.schemas.enums import FaultType, ServiceHealth, ServiceType


class ApplicationSummary(ContractModel):
    id: UUID
    name: str
    status: str
    created_at: datetime
    service_count: int


class MapNode(ContractModel):
    name: str
    type: ServiceType
    critical: bool
    health_endpoint: str | None
    health: ServiceHealth


class MapEdge(ContractModel):
    source: str
    target: str
    evidence: Literal["trace", "declared"]


class ApplicationMap(ContractModel):
    application_id: UUID
    nodes: list[MapNode]
    edges: list[MapEdge]


class AvailableExperiment(ContractModel):
    service: str
    fault_type: FaultType


class AvailableExperiments(ContractModel):
    application_id: UUID
    experiments: list[AvailableExperiment]