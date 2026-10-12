"""The almanac: what the sky was doing, and what actually happened, over many years.

This computes the sky for every day back to 2005 (Moon, Sun and planets by sign, the
Moon's phase, retrogrades and stations, every aspect between the planets, a count of
hard aspects among the difficult planets, eclipse windows) and, for every chart in the
library that belongs to a market (the market's own birth and every person or body with
an edge onto it), every transit of every body to every point of that chart, each aspect
its own factor, the transiting Moon included, angles when the birth time is recorded,
antiscia and midpoints too. Then it sets each factor against what the market did next:
Bitcoin, Ethereum, the S&P 500, gold, oil, and the VIX.

Test tens of thousands of patterns and some will look brilliant by pure luck. Two
guards against that. Every pattern is learned on the years before 2021 and must then
show the same effect on the years after, which it never saw. And the whole study is
rerun a hundred times with the sky slid out of step with the calendar, so the sky is
real but belongs to the wrong days: however many patterns pass on those scrambled
skies is what luck alone produces, and the real count only means something by how far
it stands above that.

The rules are registered in registry/ before this runs. Nothing here is tuned after.

Run with the orrery's Python, which has the ephemeris:
    D:/git/paradox-box/.venv/Scripts/python.exe almanac.py            # family 1, the per factor study
    ... almanac.py --whole                                            # the whole sky forecaster, judged
    ... almanac.py --occasions                                        # family 2, occasion by occasion
    ... almanac.py --forecast                                         # today's forecasts, old ones scored
    ... almanac.py --daily                                            # forecast, refresh, record for the site
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import numpy as np

sys.path.insert(0, "D:/git/paradox-box")
import orrery.moment  # noqa: F401,E402  (sets the ephemeris path)
import swisseph as swe  # noqa: E402

import charts  # noqa: E402

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
RESULTS = HERE / "almanac_results.json"
PAGE = HERE / "ALMANAC.md"

START = date(2005, 1, 1)
SPLIT = date(2021, 1, 1)
HORIZONS = (1, 5)
ORB = 3.0
N_SHIFTS = 100
Z_TRAIN, Z_TEST = 2.5, 1.5
MIN_DAYS, MIN_EPISODES = 60, 8

MARKETS = {
    "bitcoin": "BTC-USD", "ethereum": "ETH-USD", "sp500": "^GSPC",
    "gold": "GC=F", "oil": "CL=F", "vix": "^VIX",
}
BODIES = charts.BODIES
SIGNS = ["aries", "taurus", "gemini", "cancer", "leo", "virgo", "libra", "scorpio",
         "sagittarius", "capricorn", "aquarius", "pisces"]
PHASES = ["new_moon", "waxing_crescent", "first_quarter", "waxing_gibbous",
          "full_moon", "waning_gibbous", "last_quarter", "waning_crescent"]
ASPECTS = {"conj": 0, "sext": 60, "sq": 90, "tri": 120, "opp": 180}
HARD = ("conj", "sq", "opp")
DIFFICULT = ("mars", "saturn", "uranus", "neptune", "pluto")

LIB = charts.load()


# ---------- the sky ----------

def build_sky(days: list[date]) -> tuple[list[str], np.ndarray, dict[str, np.ndarray]]:
    """One row per day, one boolean column per sky factor. Computed at noon UTC."""
    n = len(days)
    lon = {b: np.zeros(n) for b in BODIES}
    speed = {b: np.zeros(n) for b in BODIES}
    for i, d in enumerate(days):
        jd = swe.julday(d.year, d.month, d.day, 12.0)
        for name, body in BODIES.items():
            xx = swe.calc_ut(jd, body, swe.FLG_SWIEPH | swe.FLG_SPEED)[0]
            lon[name][i], speed[name][i] = xx[0], xx[3]

    cols: dict[str, np.ndarray] = {}
    for b in ("moon", "sun", "mercury", "venus", "mars", "jupiter", "saturn"):
        idx = (lon[b] // 30).astype(int)
        for s, sign in enumerate(SIGNS):
            cols[f"{b}_in_{sign}"] = idx == s
    elong = (lon["moon"] - lon["sun"]) % 360
    for p, phase in enumerate(PHASES):
        cols[f"moon_{phase}"] = (elong // 45).astype(int) == p
    for b in ("mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune", "pluto"):
        retro = speed[b] < 0
        cols[f"{b}_retrograde"] = retro
        if b in ("mercury", "venus", "mars"):
            turn = np.zeros(n, bool)
            flips = np.nonzero(retro[1:] != retro[:-1])[0] + 1
            for f in flips:
                turn[max(0, f - 2):f + 3] = True
            cols[f"{b}_station"] = turn

    names = [b for b in BODIES if b != "moon"]
    tension = np.zeros(n, int)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            sep = np.abs((lon[a] - lon[b] + 180) % 360 - 180)
            for asp, angle in ASPECTS.items():
                active = np.abs(sep - angle) <= ORB
                cols[f"{a}_{asp}_{b}"] = active
                if asp in HARD and a in DIFFICULT and b in DIFFICULT:
                    tension += active
    cols["tension_1plus"] = tension >= 1
    cols["tension_2plus"] = tension >= 2

    jd0 = swe.julday(days[0].year, days[0].month, days[0].day, 0.0)
    jd1 = swe.julday(days[-1].year, days[-1].month, days[-1].day, 0.0)
    for label, finder in (("solar_eclipse", lambda j: swe.sol_eclipse_when_glob(j, swe.FLG_SWIEPH, 0)),
                          ("lunar_eclipse", lambda j: swe.lun_eclipse_when(j, swe.FLG_SWIEPH, 0))):
        win = np.zeros(n, bool)
        j = jd0
        while j < jd1:
            peak = finder(j)[1][0]
            k = int(round(peak - jd0))
            if 0 <= k < n:
                win[max(0, k - 3):k + 4] = True
            j = peak + 10
        cols[f"{label}_window"] = win

    keys = sorted(cols)
    return keys, np.column_stack([cols[k] for k in keys]).astype(np.float64), lon


# ---------- the charts, from the library ----------
#
# An astrologer does not only ask what the sky is doing. They ask what the sky is doing
# to this thing's chart, and to the charts of whoever acts on it. Every node in the
# library with a real birth moment and an edge onto the market becomes a block of
# factors: every transiting body, every aspect, every point. Blocks are computed one at
# a time and never held together, because a market can carry tens of thousands.

def market_blocks(market: str, keys: list[str], sky: np.ndarray, lon: dict):
    """Yield (label, keys, matrix) for the sky and for each chart connected to the market."""
    yield "sky", keys, sky
    for node_key in charts.charts_for_market(LIB, market):
        tkeys, T = charts.transit_factors(lon, LIB["nodes"][node_key], prefix=f"t_{node_key}")
        if tkeys:
            yield node_key, tkeys, T


def own_chart_matrix(market: str, keys: list[str], sky: np.ndarray, lon: dict) -> tuple[list[str], np.ndarray]:
    """Sky plus the market's own birth chart, for the whole sky forecaster. People are left
    for families 3 and 4, which read them against acts, not against every day."""
    node = LIB["nodes"].get(market, {})
    if not node.get("date"):
        return keys, sky
    tkeys, T = charts.transit_factors(lon, node, prefix=f"t_{market}")
    return keys + tkeys, np.hstack([sky, T])


def factor_column(market: str, factor: str, keys: list[str], sky: np.ndarray, lon: dict) -> np.ndarray:
    """One factor's daily column, computing only the block it lives in."""
    if factor in keys:
        return sky[:, keys.index(factor)]
    for node_key in [market] + [e["from"] for e in LIB["edges"] if e["on"] == market]:
        if factor.startswith(f"t_{node_key}_"):
            tkeys, T = charts.transit_factors(lon, LIB["nodes"][node_key], prefix=f"t_{node_key}")
            return T[:, tkeys.index(factor)]
    raise KeyError(factor)


