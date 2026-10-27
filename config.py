from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def positive_int(name: str, default: int, minimum: int = 1) -> int:
    value = int(os.environ.get(name, default))
    if value < minimum:
        raise ValueError(f"{name} debe ser mayor o igual a {minimum}")
    return value


HOST = os.environ.get("HOST", "0.0.0.0")
PORT = positive_int("PORT", 8095)
ROTATE_SECONDS = positive_int("ROTATE_SECONDS", 15, 3)
REFRESH_SECONDS = positive_int("REFRESH_SECONDS", 180, 30)
MAX_ITEMS = positive_int("MAX_ITEMS", 14)
DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE_DIR / "data")))
