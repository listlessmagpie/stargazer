"""Research budget: spend idle time learning, $3/day max.

When the agent holds (no trade), it burns remaining daily budget on
backtesting new intents and refreshing stale data. Each oracle call
costs $0.01, so $3/day = 300 calls. The research has to pay for
itself through better trades over time.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import backtest
import ledger
import oracle
import strategy

BUDGET_PATH = Path(__file__).parent / "research_budget.json"
DAILY_BUDGET_USD = 3.00
COST_PER_CALL = 0.01
STALE_DAYS = 7

ALL_INTENTS = backtest.ALL_INTENTS


def _load_budget() -> dict:
    if BUDGET_PATH.exists():
        with open(BUDGET_PATH) as f:
            data = json.load(f)
        if data.get("date") != str(date.today()):
            data = _new_day()
    else:
        data = _new_day()
    return data


def _new_day() -> dict:
    data = {
        "date": str(date.today()),
        "spent_usd": 0.0,
        "calls_made": 0,
        "intents_researched": [],
    }
    _save_budget(data)
    return data


def _save_budget(data: dict):
    with open(BUDGET_PATH, "w") as f:
        json.dump(data, f, indent=2)


def remaining_budget() -> float:
    data = _load_budget()
    return max(0, DAILY_BUDGET_USD - data["spent_usd"])


def record_spend(calls: int):
    data = _load_budget()
    data["spent_usd"] = round(data["spent_usd"] + calls * COST_PER_CALL, 4)
    data["calls_made"] += calls
    _save_budget(data)


def _research_priority() -> list[tuple[str, str]]:
    """Decide what to research next. Returns (intent, mode) pairs.

    Modes: "full" = uncached historical backtest,
           "stale" = cached but older than STALE_DAYS, re-run,
           "recent" = cached and fresh, but query last 7 days for new windows.
    """
    uncached = []
    stale = []
    recent = []

    for intent in ALL_INTENTS:
        cache_key = f"windows_{intent}_{backtest.LOOKBACK_DAYS}d"
        cached_data = backtest._load_cache(cache_key)
        if cached_data is None:
            uncached.append((intent, "full"))
        else:
            cache_path = backtest._cache_path(cache_key)
            age_days = (datetime.now(timezone.utc).timestamp() - cache_path.stat().st_mtime) / 86400
            if age_days > STALE_DAYS:
                stale.append((intent, "stale"))
            else:
                recent_key = f"recent_{intent}_{date.today().isoformat()}"
                if backtest._load_cache(recent_key) is None:
                    recent.append((intent, "recent"))

    return uncached + stale + recent


def _estimate_cost(intent: str) -> float:
    """Estimate how many calls an intent backtest will need."""
    cache_key = f"windows_{intent}_{backtest.LOOKBACK_DAYS}d"
    if backtest._load_cache(cache_key) is not None:
        return 0
    chunks_needed = 0
    now = datetime.now(timezone.utc)
    from datetime import timedelta
    cursor = now - timedelta(days=backtest.LOOKBACK_DAYS)
    while cursor < now:
        chunk_end = min(cursor + timedelta(days=backtest.QUERY_CHUNK_DAYS), now)
        chunk_cache_key = f"chunk_{intent}_{cursor.strftime('%Y%m%d')}_{chunk_end.strftime('%Y%m%d')}"
        if backtest._load_cache(chunk_cache_key) is None:
            chunks_needed += 1
        cursor = chunk_end
    return chunks_needed * COST_PER_CALL


async def do_research() -> dict:
    """Spend remaining daily budget on the highest priority research.

    Returns a summary of what was done.
    """
    budget = remaining_budget()
    if budget < COST_PER_CALL:
        return {"action": "skip", "reason": "daily research budget exhausted"}

    priorities = _research_priority()
    if not priorities:
        return {"action": "skip", "reason": "all intents cached and fresh"}

    results = {
        "action": "research",
        "budget_remaining_before": budget,
        "intents_attempted": [],
        "intents_completed": [],
        "calls_spent": 0,
        "cost_usd": 0.0,
    }

    for intent, mode in priorities:
        if remaining_budget() < COST_PER_CALL:
            break

        if mode == "recent":
            results["intents_attempted"].append(f"{intent} (recent)")
            print(f"[research] checking recent windows for {intent} "
                  f"(budget: ${remaining_budget():.2f})")
            try:
                recent_results = await backtest.fetch_historical_windows(
                    intent=intent, days_back=7,
                )
                calls_used = max(1, 7 // backtest.QUERY_CHUNK_DAYS)
                record_spend(calls_used)
                results["calls_spent"] += calls_used
                results["intents_completed"].append(f"{intent} (recent)")

                recent_key = f"recent_{intent}_{date.today().isoformat()}"
                backtest._save_cache(recent_key, recent_results)

                ledger.record(
                    "research",
                    intent=intent,
                    mode="recent",
                    windows=len(recent_results),
                    calls=calls_used,
                    cost_usd=round(calls_used * COST_PER_CALL, 2),
                )
            except oracle.BudgetExhausted:
                print(f"[research] ampersend budget hit during {intent}")
                record_spend(1)
                break
            except Exception as exc:
                print(f"[research] error on {intent}: {exc}")
                ledger.record("research_error", intent=intent, reason=str(exc))
            continue

        estimated_cost = _estimate_cost(intent)
        if estimated_cost > remaining_budget():
            max_chunks = int(remaining_budget() / COST_PER_CALL)
            if max_chunks < 5:
                continue

        results["intents_attempted"].append(intent)
        print(f"[research] studying {intent} ({mode}) "
              f"(budget: ${remaining_budget():.2f} remaining)")

        try:
            bt_results = await backtest.run_backtest(intent=intent)

            actual_calls = max(1, len([
                w for w in range(0, backtest.LOOKBACK_DAYS, backtest.QUERY_CHUNK_DAYS)
            ]))
            record_spend(actual_calls)

            results["intents_completed"].append(intent)
            results["calls_spent"] += actual_calls
            results["cost_usd"] = round(results["calls_spent"] * COST_PER_CALL, 2)

            ledger.record(
                "research",
                intent=intent,
                mode=mode,
                windows=bt_results.get("matched_windows", 0),
                calls=actual_calls,
                cost_usd=round(actual_calls * COST_PER_CALL, 2),
            )

        except oracle.BudgetExhausted:
            print(f"[research] ampersend budget hit during {intent}")
            record_spend(1)
            break
        except Exception as exc:
            print(f"[research] error on {intent}: {exc}")
            ledger.record("research_error", intent=intent, reason=str(exc))

    if results["intents_completed"]:
        strategy._build_strategy_from_backtest()
        print(f"[research] strategy rebuilt after studying "
              f"{', '.join(results['intents_completed'])}")

    results["budget_remaining_after"] = remaining_budget()
    return results
