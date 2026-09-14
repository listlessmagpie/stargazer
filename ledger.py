"""Append-only JSON ledger. Every decision gets recorded."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LEDGER_PATH = Path(os.getenv("LEDGER_PATH", "ledger.jsonl"))


def record(event_type: str, **data: Any) -> dict:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
        **data,
    }
    with open(LEDGER_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def read_all() -> list[dict]:
    if not LEDGER_PATH.exists():
        return []
    entries = []
    with open(LEDGER_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def last_action() -> dict | None:
    entries = read_all()
    for e in reversed(entries):
        if e["event"] in ("swap_usdc_to_eth", "swap_eth_to_usdc", "hold"):
            return e
    return None


def summary() -> dict:
    entries = read_all()
    checks = sum(1 for e in entries if e["event"] == "check")
    trades = sum(1 for e in entries if e["event"].startswith("swap_"))
    holds = sum(1 for e in entries if e["event"] == "hold")
    errors = sum(1 for e in entries if e["event"] == "error")
    api_spend = checks * 0.01
    return {
        "total_entries": len(entries),
        "checks": checks,
        "trades": trades,
        "holds": holds,
        "errors": errors,
        "api_spend_usd": round(api_spend, 4),
    }
