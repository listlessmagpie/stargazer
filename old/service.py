"""Stargazer as a service: what the agent learned, for sale over x402.

The agent pays the orrery for sky windows and correlates them with what ETH
did next. That work has value to anyone else trading on timing, so this sells
three things:

* the strategy it learned (which moon signs and phases have paid, and how often),
* the same training run against another asset, using the six months of sky
  windows it already bought, so a caller gets a backtest for their token
  without paying the orrery sixty times,
* its forward plan, the next seven days of windows scored for an asset.

Nothing here trades. Nothing here touches the agent's wallet. The only outbound
payment is the forward plan buying a window scan from the orrery, and that route
is simply absent unless a paying key is configured.
"""

from __future__ import annotations

import json
import os
import time
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any

import httpx
from dotenv import load_dotenv
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

import backtest
import signals
import tradition

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")

API_VERSION = "0.1.0"
CONTRACT = "stargazer.v1"
DATA = HERE / "data" / "windows"
STATIC = HERE / "static"

FREE_MODE = os.getenv("STARGAZER_FREE_MODE") == "1"
PAYTO = os.getenv("PAYTO_ADDRESS", "")
NETWORK = os.getenv("X402_NETWORK", "base")
NETWORK_ID = {"base-sepolia": "eip155:84532", "base": "eip155:8453"}.get(NETWORK, NETWORK)
PAY_KEY = os.getenv("STARGAZER_PAY_KEY", "")
ORRERY = os.getenv("PARADOX_BOX_URL", "https://paradox-box-production.up.railway.app")
PUBLIC_URL = os.getenv("PUBLIC_URL", "https://stargazer-production.up.railway.app")

# Priced above what they cost to serve, and the numbers do not move once published.
# The backtest is the expensive looking one, but the sky windows it needs were
# bought once and are bundled, so serving it costs a few free price calls.
PRICES = {
    "/": "0.0001",
    "/v1/strategy": "0.05",
    "/v1/backtest": "0.50",
}
if PAY_KEY:
    # Costs one orrery call (0.01) to serve, so the margin is real but modest.
    PRICES["/v1/windows"] = "0.05"

DESCRIPTIONS = {
    "/": "Service index with route list and prices",
    "/v1/strategy": "The learned strategy: moon signs and phases ranked by realised 24h return, with sample counts",
    "/v1/backtest": "Train on your asset: six months of sky windows correlated with your token's price history",
    "/v1/windows": "Next seven days of sky windows, scored for an asset with the learned strategy",
}

MIN_DAYS_TO_OFFER = 30

warnings.filterwarnings("ignore")

app = FastAPI(
    title="stargazer",
    version=API_VERSION,
    description="What an astrology trading agent learned, for sale.",
    contact={"email": "listlessmagpie@gmail.com"},
)


# what is bundled


def _windows_available() -> dict[str, list[dict]]:
    """Intents with enough bought windows to be worth selling."""
    out = {}
    for p in sorted(DATA.glob("windows_*_180d.json")):
        intent = p.name[len("windows_"):-len("_180d.json")]
        with open(p) as f:
            windows = json.load(f)
        if not windows:
            continue
        stamps = sorted(w["when_utc"] for w in windows if w.get("when_utc"))
        if not stamps:
            continue
        first = datetime.fromisoformat(stamps[0].replace("Z", "+00:00"))
        last = datetime.fromisoformat(stamps[-1].replace("Z", "+00:00"))
        if (last - first).days >= MIN_DAYS_TO_OFFER:
            out[intent] = windows
    return out


WINDOWS = _windows_available()
INTENTS = sorted(WINDOWS)


def _coverage(intent: str) -> dict:
    ws = WINDOWS[intent]
    stamps = sorted(w["when_utc"] for w in ws)
    return {"windows": len(ws), "from": stamps[0], "to": stamps[-1]}


# prices for any asset, cached in memory for the life of the process

_PRICE_CACHE: dict[str, tuple[float, list]] = {}
PRICE_TTL = 6 * 3600


async def _prices(asset: str, days: int) -> list:
    key = f"{asset}:{days}"
    hit = _PRICE_CACHE.get(key)
    if hit and time.time() - hit[0] < PRICE_TTL:
        return hit[1]
    try:
        series = await backtest.fetch_price_history(days_back=days, asset=asset)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(400, f"unknown CoinGecko asset id {asset!r}")
        raise HTTPException(503, "price source unavailable, nothing was charged")
    if not series:
        raise HTTPException(400, f"no price history for {asset!r}")
    _PRICE_CACHE[key] = (time.time(), series)
    return series