def chart_label(market: str) -> str:
    node = LIB["nodes"].get(market, {})
    return node.get("label", market) if node.get("date") else "no chart"


# ---------- prices ----------

def fetch_prices(symbol: str) -> list[tuple[date, float]]:
    path = CACHE / f"almanac_px_{symbol.replace('^', '').replace('=', '')}.json"
    if path.exists() and time.time() - path.stat().st_mtime < 86400:
        return [(date.fromisoformat(d), c) for d, c in json.loads(path.read_text())]
    p1 = int(datetime(START.year, START.month, START.day, tzinfo=timezone.utc).timestamp())
    r = httpx.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                  params={"period1": p1, "period2": int(time.time()), "interval": "1d"},
                  headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    closes = res["indicators"]["quote"][0]["close"]
    out, seen = [], set()
    for t, c in zip(res["timestamp"], closes):
        d = datetime.fromtimestamp(t, timezone.utc).date()
        if c and d not in seen:
            seen.add(d)
            out.append((d, float(c)))
    CACHE.mkdir(exist_ok=True)
    path.write_text(json.dumps([(d.isoformat(), c) for d, c in out]))
    return out


# ---------- the test ----------

def _z(F: np.ndarray, r: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """For every factor at once: days active, mean return active minus inactive, and its z."""
    T = len(r)
    n1 = F.sum(0)
    n0 = T - n1
    s1 = F.T @ r
    with np.errstate(divide="ignore", invalid="ignore"):
        m1 = s1 / n1
        m0 = (r.sum() - s1) / n0
        z = (m1 - m0) / (r.std() * np.sqrt(1 / n1 + 1 / n0))
    return n1, m1 - m0, np.nan_to_num(z)


def _episodes_all(M: np.ndarray) -> np.ndarray:
    """Separate stretches per column, vectorised."""
    B = M > 0
    starts = B[1:] & ~B[:-1]
    return B[0].astype(int) + starts.sum(0)


def study() -> dict:
    today = datetime.now(timezone.utc).date()
    days = [START + timedelta(days=i) for i in range((today - START).days + 1)]
    print(f"computing the sky for {len(days)} days...", flush=True)
    keys, sky, lon = build_sky(days)
    day_index = {d: i for i, d in enumerate(days)}

    rng = np.random.default_rng(20261012)
    survivors, moon_rows, tests, factors_total = [], [], 0, 0
    real_pass = 0
    null_pass = np.zeros(N_SHIFTS)
    blocks_used: dict[str, list[str]] = {}

    for market, symbol in MARKETS.items():
        px = fetch_prices(symbol)
        print(f"{market}: {len(px)} trading days from {px[0][0]}", flush=True)
        dates = [d for d, _ in px]
        close = np.array([c for _, c in px])
        rows = np.array([day_index[d] for d in dates])
        blocks_used[market] = []
        # one set of shifts per market and horizon, shared by every block, so a scrambled
        # run is one scrambled sky and not a different scramble per chart
        shifts = {h: rng.integers(90, len(rows) - h - 90, size=N_SHIFTS) for h in HORIZONS}
        for label, bkeys, B in market_blocks(market, keys, sky, lon):
            blocks_used[market].append(f"{label} ({len(bkeys)})")
            factors_total += len(bkeys)
            eligible_b = (B.sum(0) >= MIN_DAYS) & (_episodes_all(B) >= MIN_EPISODES)
            F_full = B[rows]
            for h in HORIZONS:
                r = close[h:] / close[:-h] - 1.0
                F = F_full[:-h]
                dts = dates[:-h]
                train = np.array([d < SPLIT for d in dts])
                if train.sum() < 250 or (~train).sum() < 250:
                    continue
                elig = eligible_b & (F[train].sum(0) >= 30) & (F[~train].sum(0) >= 20)
                tests += int(elig.sum())
                if not elig.any():
                    continue

                def passes(Fm):
                    n_tr, d_tr, z_tr = _z(Fm[train], r[train])
                    n_te, d_te, z_te = _z(Fm[~train], r[~train])
                    ok = elig & (np.abs(z_tr) >= Z_TRAIN) & (np.sign(z_tr) == np.sign(z_te)) & (np.abs(z_te) >= Z_TEST)
                    return ok, (n_tr, d_tr, z_tr, n_te, d_te, z_te)

                ok, (n_tr, d_tr, z_tr, n_te, d_te, z_te) = passes(F)
                real_pass += int(ok.sum())
                for k in np.nonzero(ok)[0]:
                    act = F[~train][:, k] > 0
                    survivors.append({
                        "market": market, "horizon_days": h, "factor": bkeys[k], "block": label,
                        "learned": {"days": int(n_tr[k]), "effect_pct": round(d_tr[k] * 100, 3), "z": round(z_tr[k], 2)},
                        "confirmed": {"days": int(n_te[k]), "effect_pct": round(d_te[k] * 100, 3), "z": round(z_te[k], 2),
                                      "up_rate_pct": round(float((r[~train][act] > 0).mean()) * 100, 1)},
                    })
                if label == "sky" and market in ("bitcoin", "ethereum") and h == 1:
                    for k, name in enumerate(bkeys):
                        if name.startswith("moon_in_"):
                            moon_rows.append({"market": market, "factor": name,
                                              "learned_effect_pct": round(d_tr[k] * 100, 3), "learned_z": round(z_tr[k], 2),
                                              "confirmed_effect_pct": round(d_te[k] * 100, 3), "confirmed_z": round(z_te[k], 2)})
                for s in range(N_SHIFTS):
                    null_pass[s] += int(passes(np.roll(F, int(shifts[h][s]), axis=0))[0].sum())
            print(f"  {label}: {len(bkeys)} factors, running total {real_pass} passed of {tests} tests", flush=True)

    survivors.sort(key=lambda x: -abs(x["confirmed"]["z"]))
    out = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "from": START.isoformat(), "split": SPLIT.isoformat(),
        "factors": factors_total, "tests": tests,
        "passed": real_pass,
        "luck": {"mean": round(float(null_pass.mean()), 1), "p95": float(np.percentile(null_pass, 95)),
                 "max": float(null_pass.max()), "runs": N_SHIFTS,
                 "share_of_runs_at_or_above_real": round(float((null_pass >= real_pass).mean()), 3)},
        "blocks": blocks_used,
        "survivors": survivors, "moon_signs_long_run": moon_rows,
        "registered": "registry/2026-10-12-family-1-timing-windows.md",
    }
    RESULTS.write_text(json.dumps(out, indent=2))
    return out


