"""Scout: try outside data sources and find out whether they sharpen the prediction.

The agent's edge, such as it is, comes from correlating sky conditions with
what ETH did next. The scout asks whether any paid feed in the x402 market
adds to that. It never trades on a candidate. It samples each one on a small
trial budget, records the reading next to the ETH price at the time, and once
enough samples have aged 24 hours it measures whether the reading said
anything about the return that followed. What passes is proposed, not adopted:
wiring a source into the live signals is a decision for a person.

Every candidate reduces to a few numbers per sample, so the evaluation is the
same for all of them: correlation with the 24h return, and how often the sign
of the reading matched the sign of the return.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import httpx

import ledger
import oracle

HERE = Path(__file__).parent
SAMPLES_PATH = HERE / "scout_samples.jsonl"
BUDGET_PATH = HERE / "scout_budget.json"
REPORT_PATH = HERE / "scout_report.md"
PRICE_CACHE = HERE / "cache" / "scout_prices.json"

DAILY_BUDGET_USD = float(os.getenv("SCOUT_DAILY_BUDGET", "0.25"))
MIN_HOURS_BETWEEN_ROUNDS = float(os.getenv("SCOUT_ROUND_HOURS", "4"))
HORIZON_HOURS = 24
MIN_SAMPLES_TO_JUDGE = 15


@dataclass
class Source:
    name: str
    url: str
    cost_usd: float
    extract: Callable[[dict | list], dict[str, float]]
    method: str = "GET"
    payload: dict | None = None
    note: str = ""
    price_hint: Callable[[dict | list], float | None] | None = None


def _eth_row(rows: list, key: str) -> dict | None:
    for r in rows:
        if str(r.get(key, "")).upper() == "ETH":
            return r
    return None


def _cambrian(body) -> dict[str, float]:
    """Tweet sentiment about ETH, 0 to 10, and how it shifted.

    Not registered: the sentiment-shifts feed lists the fifty biggest movers, which
    are microcaps, and ETH never appears. Two paid probes on 2026-09-14 confirmed
    it. Kept in case Cambrian exposes a per token endpoint.
    """
    row = _eth_row(body if isinstance(body, list) else body.get("data", []), "tokenSymbol")
    if not row:
        return {}
    return {
        "sentiment_shift": float(row.get("sentimentShift", 0)),
        "sentiment_now": float(row.get("currentSentiment", 5)) - 5.0,
        "bullish_ratio": float(row.get("bullishRatio", 50)) - 50.0,
    }


def _mycelia(body) -> dict[str, float]:
    """Futures against spot: basis, carry and funding across venues."""
    ex = body.get("exchanges", [])
    funding = [e["funding_rate_pct"] for e in ex if "funding_rate_pct" in e]
    return {
        "basis_pct": float(body.get("median_basis_pct", 0)),
        "carry_pct": float(body.get("median_carry_pct", 0)),
        "funding_mean": sum(funding) / len(funding) if funding else 0.0,
    }


def _mycelia_price(body) -> float | None:
    """The exchanges' index prices are a fine ETH price when CoinGecko is sulking."""
    idx = sorted(e["index_price"] for e in body.get("exchanges", []) if e.get("index_price"))
    return idx[len(idx) // 2] if idx else None


def _nansen(body) -> dict[str, float]:
    """Nansen's composite performance and risk scores for ETH among large caps."""
    row = _eth_row(body.get("data", []), "token_symbol")
    if not row:
        return {}
    return {
        "performance": float(row.get("performance_score", 0)),
        "risk_neg": -float(row.get("risk_score", 0)),
        "momentum": float(row.get("price_momentum_performance", 0)),
    }


SOURCES: list[Source] = [
    Source(
        name="mycelia_basis",
        url="https://api.myceliasignal.com/oracle/basis/eth/usd",
        cost_usd=0.02,
        extract=_mycelia,
        price_hint=_mycelia_price,
        note="ETH spot to futures basis, carry and funding across exchanges",
    ),
    Source(
        name="nansen_score",
        url="https://api.nansen.ai/api/v1/nansen-score/top-tokens",
        cost_usd=0.01,
        extract=_nansen,
        method="POST",
        payload={"limit": 25, "market_cap_group": "largecap"},
        note="Nansen composite performance and risk scores for large caps",
    ),
]

ROUND_COST = sum(s.cost_usd for s in SOURCES)


# budget: its own pot, separate from research, so trials never eat the trading research


def _budget() -> dict:
    today = date.today().isoformat()
    if BUDGET_PATH.exists():
        with open(BUDGET_PATH) as f:
            data = json.load(f)
        if data.get("date") == today:
            return data
    return {"date": today, "spent_usd": 0.0, "last_round_ts": _last_round_ts()}


def _save_budget(data: dict) -> None:
    with open(BUDGET_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _last_round_ts() -> float:
    last = 0.0
    for s in _samples():
        last = max(last, s["ts"])
    return last


def remaining_budget() -> float:
    return max(0.0, DAILY_BUDGET_USD - _budget()["spent_usd"])


def _samples() -> list[dict]:
    if not SAMPLES_PATH.exists():
        return []
    out = []
    with open(SAMPLES_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _eth_price_now() -> float | None:
    try:
        from positions import _get_eth_price
        return _get_eth_price()
    except Exception:
        return None


# sampling


async def sample_once(force: bool = False) -> dict:
    """One round: every source once, if the budget and the interval allow."""
    budget = _budget()
    since_last = (time.time() - budget.get("last_round_ts", 0)) / 3600
    if not force and since_last < MIN_HOURS_BETWEEN_ROUNDS:
        return {"action": "skip", "reason": f"last round {since_last:.1f}h ago"}
    if not force and remaining_budget() < ROUND_COST:
        return {"action": "skip", "reason": "scout budget spent for today"}

    price = _eth_price_now()
    ts = time.time()
    taken = []
    for src in SOURCES:
        if not force and remaining_budget() < src.cost_usd:
            break
        try:
            body = await oracle.ampersend_fetch(src.url, method=src.method, payload=src.payload)
            features = src.extract(body)
            if price is None and src.price_hint:
                price = src.price_hint(body)
            ok = bool(features)
            err = None
        except Exception as exc:
            features, ok, err = {}, False, str(exc)[:200]
        record = {
            "ts": ts,
            "iso": datetime.fromtimestamp(ts, timezone.utc).isoformat(),
            "source": src.name,
            "cost_usd": src.cost_usd,
            "eth_price": price,
            "ok": ok,
            "features": features,
            "error": err,
        }
        with open(SAMPLES_PATH, "a") as f:
            f.write(json.dumps(record) + "\n")
        budget = _budget()
        budget["spent_usd"] = round(budget["spent_usd"] + src.cost_usd, 4)
        budget["last_round_ts"] = ts
        _save_budget(budget)
        taken.append(src.name if ok else f"{src.name} (failed: {err})")

    ledger.record("scout", sources=taken, cost_usd=round(sum(
        s.cost_usd for s in SOURCES[: len(taken)]), 4), eth_price=price)
    return {"action": "sampled", "sources": taken, "eth_price": price}


# evaluation


async def _price_series(start_ts: float, end_ts: float) -> list[tuple[float, float]]:
    """Hourly ETH prices over a range, from CoinGecko's free endpoint, cached."""
    cache = {}
    if PRICE_CACHE.exists():
        with open(PRICE_CACHE) as f:
            cache = json.load(f)
    have = cache.get("points", [])
    if have and have[0][0] <= start_ts and have[-1][0] >= end_ts - 3600:
        return [tuple(p) for p in have]
    url = ("https://api.coingecko.com/api/v3/coins/ethereum/market_chart/range"
           f"?vs_currency=usd&from={int(start_ts) - 3600}&to={int(end_ts) + 3600}")
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, headers={"Accept": "application/json"})
        r.raise_for_status()
        points = [(p[0] / 1000, p[1]) for p in r.json().get("prices", [])]
    PRICE_CACHE.parent.mkdir(exist_ok=True)
    with open(PRICE_CACHE, "w") as f:
        json.dump({"points": points}, f)
    return points


def _price_at(points: list[tuple[float, float]], ts: float) -> float | None:
    best = None
    for t, p in points:
        if best is None or abs(t - ts) < abs(best[0] - ts):
            best = (t, p)
    if best and abs(best[0] - ts) <= 2 * 3600:
        return best[1]
    return None


def _corr(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(sxx * syy)


async def evaluate() -> dict:
    """Score every source on the samples that have aged past the horizon."""
    samples = [s for s in _samples() if s["ok"] and s["eth_price"]]
    now = time.time()
    aged = [s for s in samples if now - s["ts"] >= HORIZON_HOURS * 3600]
    if not aged:
        return {"sources": {}, "note": "no sample has aged 24h yet"}

    points = await _price_series(min(s["ts"] for s in aged),
                                 max(s["ts"] for s in aged) + HORIZON_HOURS * 3600)
    per_source: dict[str, dict] = {}
    for s in aged:
        later = _price_at(points, s["ts"] + HORIZON_HOURS * 3600)
        if later is None:
            continue
        ret = (later - s["eth_price"]) / s["eth_price"] * 100
        entry = per_source.setdefault(s["source"], {"n": 0, "features": {}})
        entry["n"] += 1
        for k, v in s["features"].items():
            entry["features"].setdefault(k, []).append((v, ret))

    out = {}
    for name, entry in per_source.items():
        feats = {}
        for k, pairs in entry["features"].items():
            xs = [p[0] for p in pairs]
            ys = [p[1] for p in pairs]
            agree = sum(1 for x, y in pairs if x != 0 and (x > 0) == (y > 0))
            nonzero = sum(1 for x in xs if x != 0)
            feats[k] = {
                "corr_24h": _corr(xs, ys),
                "direction_hit_pct": round(agree / nonzero * 100, 1) if nonzero else None,
            }
        spent = sum(s["cost_usd"] for s in _samples() if s["source"] == name)
        n = entry["n"]
        best = max(feats.values(), key=lambda f: abs(f["corr_24h"] or 0), default=None)
        if n < MIN_SAMPLES_TO_JUDGE:
            verdict = f"too early: {n} of {MIN_SAMPLES_TO_JUDGE} samples aged"
        elif best and best["corr_24h"] is not None and abs(best["corr_24h"]) >= 0.3:
            verdict = "candidate: worth proposing for the live signals"
        else:
            verdict = "no signal so far"
        out[name] = {"samples_aged": n, "spent_usd": round(spent, 2),
                     "features": feats, "verdict": verdict}
    return {"sources": out}


def _write_report(result: dict) -> None:
    lines = ["# Scout report", "",
             f"Written {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}. "
             f"Horizon {HORIZON_HOURS}h. Trial budget ${DAILY_BUDGET_USD:.2f} a day, "
             f"one round of {len(SOURCES)} sources costs ${ROUND_COST:.2f}.", ""]
    if not result["sources"]:
        lines.append(result.get("note", "nothing to report"))
    for src in SOURCES:
        r = result["sources"].get(src.name)
        lines.append(f"## {src.name}")
        lines.append(f"{src.note}. ${src.cost_usd:.2f} a call.")
        if not r:
            lines.append("No aged samples yet.")
            lines.append("")
            continue
        lines.append(f"Samples aged: {r['samples_aged']}. Spent so far: ${r['spent_usd']:.2f}. "
                     f"Verdict: {r['verdict']}.")
        lines.append("")
        lines.append("| feature | corr with 24h return | direction hit |")
        lines.append("|---|---|---|")
        for k, f in r["features"].items():
            c = "n/a" if f["corr_24h"] is None else f"{f['corr_24h']:+.2f}"
            h = "n/a" if f["direction_hit_pct"] is None else f"{f['direction_hit_pct']:.0f}%"
            lines.append(f"| {k} | {c} | {h} |")
        lines.append("")
    lines.append("A candidate is a proposal. Adding it to the live signals, and to the "
                 "Ampersend seller allowlist, is a decision for a person.")
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def report() -> str:
    result = await evaluate()
    _write_report(result)
    return REPORT_PATH.read_text(encoding="utf-8")


async def maybe_sample() -> dict:
    """Called from the agent's idle time. Cheap when there is nothing to do."""
    try:
        return await sample_once()
    except Exception as exc:
        ledger.record("scout_error", reason=str(exc)[:200])
        return {"action": "error", "reason": str(exc)}


if __name__ == "__main__":
    import sys
    if "--sample" in sys.argv:
        print(asyncio.run(sample_once(force="--force" in sys.argv)))
    else:
        print(asyncio.run(report()))
