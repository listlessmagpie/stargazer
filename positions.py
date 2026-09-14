"""Track open positions so the agent knows its entry price.

When the agent buys ETH, it records the entry price. When it sells,
it compares entry to exit and feeds the result to strategy.record_outcome()
so the win counter advances and tiers unlock.
"""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

POSITION_PATH = Path(__file__).parent / "position.json"


def _get_eth_price() -> float:
    """Fetch current ETH/USD price from CoinGecko (free, no key)."""
    url = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    return float(data["ethereum"]["usd"])


def open_position(
    amount_usdc: str,
    moon_sign: str,
    moon_phase: str,
    tx: str,
) -> dict:
    """Record a new long ETH position after a buy."""
    eth_price = _get_eth_price()
    position = {
        "status": "open",
        "entry_price": eth_price,
        "entry_usdc": amount_usdc,
        "entry_time": datetime.now(timezone.utc).isoformat(),
        "entry_tx": tx,
        "moon_sign": moon_sign,
        "moon_phase": moon_phase,
    }
    with open(POSITION_PATH, "w") as f:
        json.dump(position, f, indent=2)
    return position


def close_position(tx: str) -> dict | None:
    """Close the current position and return the outcome.

    Returns None if no position is open.
    Returns a dict with entry_price, exit_price, return_pct, won.
    """
    if not POSITION_PATH.exists():
        return None

    with open(POSITION_PATH) as f:
        position = json.load(f)

    if position.get("status") != "open":
        return None

    exit_price = _get_eth_price()
    entry_price = position["entry_price"]
    return_pct = (exit_price - entry_price) / entry_price * 100

    outcome = {
        "entry_price": entry_price,
        "exit_price": exit_price,
        "return_pct": round(return_pct, 4),
        "won": return_pct > 0,
        "entry_time": position["entry_time"],
        "exit_time": datetime.now(timezone.utc).isoformat(),
        "entry_tx": position["entry_tx"],
        "exit_tx": tx,
        "moon_sign": position["moon_sign"],
        "moon_phase": position["moon_phase"],
        "held_hours": _hours_between(position["entry_time"]),
    }

    position["status"] = "closed"
    position["outcome"] = outcome
    with open(POSITION_PATH, "w") as f:
        json.dump(position, f, indent=2)

    return outcome


def current_position() -> dict | None:
    """Return the current open position, or None."""
    if not POSITION_PATH.exists():
        return None
    with open(POSITION_PATH) as f:
        position = json.load(f)
    if position.get("status") != "open":
        return None
    position["current_price"] = _get_eth_price()
    position["unrealized_pct"] = round(
        (position["current_price"] - position["entry_price"])
        / position["entry_price"] * 100,
        4,
    )
    return position


def _hours_between(iso_start: str) -> float:
    start = datetime.fromisoformat(iso_start)
    now = datetime.now(timezone.utc)
    return round((now - start).total_seconds() / 3600, 2)