def _ridge(X: np.ndarray, y: np.ndarray, lam: float) -> np.ndarray:
    return np.linalg.solve(X.T @ X + lam * np.eye(X.shape[1]), X.T @ y)


def whole_sky() -> dict:
    """The entire sky at once: one model per market, learned before the split, judged after.

    Each day is a row of every sky factor. A ridge regression learns, from the
    early years, how the whole configuration went with the next five days. The
    penalty is chosen inside the early years only. Then the model forecasts the
    later years it never saw, and is scored three ways: does its forecast move
    with what happened, how often does it call the direction, and what would
    holding only when it says up have made against simply holding. The same
    scrambled sky reruns say how much of that luck alone would give.
    """
    today = datetime.now(timezone.utc).date()
    days = [START + timedelta(days=i) for i in range((today - START).days + 1)]
    keys, sky, lon = build_sky(days)
    only = [a[len('--market='):] for a in sys.argv if a.startswith('--market=')]
    day_index = {d: i for i, d in enumerate(days)}
    rng = np.random.default_rng(20261012)
    h = 5
    out = {}
    for market, symbol in MARKETS.items():
        if only and market not in only:
            continue
        px = fetch_prices(symbol)
        dates = [d for d, _ in px][:-h]
        close = np.array([c for _, c in px])
        r = close[h:] / close[:-h] - 1.0
        rows = np.array([day_index[d] for d in dates])
        variants = {"sky": sky}
        if LIB["nodes"].get(market, {}).get("date"):
            variants["sky_and_chart"] = own_chart_matrix(market, keys, sky, lon)[1]
        train = np.array([d < SPLIT for d in dates])

        def score(Fm: np.ndarray) -> dict:
            mu, sd = Fm[train].mean(0), Fm[train].std(0) + 1e-9
            X = (Fm - mu) / sd
            Xtr, ytr = X[train], r[train] - r[train].mean()
            cut = int(len(Xtr) * 0.7)
            best = min((1e2, 1e3, 1e4, 1e5),
                       key=lambda lam: np.mean((Xtr[cut:] @ _ridge(Xtr[:cut], ytr[:cut], lam) - ytr[cut:]) ** 2))
            w = _ridge(Xtr, ytr, best)
            pred = X[~train] @ w
            real = r[~train]
            up = pred > 0
            step = slice(0, None, h)  # non overlapping five day steps
            timed = np.prod(1 + np.where(up[step], real[step], 0.0)) - 1
            held = np.prod(1 + real[step]) - 1
            return {"corr": float(np.corrcoef(pred, real)[0, 1]),
                    "hit": float(np.mean((pred > 0) == (real > 0))),
                    "timed": float(timed), "held": float(held), "in_market": float(up.mean())}

        out[market] = {}
        for variant, M in variants.items():
            M = M[:, M.sum(0) >= MIN_DAYS]
            F = M[rows]
            real_score = score(F)
            null = [score(np.roll(F, int(rng.integers(90, len(F) - 90)), axis=0)) for _ in range(N_SHIFTS)]
            nc = np.array([n["corr"] for n in null])
            nt = np.array([n["timed"] for n in null])
            out[market][variant] = {
                **{k: round(v, 4) for k, v in real_score.items()},
                "factors": int(F.shape[1]),
                "luck_corr_mean": round(float(nc.mean()), 4), "luck_corr_p95": round(float(np.percentile(nc, 95)), 4),
                "luck_beats_real_corr": round(float((nc >= real_score["corr"]).mean()), 3),
                "luck_timed_mean": round(float(nt.mean()), 4),
                "luck_beats_real_timed": round(float((nt >= real_score["timed"]).mean()), 3),
            }
            print(f"{market:9s} {variant:14s} {F.shape[1]:5d} factors  corr {real_score['corr']:+.3f} "
                  f"(luck p95 {np.percentile(nc, 95):+.3f}, luck beats it {100*(nc >= real_score['corr']).mean():.0f}%)"
                  f"  hit {real_score['hit']*100:.0f}%  timed {real_score['timed']*100:+.0f}% vs held {real_score['held']*100:+.0f}%"
                  f"  (luck beats timing {100*(nt >= real_score['timed']).mean():.0f}%)", flush=True)
    return out


