"""The record, as one machine readable file.

Everything the live show and the free index need, written from the ledgers by the daily
step: the forecasts and their scores, the occasions and what is active today, the paper
book, the chart library with its ratings, the registered rules, and the tally if the
oracles are up. Nothing in here is typed by hand and nothing names a buyer.

    python record.py
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
OUT = HERE / "record.json"


def _load(name: str, default):
    p = HERE / name
    if not p.exists():
        return default
    txt = p.read_text(encoding="utf-8")
    if name.endswith(".jsonl"):
        return [json.loads(l) for l in txt.splitlines() if l.strip()]
    return json.loads(txt)


def _tally() -> dict | None:
    """The oracles' counts, if they are up and a key is set. Counts only, never who."""
    base = os.getenv("ORRERY_URL", "http://127.0.0.1:8000")
    key = os.getenv("TALLY_KEY")
    if not key:
        return None
    try:
        r = httpx.get(f"{base}/tally", params={"key": key}, timeout=5)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def write() -> dict:
    now = datetime.now(timezone.utc)
    log = _load("forecasts.jsonl", [])
    forecast = _load("forecast.json", {})
    occ = _load("almanac_occasions.json", [])
    results = _load("almanac_results.json", {})
    whole = _load("almanac_whole_sky.json", {})
    paper = _load("paper_book.json", {})
    lib = _load("library/charts.json", {"nodes": {}, "edges": []})
    registry = sorted(p.name for p in (HERE / "registry").glob("*.md") if p.name != "README.md")

    scored = [(e["date"], m, f) for e in log for m, f in e["markets"].items() if "outcome" in f]
    by_market: dict[str, dict] = {}
    for _, m, f in scored:
        d = by_market.setdefault(m, {"right": 0, "of": 0})
        d["of"] += 1
        d["right"] += int(f["outcome"]["right"])

    today = now.date().isoformat()
    active = []
    upcoming = []
    for p in occ:
        row = {"market": p["market"], "factor": p["factor"], "expects": p["expects"], "horizon_days": p["horizon_days"],
               "record": f"{p['as_predicted']} of {p['occasions']}", "paper_eligible": p.get("paper_eligible", False)}
        for n in p["next"]:
            if n["from"] <= today <= n["to"]:
                active.append({**row, "from": n["from"], "to": n["to"]})
            elif n["from"] > today:
                upcoming.append({**row, "from": n["from"], "to": n["to"]})
    upcoming.sort(key=lambda x: x["from"])

    nodes = []
    for key, n in lib["nodes"].items():
        if not n.get("date"):
            continue
        nodes.append({"key": key, "label": n["label"], "kind": n["kind"], "date": n["date"],
                      "time_known": bool(n.get("time_known")), "rating": n.get("rating"),
                      "acts_on": sorted({e["on"] for e in lib["edges"] if e["from"] == key})})

    rec = {
        "written": now.isoformat(timespec="seconds"),
        "about": "Stargazer's record: forecasts dated before the fact and scored after, the sky factors "
                 "that survived a luck test, what is active now, pretend money on the paper book, and the "
                 "charts the study reads. Rules in registry/ were written before each test ran.",
        "forecasts": {
            "latest": {m: {k: v for k, v in f.items() if k != "why"} | {"why": f.get("why", [])[:3]}
                       for m, f in forecast.get("markets", {}).items()},
            "date": forecast.get("date"),
            "scored": {"right": sum(d["right"] for d in by_market.values()), "of": sum(d["of"] for d in by_market.values()),
                       "by_market": by_market},
            "log": [{"date": e["date"], "markets": e["markets"]} for e in log[-120:]],
        },
        "study": {
            "run_at": results.get("run_at"), "factors": results.get("factors"), "tests": results.get("tests"),
            "passed": results.get("passed"), "luck": results.get("luck"),
            "blocks": results.get("blocks"),
            "survivors": [{k: s[k] for k in ("market", "horizon_days", "factor", "block")} | {"confirmed": s["confirmed"]}
                          for s in results.get("survivors", [])[:60]],
        },
        "whole_sky": whole,
        "occasions": {
            "active_today": active,
            "upcoming": upcoming[:40],
            "table": [{k: p[k] for k in ("market", "factor", "expects", "horizon_days", "occasions", "as_predicted",
                                        "as_predicted_since_split", "occasions_since_split")} | {"paper_eligible": p.get("paper_eligible", False)}
                      for p in occ],
        },
        "paper": paper,
        "library": {"nodes": nodes, "edges": lib["edges"]},
        "registry": registry,
        "tally": _tally(),
    }
    OUT.write_text(json.dumps(rec, indent=1), encoding="utf-8")
    return rec


if __name__ == "__main__":
    r = write()
    print(f"record written: {r['forecasts']['scored']['right']} right of {r['forecasts']['scored']['of']}, "
          f"{len(r['occasions']['active_today'])} patterns active today, {len(r['library']['nodes'])} charts")
