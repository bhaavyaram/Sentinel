from pydantic import BaseModel, ConfigDict


class ContractModel(BaseModel):
    """Base for every contract model: unknown fields are rejected, never ignored."""

    model_config = ConfigDict(extra="forbid")