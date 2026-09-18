"""Signal aggregation: weighs every available factor into one confidence score.

Instead of binary favorable/unfavorable checks, each signal contributes a
weighted score. The agent trades when total confidence exceeds a threshold,
and sizes the trade proportionally to confidence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import tradition

RESULTS_PATH = Path(__file__).parent / "backtest_results.json"


@dataclass
class Signal:
    name: str
    score: float       # -1.0 to +1.0
    weight: float      # how much this signal matters
    reason: str


@dataclass
class Assessment:
    confidence: float              # weighted sum, roughly -1.0 to +1.0
    signals: list[Signal] = field(default_factory=list)
    action: str = "hold"           # "buy", "sell", or "hold"

    @property
    def summary(self) -> str:
        parts = []
        for s in sorted(self.signals, key=lambda x: abs(x.score * x.weight), reverse=True):
            direction = "+" if s.score > 0 else ""
            parts.append(f"{s.name}: {direction}{s.score:.2f} x{s.weight} ({s.reason})")
        return f"confidence={self.confidence:.3f} action={self.action}\n  " + "\n  ".join(parts)


COMMERCE_PATH = Path(__file__).parent / "results" / "backtest_commerce.json"
_TABLES: dict = {"mtime": None, "analysis": {}}


def _analysis() -> dict:
    """The backtest tables the agent trades on, recomputed from the raw correlations.

    Until 2026-09-18 this read a file that held only a cross intent comparison, so
    the tables came back empty and the research never reached a decision. The raw
    correlations are the source of truth; analysing them on load means a change to
    how groups are scored takes effect without paying for the windows again.
    """
    if not COMMERCE_PATH.exists():
        return {}
    mtime = COMMERCE_PATH.stat().st_mtime
    if _TABLES["mtime"] != mtime:
        import backtest
        with open(COMMERCE_PATH) as f:
            rows = json.load(f).get("correlations", [])
        _TABLES["analysis"] = backtest.analyze(rows) if rows else {}
        _TABLES["mtime"] = mtime
    return _TABLES["analysis"]


def _load_backtest_signs() -> dict:
    return _analysis().get("by_moon_sign", {})


def _load_backtest_phases() -> dict:
    return _analysis().get("by_moon_phase", {})


def _edge_score(data: dict) -> tuple[float, str]:
    """Score a group by what betting on it pays, not by how often it wins."""
    win_rate = data.get("win_rate_24h", 50)
    avg_return = data.get("avg_24h", 0)
    kelly = data.get("kelly_24h")
    if kelly is None:
        score = (win_rate - 50) / 50
        return max(-1.0, min(1.0, score)), f"{win_rate:.0f}% win rate, {avg_return:+.3f}% avg 24h"
    ratio = abs(data["avg_win_24h"] / data["avg_loss_24h"]) if data.get("avg_loss_24h") else 0
    return (max(-1.0, min(1.0, kelly)),
            f"{win_rate:.0f}% win rate, wins {ratio:.2f}x losses, {avg_return:+.3f}% avg 24h")


def _sign_score(sign: str, signs_data: dict) -> Signal | None:
    data = signs_data.get(sign)
    if not data or data.get("n_24h", 0) < 10:
        return None
    score, reason = _edge_score(data)
    return Signal(name="moon_sign", score=score, weight=0.35, reason=f"{sign} {reason}")


def _phase_score(phase: str, phases_data: dict) -> Signal | None:
    data = phases_data.get(phase)
    if not data or data.get("n_24h", 0) < 10:
        return None
    score, reason = _edge_score(data)
    return Signal(name="moon_phase", score=score, weight=0.15, reason=f"{phase} {reason}")


def _tradition_signal(
    moon_sign: str, moon_phase: str, waxing: bool,
    void_of_course: bool, retrogrades: list[str],
) -> Signal:
    reading = tradition.assess(moon_sign, moon_phase, waxing, void_of_course, retrogrades)
    factors = reading.factors + [f"! {c}" for c in reading.cautions]
    reason = "; ".join(factors[:3]) if factors else "neutral"
    return Signal(
        name="tradition",
        score=reading.score,
        weight=0.20,
        reason=reason,
    )


def _void_of_course_signal(void_of_course: bool) -> Signal | None:
    if not void_of_course:
        return None
    return Signal(
        name="void_of_course",
        score=-1.0,
        weight=0.25,
        reason="moon void of course, nothing begun now comes to fruition",
    )


def _retrograde_signal(retrogrades: list[str]) -> Signal | None:
    if not retrogrades:
        return None
    financial_planets = {"Mercury", "Venus", "Mars", "Jupiter"}
    active = [r.strip().title() for r in retrogrades if r.strip().title() in financial_planets]
    if not active:
        return None
    severity = len(active) * -0.3
    severity = max(-1.0, severity)
    return Signal(
        name="retrogrades",
        score=severity,
        weight=0.15,
        reason=f"{', '.join(active)} retrograde",
    )


def _waxing_signal(waxing: bool) -> Signal:
    return Signal(
        name="waxing",
        score=0.3 if waxing else -0.3,
        weight=0.05,
        reason="waxing moon (growth)" if waxing else "waning moon (release)",
    )


def _price_trend_signal() -> Signal | None:
    """Check recent ETH price trend via CoinGecko."""
    try:
        import urllib.request
        import json as _json
        url = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd&include_24hr_change=true"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read())
        change_24h = data["ethereum"].get("usd_24h_change", 0)
        if abs(change_24h) < 1.0:
            score = 0.0
            reason = f"ETH flat ({change_24h:+.1f}% 24h)"
        elif change_24h > 0:
            score = min(change_24h / 10, 1.0)
            reason = f"ETH trending up ({change_24h:+.1f}% 24h)"
        else:
            score = max(change_24h / 10, -1.0)
            reason = f"ETH trending down ({change_24h:+.1f}% 24h)"
        return Signal(name="price_trend", score=score, weight=0.10, reason=reason)
    except Exception:
        return None


BUY_THRESHOLD = 0.05
SELL_THRESHOLD = -0.10


def assess_conditions(
    moon_sign: str,
    moon_phase: str,
    waxing: bool,
    void_of_course: bool,
    retrogrades: list[str],
    factors: list[str],
    has_position: bool = False,
    signs_data: dict | None = None,
    phases_data: dict | None = None,
) -> Assessment:
    """Aggregate all available signals into a single assessment.

    The backtest tables default to the agent's own (ETH) results. Pass tables
    for another asset to score the same sky against that asset instead.
    """
    if signs_data is None:
        signs_data = _load_backtest_signs()
    if phases_data is None:
        phases_data = _load_backtest_phases()

    signals = []

    sign_sig = _sign_score(moon_sign, signs_data)
    if sign_sig:
        signals.append(sign_sig)

    phase_sig = _phase_score(moon_phase, phases_data)
    if phase_sig:
        signals.append(phase_sig)

    signals.append(_tradition_signal(moon_sign, moon_phase, waxing, void_of_course, retrogrades))

    voc = _void_of_course_signal(void_of_course)
    if voc:
        signals.append(voc)

    retro = _retrograde_signal(retrogrades)
    if retro:
        signals.append(retro)

    signals.append(_waxing_signal(waxing))

    price = _price_trend_signal()
    if price:
        signals.append(price)

    total_weight = sum(s.weight for s in signals)
    if total_weight == 0:
        return Assessment(confidence=0.0, signals=signals, action="hold")

    confidence = sum(s.score * s.weight for s in signals) / total_weight

    if has_position:
        action = "sell" if confidence < SELL_THRESHOLD else "hold"
    else:
        action = "buy" if confidence > BUY_THRESHOLD else "hold"

    return Assessment(confidence=confidence, signals=signals, action=action)