def _runs(active: np.ndarray) -> list[tuple[int, int]]:
    """Start and end index of every unbroken stretch where a factor was on."""
    out, start = [], None
    for i, a in enumerate(active):
        if a and start is None:
            start = i
        elif not a and start is not None:
            out.append((start, i - 1))
            start = None
    if start is not None:
        out.append((start, len(active) - 1))
    return out


def occasions() -> dict:
    """Every time each surviving pattern actually happened, and when it happens next.

    A pattern's average hides what matters: whether it showed up most times it
    occurred, or whether two big moves are carrying ten that did nothing. Days
    inside one occurrence move together, so the occurrence is the honest unit
    of evidence, and this counts them. The sky is computable ahead, so each
    pattern also gets the dates it comes round again: a prediction on the
    record before the fact.
    """
    o = json.loads(RESULTS.read_text())
    today = datetime.now(timezone.utc).date()
    days = [START + timedelta(days=i) for i in range((today - START).days + 366)]
    keys, sky, lon = build_sky(days)
    day_index = {d: i for i, d in enumerate(days)}
    today_i = day_index[today]
    report = []
    for market, symbol in MARKETS.items():
        mine = [s for s in o["survivors"] if s["market"] == market]
        if not mine:
            continue
        px = fetch_prices(symbol)
        dates = [d for d, _ in px]
        close = np.array([c for _, c in px])
        rows = np.array([day_index[d] for d in dates])
        cols: dict[str, np.ndarray] = {}
        for s in mine:
            if s["factor"] not in cols:
                cols[s["factor"]] = factor_column(market, s["factor"], keys, sky, lon)
        for s in mine:
            h = s["horizon_days"]
            col = cols[s["factor"]]
            r = close[h:] / close[:-h] - 1.0
            base = float(r.mean())
            active = col[rows][:-h] > 0
            want = 1 if s["learned"]["effect_pct"] > 0 else -1
            occ = []
            for a, b in _runs(active):
                move = float(r[a:b + 1].mean())
                occ.append({"from": dates[a].isoformat(), "to": dates[b].isoformat(), "days": b - a + 1,
                            "avg_move_pct": round(move * 100, 2),
                            "as_predicted": (move - base) * want > 0})
            ahead = [{"from": days[today_i + a].isoformat(), "to": days[today_i + b].isoformat()}
                     for a, b in _runs(col[today_i:] > 0)][:3]
            hits = sum(1 for x in occ if x["as_predicted"])
            since = [x for x in occ if x["from"] >= SPLIT.isoformat()]
            report.append({
                "market": market, "factor": s["factor"], "block": s.get("block", "sky"), "horizon_days": h,
                "expects": "up" if want > 0 else "down",
                "effect_pct": s["confirmed"]["effect_pct"],
                "occasions": len(occ), "as_predicted": hits,
                "as_predicted_since_split": sum(1 for x in since if x["as_predicted"]), "occasions_since_split": len(since),
                "paper_eligible": len(occ) >= 7 and hits / max(1, len(occ)) >= 0.70
                                  and (not since or sum(1 for x in since if x["as_predicted"]) * 2 >= len(since)),
                "list": occ,
                "next": ahead,
            })
    report.sort(key=lambda x: (-(x["as_predicted"] / max(1, x["occasions"])), -x["occasions"]))
    (HERE / "almanac_occasions.json").write_text(json.dumps(report, indent=2))
    return {"today": today.isoformat(), "patterns": report}


