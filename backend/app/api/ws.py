import asyncio
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.db import SessionLocal
from app.errors import AppError
from app.event_hub import hub
from app.repository import applications as applications_repo
from app.repository import events as events_repo

log = logging.getLogger(__name__)
router = APIRouter(tags=["events"])

REPLAY_PAGE = 500


def _application_exists(application_id: uuid.UUID) -> bool:
    with SessionLocal() as db:
        try:
            applications_repo.get_application_summary(db, application_id)
        except AppError:
            return False
    return True


async def _wait_for_disconnect(websocket: WebSocket) -> None:
    """The stream is server-to-client only. Reading here just detects the client leaving."""
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
    except Exception:
        return


@router.websocket("/ws/applications/{application_id}/events")
async def application_events(
    websocket: WebSocket, application_id: uuid.UUID, after_event_id: uuid.UUID | None = None
) -> None:
    await websocket.accept()

    # Subscribe BEFORE replaying, so an event stored during the replay is not lost.
    sub = hub.subscribe(application_id)
    disconnect = asyncio.create_task(_wait_for_disconnect(websocket))
    try:
        if not await run_in_threadpool(_application_exists, application_id):
            await websocket.close(code=4404, reason="application_not_found")
            return

        last_seq = 0
        if after_event_id is not None:
            seq = await run_in_threadpool(events_repo.get_seq, application_id, after_event_id)
            if seq is None:
                await websocket.close(code=4404, reason="unknown after_event_id")
                return
            last_seq = seq
            while True:
                page = await run_in_threadpool(
                    events_repo.list_after, application_id, last_seq, REPLAY_PAGE
                )
                for seq, event in page:
                    await websocket.send_json(event.model_dump(mode="json"))
                    last_seq = seq
                if len(page) < REPLAY_PAGE:
                    break

        while True:
            getter = asyncio.create_task(sub.queue.get())
            done, _ = await asyncio.wait({getter, disconnect}, return_when=asyncio.FIRST_COMPLETED)
            if disconnect in done:
                getter.cancel()
                break
            seq, event = getter.result()
            if seq <= last_seq:  # already sent during replay
                continue
            await websocket.send_json(event.model_dump(mode="json"))
            last_seq = seq
    except WebSocketDisconnect:
        pass
    except RuntimeError:
        pass  # sending after the socket closed
    finally:
        disconnect.cancel()
        hub.unsubscribe(sub)