from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.agents import ParamValue
from app.schemas.base import ContractModel
from app.schemas.enums import FaultType


class ExperimentCreate(ContractModel):
    application_id: UUID
    service: str
    fault_type: FaultType
    parameters: dict[str, ParamValue] = Field(default_factory=dict)


class ExperimentRecord(ContractModel):
    id: UUID
    application_id: UUID
    service: str
    fault_type: FaultType
    parameters: dict[str, ParamValue]
    started_at: datetime | None
    ended_at: datetime | None
    initiated_by: str