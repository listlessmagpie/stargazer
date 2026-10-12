"""The chart library and the full transit inventory.

A chart is a set of points: the ten bodies, and the angles when the birth time is known.
A transit is one transiting body making one named aspect to one point, within orb.
Every aspect is its own factor; nothing is folded into hard or soft. The transiting Moon
is included: it moves about thirteen degrees a day, so a Moon aspect is read as exact at
some moment in the day when the separation crosses the aspect angle between one noon and
the next, rather than by whether it sits within orb at noon.

Run with the orrery's Python, which has the ephemeris.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

sys.path.insert(0, "D:/git/paradox-box")
import orrery.moment  # noqa: F401,E402  (sets the ephemeris path)
import swisseph as swe  # noqa: E402

HERE = Path(__file__).resolve().parent
LIBRARY = HERE / "library" / "charts.json"

BODIES = {
    "sun": swe.SUN, "moon": swe.MOON, "mercury": swe.MERCURY, "venus": swe.VENUS, "mars": swe.MARS,
    "jupiter": swe.JUPITER, "saturn": swe.SATURN, "uranus": swe.URANUS, "neptune": swe.NEPTUNE,
    "pluto": swe.PLUTO,
}

#: Every aspect the orrery's inventory keeps, with its orb for a transit. Majors get two
#: degrees, minors one, the harmonic sevenths and ninths one. Nothing is left out by theory.
ASPECTS: dict[str, tuple[float, float]] = {
    "conj": (0.0, 2.0), "opp": (180.0, 2.0), "sq": (90.0, 2.0), "tri": (120.0, 2.0), "sext": (60.0, 2.0),
    "semisext": (30.0, 1.0), "semisq": (45.0, 1.0), "sesq": (135.0, 1.0), "quincunx": (150.0, 1.0),
    "quintile": (72.0, 1.0), "biquintile": (144.0, 1.0),
    "septile": (360 / 7, 1.0), "biseptile": (720 / 7, 1.0), "triseptile": (1080 / 7, 1.0),
    "novile": (40.0, 1.0), "binovile": (80.0, 1.0), "quadnovile": (160.0, 1.0),
}
ANTISCIA_ORB = 1.0
MIDPOINT_ORB = 1.0


def load() -> dict:
    return json.loads(LIBRARY.read_text(encoding="utf-8"))


def _julday_utc(node: dict) -> float | None:
    if not node.get("date"):
        return None
    y, m, d = (int(x) for x in node["date"].split("-"))
    if node.get("time_known") and node.get("time"):
        hh, mm, *rest = (int(x) for x in node["time"].split(":"))
        ss = rest[0] if rest else 0
        zone = node.get("zone") or "UTC"
        if zone == "UTC":
            dt = datetime(y, m, d, hh, mm, ss, tzinfo=timezone.utc)
        else:
            dt = datetime(y, m, d, hh, mm, ss, tzinfo=ZoneInfo(zone)).astimezone(timezone.utc)
    else:
        # Noon local, so the slow bodies are right and the Moon is dropped below.
        lon = node.get("lon")
        offset_h = (lon / 15.0) if lon is not None else 0.0
        dt = datetime(y, m, d, 12, 0, tzinfo=timezone.utc) - timedelta(hours=offset_h)
    return swe.julday(dt.year, dt.month, dt.day, dt.hour + dt.minute / 60 + dt.second / 3600)


def points(node: dict) -> dict[str, float]:
    """Natal points of one node: bodies, and angles when the time is known. Empty if no birth."""
    jd = _julday_utc(node)
    if jd is None:
        return {}
    out: dict[str, float] = {}
    for name, body in BODIES.items():
        if name == "moon" and not node.get("time_known"):
            continue
        out[name] = swe.calc_ut(jd, body, swe.FLG_MOSEPH)[0][0]
    if node.get("time_known") and node.get("lat") is not None and node.get("lon") is not None:
        cusps, ascmc = swe.houses(jd, node["lat"], node["lon"], b"W")
        out["asc"] = ascmc[0]
        out["mc"] = ascmc[1]
    return out


def transit_factors(lon: dict[str, np.ndarray], node: dict, prefix: str = "t") -> tuple[list[str], np.ndarray]:
    """Every transit of every body to every point of one chart, one column per named contact.

    lon: daily noon longitudes of the transiting bodies (from almanac.build_sky).
    Also: antiscia contacts (transit to the point's reflection about 0 Cancer) and
    contacts to the midpoints of natal pairs, each its own column.
    """
    natal = points(node)
    if not natal:
        return [], np.zeros((len(next(iter(lon.values()))), 0))
    n = len(next(iter(lon.values())))
    cols: dict[str, np.ndarray] = {}

    def crossing(tl: np.ndarray, target: float, orb: float) -> np.ndarray:
        """Active if within orb at noon, or (for the Moon) if the separation crosses the angle
        between this noon and the next."""
        sep = np.abs((tl - target + 180) % 360 - 180)
        hit = sep <= orb
        return hit

    def moon_crossing(tl: np.ndarray, target: float) -> np.ndarray:
        d0 = (tl - target + 180) % 360 - 180            # signed separation today
        d1 = np.roll(d0, -1)                            # tomorrow noon
        d1[-1] = d0[-1]
        # the Moon moves forward about 13 degrees; a crossing is a sign change over a short step
        step = (d1 - d0 + 180) % 360 - 180
        crossed = (np.sign(d0) != np.sign(d1)) & (np.abs(step) < 20)
        return crossed | (np.abs(d0) <= 2.0)

    targets: dict[str, float] = dict(natal)
    for name, pl in natal.items():
        targets[f"anti_{name}"] = (180.0 - pl) % 360          # antiscion: reflection about 0 Cancer / 0 Capricorn axis
    names = sorted(natal)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            mid = ((natal[a] + natal[b]) / 2) % 360
            if abs(((natal[a] - natal[b] + 180) % 360) - 180) > 180:
                mid = (mid + 180) % 360
            targets[f"mid_{a}_{b}"] = mid

    for t in BODIES:
        tl = lon[t]
        for pname, plon in targets.items():
            is_special = pname.startswith("anti_") or pname.startswith("mid_")
            for asp, (angle, orb) in ASPECTS.items():
                if is_special and asp != "conj":
                    continue  # antiscia and midpoints are read by conjunction only
                orb_use = ANTISCIA_ORB if pname.startswith("anti_") else MIDPOINT_ORB if pname.startswith("mid_") else orb
                target = (plon + angle) % 360
                target2 = (plon - angle) % 360
                if t == "moon":
                    hit = moon_crossing(tl, target) | moon_crossing(tl, target2)
                else:
                    hit = crossing(tl, target, orb_use) | crossing(tl, target2, orb_use)
                cols[f"{prefix}_{t}_{asp}_{pname}"] = hit
    keys = sorted(cols)
    return keys, np.column_stack([cols[k] for k in keys]).astype(np.float64)


def charts_for_market(lib: dict, market: str) -> list[str]:
    """The market's own node, plus every node with an edge onto it, that has a chart."""
    nodes = lib["nodes"]
    out = [market] if nodes.get(market, {}).get("date") else []
    for e in lib["edges"]:
        if e["on"] == market and nodes.get(e["from"], {}).get("date") and e["from"] not in out:
            out.append(e["from"])
    return out


if __name__ == "__main__":
    lib = load()
    for key, node in lib["nodes"].items():
        p = points(node)
        if not p:
            print(f"{key:18s} no chart ({node.get('rating')})")
            continue
        parts = ", ".join(f"{k} {v:6.2f}" for k, v in p.items() if k in ("sun", "moon", "asc", "mc"))
        print(f"{key:18s} {node.get('rating'):10s} {len(p):2d} points  {parts}")
