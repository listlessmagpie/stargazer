"""Stargazer: an agent that plans its moves by reading the sky ahead.

Instead of polling every few hours, it asks the orrery for the next
7 days of windows, scores them all, and sleeps until the next
favorable moment. While waiting, it spends its daily research budget
learning from new data.
"""

from __future__ import annotations

import asyncio
import os
import sys
from decimal import Decimal
from pathlib import Path

_HERE = Path(__file__).parent.resolve()
os.chdir(_HERE)
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from dotenv import load_dotenv

load_dotenv(_HERE / ".env")

import experiment
import ledger
import oracle
import paper
import planner
import positions
import research
import scout
import signals
import strategy
import trader

MIN_TRADE_USD = Decimal("0.50")
LOCATION_LAT = float(os.getenv("LOCATION_LAT", "45.52"))
LOCATION_LON = float(os.getenv("LOCATION_LON", "-122.68"))
RESEARCH_INTERVAL_HOURS = 1


async def _run_research():
    """Run a backtest and rebuild the strategy from fresh data."""
    import backtest
    print("[stargazer] running research cycle...")
    await backtest.run_backtest()
    strategy._build_strategy_from_backtest()
    strategy.clear_research_flag()
    print("[stargazer] strategy rebuilt from new research")


POSITION_DUST_USD = 0.25


def _position_usd(portfolio, price: float) -> float:
    return float(portfolio.weth) * price


def _has_position(portfolio, price: float | None = None) -> bool:
    """A position is wrapped ETH worth more than dust. Native ETH is gas, not a bet."""
    return _position_usd(portfolio, price or trader.eth_price()) > POSITION_DUST_USD


