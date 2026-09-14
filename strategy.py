"""Strategy engine: decides whether to trade based on backtest evidence.

Learns from historical correlations and its own trade outcomes.
When performance degrades, triggers new research automatically.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

RESULTS_PATH = Path(__file__).parent / "backtest_results.json"
STRATEGY_PATH = Path(__file__).parent / "strategy.json"

MIN_SAMPLES = 10
MIN_WIN_RATE = 55.0
MIN_TRADE_USD = 0.50
MIN_AVG_RETURN = 0.1


def _load_backtest() -> dict | None:
    if not RESULTS_PATH.exists():
        return None
    with open(RESULTS_PATH) as f:
        return json.load(f)


def _load_strategy() -> dict:
    if STRATEGY_PATH.exists():
        with open(STRATEGY_PATH) as f:
            return json.load(f)
    return _build_strategy_from_backtest()


def _save_strategy(strategy: dict):
    with open(STRATEGY_PATH, "w") as f:
        json.dump(strategy, f, indent=2)


def _build_strategy_from_backtest() -> dict:
    """Extract actionable rules from backtest results."""
    bt = _load_backtest()
    if bt is None:
        return _default_strategy()

    analysis = bt.get("analysis", {})

    if not analysis and bt.get("comparison"):
        commerce_path = Path(__file__).parent / "results" / "backtest_commerce.json"
        if commerce_path.exists():
            with open(commerce_path) as f:
                commerce = json.load(f)
            analysis = commerce.get("analysis", {})
    signs = analysis.get("by_moon_sign", {})
    phases = analysis.get("by_moon_phase", {})

    favorable_signs = []
    unfavorable_signs = []
    for sign, data in signs.items():
        n = data.get("n_24h", 0)
        if n < MIN_SAMPLES:
            continue
        win_rate = data.get("win_rate_24h", 50)
        avg_return = data.get("avg_24h", 0)
        if win_rate >= MIN_WIN_RATE and avg_return >= MIN_AVG_RETURN:
            favorable_signs.append({
                "sign": sign,
                "win_rate_24h": win_rate,
                "avg_return_24h": avg_return,
                "samples": n,
            })
        elif win_rate < 45 and avg_return < -0.3:
            unfavorable_signs.append({
                "sign": sign,
                "win_rate_24h": win_rate,
                "avg_return_24h": avg_return,
                "samples": n,
            })

    favorable_phases = []
    unfavorable_phases = []
    for phase, data in phases.items():
        n = data.get("n_24h", 0)
        if n < MIN_SAMPLES:
            continue
        win_rate = data.get("win_rate_24h", 50)
        avg_return = data.get("avg_24h", 0)
        if win_rate >= MIN_WIN_RATE and avg_return >= MIN_AVG_RETURN:
            favorable_phases.append({
                "phase": phase,
                "win_rate_24h": win_rate,
                "avg_return_24h": avg_return,
                "samples": n,
            })
        elif win_rate < 45 and avg_return < -0.3:
            unfavorable_phases.append({
                "phase": phase,
                "win_rate_24h": win_rate,
                "avg_return_24h": avg_return,
                "samples": n,
            })

    existing = {}
    if STRATEGY_PATH.exists():
        with open(STRATEGY_PATH) as f:
            existing = json.load(f)

    strategy = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "source": "backtest",
        "backtest_windows": bt.get("total_windows", bt.get("matched_windows", 0)),
        "favorable_signs": favorable_signs,
        "unfavorable_signs": unfavorable_signs,
        "favorable_phases": favorable_phases,
        "unfavorable_phases": unfavorable_phases,
        "trade_outcomes": existing.get("trade_outcomes", []),
        "consecutive_losses": existing.get("consecutive_losses", 0),
        "research_triggers": existing.get("research_triggers", 0),
    }

    _save_strategy(strategy)
    return strategy


def _default_strategy() -> dict:
    """Fallback when no backtest exists: observe only."""
    return {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "source": "default",
        "backtest_windows": 0,
        "favorable_signs": [],
        "unfavorable_signs": [],
        "favorable_phases": [],
        "unfavorable_phases": [],
        "trade_outcomes": [],
        "consecutive_losses": 0,
        "research_triggers": 0,
        "observe_only": True,
    }


def should_buy(
    moon_sign: str,
    moon_phase: str,
    void_of_course: bool,
    waxing: bool = True,
    retrogrades: list[str] | None = None,
) -> tuple[bool, str]:
    """Decide whether current conditions favor buying ETH.

    Consults both empirical backtest data and traditional electional
    astrology rules. Returns (should_trade, reasoning).
    """
    import tradition

    strat = _load_strategy()

    if strat.get("observe_only"):
        return False, "no backtest data yet, observing only"

    if strat.get("needs_research"):
        return False, "paused for research after consecutive losses"

    traditional = tradition.assess(
        moon_sign, moon_phase, waxing, void_of_course, retrogrades or [],
    )

    if void_of_course:
        return False, f"void of course, no action ({traditional.cautions[0] if traditional.cautions else 'tradition agrees'})"

    favorable_sign_names = [s["sign"] for s in strat["favorable_signs"]]
    unfavorable_sign_names = [s["sign"] for s in strat["unfavorable_signs"]]
    favorable_phase_names = [p["phase"] for p in strat["favorable_phases"]]
    unfavorable_phase_names = [p["phase"] for p in strat["unfavorable_phases"]]

    sign_favorable = moon_sign in favorable_sign_names
    sign_unfavorable = moon_sign in unfavorable_sign_names
    phase_favorable = moon_phase in favorable_phase_names
    phase_unfavorable = moon_phase in unfavorable_phase_names

    sign_data = next((s for s in strat["favorable_signs"] if s["sign"] == moon_sign), None)
    phase_data = next((p for p in strat["favorable_phases"] if p["phase"] == moon_phase), None)

    reasons = []

    if sign_unfavorable:
        reasons.append(f"{moon_sign} moon historically loses money")
        if traditional.score < 0:
            reasons.append(f"tradition concurs ({traditional.cautions[0]})" if traditional.cautions else "tradition concurs")
        return False, "; ".join(reasons)

    if phase_unfavorable and not sign_favorable:
        reasons.append(f"{moon_phase} historically loses money and {moon_sign} is not strong")
        return False, "; ".join(reasons)

    if traditional.score < -0.3:
        caution_text = "; ".join(traditional.cautions[:2])
        return False, f"tradition strongly advises against: {caution_text}"

    if sign_favorable and phase_favorable:
        sign_wr = sign_data["win_rate_24h"] if sign_data else 0
        phase_wr = phase_data["win_rate_24h"] if phase_data else 0
        reasons.append(f"strong empirical: {moon_sign} ({sign_wr}%) + {moon_phase} ({phase_wr}%)")
        if traditional.factors:
            reasons.append(traditional.factors[0])
        return True, "; ".join(reasons)

    if sign_favorable:
        sign_wr = sign_data["win_rate_24h"] if sign_data else 0
        reasons.append(f"{moon_sign} historically favorable ({sign_wr}%)")
        if traditional.factors:
            reasons.append(traditional.factors[0])
        if traditional.cautions:
            reasons.append(f"(caution: {traditional.cautions[0]})")
        return True, "; ".join(reasons)

    if phase_favorable and not sign_unfavorable:
        phase_wr = phase_data["win_rate_24h"] if phase_data else 0
        reasons.append(f"{moon_phase} historically favorable ({phase_wr}%) and {moon_sign} neutral")
        if traditional.score > 0.2:
            reasons.append("tradition supports")
            return True, "; ".join(reasons)
        return True, "; ".join(reasons)

    if traditional.score > 0.4 and traditional.factors:
        return True, f"tradition favors: {'; '.join(traditional.factors[:2])} (no empirical signal)"

    return False, f"no strong signal: {moon_sign} {moon_phase} is neutral (tradition score: {traditional.score})"


def should_sell(
    moon_sign: str,
    moon_phase: str,
    void_of_course: bool,
    waxing: bool = True,
    retrogrades: list[str] | None = None,
) -> tuple[bool, str]:
    """Decide whether current conditions favor selling ETH back to USDC.

    Sells when conditions turn unfavorable or when void of course.
    Consults both empirical and traditional signals.
    """
    import tradition

    strat = _load_strategy()

    traditional = tradition.assess(
        moon_sign, moon_phase, waxing, void_of_course, retrogrades or [],
    )

    if void_of_course:
        return True, f"void of course, exiting position ({traditional.cautions[0] if traditional.cautions else 'tradition agrees'})"

    unfavorable_sign_names = [s["sign"] for s in strat["unfavorable_signs"]]
    unfavorable_phase_names = [p["phase"] for p in strat["unfavorable_phases"]]

    if moon_sign in unfavorable_sign_names:
        extra = f"; {traditional.cautions[0]}" if traditional.cautions else ""
        return True, f"{moon_sign} moon historically loses money{extra}"

    if moon_phase in unfavorable_phase_names:
        return True, f"{moon_phase} historically unfavorable, exiting"

    if traditional.score < -0.4:
        caution_text = "; ".join(traditional.cautions[:2])
        return True, f"tradition strongly warns: {caution_text}"

    return False, f"{moon_sign} {moon_phase} is not a sell signal (tradition score: {traditional.score})"


def record_outcome(entry_price: float, exit_price: float, moon_sign: str, moon_phase: str):
    """Record a trade outcome and check if research is needed."""
    strategy = _load_strategy()

    pct = (exit_price - entry_price) / entry_price * 100
    won = pct > 0

    outcome = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "moon_sign": moon_sign,
        "moon_phase": moon_phase,
        "return_pct": round(pct, 4),
        "won": won,
    }

    strategy["trade_outcomes"].append(outcome)

    if won:
        strategy["consecutive_losses"] = 0
    else:
        strategy["consecutive_losses"] = strategy.get("consecutive_losses", 0) + 1

    if strategy["consecutive_losses"] >= 3:
        strategy["needs_research"] = True
        strategy["research_triggers"] = strategy.get("research_triggers", 0) + 1

    _save_strategy(strategy)
    return outcome


def needs_research() -> bool:
    """Check if the strategy has flagged itself for re-research."""
    strategy = _load_strategy()
    return strategy.get("needs_research", False) or strategy.get("observe_only", False)


def clear_research_flag():
    """Clear the research flag after a new backtest completes."""
    strategy = _load_strategy()
    strategy["needs_research"] = False
    strategy["observe_only"] = False
    _save_strategy(strategy)


TRADE_TIERS = [
    {"min_wins": 0,  "max_usd": 0.50,  "fraction": 0.05},
    {"min_wins": 3,  "max_usd": 1.00,  "fraction": 0.08},
    {"min_wins": 6,  "max_usd": 2.00,  "fraction": 0.10},
    {"min_wins": 10, "max_usd": 3.00,  "fraction": 0.15},
    {"min_wins": 15, "max_usd": 5.00,  "fraction": 0.20},
    {"min_wins": 25, "max_usd": 10.00, "fraction": 0.25},
]


SIGNAL_MULTIPLIERS = {
    "strong": 1.0,    # both sign and phase favorable
    "moderate": 0.7,  # one of sign or phase favorable
    "weak": 0.4,      # tradition only, no empirical signal
}


def get_trade_size(
    portfolio_usdc: float,
    signal_strength: str = "moderate",
) -> tuple[float, dict]:
    """Return the trade amount and current tier based on proven performance.

    Starts at $0.50 max / 5% of portfolio. Scales up as wins accumulate.
    Drops back one tier after 2 consecutive losses.
    Signal strength scales the amount within the tier.
    """
    strat = _load_strategy()
    outcomes = strat.get("trade_outcomes", [])
    wins = sum(1 for o in outcomes if o["won"])
    consecutive_losses = strat.get("consecutive_losses", 0)

    if consecutive_losses >= 2:
        wins = max(0, wins - 3)

    tier = TRADE_TIERS[0]
    for t in TRADE_TIERS:
        if wins >= t["min_wins"]:
            tier = t

    multiplier = SIGNAL_MULTIPLIERS.get(signal_strength, 0.7)
    amount = min(portfolio_usdc * tier["fraction"], tier["max_usd"]) * multiplier
    # A swap under fifty cents is not worth its gas, and on a small wallet the
    # first tier's 5% never reaches that, so the floor wins as long as the
    # wallet can cover it. The tier cap still holds above it.
    if portfolio_usdc >= MIN_TRADE_USD:
        amount = max(amount, min(MIN_TRADE_USD, tier["max_usd"]))
    return round(amount, 2), tier


def get_summary() -> dict:
    """Return a summary of the current strategy state."""
    strat = _load_strategy()
    outcomes = strat.get("trade_outcomes", [])
    wins = sum(1 for o in outcomes if o["won"])
    total = len(outcomes)

    _, tier = get_trade_size(10.0)

    return {
        "source": strat.get("source", "unknown"),
        "backtest_windows": strat.get("backtest_windows", 0),
        "favorable_signs": [s["sign"] for s in strat.get("favorable_signs", [])],
        "unfavorable_signs": [s["sign"] for s in strat.get("unfavorable_signs", [])],
        "favorable_phases": [p["phase"] for p in strat.get("favorable_phases", [])],
        "unfavorable_phases": [p["phase"] for p in strat.get("unfavorable_phases", [])],
        "trades": total,
        "wins": wins,
        "win_rate": round(wins / total * 100, 1) if total else 0,
        "consecutive_losses": strat.get("consecutive_losses", 0),
        "needs_research": strat.get("needs_research", False),
        "observe_only": strat.get("observe_only", False),
        "tier_max_usd": tier["max_usd"],
        "tier_fraction": tier["fraction"],
        "tier_min_wins": tier["min_wins"],
    }
