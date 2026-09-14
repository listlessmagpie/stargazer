"""Talk to the Paradox Box. Pay for every answer via Ampersend."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


API_BASE = os.getenv(
    "PARADOX_BOX_URL",
    "https://paradox-box-production.up.railway.app",
)

AMPERSEND_CONTEXT = os.getenv("AMPERSEND_CONTEXT", "ctx-61d1")


@dataclass
class Window:
    when_utc: str
    score: int
    moon_sign: str
    moon_phase: str
    waxing: bool
    void_of_course: bool
    retrogrades: list[str]
    factors: list[str]


class BudgetExhausted(RuntimeError):
    """Daily or monthly spending limit reached."""
    pass


async def _ampersend_post(url: str, payload: dict) -> dict:
    """POST via ampersend fetch --pay, which handles x402 payment."""
    return await ampersend_fetch(url, method="POST", payload=payload)


async def ampersend_fetch(url: str, method: str = "GET", payload: dict | None = None) -> dict:
    """Fetch any x402 resource through ampersend, paying if it asks."""
    import subprocess
    import sys
    base_args = [
        "ampersend", "fetch", "--pay",
        "--context", AMPERSEND_CONTEXT,
        "-X", method,
    ]
    if payload is not None:
        base_args += ["-H", "Content-Type: application/json", "-d", json.dumps(payload)]
    base_args.append(url)
    if sys.platform == "win32":
        args = ["cmd", "/c"] + base_args
    else:
        args = base_args
    proc = await asyncio.to_thread(
        subprocess.run, args,
        capture_output=True, text=True,
    )

    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()

    if "exceeds daily remaining budget" in stderr or "exceeds monthly remaining budget" in stderr:
        raise BudgetExhausted("Ampersend daily/monthly spending limit reached")

    if not stdout:
        raise RuntimeError(f"ampersend returned no output. stderr: {stderr}")

    try:
        result = json.loads(stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"ampersend returned non-JSON: {stdout[:200]}. stderr: {stderr[:200]}")

    if not result.get("ok"):
        error = result.get("error", {})
        msg = error.get("message", str(error))
        if "budget" in msg.lower() or "declined" in msg.lower():
            raise BudgetExhausted(msg)
        raise RuntimeError(f"ampersend fetch failed: {msg}")

    return result["data"].get("body", {})


async def elect(
    intent: str = "commerce",
    lat: float = 45.52,
    lon: float = -122.68,
    days_ahead: int = 3,
    top_n: int = 5,
) -> list[Window]:
    """Ask the Paradox Box for the best windows. Costs $0.01 per call."""
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days_ahead)

    payload = {
        "where": [lat, lon],
        "start": now.strftime("%Y-%m-%d"),
        "end": end.strftime("%Y-%m-%d"),
        "intent": intent,
        "top_n": top_n,
    }

    data = await _ampersend_post(f"{API_BASE}/v1/elect", payload)

    windows = []
    for w in data.get("windows", []):
        windows.append(Window(**w))
    return windows


async def best_intent(
    intents: list[str] | None = None,
    lat: float = 45.52,
    lon: float = -122.68,
) -> tuple[str, Window | None]:
    """Check multiple intents, return the one with the highest top score.

    Each intent costs one API call ($0.01).
    """
    if intents is None:
        intents = ["commerce", "launch", "general"]

    best_score = -1
    best_window = None
    best_name = "general"

    for intent in intents:
        windows = await elect(intent=intent, lat=lat, lon=lon, top_n=1)
        if windows and windows[0].score > best_score:
            best_score = windows[0].score
            best_window = windows[0]
            best_name = intent

    return best_name, best_window
