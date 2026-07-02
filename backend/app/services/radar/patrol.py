"""Background patrol loop for Research Radar."""

from __future__ import annotations

import asyncio
import os
import threading
import time

from .radar_service import radar_service


RADAR_PATROL_INTERVAL_HOURS = int(os.getenv("RADAR_PATROL_INTERVAL_HOURS", "24"))
_started = False
_lock = threading.Lock()


def run_patrol_once():
    return asyncio.run(radar_service.run_patrol_once())


def start_daily_patrol() -> None:
    """Start one daemon patrol loop per process."""
    global _started
    with _lock:
        if _started:
            return
        _started = True

    def _loop():
        while True:
            time.sleep(max(RADAR_PATROL_INTERVAL_HOURS, 1) * 3600)
            try:
                asyncio.run(radar_service.run_patrol_once())
            except Exception as exc:
                print(f"[Radar] daily patrol failed: {exc}")

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
    print(f"[Radar] daily patrol thread started, interval={RADAR_PATROL_INTERVAL_HOURS}h")