async def execute_trade(action: planner.PlannedAction) -> dict:
    """Decide at the appointed time: add to the position, sell it, or stand still."""
    if strategy.needs_research():
        await _run_research()

    portfolio = await trader.get_portfolio()
    price = trader.eth_price()
    position_usd = _position_usd(portfolio, price)
    has_position = position_usd > POSITION_DUST_USD
    wallet_usd = float(portfolio.usdc) + position_usd
    exposure = position_usd / wallet_usd if wallet_usd else 0.0

    assessment = signals.assess_conditions(
        moon_sign=action.moon_sign,
        moon_phase=action.moon_phase,
        waxing=action.waxing,
        void_of_course=action.void_of_course,
        retrogrades=action.retrogrades,
        factors=action.factors,
        has_position=False,
    )
    confidence = assessment.confidence

    result = {
        "moon_sign": action.moon_sign,
        "moon_phase": action.moon_phase,
        "void_of_course": action.void_of_course,
        "waxing": action.waxing,
        "retrogrades": action.retrogrades,
        "factors": action.factors,
        "orrery_score": action.orrery_score,
        "planned_confidence": action.confidence,
        "live_confidence": confidence,
        "signal_count": len(assessment.signals),
        "eth_price": round(price, 2),
        "wallet_usd": round(wallet_usd, 2),
        "exposure": round(exposure, 3),
    }

    if has_position and confidence < signals.SELL_THRESHOLD:
        if not portfolio.has_gas:
            ledger.record("hold", reason="no ETH for gas fees", **result)
            return {"action": "hold", "reason": "no ETH for gas", **result}
        try:
            sell_eth = portfolio.weth
            tx = await trader.swap_eth_to_usdc(sell_eth)
            outcome = positions.close_position(tx=tx)
            if outcome:
                strategy.record_outcome(
                    entry_price=outcome["entry_price"],
                    exit_price=outcome["exit_price"],
                    moon_sign=outcome["moon_sign"],
                    moon_phase=outcome["moon_phase"],
                )
                ledger.record(
                    "swap_eth_to_usdc",
                    amount_eth=str(sell_eth),
                    tx=tx,
                    entry_price=outcome["entry_price"],
                    exit_price=outcome["exit_price"],
                    return_pct=outcome["return_pct"],
                    won=outcome["won"],
                    held_hours=outcome["held_hours"],
                    lots=outcome["lots"],
                    **result,
                )
                won_str = "WIN" if outcome["won"] else "LOSS"
                print(f"[stargazer] SOLD {outcome['lots']} lots: {won_str} "
                      f"{outcome['return_pct']:+.2f}% (held {outcome['held_hours']:.1f}h)")
            else:
                ledger.record("swap_eth_to_usdc", amount_eth=str(sell_eth), tx=tx, **result)
            return {"action": "sell_eth", "amount": str(sell_eth), "tx": tx,
                    "outcome": outcome, **result}
        except Exception as exc:
            ledger.record("error", reason=str(exc), **result)
            return {"action": "error", "reason": str(exc), **result}

    if confidence > signals.BUY_THRESHOLD:
        target, edge = strategy.target_exposure(action.moon_sign)
        result["target_exposure"] = target
        result["edge"] = edge
        room_usd = (target - exposure) * wallet_usd
        if room_usd < float(MIN_TRADE_USD):
            reason = (f"holding {exposure:.0%} of the wallet against a target of {target:.0%} "
                      f"for {action.moon_sign}; no room to add")
            ledger.record("hold", reason=reason, **result)
            return {"action": "hold", "reason": reason, **result}

        confidence_abs = abs(confidence)
        strength = "strong" if confidence_abs > 0.3 else "moderate" if confidence_abs > 0.1 else "weak"
        sized, tier = strategy.get_trade_size(float(portfolio.usdc), strength)
        trade_amount = Decimal(str(round(min(sized, room_usd, float(portfolio.usdc)), 2)))
        result["tier"] = tier
        result["signal_strength"] = strength

        if trade_amount < MIN_TRADE_USD:
            ledger.record("hold", reason="insufficient USDC to trade", **result)
            return {"action": "hold", "reason": "insufficient USDC", **result}
        if not portfolio.has_gas:
            ledger.record("hold", reason="no ETH for gas fees", **result)
            return {"action": "hold", "reason": "no ETH for gas", **result}

        try:
            tx = await trader.swap_usdc_to_eth(trade_amount)
            pos = positions.open_position(
                amount_usdc=str(trade_amount),
                moon_sign=action.moon_sign,
                moon_phase=action.moon_phase,
                tx=tx,
                price=price,
            )
            ledger.record(
                "swap_usdc_to_eth",
                amount_usdc=str(trade_amount),
                entry_price=pos["lot_price"],
                average_entry=round(pos["entry_price"], 2),
                lots=len(pos["lots"]),
                tx=tx,
                **result,
            )
            print(f"[stargazer] BOUGHT ${trade_amount} ETH @ ${pos['lot_price']:.2f} "
                  f"(lot {len(pos['lots'])}, exposure {exposure:.0%} toward {target:.0%})")
            return {"action": "buy_eth", "amount": str(trade_amount), "tx": tx,
                    "entry_price": pos["lot_price"], **result}
        except Exception as exc:
            ledger.record("error", reason=str(exc), **result)
            return {"action": "error", "reason": str(exc), **result}

    reason = f"nothing to do: confidence {confidence:+.3f}, holding={has_position}"
    ledger.record("hold", reason=reason, **result)
    return {"action": "hold", "reason": reason, **result}


async def _do_idle_research():
    """Spend research budget while waiting for the next window."""
    s = await scout.maybe_sample()
    if s.get("action") == "sampled":
        print(f"[stargazer] scout sampled: {', '.join(s['sources'])}")
    pt = await paper.maybe_tick()
    if pt.get("action") == "ticked":
        print(f"[stargazer] paper book: {', '.join(pt['moves']) or 'no moves'}")
    try:
        pub = experiment.publish()
        if pub.get("action") == "published":
            print(f"[stargazer] experiment page published {pub['at']}")
    except Exception as exc:
        print(f"[stargazer] experiment page error: {exc}")
    budget_left = research.remaining_budget()
    if budget_left < research.COST_PER_CALL:
        return
    print(f"[stargazer] researching while waiting (${budget_left:.2f} budget remaining)")
    try:
        r = await research.do_research()
        if r.get("intents_completed"):
            print(f"[stargazer] learned from: {', '.join(r['intents_completed'])} "
                  f"(spent ${r.get('cost_usd', 0):.2f})")
    except Exception as exc:
        print(f"[stargazer] research error: {exc}")


