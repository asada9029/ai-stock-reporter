from __future__ import annotations

import os
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional


def _enabled(level: str) -> bool:
    """
    LOG_LEVEL:
      - quiet: 最小限
      - info: 既定
      - debug: 詳細
    """
    lv = (os.getenv("LOG_LEVEL") or "info").lower().strip()
    order = {"quiet": 0, "info": 1, "debug": 2}
    return order.get(lv, 1) >= order.get(level, 1)


def log(msg: str, *, level: str = "info") -> None:
    if _enabled(level):
        print(msg)


def log_kv(prefix: str, kv: Dict[str, Any], *, level: str = "info") -> None:
    if not _enabled(level):
        return
    parts = []
    for k, v in kv.items():
        parts.append(f"{k}={v}")
    joined = " ".join(parts)
    print(f"{prefix} {joined}".rstrip())


@contextmanager
def timed(label: str, *, level: str = "info") -> Iterator[Dict[str, Any]]:
    start = time.time()
    ctx: Dict[str, Any] = {}
    try:
        yield ctx
    finally:
        elapsed = time.time() - start
        if _enabled(level):
            extra = ""
            if ctx:
                extra = " " + " ".join([f"{k}={v}" for k, v in ctx.items()])
            print(f"⏱️ {label} {elapsed:.2f}s{extra}")

