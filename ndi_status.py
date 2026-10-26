"""File heartbeat: successful SDK submission, not receiver/network validation."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from config import BASE_DIR, positive_int

STATUS_FILE = Path(os.environ.get("NDI_STATUS_FILE", str(BASE_DIR / "data" / "ndi" / "status.json")))
STALL_SECONDS = positive_int("NDI_STALL_SECONDS", 30, 5)
STARTUP_SECONDS = positive_int("NDI_STARTUP_SECONDS", 120, 10)


def write_status(path: Path, **values):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(values, pid=os.getpid(), monotonic=time.monotonic(), updated_at=time.time())
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    temporary.replace(path)


def read_status(path: Path = STATUS_FILE):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def is_healthy(status, now=None, pid=None):
    try:
        age = (time.monotonic() if now is None else now) - status["monotonic"]
        return (status["frames"] > 0 and 0 <= age < STALL_SECONDS
                and (pid is None or status["pid"] == pid))
    except (KeyError, TypeError):
        return False


if __name__ == "__main__":
    status = read_status()
    print(json.dumps(status))
    raise SystemExit(0 if is_healthy(status) else 1)