async def run_once() -> None:
    """Scan ahead, show the plan, and execute the first action if it's now."""
    strat = strategy.get_summary()
    print(f"[stargazer] strategy: {strat['source']}, "
          f"favorable: {strat['favorable_signs']}, "
          f"unfavorable: {strat['unfavorable_signs']}")
    print(f"  phases: {strat['favorable_phases']}")
    print(f"  trades: {strat['trades']}, win rate: {strat['win_rate']}%")
    print(f"  tier: max ${strat['tier_max_usd']}, "
          f"{int(strat['tier_fraction']*100)}% of portfolio")

    pos = positions.current_position()
    if pos:
        print(f"  position: LONG ETH @ ${pos['entry_price']:.2f}, "
              f"now ${pos['current_price']:.2f} "
              f"({pos['unrealized_pct']:+.2f}%)")

    portfolio = await trader.get_portfolio()
    has_position = _has_position(portfolio)

    print(f"\n[stargazer] scanning ahead {planner.LOOKAHEAD_DAYS} days...")
    ledger.record("check", usdc=str(portfolio.usdc), eth=str(portfolio.eth), weth=str(portfolio.weth),
                  address=portfolio.address)

    planned = await planner.scan_ahead(
        has_position=has_position, lat=LOCATION_LAT, lon=LOCATION_LON,
    )
    planner.save_plan(planned)
    planner.print_plan(planned)

    nxt = planner.next_action(planned)
    if nxt and nxt.hours_until() < 1:
        print(f"\n[stargazer] next action is in {nxt.hours_until():.1f}h, executing now")
        result = await execute_trade(nxt)
        print(f"  result: {result['action']}")
    elif nxt:
        print(f"\n[stargazer] next move: {nxt.action.upper()} in {nxt.hours_until():.1f}h "
              f"({nxt.moon_sign} {nxt.moon_phase})")
    else:
        print(f"\n[stargazer] no favorable windows ahead, will re-scan in "
              f"{planner.LOOKAHEAD_DAYS} days")

    await _do_idle_research()


async def run_loop() -> None:
    """Plan, wait, execute, repeat.

    The loop is:
    1. Scan ahead 7 days, score every window
    2. If there's a planned action, sleep until it's time
    3. Re-check conditions at execution time (they might have shifted)
    4. Execute (or abort if conditions changed)
    5. Research during idle time
    6. When the plan runs out, scan ahead again
    """
    print(f"[stargazer] starting planner loop")
    print(f"  research budget: ${research.DAILY_BUDGET_USD}/day")

    while True:
        try:
            portfolio = await trader.get_portfolio()
            has_position = _has_position(portfolio)

            print(f"\n[stargazer] scanning ahead {planner.LOOKAHEAD_DAYS} days "
                  f"(portfolio: {portfolio.usdc} USDC, {portfolio.weth:.6f} WETH held, {portfolio.eth:.6f} ETH gas)")
            ledger.record("check", usdc=str(portfolio.usdc), eth=str(portfolio.eth), weth=str(portfolio.weth),
                          address=portfolio.address)

            planned = await planner.scan_ahead(
                has_position=has_position, lat=LOCATION_LAT, lon=LOCATION_LON,
            )
            planner.save_plan(planned)
            planner.print_plan(planned)

            nxt = planner.next_action(planned)

            if not nxt:
                print(f"[stargazer] nothing favorable ahead, researching and "
                      f"re-scanning in {planner.LOOKAHEAD_DAYS} days")
                await _do_idle_research()
                await asyncio.sleep(planner.LOOKAHEAD_DAYS * 24 * 3600)
                continue

            hours_away = nxt.hours_until()
            print(f"[stargazer] next: {nxt.action.upper()} "
                  f"{nxt.moon_sign} {nxt.moon_phase} "
                  f"in {hours_away:.1f}h (confidence {nxt.confidence:+.3f})")

            while nxt.seconds_until() > 60:
                sleep_secs = min(
                    nxt.seconds_until() - 30,
                    RESEARCH_INTERVAL_HOURS * 3600,
                )
                if sleep_secs > 300:
                    await _do_idle_research()
                remaining = nxt.hours_until()
                print(f"[stargazer] waiting {remaining:.1f}h until "
                      f"{nxt.action.upper()} window...")
                await asyncio.sleep(max(60, sleep_secs))

            print(f"\n[stargazer] window open! executing planned "
                  f"{nxt.action.upper()} ({nxt.moon_sign} {nxt.moon_phase})")
            result = await execute_trade(nxt)
            print(f"[stargazer] result: {result['action']}")
            if result.get("tx"):
                print(f"  tx: {result['tx']}")

        except oracle.BudgetExhausted as exc:
            print(f"[stargazer] budget exhausted: {exc}")
            print(f"  sleeping 6 hours before retry")
            await asyncio.sleep(6 * 3600)
        except Exception as exc:
            print(f"[stargazer] error: {exc}")
            ledger.record("error", reason=str(exc))
            await asyncio.sleep(300)