def _pretty(factor: str) -> str:
    return factor.replace("_", " ")


def write_occasions(rep: dict) -> None:
    pats = rep["patterns"]
    L = ["# The almanac, occasion by occasion", "",
         "Each pattern that passed the almanac's two tests, opened up: every separate time it actually",
         "happened, and whether the market went the way the pattern says. Days inside one occurrence",
         "move together, so the occurrence is the honest unit. Then the dates each one comes round",
         "again, written down before they happen.", "",
         f"Written {rep['today']} by `almanac.py --occasions`. The paper book rule is registered in",
         "`registry/2026-10-12-family-2-occasions.md`: at least 7 occurrences, 70% as expected, half of",
         "those since 2021. Patterns meeting it are marked.", "",
         "## How often each pattern showed up when it occurred", "",
         "| market | factor | expects | times it happened | went as expected | of those since 2021 | paper book | next |",
         "|---|---|---|---|---|---|---|---|"]
    for p in pats:
        nxt = p["next"][0]["from"] if p["next"] else "not within a year"
        L.append(f"| {p['market']} | {_pretty(p['factor'])} | {p['expects']} {p['horizon_days']}d | {p['occasions']} | "
                 f"{p['as_predicted']} ({p['as_predicted'] / max(1, p['occasions']) * 100:.0f}%) | "
                 f"{p['as_predicted_since_split']} of {p['occasions_since_split']} | {'yes' if p.get('paper_eligible') else 'no'} | {nxt} |")
    soon = sorted(((n["from"], n["to"], p) for p in pats for n in p["next"]), key=lambda x: x[0])
    horizon = (date.fromisoformat(rep["today"]) + timedelta(days=90)).isoformat()
    L += ["", "## On the record: the next ninety days", "",
          "What the surviving patterns expect, dated in advance. Scored after the fact, in public.", "",
          "| from | to | market | factor | expects | record |", "|---|---|---|---|---|---|"]
    for f, t, p in soon:
        if f <= horizon:
            L.append(f"| {f} | {t} | {p['market']} | {_pretty(p['factor'])} | {p['expects']} over {p['horizon_days']}d | "
                     f"{p['as_predicted']} of {p['occasions']} |")
    L += ["", "## Every occasion", ""]
    for p in pats:
        L += [f"<details><summary>{p['market']}: {_pretty(p['factor'])}, expects {p['expects']} "
              f"({p['as_predicted']} of {p['occasions']})</summary>", "",
              "| from | to | days | average move | as expected |", "|---|---|---|---|---|"]
        for x in p["list"]:
            L.append(f"| {x['from']} | {x['to']} | {x['days']} | {x['avg_move_pct']:+.2f}% | {'yes' if x['as_predicted'] else 'no'} |")
        L += ["", "</details>", ""]
    (HERE / "ALMANAC_OCCASIONS.md").write_text("\n".join(L), encoding="utf-8")


