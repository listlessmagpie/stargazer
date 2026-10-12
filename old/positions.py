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
    """ETH/USD from the pool the agent trades in; CoinGecko only if the node fails."""
    try:
        import trader
        return trader.eth_price()
    except Exception:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return float(data["ethereum"]["usd"])


def _path(asset: str) -> Path:
    """ETH keeps the original file; every other asset gets its own beside it."""
    return POSITION_PATH if asset == "ethereum" else POSITION_PATH.with_name(f"position_{asset}.json")


def _load(asset: str = "ethereum") -> dict | None:
    path = _path(asset)
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _save(position: dict, asset: str = "ethereum") -> None:
    with open(_path(asset), "w") as f:
        json.dump(position, f, indent=2)


def _summarise(position: dict) -> dict:
    lots = position["lots"]
    total_usdc = sum(l["usdc"] for l in lots)
    total_eth = sum(l["usdc"] / l["price"] for l in lots)
    position.update({
        "entry_usdc": round(total_usdc, 6),
        "entry_price": total_usdc / total_eth,
        "entry_tx": lots[-1].get("tx"),
        "moon_sign": lots[0]["moon_sign"],
        "moon_phase": lots[0]["moon_phase"],
    })
    return position


def open_position(
    amount_usdc: str,
    moon_sign: str,
    moon_phase: str,
    tx: str,
    price: float | None = None,
    asset: str = "ethereum",
) -> dict:
    """Record a buy. Buys add to an open position; the entry price is the average."""
    eth_price = price or _get_eth_price()
    lot = {
        "usdc": float(amount_usdc),
        "price": eth_price,
        "time": datetime.now(timezone.utc).isoformat(),
        "tx": tx,
        "moon_sign": moon_sign,
        "moon_phase": moon_phase,
    }
    position = _load(asset)
    if not position or position.get("status") != "open" or "lots" not in position:
        position = {"status": "open", "lots": [], "entry_time": lot["time"], "asset": asset}
    position["lots"].append(lot)
    _save(_summarise(position), asset)
    return position | {"lot_price": eth_price}


def reduce_position(fraction: float, tx: str, price: float, asset: str = "ethereum") -> dict | None:
    """Sell part of a position. The outcome is that part, judged against the average entry.

    Every lot shrinks by the same fraction, so the average entry of what is left
    does not move: selling some does not rewrite what the rest cost.
    """
    position = _load(asset)
    if not position or position.get("status") != "open":
        return None
    fraction = max(0.0, min(1.0, fraction))
    entry_price = position["entry_price"]
    return_pct = (price - entry_price) / entry_price * 100
    outcome = {
        "asset": asset, "fraction": round(fraction, 4),
        "entry_price": entry_price, "exit_price": price,
        "return_pct": round(return_pct, 4), "won": return_pct > 0,
        "usdc_cost_sold": round(position["entry_usdc"] * fraction, 4),
        "entry_time": position["entry_time"],
        "exit_time": datetime.now(timezone.utc).isoformat(),
        "exit_tx": tx, "held_hours": _hours_between(position["entry_time"]),
        "moon_sign": position.get("moon_sign", ""), "moon_phase": position.get("moon_phase", ""),
    }
    position.setdefault("sales", []).append(outcome)
    if fraction >= 0.999:
        position["status"] = "closed"
        position["outcome"] = outcome
        _save(position, asset)
        return outcome
    for lot in position["lots"]:
        lot["usdc"] = lot["usdc"] * (1 - fraction)
    _save(_summarise(position), asset)
    return outcome


def current(asset: str, price: float) -> dict | None:
    """The open position in one asset, marked to a price the caller already has."""
    position = _load(asset)
    if not position or position.get("status") != "open":
        return None
    position["current_price"] = price
    position["unrealized_pct"] = round((price - position["entry_price"]) / position["entry_price"] * 100, 4)
    return position


def close_position(tx: str) -> dict | None:
    """Close the whole position and return the outcome against the average entry."""
    position = _load()
    if not position or position.get("status") != "open":
        return None

    exit_price = _get_eth_price()
    entry_price = position["entry_price"]
    return_pct = (exit_price - entry_price) / entry_price * 100

    outcome = {
        "entry_price": entry_price,
        "exit_price": exit_price,
        "return_pct": round(return_pct, 4),
        "won": return_pct > 0,
        "entry_usdc": position.get("entry_usdc"),
        "lots": len(position.get("lots", [])) or 1,
        "entry_time": position["entry_time"],
        "exit_time": datetime.now(timezone.utc).isoformat(),
        "entry_tx": position.get("entry_tx"),
        "exit_tx": tx,
        "moon_sign": position["moon_sign"],
        "moon_phase": position["moon_phase"],
        "held_hours": _hours_between(position["entry_time"]),
    }

    position["status"] = "closed"
    position["outcome"] = outcome
    _save(position)
    return outcome


def current_position() -> dict | None:
    """Return the current open position, or None."""
    position = _load()
    if not position or position.get("status") != "open":
        return None
    position["current_price"] = _get_eth_price()
    position["unrealized_pct"] = round(
        (position["current_price"] - position["entry_price"])
        / position["entry_price"] * 100,
        4,
    )
    return position


def rebuild_from_ledger() -> dict | None:
    """Reconstruct the open position from every buy since the last sell.

    Needed once: before 2026-09-18 each buy overwrote the record of the one
    before, because the agent could not see the wrapped ETH it already held.
    """
    import ledger
    lots = []
    for e in ledger.read_all():
        if e["event"] == "swap_eth_to_usdc":
            lots = []
        elif e["event"] == "swap_usdc_to_eth":
            lots.append({
                "usdc": float(e["amount_usdc"]), "price": float(e["entry_price"]),
                "time": e["ts"], "tx": e.get("tx"),
                "moon_sign": e.get("moon_sign", ""), "moon_phase": e.get("moon_phase", ""),
            })
    if not lots:
        return None
    position = {"status": "open", "lots": lots, "entry_time": lots[0]["time"]}
    _save(_summarise(position))
    return position


def _hours_between(iso_start: str) -> float:
    start = datetime.fromisoformat(iso_start)
    now = datetime.now(timezone.utc)
    return round((now - start).total_seconds() / 3600, 2)