def _train(intent: str, prices: list) -> dict:
    """The agent's own training step, on whichever asset's prices are given."""
    correlations = backtest.correlate(WINDOWS[intent], prices)
    analysis = backtest.analyze(correlations)
    return {"matched_windows": len(correlations), "analysis": analysis}


def _rules(analysis: dict, min_samples: int = 20) -> dict:
    """What the agent would act on, given these tables: the same thresholds it uses."""
    import strategy as strat

    def pick(table: dict, label: str) -> tuple[list, list]:
        good, bad = [], []
        for key, d in table.items():
            n = d.get("n_24h", 0)
            if n < min_samples:
                continue
            wr, avg = d.get("win_rate_24h", 50), d.get("avg_24h", 0)
            row = {label: key, "win_rate_24h": wr, "avg_return_24h": avg, "samples": n}
            if wr >= strat.MIN_WIN_RATE and avg >= strat.MIN_AVG_RETURN:
                good.append(row)
            elif wr < 45 and avg < -0.3:
                bad.append(row)
        return good, bad

    fs, us = pick(analysis.get("by_moon_sign", {}), "sign")
    fp, up = pick(analysis.get("by_moon_phase", {}), "phase")
    return {
        "favorable_signs": fs, "unfavorable_signs": us,
        "favorable_phases": fp, "unfavorable_phases": up,
        "thresholds": {
            "min_win_rate_pct": strat.MIN_WIN_RATE,
            "min_avg_return_pct": strat.MIN_AVG_RETURN,
            "min_samples": min_samples,
        },
    }


# free discovery


@app.get("/llms.txt", response_class=PlainTextResponse, include_in_schema=False)
def llms_txt():
    p = STATIC / "llms.txt"
    if not p.is_file():
        raise HTTPException(404)
    return p.read_text(encoding="utf-8")


@app.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
def robots_txt():
    return "User-agent: *\nAllow: /\n"


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    from fastapi.responses import Response

    p = STATIC / "favicon.svg"
    if not p.is_file():
        raise HTTPException(404)
    return Response(content=p.read_bytes(), media_type="image/svg+xml")


# routes


class DiscoveryBody(BaseModel):
    contract: str | None = None


def _index() -> dict:
    return {
        "service": "stargazer",
        "part_of": "The Paradox Box",
        "contract": CONTRACT,
        "version": API_VERSION,
        "thesis": (
            "An agent that times ETH trades by the sky, and sells what it learned. "
            "Every number here comes from realised prices against bought sky windows, "
            "and every table carries its sample count."
        ),
        "discovery": "GET /llms.txt for a free description of the service and request formats",
        "routes": {
            route: {"price_usdc": price, "network": NETWORK, "description": DESCRIPTIONS[route]}
            for route, price in PRICES.items()
        },
        "intents_available": {i: _coverage(i) for i in INTENTS},
        "guarantees": [
            "failed calls are never charged",
            "no request is stored or logged",
            "every table carries its sample count; nothing is reported without one",
            "the service never trades and holds no position",
        ],
    }


@app.get("/", summary="What this serves and what it costs")
def index() -> dict:
    return _index()


@app.post("/", summary="What this serves and what it costs")
def index_post(body: DiscoveryBody | None = Body(default=None)) -> dict:
    return _index()


class StrategyRequest(BaseModel):
    intent: str = Field("commerce", description="Which intent's windows the strategy was learned on")


@app.post("/v1/strategy", summary="What the agent learned")
async def strategy_route(req: Annotated[StrategyRequest | None, Body()] = None) -> dict[str, Any]:
    intent = (req.intent if req else "commerce")
    if intent not in WINDOWS:
        raise HTTPException(400, f"no trained windows for {intent!r}; available: {INTENTS}")
    prices = await _prices("ethereum", 180)
    trained = _train(intent, prices)
    a = trained["analysis"]
    return {
        "contract": CONTRACT,
        "asset": "ethereum",
        "intent": intent,
        "coverage": _coverage(intent),
        "matched_windows": trained["matched_windows"],
        "rules": _rules(a),
        "by_moon_sign": a.get("by_moon_sign", {}),
        "by_moon_phase": a.get("by_moon_phase", {}),
        "by_void_of_course": a.get("by_void_of_course", {}),
        "by_waxing": a.get("by_waxing", {}),
        "how_it_is_used": (
            "The agent weights moon sign at 0.35 and phase at 0.15 of its confidence, "
            "with tradition, void of course, retrogrades and 24h price trend making up "
            "the rest. It buys above +0.05 confidence and sells below -0.10."
        ),
    }