if __name__ == "__main__":
    if "--research" in sys.argv:
        asyncio.run(_run_research())
    elif "--strategy" in sys.argv:
        s = strategy.get_summary()
        for k, v in s.items():
            print(f"  {k}: {v}")
    elif "--tradition" in sys.argv:
        import tradition
        sign = sys.argv[sys.argv.index("--tradition") + 1] if len(sys.argv) > sys.argv.index("--tradition") + 1 else "Scorpio"
        phase = sys.argv[sys.argv.index("--tradition") + 2] if len(sys.argv) > sys.argv.index("--tradition") + 2 else "waxing_gibbous"
        reading = tradition.assess(sign, phase, waxing=True, void_of_course=False, retrogrades=[])
        print(f"[tradition] {sign} {phase}")
        print(f"  score: {reading.score}")
        for f in reading.factors:
            print(f"  + {f}")
        for c in reading.cautions:
            print(f"  ! {c}")
        print(f"\n  {tradition.explain_sign(sign)}")
    elif "--position" in sys.argv:
        pos = positions.current_position()
        if pos:
            print(f"[position] LONG ETH")
            print(f"  entry:  ${pos['entry_price']:.2f} ({pos['entry_time'][:16]})")
            print(f"  now:    ${pos['current_price']:.2f}")
            print(f"  P/L:    {pos['unrealized_pct']:+.2f}%")
            print(f"  sky at entry: {pos['moon_sign']} {pos['moon_phase']}")
        else:
            print("[position] no open position (holding USDC)")
    elif "--budget" in sys.argv:
        budget = research.remaining_budget()
        total = research.DAILY_BUDGET_USD
        spent = total - budget
        ls = ledger.summary()
        print(f"[research budget]")
        print(f"  daily limit: ${total:.2f}")
        print(f"  spent today: ${spent:.2f}")
        print(f"  remaining:   ${budget:.2f}")
        print(f"  total api spend (all time): ${ls['api_spend_usd']:.2f}")
    elif "--paper" in sys.argv:
        for r in paper.summary():
            tag = " (live)" if r["live"] else ""
            print(f"  {r['strategy']}{tag}: {r['closed']} closed, {r['wins']} won, "
                  f"net {r['net_pct']:+.2f}%{', open' if r['open'] else ''}")
    elif "--scout" in sys.argv:
        print(asyncio.run(scout.report()))
    elif "--plan" in sys.argv:
        saved = planner.load_plan()
        if saved:
            planner.print_plan(saved)
            nxt = planner.next_action(saved)
            if nxt:
                print(f"\n  next: {nxt.action.upper()} in {nxt.hours_until():.1f}h")
        else:
            print("[plan] no saved plan, run the agent to scan ahead")
    elif "--loop" in sys.argv:
        asyncio.run(run_loop())
    else:
        asyncio.run(run_once())
