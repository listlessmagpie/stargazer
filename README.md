# Stargazer

What the sky was doing, and what actually happened, across everything, with the record left
to judge. Restarted 2026-10-12; the design is in [RESTART.md](RESTART.md), the diagnosis of the
first attempt in [RETHINK.md](RETHINK.md).

## What it does

1. Computes the sky for every day since 2005 and, for every chart in the
   [library](library/charts.json) connected to a market (the market's own birth, and every
   person or body that acts on it), every transit of every body to every point of that chart,
   each aspect its own factor, the Moon included, angles when the birth time is recorded,
   antiscia and midpoints too. Nothing is pre selected as mattering (`charts.py`, `almanac.py`).
2. Sets each factor against Bitcoin, Ethereum, the S&P 500, gold, oil and the VIX, learned on
   the years before 2021 and confirmed after, with the whole study rerun a hundred times on a
   sky slid out of step with the calendar so luck's share is measured, not assumed
   ([ALMANAC.md](ALMANAC.md)).
3. Opens each survivor occasion by occasion, since days inside one occurrence move together
   ([ALMANAC_OCCASIONS.md](ALMANAC_OCCASIONS.md)), and dates the next occurrences in advance.
4. Writes a forecast for every market every day, before the fact, and scores it after
   ([FORECASTS.md](FORECASTS.md)).
5. Puts pretend money on the occasions that meet the registered rule (`paper.py`), mirrored to
   an Alpaca paper account when keys exist (`alpaca_paper.py`).
6. Writes the whole record as one file, `record.json`, for the live show on
   catshapedparadox.com and for agents over x402 through the orrery.

Every rule was written down in [registry/](registry/) before the test that answers it ran.
Nothing moves real money unless a rule here, a historical pass, and ten forward occasions on
the paper book say so, and then only by Magpie's hand. The trading code for Base from the first
attempt (`trader.py`, `x402pay.py`) is kept for that day and is not run.

## Running it

Everything runs with the orrery's Python, which has the ephemeris:

    D:/git/paradox-box/.venv/Scripts/python.exe almanac.py              # the study
    D:/git/paradox-box/.venv/Scripts/python.exe almanac.py --whole      # the whole sky forecaster, judged
    D:/git/paradox-box/.venv/Scripts/python.exe almanac.py --occasions  # occasion by occasion
    D:/git/paradox-box/.venv/Scripts/python.exe almanac.py --daily      # the daily step

A Windows task runs `forecast_daily.bat` once a day and publishes the record.

## What this is not

Advice. A promise. A large sample. Read the luck columns before anything else.

Part of [The Paradox Box](https://github.com/listlessmagpie/paradox-box). AGPL v3. The first
attempt, a Moon sign trader, is kept in [old/](old/) for the record.