class BacktestRequest(BaseModel):
    asset: str = Field("ethereum", description="CoinGecko asset id, e.g. 'bitcoin', 'solana'")
    intent: str = Field("commerce", description="Which intent's sky windows to train on")
    days: int = Field(180, ge=30, le=180, description="How far back to correlate")


@app.post("/v1/backtest", summary="Train on your asset")
async def backtest_route(req: Annotated[BacktestRequest, Body()]) -> dict[str, Any]:
    if req.intent not in WINDOWS:
        raise HTTPException(400, f"no trained windows for {req.intent!r}; available: {INTENTS}")
    asset = req.asset.strip().lower()
    prices = await _prices(asset, req.days)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=req.days)).isoformat()
    windows = [w for w in WINDOWS[req.intent] if w.get("when_utc", "") >= cutoff]
    correlations = backtest.correlate(windows, prices)
    if len(correlations) < MIN_DAYS_TO_OFFER:
        raise HTTPException(400, f"only {len(correlations)} windows matched {asset!r} prices")
    a = backtest.analyze(correlations)
    return {
        "contract": CONTRACT,
        "asset": asset,
        "intent": req.intent,
        "days": req.days,
        "coverage": _coverage(req.intent),
        "matched_windows": len(correlations),
        "horizons_hours": backtest.HORIZONS_HOURS,
        "rules": _rules(a),
        "analysis": a,
        "caveat": (
            "Sky windows were computed for Portland, Oregon. Moon sign and phase do not "
            "depend on place; the orrery's score and void of course flag do, slightly."
        ),
    }


class WindowsRequest(BaseModel):
    asset: str = Field("ethereum", description="CoinGecko asset id to score the windows for")
    intent: str = Field("commerce", description="Orrery intent to scan with")
    has_position: bool = Field(False, description="True to get sell windows instead of buy windows")


async def _orrery_windows(intent: str) -> list[dict]:
    from eth_account import Account
    import x402pay

    now = datetime.now(timezone.utc)
    body = {
        "where": [45.52, -122.68],
        "start": now.strftime("%Y-%m-%d"),
        "end": (now + timedelta(days=7)).strftime("%Y-%m-%d"),
        "intent": intent,
        "top_n": 20,
    }
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            data = await x402pay.paid_post(client, f"{ORRERY}/v1/elect", body, Account.from_key(PAY_KEY))
    except Exception as exc:
        raise HTTPException(503, f"the orrery did not answer ({type(exc).__name__}); nothing was charged")
    return data.get("windows", [])


if PAY_KEY:
    @app.post("/v1/windows", summary="The next seven days, scored")
    async def windows_route(req: Annotated[WindowsRequest | None, Body()] = None) -> dict[str, Any]:
        req = req or WindowsRequest()
        if req.intent not in WINDOWS:
            raise HTTPException(400, f"no trained windows for {req.intent!r}; available: {INTENTS}")
        asset = req.asset.strip().lower()
        prices = await _prices(asset, 180)
        a = _train(req.intent, prices)["analysis"]
        raw = await _orrery_windows(req.intent)
        scored = []
        for w in raw:
            assessment = signals.assess_conditions(
                moon_sign=w["moon_sign"], moon_phase=w["moon_phase"], waxing=w["waxing"],
                void_of_course=w["void_of_course"], retrogrades=w.get("retrogrades", []),
                factors=w.get("factors", []), has_position=req.has_position,
                signs_data=a.get("by_moon_sign", {}), phases_data=a.get("by_moon_phase", {}),
            )
            scored.append({
                "when_utc": w["when_utc"],
                "action": assessment.action,
                "confidence": round(assessment.confidence, 3),
                "moon_sign": w["moon_sign"],
                "moon_phase": w["moon_phase"],
                "void_of_course": w["void_of_course"],
                "retrogrades": w.get("retrogrades", []),
                "orrery_score": w.get("score"),
                "signals": [
                    {"name": s.name, "score": round(s.score, 3), "weight": s.weight, "reason": s.reason}
                    for s in assessment.signals
                ],
            })
        scored.sort(key=lambda s: s["when_utc"])
        return {
            "contract": CONTRACT,
            "asset": asset,
            "intent": req.intent,
            "scanned_days": 7,
            "windows": scored,
            "actionable": [s for s in scored if s["action"] != "hold"],
        }


