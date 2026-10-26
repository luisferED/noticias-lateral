"""Supervise the native SDK in a child process so a blocked C call is recoverable.

Exit on crash/stall and let Docker's restart policy recreate the service.
Docker health=unhealthy alone does NOT trigger Docker restart.
"""
from __future__ import annotations

import logging
import signal
import subprocess
import sys
import threading
import time

from config import BASE_DIR
from ndi_status import STATUS_FILE, STALL_SECONDS, STARTUP_SECONDS, is_healthy, read_status, write_status

logger = logging.getLogger(__name__)


def monitor(child, stop, started):
    while not stop.wait(1):
        code = child.poll()
        if code is not None:
            logger.error("Emisor terminó: código %s", code)
            return code or 1
        status = read_status()
        now = time.monotonic()
        if is_healthy(status, now, child.pid):
            continue
        own_status = status.get("pid") == child.pid and status.get("frames", 0) > 0
        deadline = status.get("monotonic", started) + STALL_SECONDS if own_status else started + STARTUP_SECONDS
        if now >= deadline:
            logger.error("Sin avance de frames; se termina el servicio para reinicio Docker")
            return 1
    return 0


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    write_status(STATUS_FILE, frames=0, phase="starting")
    child = subprocess.Popen([sys.executable, "-u", str(BASE_DIR / "ndi_sender.py")])
    try:
        return monitor(child, stop, time.monotonic())
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        write_status(STATUS_FILE, frames=0, phase="stopped")


if __name__ == "__main__":
    raise SystemExit(main())
