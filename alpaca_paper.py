"""Mirror the paper book onto an Alpaca paper account, when keys exist.

Alpaca's paper environment is free, needs only an email to open, simulates fills against
real time quotes, and allows shorting stocks and ETFs and trading crypto. Magpie opens the
account herself; this file never creates one. Set ALPACA_KEY and ALPACA_SECRET in the
environment (or .env) and the book's positions are placed there as notional orders of the
same pretend stake. Without keys this does nothing and says so once.

The local book stays the record. Alpaca is the independent witness.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
BASE = "https://paper-api.alpaca.markets"


def _env() -> tuple[str, str] | None:
    env = HERE / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    k, s = os.getenv("ALPACA_KEY"), os.getenv("ALPACA_SECRET")
    return (k, s) if k and s else None


def _headers(k: str, s: str) -> dict:
    return {"APCA-API-KEY-ID": k, "APCA-API-SECRET-KEY": s}


def mirror(book: dict) -> None:
    creds = _env()
    state = book.setdefault("alpaca", {"placed": {}, "status": "no keys; local book only"})
    if not creds:
        state["status"] = "no keys; local book only"
        return
    k, s = creds
    placed: dict = state.setdefault("placed", {})
    with httpx.Client(base_url=BASE, headers=_headers(k, s), timeout=20) as c:
        acct = c.get("/v2/account")
        acct.raise_for_status()
        state["status"] = f"paper account {acct.json().get('account_number', '?')}, equity {acct.json().get('equity')}"
        for x in book["positions"]:
            pid = f"{x['market']}|{x['factor']}|{x['from']}"
            sym = x.get("alpaca_symbol")
            if not sym:
                continue
            if pid not in placed:
                side = "buy" if x["side"] == "long" else "sell"
                order = {"symbol": sym, "notional": str(x["stake"]), "side": side, "type": "market", "time_in_force": "day"}
                if "/" in sym:  # crypto: no shorting, fractional qty by notional, gtc
                    if side == "sell":
                        placed[pid] = {"skipped": "crypto cannot be shorted on Alpaca; local book only"}
                        continue
                    order["time_in_force"] = "gtc"
                r = c.post("/v2/orders", json=order)
                placed[pid] = {"open_order": r.json().get("id") if r.status_code < 300 else None,
                               "error": None if r.status_code < 300 else r.text[:200]}
            elif "exit_price" in x and placed[pid].get("open_order") and not placed[pid].get("close_order"):
                side = "sell" if x["side"] == "long" else "buy"
                order = {"symbol": sym, "notional": str(x["stake"]), "side": side, "type": "market",
                         "time_in_force": "gtc" if "/" in sym else "day"}
                r = c.post("/v2/orders", json=order)
                placed[pid]["close_order"] = r.json().get("id") if r.status_code < 300 else None
                if r.status_code >= 300:
                    placed[pid]["close_error"] = r.text[:200]
    (HERE / "paper_book.json").write_text(json.dumps(book, indent=1), encoding="utf-8")
