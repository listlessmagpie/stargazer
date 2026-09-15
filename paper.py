"""The paper book: every strategy the agent is not running, tracked as if it were.

The live agent does one thing: long ETH, in on a favourable window, out on an
unfavourable one. That is the right amount of risk for nine dollars. But the
question the experiment asks is wider than one asset and one direction, so the
rest is answered on paper. Every four hours the book reads the current sky
from the orrery, prices every asset, and for each strategy decides what it
would do, opening and closing pretend positions at real prices. Wins and
losses accumulate the same way the live ledger's do, and the experiment page
shows them side by side.

A strategy is an asset, a direction, and the intent whose windows it was
trained on. Long is the live logic. Short is its mirror: out (or, with real
leverage, short) ahead of an unfavourable window, back in on a favourable one.
Nothing here spends a cent beyond the sky reading, and nothing here can be
promoted to live by code; that is a person's decision, made on this evidence.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import backtest
import ledger
import oracle
import signals

HERE = Path(__file__).resolve().parent
BOOK_PATH = HERE / "paper_book.json"
TABLES_PATH = HERE / "paper_tables.json"
WINDOWS_PATH = HERE / "cache" / "windows_commerce_180d.json"

ASSETS = ["ethereum", "bitcoin", "solana"]
DIRECTIONS = ["long", "short"]
INTENT = "commerce"
TICK_HOURS = 4
TABLES_TTL_DAYS = 7
SKY_COST_USD = 0.002

LIVE = ("ethereum", "long")  # what the real wallet runs; kept on paper too, for the gap


def _key(asset: str, direction: str) -> str:
    return f"{asset}:{direction}"


def _load(path: Path, default):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return default


def _save(path: Path, data) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _book() -> dict:
    book = _load(BOOK_PATH, {"last_tick": 0, "strategies": {}})
    for a in ASSETS:
        for d in DIRECTIONS:
            book["strategies"].setdefault(_key(a, d), {
                "asset": a, "direction": d, "intent": INTENT,
                "position": None, "outcomes": [],
            })
    return book


# tables: the same backtest the live strategy uses, per asset


async def _tables() -> dict:
    """Moon sign and phase tables per asset, rebuilt weekly from bundled windows."""
    tables = _load(TABLES_PATH, {})
    windows = _load(WINDOWS_PATH, [])
    if not windows:
        return tables
    for asset in ASSETS:
        entry = tables.get(asset)
        if entry and time.time() - entry.get("built", 0) < TABLES_TTL_DAYS * 86400:
            continue
        try:
            prices = await backtest.fetch_price_history(days_back=backtest.LOOKBACK_DAYS, asset=asset)
        except Exception as exc:
            ledger.record("paper_error", asset=asset, reason=f"prices: {exc}"[:200])
            continue
        analysis = backtest.analyze(backtest.correlate(windows, prices))
        tables[asset] = {
            "built": time.time(),
            "by_moon_sign": analysis.get("by_moon_sign", {}),
            "by_moon_phase": analysis.get("by_moon_phase", {}),
            "windows": analysis.get("total_windows", 0),
        }
        _save(TABLES_PATH, tables)
    return tables


# the sky and the prices


async def _sky() -> dict:
    """Current moon sign, phase, void of course, and retrogrades, from the orrery."""
    data = await oracle._ampersend_post(f"{oracle.API_BASE}/v1/aspects", {
        "when": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "where": [45.52, -122.68],
    })
    moon = data.get("moon", {})
    phase = moon.get("phase", "")
    return {
        "moon_sign": moon.get("sign", ""),
        "moon_phase": phase,
        "waxing": phase in ("new_moon", "waxing_crescent", "first_quarter", "waxing_gibbous"),
        "void_of_course": bool(moon.get("void_of_course", False)),
        "retrogrades": [r.title() for r in data.get("retrogrades", [])],
    }


def _prices() -> dict[str, float]:
    ids = ",".join(ASSETS)
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={urllib.parse.quote(ids)}&vs_currencies=usd"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return {a: float(data[a]["usd"]) for a in ASSETS if a in data}


# the tick


def _decide(direction: str, confidence: float, has_position: bool) -> str:
    """Long mirrors the live thresholds. Short is the same thresholds, reflected."""
    if direction == "long":
        if has_position:
            return "close" if confidence < signals.SELL_THRESHOLD else "hold"
        return "open" if confidence > signals.BUY_THRESHOLD else "hold"
    if has_position:
        return "close" if confidence > signals.BUY_THRESHOLD else "hold"
    return "open" if confidence < signals.SELL_THRESHOLD else "hold"


def _return_pct(direction: str, entry: float, exit_: float) -> float:
    pct = (exit_ - entry) / entry * 100
    return round(pct if direction == "long" else -pct, 4)


async def tick(force: bool = False) -> dict:
    book = _book()
    if not force and time.time() - book.get("last_tick", 0) < TICK_HOURS * 3600:
        return {"action": "skip", "reason": "ticked recently"}

    tables = await _tables()
    try:
        prices = _prices()
    except Exception as exc:
        return {"action": "error", "reason": f"prices: {exc}"}
    sky = await _sky()
    now = datetime.now(timezone.utc).isoformat()
    moves = []

    for key, strat in book["strategies"].items():
        asset, direction = strat["asset"], strat["direction"]
        if asset not in prices:
            continue
        t = tables.get(asset, {})
        has_position = strat["position"] is not None
        assessment = signals.assess_conditions(
            moon_sign=sky["moon_sign"], moon_phase=sky["moon_phase"], waxing=sky["waxing"],
            void_of_course=sky["void_of_course"], retrogrades=sky["retrogrades"], factors=[],
            has_position=(has_position if direction == "long" else not has_position),
            signs_data=t.get("by_moon_sign", {}), phases_data=t.get("by_moon_phase", {}),
        )
        decision = _decide(direction, assessment.confidence, has_position)
        price = prices[asset]
        if decision == "open":
            strat["position"] = {
                "entry_price": price, "entry_time": now, "confidence": round(assessment.confidence, 3),
                "moon_sign": sky["moon_sign"], "moon_phase": sky["moon_phase"],
            }
            moves.append(f"{key} open @ {price:.2f}")
            ledger.record("paper_open", strategy=key, price=price, confidence=round(assessment.confidence, 3),
                          moon_sign=sky["moon_sign"], moon_phase=sky["moon_phase"])
        elif decision == "close":
            pos = strat["position"]
            pct = _return_pct(direction, pos["entry_price"], price)
            held = round((datetime.fromisoformat(now) - datetime.fromisoformat(pos["entry_time"])).total_seconds() / 3600, 1)
            outcome = {
                "entry_price": pos["entry_price"], "exit_price": price, "return_pct": pct,
                "won": pct > 0, "entry_time": pos["entry_time"], "exit_time": now, "held_hours": held,
                "moon_sign_in": pos["moon_sign"], "moon_phase_in": pos["moon_phase"],
                "moon_sign_out": sky["moon_sign"], "moon_phase_out": sky["moon_phase"],
            }
            strat["outcomes"].append(outcome)
            strat["position"] = None
            moves.append(f"{key} close {pct:+.2f}%")
            ledger.record("paper_close", strategy=key, price=price, return_pct=pct, won=pct > 0, held_hours=held)

    book["last_tick"] = time.time()
    book["last_sky"] = sky
    book["last_prices"] = prices
    _save(BOOK_PATH, book)
    ledger.record("paper_tick", cost_usd=SKY_COST_USD, moves=moves, moon_sign=sky["moon_sign"],
                  moon_phase=sky["moon_phase"])
    return {"action": "ticked", "moves": moves, "sky": sky}


def summary() -> list[dict]:
    """One row per strategy for the experiment page."""
    book = _book()
    rows = []
    for key, strat in book["strategies"].items():
        outs = strat["outcomes"]
        wins = sum(1 for o in outs if o["won"])
        net = sum(o["return_pct"] for o in outs)
        rows.append({
            "strategy": key, "asset": strat["asset"], "direction": strat["direction"],
            "live": (strat["asset"], strat["direction"]) == LIVE,
            "closed": len(outs), "wins": wins,
            "win_rate": round(wins / len(outs) * 100, 1) if outs else None,
            "net_pct": round(net, 2),
            "open": strat["position"] is not None,
        })
    return rows


async def maybe_tick() -> dict:
    try:
        return await tick()
    except Exception as exc:
        ledger.record("paper_error", reason=str(exc)[:200])
        return {"action": "error", "reason": str(exc)}


if __name__ == "__main__":
    import asyncio
    import sys
    if "--tick" in sys.argv:
        print(asyncio.run(tick(force="--force" in sys.argv)))
    else:
        for r in summary():
            tag = " (live)" if r["live"] else ""
            print(f"{r['strategy']}{tag}: {r['closed']} closed, {r['wins']} won, net {r['net_pct']:+.2f}%"
                  f"{', open' if r['open'] else ''}")
