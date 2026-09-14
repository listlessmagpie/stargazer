"""Plan trades by scanning ahead instead of polling.

Asks the orrery for all windows in the next 7 days, scores each one
through the signal aggregation system, and returns a schedule of
when to act and what to do. The agent sleeps until the next planned
event instead of waking up every 4 hours to ask "is it time yet?"
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import oracle
import signals

PLAN_PATH = Path(__file__).parent / "plan.json"
LOOKAHEAD_DAYS = 7


@dataclass
class PlannedAction:
    when_utc: str
    action: str
    confidence: float
    strength: str
    moon_sign: str
    moon_phase: str
    waxing: bool
    void_of_course: bool
    retrogrades: list[str]
    factors: list[str]
    orrery_score: int
    signal_summary: str

    @property
    def when(self) -> datetime:
        return datetime.fromisoformat(self.when_utc.replace("Z", "+00:00"))

    def seconds_until(self) -> float:
        delta = self.when - datetime.now(timezone.utc)
        return max(0, delta.total_seconds())

    def hours_until(self) -> float:
        return self.seconds_until() / 3600


async def scan_ahead(
    has_position: bool = False,
    lat: float = 45.52,
    lon: float = -122.68,
) -> list[PlannedAction]:
    """Query the orrery for upcoming windows and score them all.

    Returns planned actions sorted by time, with only actionable
    windows included (confidence above buy threshold or below sell).
    Costs $0.01 per oracle call.
    """
    windows = await oracle.elect(
        intent="commerce",
        lat=lat,
        lon=lon,
        days_ahead=LOOKAHEAD_DAYS,
        top_n=20,
    )

    planned = []
    for w in windows:
        assessment = signals.assess_conditions(
            moon_sign=w.moon_sign,
            moon_phase=w.moon_phase,
            waxing=w.waxing,
            void_of_course=w.void_of_course,
            retrogrades=w.retrogrades,
            factors=w.factors,
            has_position=has_position,
        )

        if assessment.action == "hold":
            continue

        confidence_abs = abs(assessment.confidence)
        if confidence_abs > 0.3:
            strength = "strong"
        elif confidence_abs > 0.1:
            strength = "moderate"
        else:
            strength = "weak"

        planned.append(PlannedAction(
            when_utc=w.when_utc,
            action=assessment.action,
            confidence=assessment.confidence,
            strength=strength,
            moon_sign=w.moon_sign,
            moon_phase=w.moon_phase,
            waxing=w.waxing,
            void_of_course=w.void_of_course,
            retrogrades=w.retrogrades,
            factors=w.factors,
            orrery_score=w.score,
            signal_summary=assessment.summary,
        ))

    planned.sort(key=lambda p: p.when_utc)
    return planned


def save_plan(planned: list[PlannedAction]):
    """Persist the current plan so it survives restarts."""
    data = {
        "planned_at": datetime.now(timezone.utc).isoformat(),
        "actions": [
            {
                "when_utc": p.when_utc,
                "action": p.action,
                "confidence": p.confidence,
                "strength": p.strength,
                "moon_sign": p.moon_sign,
                "moon_phase": p.moon_phase,
                "waxing": p.waxing,
                "void_of_course": p.void_of_course,
                "retrogrades": p.retrogrades,
                "factors": p.factors,
                "orrery_score": p.orrery_score,
            }
            for p in planned
        ],
    }
    with open(PLAN_PATH, "w") as f:
        json.dump(data, f, indent=2)


def load_plan() -> list[PlannedAction] | None:
    """Load a previously saved plan. Returns None if no plan exists."""
    if not PLAN_PATH.exists():
        return None
    with open(PLAN_PATH) as f:
        data = json.load(f)

    now = datetime.now(timezone.utc)
    actions = []
    for a in data.get("actions", []):
        pa = PlannedAction(
            when_utc=a["when_utc"],
            action=a["action"],
            confidence=a["confidence"],
            strength=a["strength"],
            moon_sign=a["moon_sign"],
            moon_phase=a["moon_phase"],
            waxing=a["waxing"],
            void_of_course=a["void_of_course"],
            retrogrades=a["retrogrades"],
            factors=a["factors"],
            orrery_score=a["orrery_score"],
            signal_summary="",
        )
        if pa.when > now:
            actions.append(pa)

    return actions if actions else None


def next_action(planned: list[PlannedAction]) -> PlannedAction | None:
    """Return the soonest planned action that hasn't passed yet."""
    now = datetime.now(timezone.utc)
    for p in planned:
        if p.when > now:
            return p
    return None


def print_plan(planned: list[PlannedAction]):
    """Print the upcoming schedule."""
    if not planned:
        print("[plan] no actionable windows in the next 7 days")
        return

    print(f"[plan] {len(planned)} actionable windows found:")
    for p in planned:
        hours = p.hours_until()
        when_local = p.when_utc[:16].replace("T", " ")
        print(f"  {p.action.upper():4s} | {when_local} UTC "
              f"({hours:.1f}h from now) | "
              f"{p.moon_sign} {p.moon_phase} | "
              f"confidence {p.confidence:+.3f} ({p.strength})")
