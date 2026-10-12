"""The paper book: pretend money on the family 2 occasions, by the registered rule.

Stage 2 of the gate. A pattern reaches here only if the occasions report marks it
paper eligible (at least 7 occurrences, 70% as expected, half of those since 2021; see
registry/2026-10-12-family-2-occasions.md). From the day it is marked, every new
occurrence opens one pretend position at the close of its first active day: long if the
pattern expects up, short if it expects down. It closes at the later of the horizon or
the last active day. Every position is appended the day it opens, with the price and the
reason; the close is filled in afterwards and nothing is edited.

Prices are the daily closes the almanac already fetches. When Alpaca paper keys are set
(ALPACA_KEY, ALPACA_SECRET), the same orders are also sent to the Alpaca paper account
through alpaca_paper.py, so the record has fills from a real simulator for stocks, ETFs
and crypto, and shorting exists. Without keys, the local book is the record.

    python paper.py            # open and close what the day calls for
    python paper.py --show
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOOK = HERE / "paper_book.json"
OCC = HERE / "almanac_occasions.json"
STAKE = 100.0  # pretend dollars per position; equal size by rule
REGISTERED = date(2026, 10, 12)

#: What each market trades as on Alpaca paper. Oil and the VIX trade through their funds.
ALPACA_SYMBOLS = {"bitcoin": "BTC/USD", "ethereum": "ETH/USD", "sp500": "SPY", "gold": "GLD", "oil": "USO", "vix": "VIXY"}


def _closes(market: str) -> list[tuple[date, float]]:
    import almanac
    return almanac.fetch_prices(almanac.MARKETS[market])


def load() -> dict:
    if BOOK.exists():
        return json.loads(BOOK.read_text(encoding="utf-8"))
    return {"stake_per_position": STAKE, "registered": REGISTERED.isoformat(), "positions": []}


def save(book: dict) -> None:
    BOOK.write_text(json.dumps(book, indent=1), encoding="utf-8")


def step(today: date | None = None) -> dict:
    today = today or datetime.now(timezone.utc).date()
    book = load()
    pats = json.loads(OCC.read_text(encoding="utf-8")) if OCC.exists() else []
    opened, closed = 0, 0
    key = lambda p: (p["market"], p["factor"], p["horizon_days"])
    have = {(x["market"], x["factor"], x["horizon_days"], x["from"]) for x in book["positions"]}

    for p in pats:
        if not p.get("paper_eligible"):
            continue
        px = _closes(p["market"])
        bydate = {d.isoformat(): c for d, c in px}
        dates = sorted(bydate)
        for n in p["next"]:
            if n["from"] < REGISTERED.isoformat() or n["from"] > today.isoformat():
                continue
            k = key(p) + (n["from"],)
            if k in have:
                continue
            # entry: first close on or after the window opens
            entry_dates = [d for d in dates if d >= n["from"]]
            if not entry_dates:
                continue
            ed = entry_dates[0]
            book["positions"].append({
                "market": p["market"], "alpaca_symbol": ALPACA_SYMBOLS.get(p["market"]),
                "factor": p["factor"], "horizon_days": p["horizon_days"],
                "side": "long" if p["expects"] == "up" else "short",
                "from": n["from"], "to": n["to"], "record_at_entry": f"{p['as_predicted']} of {p['occasions']}",
                "entry_date": ed, "entry_price": bydate[ed], "stake": STAKE,
                "opened_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })
            have.add(k)
            opened += 1

    for x in book["positions"]:
        if "exit_price" in x:
            continue
        px = _closes(x["market"])
        bydate = {d.isoformat(): c for d, c in px}
        dates = sorted(bydate)
        if x["entry_date"] not in dates:
            continue
        i = dates.index(x["entry_date"])
        horizon_exit = dates[i + x["horizon_days"]] if i + x["horizon_days"] < len(dates) else None
        after_window = [d for d in dates if d > x["to"]]
        window_exit = after_window[0] if after_window else None
        if horizon_exit and window_exit:
            ex = max(horizon_exit, window_exit)
        else:
            continue  # not closable yet
        if ex > today.isoformat():
            continue
        move = bydate[ex] / x["entry_price"] - 1
        pnl = STAKE * (move if x["side"] == "long" else -move)
        x.update({"exit_date": ex, "exit_price": bydate[ex], "move_pct": round(move * 100, 2),
                  "pnl": round(pnl, 2), "right": pnl > 0,
                  "closed_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        closed += 1

    done = [x for x in book["positions"] if "pnl" in x]
    book["summary"] = {
        "open": len(book["positions"]) - len(done), "closed": len(done),
        "right": sum(1 for x in done if x["right"]),
        "pnl": round(sum(x["pnl"] for x in done), 2),
        "as_of": today.isoformat(),
    }
    save(book)

    try:
        import alpaca_paper
        alpaca_paper.mirror(book)
    except Exception as e:  # the local book is the record; Alpaca is a mirror
        book.setdefault("alpaca", {})["last_error"] = str(e)[:200]
        save(book)
    return {"opened": opened, "closed": closed, **book["summary"]}


if __name__ == "__main__":
    if "--show" in sys.argv:
        b = load()
        print(json.dumps(b.get("summary", {}), indent=1))
        for x in b["positions"][-20:]:
            print(f"{x['entry_date']} {x['market']:9s} {x['side']:5s} {x['factor'][:40]:40s} "
                  + (f"{x['pnl']:+.2f}" if "pnl" in x else "open"))
        sys.exit(0)
    print(step())
