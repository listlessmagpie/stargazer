"""Backtest: correlate Paradox Box scores with actual ETH price movement."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

import oracle

CACHE_DIR = Path(__file__).parent / "cache"
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_PATH = Path(__file__).parent / "backtest_results.json"

COINGECKO_BASE = "https://api.coingecko.com/api/v3"

ALL_INTENTS = ["commerce", "communication", "creative", "general", "launch", "legal", "travel"]

LOOKBACK_DAYS = 180
QUERY_CHUNK_DAYS = 3
PRICE_CHUNK_DAYS = 30

HORIZONS_HOURS = [4, 8, 12, 24, 48]

#: Orrery calls this process has actually paid for. A cached chunk costs nothing,
#: so anything that reports spend reads the change in this, never a planned count.
PAID_CALLS = 0


def _cache_path(label: str) -> Path:
    CACHE_DIR.mkdir(exist_ok=True)
    return CACHE_DIR / f"{label}.json"


def _load_cache(label: str) -> dict | None:
    p = _cache_path(label)
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return None


def _save_cache(label: str, data: dict) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    with open(_cache_path(label), "w") as f:
        json.dump(data, f, indent=2)


async def fetch_historical_windows(
    intent: str = "commerce",
    days_back: int = LOOKBACK_DAYS,
    lat: float = 45.52,
    lon: float = -122.68,
) -> list[dict]:
    """Query the oracle for historical windows in 3-day chunks. Cached."""
    cache_key = f"windows_{intent}_{days_back}d"
    cached = _load_cache(cache_key)
    if cached:
        print(f"  loaded {len(cached)} cached windows for {intent}")
        return cached

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days_back)

    all_windows = []
    cursor = start
    chunk_num = 0
    total_chunks = days_back // QUERY_CHUNK_DAYS

    while cursor < now:
        chunk_end = min(cursor + timedelta(days=QUERY_CHUNK_DAYS), now)
        chunk_num += 1

        chunk_cache_key = f"chunk_{intent}_{cursor.strftime('%Y%m%d')}_{chunk_end.strftime('%Y%m%d')}"
        chunk_data = _load_cache(chunk_cache_key)

        if chunk_data is None:
            print(f"  [{chunk_num}/{total_chunks}] querying {cursor.strftime('%Y-%m-%d')} to {chunk_end.strftime('%Y-%m-%d')}...")
            try:
                payload = {
                    "where": [lat, lon],
                    "start": cursor.strftime("%Y-%m-%d"),
                    "end": chunk_end.strftime("%Y-%m-%d"),
                    "intent": intent,
                    "top_n": 10,
                }
                data = await oracle._ampersend_post(
                    f"{oracle.API_BASE}/v1/elect", payload
                )
                chunk_data = data.get("windows", [])
                _save_cache(chunk_cache_key, chunk_data)
                global PAID_CALLS
                PAID_CALLS += 1
            except oracle.BudgetExhausted:
                print(f"    budget exhausted, stopping {intent} (got {len(all_windows)} windows so far)")
                break
            except Exception as e:
                print(f"    error: {e}")
                chunk_data = []
        else:
            print(f"  [{chunk_num}/{total_chunks}] cached {cursor.strftime('%Y-%m-%d')}")

        all_windows.extend(chunk_data)
        cursor = chunk_end

    _save_cache(cache_key, all_windows)
    print(f"  total: {len(all_windows)} windows for {intent}")
    return all_windows


async def fetch_price_history(
    days_back: int = LOOKBACK_DAYS, asset: str = "ethereum",
) -> list[tuple[float, float]]:
    """Fetch hourly USD prices for a CoinGecko asset id. Returns [(unix_ts, price), ...]."""
    cache_key = f"prices_eth_{days_back}d" if asset == "ethereum" else f"prices_{asset}_{days_back}d"
    cached = _load_cache(cache_key)
    if cached:
        print(f"  loaded {len(cached)} cached price points")
        return cached

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days_back)

    all_prices = []
    cursor = start

    async with httpx.AsyncClient() as client:
        while cursor < now:
            chunk_end = min(cursor + timedelta(days=PRICE_CHUNK_DAYS), now)
            from_ts = int(cursor.timestamp())
            to_ts = int(chunk_end.timestamp())

            print(f"  fetching prices {cursor.strftime('%Y-%m-%d')} to {chunk_end.strftime('%Y-%m-%d')}...")

            resp = await client.get(
                f"{COINGECKO_BASE}/coins/{asset}/market_chart/range",
                params={
                    "vs_currency": "usd",
                    "from": from_ts,
                    "to": to_ts,
                },
                timeout=30,
            )
            if resp.status_code == 429:
                print("    rate limited, waiting 60s...")
                await asyncio.sleep(60)
                continue

            resp.raise_for_status()
            data = resp.json()
            prices = data.get("prices", [])
            all_prices.extend(prices)

            cursor = chunk_end
            await asyncio.sleep(2)

    all_prices.sort(key=lambda x: x[0])

    seen = set()
    deduped = []
    for ts, price in all_prices:
        if ts not in seen:
            seen.add(ts)
            deduped.append([ts, price])

    _save_cache(cache_key, deduped)
    print(f"  total: {len(deduped)} price points")
    return deduped


def _price_at(prices: list, target_ts: float) -> float | None:
    """Find the closest price to a given unix timestamp."""
    if not prices:
        return None

    best_idx = 0
    best_diff = abs(prices[0][0] - target_ts)

    for i, (ts, _) in enumerate(prices):
        diff = abs(ts - target_ts)
        if diff < best_diff:
            best_diff = diff
            best_idx = i

    if best_diff > 3600 * 2000:
        return None

    return prices[best_idx][1]


def correlate(windows: list[dict], prices: list) -> list[dict]:
    """For each window, calculate price changes over multiple horizons."""
    results = []

    for w in windows:
        when = w.get("when_utc", "")
        if not when:
            continue

        try:
            dt = datetime.fromisoformat(when.replace("Z", "+00:00"))
        except ValueError:
            continue

        window_ts = dt.timestamp() * 1000

        entry_price = _price_at(prices, window_ts)
        if entry_price is None:
            continue

        row = {
            "when_utc": when,
            "score": w.get("score", 0),
            "moon_sign": w.get("moon_sign", ""),
            "moon_phase": w.get("moon_phase", ""),
            "waxing": w.get("waxing", False),
            "void_of_course": w.get("void_of_course", False),
            "retrogrades": w.get("retrogrades", []),
            "factors": w.get("factors", []),
            "entry_price": entry_price,
        }

        for h in HORIZONS_HOURS:
            future_ts = window_ts + (h * 3600 * 1000)
            future_price = _price_at(prices, future_ts)
            if future_price is not None:
                pct = (future_price - entry_price) / entry_price * 100
                row[f"return_{h}h"] = round(pct, 4)
            else:
                row[f"return_{h}h"] = None

        results.append(row)

    return results


def analyze(correlations: list[dict]) -> dict:
    """Analyze correlations to find what predicts profitable moves."""
    analysis = {
        "total_windows": len(correlations),
        "by_score_bucket": {},
        "by_moon_sign": {},
        "by_moon_phase": {},
        "by_void_of_course": {},
        "by_waxing": {},
    }

    def _bucket(score: int) -> str:
        if score >= 70:
            return "70+"
        elif score >= 60:
            return "60-69"
        elif score >= 50:
            return "50-59"
        elif score >= 40:
            return "40-49"
        else:
            return "<40"

    def _add_to_group(group_dict: dict, key: str, row: dict):
        if key not in group_dict:
            group_dict[key] = {"count": 0, "returns": {h: [] for h in HORIZONS_HOURS}}
        group_dict[key]["count"] += 1
        for h in HORIZONS_HOURS:
            val = row.get(f"return_{h}h")
            if val is not None:
                group_dict[key]["returns"][h].append(val)

    for row in correlations:
        score = row.get("score", 0)
        _add_to_group(analysis["by_score_bucket"], _bucket(score), row)
        _add_to_group(analysis["by_moon_sign"], row.get("moon_sign", "unknown"), row)
        _add_to_group(analysis["by_moon_phase"], row.get("moon_phase", "unknown"), row)
        _add_to_group(analysis["by_void_of_course"], str(row.get("void_of_course", False)), row)
        _add_to_group(analysis["by_waxing"], str(row.get("waxing", False)), row)

    def _summarize_group(group_dict: dict) -> dict:
        summary = {}
        for key, data in sorted(group_dict.items()):
            entry = {"count": data["count"]}
            for h in HORIZONS_HOURS:
                vals = data["returns"][h]
                if vals:
                    avg = sum(vals) / len(vals)
                    pos = sum(1 for v in vals if v > 0)
                    entry[f"avg_{h}h"] = round(avg, 4)
                    entry[f"win_rate_{h}h"] = round(pos / len(vals) * 100, 1)
                    entry[f"n_{h}h"] = len(vals)
                    # A win rate says nothing about what a loss costs. Kelly folds
                    # both in: W - (1 - W) / R, where R is average win over average loss.
                    wins = [v for v in vals if v > 0]
                    losses = [v for v in vals if v <= 0]
                    if wins and losses and sum(losses) != 0:
                        w = len(wins) / len(vals)
                        r = (sum(wins) / len(wins)) / abs(sum(losses) / len(losses))
                        entry[f"avg_win_{h}h"] = round(sum(wins) / len(wins), 4)
                        entry[f"avg_loss_{h}h"] = round(sum(losses) / len(losses), 4)
                        entry[f"kelly_{h}h"] = round(w - (1 - w) / r, 4)
            summary[key] = entry
        return summary

    for group_name in ["by_score_bucket", "by_moon_sign", "by_moon_phase", "by_void_of_course", "by_waxing"]:
        analysis[group_name] = _summarize_group(analysis[group_name])

    return analysis


def print_analysis(analysis: dict, intent: str = ""):
    """Print a readable summary of the backtest results."""
    label = f" ({intent})" if intent else ""
    print(f"\n{'='*60}")
    print(f"BACKTEST RESULTS{label} ({analysis['total_windows']} windows)")
    print(f"{'='*60}")

    for group_name, group_label in [
        ("by_score_bucket", "SCORE BUCKET"),
        ("by_moon_sign", "MOON SIGN"),
        ("by_moon_phase", "MOON PHASE"),
        ("by_waxing", "WAXING/WANING"),
        ("by_void_of_course", "VOID OF COURSE"),
    ]:
        print(f"\n--- {group_label} ---")
        group = analysis[group_name]
        print(f"{'Key':<16} {'N':>5}  {'24h avg%':>9}  {'24h win%':>9}  {'48h avg%':>9}  {'48h win%':>9}")
        for key, data in group.items():
            n = data["count"]
            avg_24 = data.get("avg_24h", "n/a")
            win_24 = data.get("win_rate_24h", "n/a")
            avg_48 = data.get("avg_48h", "n/a")
            win_48 = data.get("win_rate_48h", "n/a")

            avg_24_s = f"{avg_24:>8.3f}%" if isinstance(avg_24, (int, float)) else f"{avg_24:>9}"
            win_24_s = f"{win_24:>8.1f}%" if isinstance(win_24, (int, float)) else f"{win_24:>9}"
            avg_48_s = f"{avg_48:>8.3f}%" if isinstance(avg_48, (int, float)) else f"{avg_48:>9}"
            win_48_s = f"{win_48:>8.1f}%" if isinstance(win_48, (int, float)) else f"{win_48:>9}"

            print(f"{key:<16} {n:>5}  {avg_24_s}  {win_24_s}  {avg_48_s}  {win_48_s}")


async def run_backtest(
    intent: str = "commerce",
    days_back: int = LOOKBACK_DAYS,
) -> dict:
    """Full backtest pipeline for a single intent."""
    print(f"\nStargazer backtest: {days_back} days, intent={intent}")

    print("  Historical oracle windows")
    windows = await fetch_historical_windows(intent=intent, days_back=days_back)

    print("  ETH price history")
    prices = await fetch_price_history(days_back=days_back)

    print("  Correlating scores with price movement")
    correlations = correlate(windows, prices)
    print(f"  matched {len(correlations)} windows to price data")

    analysis = analyze(correlations)

    results = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "intent": intent,
        "days_back": days_back,
        "total_windows": len(windows),
        "matched_windows": len(correlations),
        "analysis": analysis,
        "correlations": correlations,
    }

    return results


async def run_all_intents(days_back: int = LOOKBACK_DAYS) -> dict:
    """Run backtests for all seven intents and produce a combined report."""
    RESULTS_DIR.mkdir(exist_ok=True)

    print(f"{'='*60}")
    print(f"STARGAZER FULL RESEARCH: all intents, {days_back} days")
    print(f"{'='*60}")

    all_results = {}
    cost_calls = 0
    budget_hit = False

    for intent in ALL_INTENTS:
        if budget_hit:
            print(f"\n  skipping {intent} (budget exhausted, will resume tomorrow)")
            continue

        cache_key = f"windows_{intent}_{days_back}d"
        is_cached = _load_cache(cache_key) is not None
        if not is_cached:
            cost_calls += days_back // QUERY_CHUNK_DAYS

        try:
            results = await run_backtest(intent=intent, days_back=days_back)
        except oracle.BudgetExhausted:
            print(f"\n  budget exhausted during {intent}, saving partial results")
            budget_hit = True
            continue

        all_results[intent] = results

        intent_path = RESULTS_DIR / f"backtest_{intent}.json"
        with open(intent_path, "w") as f:
            json.dump(results, f, indent=2)

    # Build a cross-intent comparison
    comparison = _compare_intents(all_results)

    combined = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "days_back": days_back,
        "intents": ALL_INTENTS,
        "oracle_calls": cost_calls,
        "oracle_cost_usd": round(cost_calls * 0.01, 2),
        "comparison": comparison,
    }

    with open(RESULTS_PATH, "w") as f:
        json.dump(combined, f, indent=2)

    _print_comparison(comparison)

    # Print per-intent details for the most interesting ones
    for intent in ALL_INTENTS:
        analysis = all_results[intent]["analysis"]
        print_analysis(analysis, intent=intent)

    return combined


def _compare_intents(all_results: dict) -> dict:
    """Compare how different intents predict ETH price movement."""
    comparison = {"by_intent_score": {}, "best_signals": []}

    for intent, results in all_results.items():
        analysis = results["analysis"]
        signs = analysis.get("by_moon_sign", {})
        phases = analysis.get("by_moon_phase", {})

        best_sign = None
        best_sign_wr = 0
        worst_sign = None
        worst_sign_wr = 100

        for sign, data in signs.items():
            wr = data.get("win_rate_24h", 50)
            n = data.get("n_24h", 0)
            if n < 10:
                continue
            if wr > best_sign_wr:
                best_sign_wr = wr
                best_sign = sign
            if wr < worst_sign_wr:
                worst_sign_wr = wr
                worst_sign = sign

        # overall win rate for this intent's high-score windows
        scores = analysis.get("by_score_bucket", {})
        high_score = scores.get("70+", scores.get("60-69", {}))
        high_wr = high_score.get("win_rate_24h", 50) if high_score else 50
        high_avg = high_score.get("avg_24h", 0) if high_score else 0

        comparison["by_intent_score"][intent] = {
            "high_score_win_rate_24h": high_wr,
            "high_score_avg_return_24h": high_avg,
            "best_sign": best_sign,
            "best_sign_win_rate": best_sign_wr,
            "worst_sign": worst_sign,
            "worst_sign_win_rate": worst_sign_wr,
            "total_windows": results["matched_windows"],
        }

        # Collect strong signals across all intents
        for sign, data in signs.items():
            wr = data.get("win_rate_24h", 50)
            avg = data.get("avg_24h", 0)
            n = data.get("n_24h", 0)
            if n >= 10 and (wr >= 65 or wr <= 35):
                comparison["best_signals"].append({
                    "intent": intent,
                    "factor": f"moon_sign:{sign}",
                    "win_rate_24h": wr,
                    "avg_return_24h": avg,
                    "samples": n,
                })

        for phase, data in phases.items():
            wr = data.get("win_rate_24h", 50)
            avg = data.get("avg_24h", 0)
            n = data.get("n_24h", 0)
            if n >= 10 and (wr >= 65 or wr <= 35):
                comparison["best_signals"].append({
                    "intent": intent,
                    "factor": f"moon_phase:{phase}",
                    "win_rate_24h": wr,
                    "avg_return_24h": avg,
                    "samples": n,
                })

    comparison["best_signals"].sort(key=lambda x: x["win_rate_24h"], reverse=True)

    return comparison


def _print_comparison(comparison: dict):
    """Print a readable cross-intent comparison."""
    print(f"\n{'='*60}")
    print("CROSS-INTENT COMPARISON")
    print(f"{'='*60}")

    print(f"\n--- INTENT OVERVIEW ---")
    print(f"{'Intent':<16} {'High Score WR':>14} {'High Score Avg':>14} {'Best Sign':<12} {'Worst Sign':<12}")
    for intent, data in comparison["by_intent_score"].items():
        wr = data["high_score_win_rate_24h"]
        avg = data["high_score_avg_return_24h"]
        bs = data.get("best_sign", "?")
        ws = data.get("worst_sign", "?")
        print(f"{intent:<16} {wr:>13.1f}% {avg:>13.3f}% {bs:<12} {ws:<12}")

    print(f"\n--- STRONGEST SIGNALS (win rate >= 65% or <= 35%, n >= 10) ---")
    print(f"{'Intent':<16} {'Factor':<24} {'WR 24h':>8} {'Avg 24h':>9} {'N':>5}")
    for sig in comparison["best_signals"][:20]:
        print(f"{sig['intent']:<16} {sig['factor']:<24} {sig['win_rate_24h']:>7.1f}% {sig['avg_return_24h']:>8.3f}% {sig['samples']:>5}")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")

    if "--all" in sys.argv:
        asyncio.run(run_all_intents())
    else:
        intent = "commerce"
        for arg in sys.argv[1:]:
            if not arg.startswith("--"):
                intent = arg
        asyncio.run(run_backtest(intent=intent))
