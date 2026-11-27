"""Runs the health probe for every registered service, exactly like the monitor does.

Usage (from the backend folder, venv active):
    python scripts\\probe_check.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.monitoring import probes  # noqa: E402


def main() -> None:
    with SessionLocal() as db:
        rows = db.execute(text("select name, health_endpoint from services order by name")).all()
    for name, address in rows:
        start = time.perf_counter()
        result = probes.probe(address)
        elapsed_ms = (time.perf_counter() - start) * 1000
        print(f"{name:24} {str(address):34} {str(result):6} {elapsed_ms:7.0f} ms")


if __name__ == "__main__":
    main()