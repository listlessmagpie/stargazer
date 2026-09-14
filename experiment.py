"""The lab notebook: turn the ledger into a page anyone can read, and publish it.

Stargazer is an experiment in public. The question is whether the sky says
anything about ETH, measured at fifty cents a bet with real money. This module
writes EXPERIMENT.md from the agent's own records and pushes it to the repo
every few hours, so the answer accumulates where anyone can watch it.

What goes out: balances, every trade and what followed, win rate and tier,
research spend, and the scout's grades. What stays home: keys, wallet
addresses, and the raw readings the scout buys from other services (those are
theirs to sell; only what we derived from them is ours to show).
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import ledger

HERE = Path(__file__).resolve().parent
PAGE = HERE / "EXPERIMENT.md"
STRATEGY_PATH = HERE / "strategy.json"
STAMP_PATH = HERE / "experiment_published.json"
PUBLISH_EVERY_HOURS = 6


def _fmt_ts(iso: str) -> str:
    return iso[:16].replace("T", " ") + " UTC"


def _balance_rows(entries: list[dict]) -> list[dict]:
    return [e for e in entries if e["event"] == "check"]


def _first_and_latest(checks: list[dict]) -> tuple[dict | None, dict | None]:
    if not checks:
        return None, None
    return checks[0], checks[-1]


def build() -> str:
    entries = ledger.read_all()
    checks = _balance_rows(entries)
    first, latest = _first_and_latest(checks)
    trades = [e for e in entries if e["event"] in ("swap_usdc_to_eth", "swap_eth_to_usdc")]
    sells = [e for e in trades if e["event"] == "swap_eth_to_usdc" and "won" in e]
    holds = [e for e in entries if e["event"] == "hold"]
    errors = [e for e in entries if e["event"] == "error"]
    research_spend = sum(e.get("cost_usd", 0) for e in entries if e["event"] == "research")
    scout_spend = sum(e.get("cost_usd", 0) for e in entries if e["event"] == "scout")
    wins = sum(1 for e in sells if e.get("won"))

    strategy = {}
    if STRATEGY_PATH.exists():
        with open(STRATEGY_PATH) as f:
            strategy = json.load(f)

    now = datetime.now(timezone.utc)
    lines = [
        "# Stargazer, a running experiment",
        "",
        "Does the sky say anything about ETH? This agent buys electional windows from the",
        "orrery, correlates six months of them with what the price did next, and bets fifty",
        "cents at a time on what held up. It earns bigger bets only by winning. Everything",
        "below is generated from its own ledger; nothing is typed by hand.",
        "",
        f"Updated {now.strftime('%Y-%m-%d %H:%M UTC')}.",
        "",
        "## The number",
        "",
    ]
    if first and latest:
        lines += [
            "| | USDC | ETH |",
            "|---|---|---|",
            f"| started {_fmt_ts(first['ts'])} | {first['usdc']} | {first['eth']} |",
            f"| now {_fmt_ts(latest['ts'])} | {latest['usdc']} | {latest['eth']} |",
            "",
            "USDC is the stake. ETH is what it holds between a buy and a sell, plus a sliver kept",
            "for gas. Money it spends on research and the scout comes from a separate wallet and",
            "is counted below, not here.",
            "",
        ]
    else:
        lines += ["No balance recorded yet.", ""]

    lines += [
        "## Trades",
        "",
        f"{len(trades)} trades, {len(sells)} closed, {wins} won.",
        "",
    ]
    if trades:
        lines += ["| when | action | amount | sky | result |", "|---|---|---|---|---|"]
        for t in trades:
            sky = f"Moon in {t.get('moon_sign', '?')}, {str(t.get('moon_phase', '?')).replace('_', ' ')}"
            if t["event"] == "swap_usdc_to_eth":
                amount = f"{t.get('amount_usdc', '?')} USDC at ${t.get('entry_price', 0):.2f}"
                result = "open"
            else:
                amount = f"{t.get('amount_eth', '?')} ETH at ${t.get('exit_price', 0):.2f}"
                result = ("won" if t.get("won") else "lost") if "won" in t else "closed"
                if t.get("return_pct") is not None:
                    result += f" {t['return_pct']:+.2f}% over {t.get('held_hours', 0):.0f}h"
            lines.append(f"| {_fmt_ts(t['ts'])} | {t['event'].replace('swap_', '').replace('_to_', ' to ')} | {amount} | {sky} | {result} |")
        lines.append("")

    lines += [
        "## What it is betting on",
        "",
        "Learned from the backtest, refreshed as research runs. A sign or phase counts as",
        "favourable at a 55% win rate and a positive mean 24h return over enough samples.",
        "",
    ]
    fav = strategy.get("favorable_signs", [])
    unf = strategy.get("unfavorable_signs", [])
    if fav or unf:
        lines += ["| moon sign | 24h win rate | mean 24h return | samples | verdict |", "|---|---|---|---|---|"]
        for s in fav:
            lines.append(f"| {s['sign']} | {s['win_rate_24h']:.0f}% | {s['avg_return_24h']:+.2f}% | {s['samples']} | favourable |")
        for s in unf:
            lines.append(f"| {s['sign']} | {s['win_rate_24h']:.0f}% | {s['avg_return_24h']:+.2f}% | {s['samples']} | unfavourable |")
        lines.append("")
    for key, label in (("favorable_phases", "favourable"), ("unfavorable_phases", "unfavourable")):
        for p in strategy.get(key, []):
            lines.append(f"* {p['phase'].replace('_', ' ')}: {p['win_rate_24h']:.0f}% win rate, "
                         f"{p['avg_return_24h']:+.2f}% mean, {p['samples']} samples, {label}")
    if strategy.get("favorable_phases") or strategy.get("unfavorable_phases"):
        lines.append("")
    tier_wins = wins
    lines += [
        f"Trade size tier: {tier_wins} wins so far. The ladder is 0 wins for $0.50, 3 for $1, "
        "6 for $2, 10 for $3, 15 for $5, 25 for $10. Two losses in a row drop it a rung.",
        "",
        "## What it costs to think",
        "",
        f"* Research (backtests bought from the orrery at a cent a call): ${research_spend:.2f}",
        f"* Scout (outside data feeds on trial, graded against the 24h return): ${scout_spend:.2f}",
        f"* Held instead of trading: {len(holds)} times",
        f"* Errors: {len(errors)}",
        "",
    ]

    report = HERE / "scout_report.md"
    if report.exists():
        body = report.read_text(encoding="utf-8").split("\n", 2)
        lines += ["## Scout", "", "Outside feeds being graded. A candidate is a proposal to a person, never adopted by the agent.", ""]
        lines += [ln for ln in body[2].splitlines() if not ln.startswith("# ")] if len(body) > 2 else []
        lines.append("")

    lines += [
        "## How to read this honestly",
        "",
        "* Sample sizes are small. A 60% win rate over 50 windows is a coin that came up heads a",
        "  few extra times. Watch whether it holds as the count grows.",
        "* Every trade pays gas and a spread. Small bets lose a larger share to both.",
        "* The agent never sees this page and does not tune itself to look good on it.",
        "",
        "Source and method in this repo. The sky comes from [The Paradox Box]"
        "(https://github.com/listlessmagpie/paradox-box).",
        "",
    ]
    return "\n".join(lines)


def write() -> Path:
    PAGE.write_text(build(), encoding="utf-8")
    return PAGE


def _last_published() -> float:
    if STAMP_PATH.exists():
        with open(STAMP_PATH) as f:
            return json.load(f).get("ts", 0)
    return 0


def publish(force: bool = False) -> dict:
    """Write the page and push it, if it is time and the repo has a remote."""
    now = datetime.now(timezone.utc).timestamp()
    if not force and now - _last_published() < PUBLISH_EVERY_HOURS * 3600:
        return {"action": "skip", "reason": "published recently"}
    write()

    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=HERE, capture_output=True, text=True)

    if git("remote").stdout.strip() == "":
        return {"action": "written", "reason": "no remote, page written only"}
    git("add", "EXPERIMENT.md")
    if git("diff", "--cached", "--quiet", "--", "EXPERIMENT.md").returncode == 0:
        return {"action": "skip", "reason": "page unchanged"}
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    commit = git("commit", "-q", "-m", f"Experiment page, {stamp}", "--", "EXPERIMENT.md")
    if commit.returncode != 0:
        return {"action": "error", "reason": commit.stderr[:200]}
    push = git("push", "-q")
    with open(STAMP_PATH, "w") as f:
        json.dump({"ts": now}, f)
    if push.returncode != 0:
        return {"action": "error", "reason": push.stderr[:200]}
    return {"action": "published", "at": stamp}


if __name__ == "__main__":
    import sys
    if "--publish" in sys.argv:
        print(publish(force=True))
    else:
        print(write().read_text(encoding="utf-8"))