FORECAST_PATH = HERE / "forecast.json"
FORECAST_LOG = HERE / "forecasts.jsonl"
FORECAST_PAGE = HERE / "FORECASTS.md"
WHOLE_PATH = HERE / "almanac_whole_sky.json"


def forecast_variants() -> dict[str, str]:
    """Which reading each market's forecast uses: whichever the long test favoured, judged by
    how rarely a scrambled sky matched it. The sky alone when nothing has been judged."""
    out = {m: "sky" for m in MARKETS}
    if WHOLE_PATH.exists():
        ws = json.loads(WHOLE_PATH.read_text())
        for m, variants in ws.items():
            if m in out and isinstance(variants, dict) and "sky" in variants:
                out[m] = min(variants, key=lambda v: variants[v].get("luck_beats_real_corr", 1.0))
    return out


def forecast() -> dict:
    """Today's forecast for every market, written down before the fact, and the old ones scored.

    For each market the whole sky model is refit on everything known up to
    today and asked about the next five trading days. The forecast goes into a
    public log with its date. When five days have passed, the log entry gets
    what actually happened beside it. Nothing is ever edited after the fact:
    entries are appended, and scoring only fills in outcomes.
    """
    today = datetime.now(timezone.utc).date()
    days = [START + timedelta(days=i) for i in range((today - START).days + 1)]
    keys, sky, lon = build_sky(days)
    day_index = {d: i for i, d in enumerate(days)}
    h = 5
    out = {"date": today.isoformat(), "horizon_trading_days": h, "markets": {}}
    closes: dict[str, dict[str, float]] = {}
    for market, variant in forecast_variants().items():
        px = fetch_prices(MARKETS[market])
        closes[market] = {d.isoformat(): c for d, c in px}
        mkeys, M = own_chart_matrix(market, keys, sky, lon) if variant == "sky_and_chart" else (keys, sky)
        keep = M.sum(0) >= MIN_DAYS
        M = M[:, keep]
        mkeys = [k for k, kp in zip(mkeys, keep) if kp]
        dates = [d for d, _ in px]
        close = np.array([c for _, c in px])
        r = close[h:] / close[:-h] - 1.0
        F = M[np.array([day_index[d] for d in dates[:-h]])]
        mu, sd = F.mean(0), F.std(0) + 1e-9
        X, y = (F - mu) / sd, r - r.mean()
        cut = int(len(X) * 0.7)
        lam = min((1e2, 1e3, 1e4, 1e5),
                  key=lambda l: np.mean((X[cut:] @ _ridge(X[:cut], y[:cut], l) - y[cut:]) ** 2))
        w = _ridge(X, y, lam)
        x_today = (M[day_index[today]] - mu) / sd
        pred = float(x_today @ w)
        contrib = sorted(zip(x_today * w, mkeys), key=lambda t: -abs(t[0]))[:5]
        out["markets"][market] = {
            "reading": variant, "expects": "up" if pred > 0 else "down",
            "forecast_vs_usual_pct": round(pred * 100, 2),
            "price_at_forecast": round(float(close[-1]), 2), "price_date": dates[-1].isoformat(),
            "why": [{"factor": k, "pull_pct": round(float(c) * 100, 2)} for c, k in contrib],
        }

    occ_path = HERE / "almanac_occasions.json"
    if occ_path.exists():
        active = []
        for p in json.loads(occ_path.read_text()):
            for n in p["next"]:
                if n["from"] <= today.isoformat() <= n["to"]:
                    active.append({"market": p["market"], "factor": p["factor"], "expects": p["expects"],
                                   "record": f"{p['as_predicted']} of {p['occasions']}",
                                   "paper_eligible": p.get("paper_eligible", False)})
        out["patterns_active_today"] = active

    FORECAST_PATH.write_text(json.dumps(out, indent=2))
    log = [json.loads(l) for l in FORECAST_LOG.read_text().splitlines() if l.strip()] if FORECAST_LOG.exists() else []
    if not any(e["date"] == out["date"] for e in log):
        log.append({"date": out["date"], "markets": {m: {k: v[k] for k in ("expects", "forecast_vs_usual_pct",
                    "price_at_forecast", "price_date")} for m, v in out["markets"].items()}})
    for e in log:
        for m, f in e["markets"].items():
            if "outcome" in f or m not in closes:
                continue
            ds = sorted(closes[m])
            if f["price_date"] in ds and ds.index(f["price_date"]) + h < len(ds):
                later = ds[ds.index(f["price_date"]) + h]
                move = closes[m][later] / f["price_at_forecast"] - 1
                f["outcome"] = {"date": later, "price": round(closes[m][later], 2), "move_pct": round(move * 100, 2),
                                "right": (move > 0) == (f["expects"] == "up")}
    FORECAST_LOG.write_text("\n".join(json.dumps(e) for e in log) + "\n")
    write_forecast_page(log, h)
    return out


