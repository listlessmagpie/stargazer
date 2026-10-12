"""The allocator: one rule for every holding, the sky for a signal, the record for a judge.

Every asset has a table of what it did in the 24 hours after each kind of sky,
learned from six months of windows. From the table for the Moon's current sign
comes a Kelly fraction, which folds together how often that sky paid and how
big the wins ran against the losses. Half of that is the share of the wallet
the asset has earned right now. ETH is home, so it keeps a floor whatever the
sky says, halved when its own record calls the sky bad. Whatever is not held
in an asset rests in dollars.

Then one mechanism does everything:

* an asset worth more than its share, past a band, gets the extra sold into
  dollars. When the price ran up, that is skimming profit. When the Moon moved
  somewhere worse, that is stepping out.
* an asset worth less than its share gets topped up from the dollars. When the
  price fell, that is buying the dip. When the Moon moved somewhere better,
  that is stepping in.
* since shares move with the sky, the wallet trades between its holdings
  without being told to.

An asset with no record earns nothing, which is the whole risk rule. The same
arithmetic would give a roulette wheel a share of zero.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import assets
import ledger
import paper
import positions
import strategy
import trader

HERE = Path(__file__).resolve().parent
STATE_PATH = HERE / "allocator_state.json"

TICK_HOURS = 2
KELLY_SHARE = 0.5          # half Kelly: the estimates are rough
MAX_PER_ASSET = 0.40
MAX_INVESTED = 0.85        # some dollars always stay dollars
BAND = 0.10                # act only when 10% off the target value
MIN_TRADE_USD = 0.50
MIN_SAMPLES = 20
BAD_SKY_KELLY = -0.20
GAS_RESERVE_ETH = 0.0006   # plain ETH kept back for gas; the rest is wrapped and counted
SLIPPAGE_BPS = 100


def _state() -> dict:
    if STATE_PATH.exists():
        with open(STATE_PATH) as f:
            return json.load(f)
    return {"last_tick": 0}


def _save_state(state: dict) -> None:
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def edge(table: dict, sign: str) -> dict:
    row = (table.get("by_moon_sign") or {}).get(sign) or {}
    n = row.get("n_24h", 0)
    return {
        "samples": n,
        "win_rate": row.get("win_rate_24h"),
        "kelly": row.get("kelly_24h") if n >= MIN_SAMPLES else None,
    }


def targets(tables: dict, sign: str) -> dict[str, dict]:
    """The share of the wallet each live asset has earned under this sign."""
    out = {}
    for a in assets.LIVE:
        e = edge(tables.get(a.id, {}), sign)
        k = e["kelly"]
        share = max(0.0, min(MAX_PER_ASSET, (k or 0.0) * KELLY_SHARE))
        if a.home_floor:
            floor = a.home_floor / 2 if (k is not None and k < BAD_SKY_KELLY) else a.home_floor
            share = max(share, floor)
        out[a.id] = {"share": round(share, 4), **e}
    total = sum(t["share"] for t in out.values())
    if total > MAX_INVESTED:
        scale = MAX_INVESTED / total
        for t in out.values():
            t["share"] = round(t["share"] * scale, 4)
    return out


async def snapshot() -> dict:
    """What the wallet holds right now, priced from the pools it trades in."""
    portfolio = await trader.get_portfolio()
    holdings = {}
    for a in assets.LIVE:
        px = assets.price_usd(a)
        bal = float(portfolio.weth) if a.id == "ethereum" else assets.balance(a, portfolio.address)
        holdings[a.id] = {"balance": bal, "price": px, "value": bal * px}
    usdc = float(portfolio.usdc)
    return {
        "usdc": usdc,
        "gas_eth": float(portfolio.eth),
        "holdings": holdings,
        "total": usdc + sum(h["value"] for h in holdings.values()),
        "has_gas": portfolio.has_gas,
        "address": portfolio.address,
    }


def plan(snap: dict, tgt: dict[str, dict], lot_cap_usd: float) -> list[dict]:
    """Sells first, so the dollars they raise can pay for the buys."""
    sells, buys = [], []
    for asset_id, t in tgt.items():
        h = snap["holdings"][asset_id]
        want = t["share"] * snap["total"]
        diff = h["value"] - want
        band = max(MIN_TRADE_USD, want * BAND)
        if diff > band:
            usd = h["value"] if want < MIN_TRADE_USD else diff
            sells.append({"side": "sell", "asset": asset_id, "usd": round(usd, 2),
                          "reason": f"holds ${h['value']:.2f}, share is ${want:.2f}"})
        elif -diff > band:
            usd = min(-diff, lot_cap_usd)
            buys.append({"side": "buy", "asset": asset_id, "usd": round(usd, 2),
                         "reason": f"holds ${h['value']:.2f}, share is ${want:.2f}"})
    dollars = snap["usdc"] + sum(s["usd"] for s in sells)
    kept = []
    for b in sorted(buys, key=lambda b: -b["usd"]):
        b["usd"] = round(min(b["usd"], dollars), 2)
        if b["usd"] >= MIN_TRADE_USD:
            kept.append(b)
            dollars -= b["usd"]
    return sells + kept


async def _wrap_spare_gas(snap: dict, dry: bool) -> float:
    """Plain ETH beyond the gas reserve is ETH she meant to hold. Wrap it so it counts."""
    spare = snap["gas_eth"] - GAS_RESERVE_ETH
    eth_px = snap["holdings"]["ethereum"]["price"]
    if spare * eth_px < MIN_TRADE_USD:
        return 0.0
    if dry:
        return spare
    tx = trader.wrap_eth(Decimal(str(round(spare, 8))))
    positions.open_position(amount_usdc=str(round(spare * eth_px, 2)), moon_sign="", moon_phase="",
                            tx=tx, price=eth_px, asset="ethereum")
    ledger.record("wrap", amount_eth=round(spare, 8), usd=round(spare * eth_px, 2), tx=tx)
    return spare


async def tick(force: bool = False, dry: bool = False) -> dict:
    state = _state()
    if not force and time.time() - state.get("last_tick", 0) < TICK_HOURS * 3600:
        return {"action": "skip", "reason": "ticked recently"}

    sky = await paper._sky()
    tables = await paper._tables()
    snap = await snapshot()
    if not snap["has_gas"] and not dry:
        return {"action": "hold", "reason": "no ETH for gas"}

    wrapped = await _wrap_spare_gas(snap, dry)
    if wrapped:
        if dry:
            h = snap["holdings"]["ethereum"]
            h["balance"] += wrapped
            h["value"] = h["balance"] * h["price"]
            snap["gas_eth"] -= wrapped
            snap["total"] += wrapped * h["price"]
        else:
            snap = await snapshot()

    tgt = targets(tables, sky["moon_sign"])
    lot_cap, tier = strategy.get_trade_size(snap["usdc"], "strong")
    actions = plan(snap, tgt, lot_cap)
    result = {
        "action": "planned" if dry else "ticked",
        "sky": sky, "total": round(snap["total"], 2), "usdc": round(snap["usdc"], 2),
        "holdings": {k: round(v["value"], 2) for k, v in snap["holdings"].items()},
        "targets": {k: v["share"] for k, v in tgt.items()},
        "edges": {k: {"kelly": v["kelly"], "samples": v["samples"]} for k, v in tgt.items()},
        "lot_cap": lot_cap, "wrapped_eth": round(wrapped, 6), "actions": actions,
    }
    if dry:
        return result

    done = []
    for act in actions:
        a = assets.REGISTRY[act["asset"]]
        h = snap["holdings"][a.id]
        try:
            if act["side"] == "sell":
                fraction = min(1.0, act["usd"] / h["value"]) if h["value"] else 0
                amount = h["balance"] * fraction
                tx = await trader.sell_asset(a, amount, h["price"], SLIPPAGE_BPS)
                outcome = positions.reduce_position(fraction, tx, price=h["price"], asset=a.id)
                if outcome:
                    strategy.record_outcome(outcome["entry_price"], outcome["exit_price"],
                                            sky["moon_sign"], sky["moon_phase"])
                ledger.record("sell", asset=a.id, usd=act["usd"], amount=amount, price=h["price"], tx=tx,
                              reason=act["reason"], moon_sign=sky["moon_sign"], moon_phase=sky["moon_phase"],
                              return_pct=outcome["return_pct"] if outcome else None,
                              won=outcome["won"] if outcome else None, target=tgt[a.id]["share"])
            else:
                tx = await trader.buy_asset(a, Decimal(str(act["usd"])), h["price"], SLIPPAGE_BPS)
                positions.open_position(amount_usdc=str(act["usd"]), moon_sign=sky["moon_sign"],
                                        moon_phase=sky["moon_phase"], tx=tx, price=h["price"], asset=a.id)
                ledger.record("buy", asset=a.id, usd=act["usd"], price=h["price"], tx=tx,
                              reason=act["reason"], moon_sign=sky["moon_sign"], moon_phase=sky["moon_phase"],
                              target=tgt[a.id]["share"])
            done.append(f"{act['side']} {a.symbol} ${act['usd']:.2f}")
        except Exception as exc:
            ledger.record("error", reason=str(exc)[:200], asset=a.id, side=act["side"])
            done.append(f"{act['side']} {a.symbol} failed: {str(exc)[:80]}")

    state["last_tick"] = time.time()
    state["last"] = {k: result[k] for k in ("sky", "total", "usdc", "holdings", "targets", "edges")}
    state["last"]["at"] = datetime.now(timezone.utc).isoformat()
    _save_state(state)
    ledger.record("allocate", moon_sign=sky["moon_sign"], moon_phase=sky["moon_phase"], total=result["total"],
                  usdc=result["usdc"], holdings=result["holdings"], targets=result["targets"], done=done,
                  cost_usd=paper.SKY_COST_USD)
    result["done"] = done
    return result


async def maybe_tick() -> dict:
    try:
        return await tick()
    except Exception as exc:
        ledger.record("allocator_error", reason=str(exc)[:200])
        return {"action": "error", "reason": str(exc)}


if __name__ == "__main__":
    import asyncio
    import sys
    live = "--live" in sys.argv
    out = asyncio.run(tick(force=True, dry=not live))
    print(json.dumps(out, indent=2, default=str))
