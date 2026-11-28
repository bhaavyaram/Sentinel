"""Find a Docker container by its compose labels (Contracts section 2).

Docker names real containers like 'online-boutique-cartservice-1', so we look them up
through the com.docker.compose.service label, scoped by the optional compose project.
"""

import docker
from docker.errors import DockerException

from app.tools.base import ToolError


def find_container(compose_service: str, compose_project: str | None = None):
    labels = [f"com.docker.compose.service={compose_service}"]
    if compose_project:
        labels.append(f"com.docker.compose.project={compose_project}")
    try:
        client = docker.from_env()
        found = client.containers.list(all=True, filters={"label": labels})
    except DockerException as exc:
        raise ToolError(f"Cannot reach Docker: {exc}") from exc
    if not found:
        raise ToolError(f"No container found for compose service '{compose_service}'")
    return found[0]