from typing import Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.schemas.base import ContractModel
from app.schemas.enums import FaultType, ServiceType

SLUG_PATTERN = r"^[a-z0-9][a-z0-9_-]*$"
HEALTH_PREFIXES = ("/", "tcp://", "http://", "https://")


class AdapterService(ContractModel):
    name: str = Field(pattern=SLUG_PATTERN)
    container: str = Field(min_length=1)  # docker compose service name
    type: ServiceType
    critical: bool = False
    health: str | None = None
    faults: list[FaultType] = Field(default_factory=list)

    @field_validator("health")
    @classmethod
    def health_must_be_probeable(cls, v: str | None) -> str | None:
        if v is not None and not v.startswith(HEALTH_PREFIXES):
            raise ValueError(
                "health must be an HTTP path starting with '/', an http(s):// URL, or a 'tcp://host:port' address"
            )
        return v


class DeclaredDependency(ContractModel):
    # "from" is a Python keyword, so the field is from_ and the file key is "from".
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str


class AdapterFile(ContractModel):
    app: str = Field(pattern=SLUG_PATTERN)
    version: Literal[1] = 1
    description: str | None = None
    compose_project: str | None = Field(default=None, pattern=SLUG_PATTERN)
    services: list[AdapterService] = Field(min_length=1)
    declared_dependencies: list[DeclaredDependency] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_references(self) -> "AdapterFile":
        names = [s.name for s in self.services]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            raise ValueError(f"duplicate service names: {sorted(duplicates)}")
        known = set(names)
        for dep in self.declared_dependencies:
            for end in (dep.from_, dep.to):
                if end not in known:
                    raise ValueError(f"declared dependency references unknown service '{end}'")
        return self