def followed(f: dict, stake: float = 100.0) -> float:
    """What a pretend stake would have made following one scored forecast: long on up, short on down."""
    move = f["outcome"]["move_pct"] / 100
    return round(stake * (move if f["expects"] == "up" else -move), 2)


def write_forecast_page(log: list, h: int) -> None:
    scored = [(e["date"], m, f) for e in log for m, f in e["markets"].items() if "outcome" in f]
    L = ["# Forecasts, written before the fact", "",
         "Each day the whole sky model says what it expects over the next five trading days, for every",
         "market the almanac studies. The entry is dated and appended here before anyone knows the",
         "answer, and scored once the days have passed. Each market is read the way the long test",
         "favoured: the sky alone, or the sky plus the market's own birth chart.", "",
         "Until 2026-10-12 only Bitcoin and Ethereum were forecast. From that date all six are.", ""]
    if scored:
        right = sum(1 for _, _, f in scored if f["outcome"]["right"])
        L += [f"**Scored so far: {right} right of {len(scored)}.**", ""]
        by_m: dict[str, list] = {}
        for _, m, f in scored:
            by_m.setdefault(m, []).append(f)
        L += ["No real money follows these. The last column is what 100 pretend dollars would have made",
              "following each forecast for five days, long on up and short on down, fees ignored.", "",
              "| market | right | of | if followed, pretend dollars | standing |", "|---|---|---|---|---|"]
        total = 0.0
        for m, fs in sorted(by_m.items()):
            made = sum(followed(f) for f in fs)
            total += made
            rt = sum(1 for f in fs if f['outcome']['right'])
            trust = ("earning trust" if len(fs) >= 10 and rt * 2 > len(fs) and made > 0
                     else "not earned" if len(fs) >= 10 else "still learning")
            L.append(f"| {m} | {rt} | {len(fs)} | {made:+.2f} | {trust} |")
        L += [f"| all | {right} | {len(scored)} | {total:+.2f} | |", ""]
    else:
        L += ["**Nothing scored yet.** The first entries mature five trading days after they were written.", ""]
    L += ["| written | market | expects | price then | five days on | move | right |", "|---|---|---|---|---|---|---|"]
    for e in reversed(log[-90:]):
        for m, f in e["markets"].items():
            oc = f.get("outcome")
            L.append(f"| {e['date']} | {m} | {f['expects']} ({f['forecast_vs_usual_pct']:+.2f}% vs usual) | {f['price_at_forecast']:,} | "
                     + (f"{oc['price']:,} | {oc['move_pct']:+.2f}% | {'yes' if oc['right'] else 'no'} |" if oc else "pending | | |"))
    FORECAST_PAGE.write_text("\n".join(L) + "\n", encoding="utf-8")


