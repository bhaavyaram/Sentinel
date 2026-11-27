"""Prints events from the SENTINEL WebSocket stream.

Usage (from the backend folder, venv active):
    python scripts\\ws_listen.py <application_id> [after_event_id]
"""

import asyncio
import json
import sys

import websockets


async def main(application_id: str, after_event_id: str | None) -> None:
    url = f"ws://localhost:8000/api/v1/ws/applications/{application_id}/events"
    if after_event_id:
        url += f"?after_event_id={after_event_id}"
    async with websockets.connect(url) as ws:
        print(f"connected: {url}")
        async for message in ws:
            event = json.loads(message)
            print(event["event_id"], event["type"], event["actor"], event["payload"])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python scripts\\ws_listen.py <application_id> [after_event_id]")
    try:
        asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))
    except KeyboardInterrupt:
        pass