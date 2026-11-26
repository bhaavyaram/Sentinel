import yaml
from pydantic import ValidationError

from app.schemas import AdapterFile

MAX_ADAPTER_BYTES = 1_000_000


class AdapterError(ValueError):
    """The adapter text could not be turned into a valid AdapterFile."""


def format_validation_error(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        location = ".".join(str(p) for p in err["loc"]) or "adapter"
        parts.append(f"{location}: {err['msg']}")
    return "; ".join(parts)


def parse_adapter(text: str) -> AdapterFile:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise AdapterError(f"Invalid YAML: {exc}") from exc

    if not isinstance(data, dict):
        raise AdapterError("Adapter file must be a YAML mapping at the top level")

    try:
        return AdapterFile.model_validate(data)
    except ValidationError as exc:
        raise AdapterError(format_validation_error(exc)) from exc