def write_page(o: dict) -> None:
    luck = o["luck"]
    L = [
        "# The almanac",
        "",
        "What the sky was doing, and what actually happened. Every sky factor, and every transit to",
        "every chart connected to a market, against that market, from",
        f"{o['from']} to now. Learned on the years before {o['split']}, then made to",
        "prove itself on the years after.",
        "",
        f"Written {o['run_at'][:16].replace('T', ' ')} UTC by `almanac.py`. Nothing here is typed by hand.",
        f"Rules registered before the run: `{o.get('registered', 'registry/')}`.",
        "",
        "## The honest headline",
        "",
        f"{o['factors']:,} factors in all, {o['tests']:,} tests across six markets and two horizons.",
        f"**{o['passed']} patterns passed**: strong in the early years, same direction in the later years.",
        "",
        f"Luck's share: with the sky slid out of step with the calendar {luck['runs']} times, an average of",
        f"**{luck['mean']}** patterns passed by chance, 95 runs in 100 gave {luck['p95']:.0f} or fewer, and the most",
        f"any run gave was {luck['max']:.0f}. A scrambled sky did as well as the real one in",
        f"{luck['share_of_runs_at_or_above_real'] * 100:.0f}% of runs.",
        "",
    ]
    if o["passed"] > luck["p95"]:
        L += ["The real sky passed more patterns than luck usually manages. That is evidence of something,",
              "and it still does not say which of the survivors below are the real ones.", ""]
    else:
        L += ["That is inside what luck produces. On this evidence, taken as a whole, the survivors below",
              "cannot be told apart from chance, and none of them has earned real money.", ""]
    if o.get("blocks"):
        L += ["## What was read against each market", ""]
        for m, bl in o["blocks"].items():
            L.append(f"* {m}: " + ", ".join(bl))
        L.append("")
    L += ["## What survived", "",
          "| market | horizon | factor | learned: effect, z | confirmed: effect, z | up rate after |",
          "|---|---|---|---|---|---|"]
    for s in o["survivors"][:60]:
        L.append(f"| {s['market']} | {s['horizon_days']}d | {_pretty(s['factor'])} | "
                 f"{s['learned']['effect_pct']:+.2f}%, {s['learned']['z']:+.1f} | "
                 f"{s['confirmed']['effect_pct']:+.2f}%, {s['confirmed']['z']:+.1f} | {s['confirmed']['up_rate_pct']:.0f}% |")
    if not o["survivors"]:
        L.append("| nothing | | | | | |")
    L += ["", "Effect is the average move over the horizon on days the factor was active, minus the average on",
          "days it was not. For the VIX an up move means fear rising. Factor names beginning `t <chart>` are",
          "transits to that chart: transiting body, aspect, natal point (`anti` is the point's antiscion,",
          "`mid` a midpoint of two natal points).", "",
          "## The Moon signs the old agent traded on, over the long run", "",
          "The retired agent sized its bets from six months of Moon signs. Here is each sign against",
          "Bitcoin and Ethereum one day ahead, over the full history. A sign that matters should show the",
          "same direction in both halves.", "",
          "| market | Moon in | learned: effect, z | confirmed: effect, z | same direction |",
          "|---|---|---|---|---|"]
    for m in o["moon_signs_long_run"]:
        same = "yes" if m["learned_effect_pct"] * m["confirmed_effect_pct"] > 0 else "no"
        L.append(f"| {m['market']} | {m['factor'].replace('moon_in_', '')} | {m['learned_effect_pct']:+.2f}%, {m['learned_z']:+.1f} | "
                 f"{m['confirmed_effect_pct']:+.2f}%, {m['confirmed_z']:+.1f} | {same} |")
    if WHOLE_PATH.exists():
        ws = json.loads(WHOLE_PATH.read_text())
        L += ["", "## The whole sky at once", "",
              "One model per market, fed every sky factor together, learned before the split and made to",
              "forecast the years after. Forecast five days ahead. 'Timed' is holding only on days the model",
              "said up; 'held' is simply holding. The last two columns say how often a scrambled sky did as",
              "well or better, which is the only honest measure of whether the real one did anything.", "",
              "| market | forecast vs outcome | called direction | timed | held | luck matched the forecast | luck matched the timing |",
              "|---|---|---|---|---|---|---|"]
        label = {"sky": "the sky alone", "sky_and_chart": "sky plus its birth chart"}
        for m, variants in ws.items():
            if "sky" not in variants:
                variants = {"sky": variants}
            for name, v in variants.items():
                L.append(f"| {m}, {label.get(name, name)} | {v['corr']:+.3f} | {v['hit']*100:.0f}% | {v['timed']*100:+.0f}% | "
                         f"{v['held']*100:+.0f}% | {v['luck_beats_real_corr']*100:.0f}% of runs | "
                         f"{v['luck_beats_real_timed']*100:.0f}% of runs |")
        L += ["", "Birth charts used: " + "; ".join(f"{m}: {chart_label(m)}" for m in MARKETS) + ".",
              "Gold, oil and the VIX have no agreed moment of birth, so they get no chart rather than an invented one."]
        L += ["", "Read the last two columns first. Under about 5% would be evidence.", ""]
    L += ["", "## How to read this", "",
          "* z is how far the effect stands from nothing, in units of its own noise. It is flattered here,",
          "  because a planet sits in a sign for weeks and those days are not independent. The scrambled",
          "  sky runs are the correction for that, which is why the headline leans on them and not on z.",
          "* Passing twice is a filter, not proof. The point of the filter is to decide what deserves a",
          "  forward test with pretend money, and then, if it keeps working, real money. The rule for",
          "  each step is in `registry/`.",
          ""]
    PAGE.write_text("\n".join(L), encoding="utf-8")


def daily() -> None:
    """The learning loop's daily step: forecast, score, refresh what has gone stale, write the record."""
    forecast()
    occ_path = HERE / "almanac_occasions.json"
    if RESULTS.exists() and (not occ_path.exists() or time.time() - occ_path.stat().st_mtime > 7 * 86400):
        write_occasions(occasions())
    import paper
    print("paper book:", paper.step())
    import record
    record.write()


if __name__ == "__main__":
    t0 = time.time()
    if "--forecast" in sys.argv:
        print(json.dumps(forecast(), indent=2))
        sys.exit(0)
    if "--daily" in sys.argv:
        daily()
        print(f"daily done. {time.time() - t0:.0f}s")
        sys.exit(0)
    if "--occasions" in sys.argv:
        rep = occasions()
        write_occasions(rep)
        print(f"{len(rep['patterns'])} patterns opened up. {time.time() - t0:.0f}s")
        sys.exit(0)
    if "--whole" in sys.argv:
        merged = json.loads(WHOLE_PATH.read_text()) if WHOLE_PATH.exists() else {}
        merged = {k: (v if "sky" in v else {"sky": v}) for k, v in merged.items()}
        merged.update(whole_sky())
        WHOLE_PATH.write_text(json.dumps(merged, indent=2))
        print(f"{time.time() - t0:.0f}s")
        sys.exit(0)
    result = study()
    write_page(result)
    print(f"\n{result['tests']} tests, {result['passed']} passed; luck averages {result['luck']['mean']}, "
          f"95th percentile {result['luck']['p95']:.0f}. {time.time() - t0:.0f}s. Page written to {PAGE.name}")
