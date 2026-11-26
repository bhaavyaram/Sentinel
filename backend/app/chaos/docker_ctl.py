"""Find and control containers through the Docker SDK (talks to Docker Desktop's named pipe)."""

import docker
from docker.errors import DockerException

from app.errors import AppError


def _find(compose_service: str, compose_project: str | None):
    try:
        client = docker.from_env()
        labels = [f"com.docker.compose.service={compose_service}"]
        if compose_project:
            labels.append(f"com.docker.compose.project={compose_project}")
        found = client.containers.list(all=True, filters={"label": labels})
    except DockerException as exc:
        raise AppError(502, "chaos_failed", f"Cannot reach Docker: {exc}")
    if not found:
        raise AppError(502, "chaos_failed", f"No container found for compose service '{compose_service}'")
    return found[0]


def kill_container(compose_service: str, compose_project: str | None) -> None:
    container = _find(compose_service, compose_project)
    try:
        if container.status == "running":
            container.kill()  # abrupt stop, like a crash
    except DockerException as exc:
        raise AppError(502, "chaos_failed", f"Docker could not stop '{compose_service}': {exc}")


def start_container(compose_service: str, compose_project: str | None) -> None:
    container = _find(compose_service, compose_project)
    try:
        if container.status != "running":
            container.start()
    except DockerException as exc:
        raise AppError(502, "chaos_failed", f"Docker could not start '{compose_service}': {exc}")