# paywall, attached last so it wraps every priced route

if not FREE_MODE:
    if not PAYTO:
        raise RuntimeError("PAYTO_ADDRESS is not set; refusing to serve paid work for free")

    from cdp.x402 import create_facilitator_config
    from x402.http import HTTPFacilitatorClient, PaymentOption
    from x402.http.middleware.fastapi import PaymentMiddlewareASGI
    from x402.http.types import RouteConfig
    from x402.mechanisms.evm.exact.server import ExactEvmScheme
    from x402.server import x402ResourceServer

    _server = x402ResourceServer(HTTPFacilitatorClient(create_facilitator_config()))
    _server.register(NETWORK_ID, ExactEvmScheme())

    _extensions = {}
    try:
        from x402.extensions.bazaar import (
            bazaar_resource_server_extension,
            declare_discovery_extension,
            OutputConfig,
        )
        _server.register_extension(bazaar_resource_server_extension)
        _extensions = {
            "/v1/strategy": declare_discovery_extension(
                input={"intent": "commerce"},
                input_schema={"type": "object", "properties": {
                    "intent": {"type": "string", "enum": INTENTS, "default": "commerce"}}},
                body_type="json",
                output=OutputConfig(example={
                    "contract": CONTRACT, "asset": "ethereum", "intent": "commerce",
                    "rules": {"favorable_signs": [
                        {"sign": "Aquarius", "win_rate_24h": 62.7, "avg_return_24h": 0.17, "samples": 67}]},
                }),
            ),
            "/v1/backtest": declare_discovery_extension(
                input={"asset": "bitcoin", "intent": "commerce", "days": 180},
                input_schema={"type": "object", "properties": {
                    "asset": {"type": "string", "description": "CoinGecko asset id"},
                    "intent": {"type": "string", "enum": INTENTS, "default": "commerce"},
                    "days": {"type": "integer", "minimum": 30, "maximum": 180, "default": 180},
                }, "required": ["asset"]},
                body_type="json",
                output=OutputConfig(example={
                    "contract": CONTRACT, "asset": "bitcoin", "matched_windows": 600,
                    "rules": {"favorable_signs": []}, "analysis": {"by_moon_sign": {}},
                }),
            ),
            "/v1/windows": declare_discovery_extension(
                input={"asset": "ethereum", "intent": "commerce", "has_position": False},
                input_schema={"type": "object", "properties": {
                    "asset": {"type": "string", "default": "ethereum"},
                    "intent": {"type": "string", "enum": INTENTS, "default": "commerce"},
                    "has_position": {"type": "boolean", "default": False},
                }},
                body_type="json",
                output=OutputConfig(example={
                    "contract": CONTRACT, "asset": "ethereum",
                    "windows": [{"when_utc": "2026-09-19T10:00:00Z", "action": "buy", "confidence": 0.34,
                                 "moon_sign": "Capricorn", "moon_phase": "first_quarter"}],
                }),
            ),
        }
    except Exception as exc:
        warnings.warn(f"Bazaar discovery extensions unavailable: {exc}")

    _routes = {}
    for route, price in PRICES.items():
        _routes[f"* {route}"] = RouteConfig(
            accepts=[PaymentOption(scheme="exact", pay_to=PAYTO, price=price,
                                   network=NETWORK_ID, max_timeout_seconds=300)],
            resource=route,
            description=DESCRIPTIONS[route],
            service_name="Paradox Box Stargazer",
            tags=["astrology", "timing", "trading", "backtest", "signals"],
            icon_url=f"{PUBLIC_URL}/favicon.ico",
            extensions=_extensions.get(route),
        )
    app.add_middleware(PaymentMiddlewareASGI, routes=_routes, server=_server)
