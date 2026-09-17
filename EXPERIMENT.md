# Stargazer, a running experiment

Does the sky say anything about ETH? This agent buys electional windows from the
orrery, correlates six months of them with what the price did next, and bets fifty
cents at a time on what held up. It earns bigger bets only by winning. Everything
below is generated from its own ledger; nothing is typed by hand.

Updated 2026-09-17 11:02 UTC.

## The number

| | USDC | ETH |
|---|---|---|
| started 2026-09-11 00:34 UTC | 8.98 | 0 |
| now 2026-09-16 09:59 UTC | 6.5 | 0.000805877244595402 |

USDC is the stake. ETH is what it holds between a buy and a sell, plus a sliver kept
for gas. Money it spends on research and the scout comes from a separate wallet and
is counted below, not here.

## Trades

5 trades, 0 closed, 0 won.

| when | action | amount | sky | result |
|---|---|---|---|---|
| 2026-09-16 01:58 UTC | usdc to eth | 0.5 USDC at $2389.64 | Moon in Scorpio, waxing crescent | open |
| 2026-09-16 03:59 UTC | usdc to eth | 0.5 USDC at $2400.10 | Moon in Scorpio, waxing crescent | open |
| 2026-09-16 05:59 UTC | usdc to eth | 0.5 USDC at $2404.75 | Moon in Scorpio, waxing crescent | open |
| 2026-09-16 07:58 UTC | usdc to eth | 0.5 USDC at $2395.57 | Moon in Scorpio, waxing crescent | open |
| 2026-09-16 09:59 UTC | usdc to eth | 0.5 USDC at $2403.91 | Moon in Scorpio, waxing crescent | open |

## What it is betting on

Learned from the backtest, refreshed as research runs. A sign or phase counts as
favourable at a 55% win rate and a positive mean 24h return over enough samples.

| moon sign | 24h win rate | mean 24h return | samples | verdict |
|---|---|---|---|---|
| Aquarius | 63% | +0.17% | 67 | favourable |
| Sagittarius | 56% | +0.83% | 50 | favourable |
| Scorpio | 82% | +1.45% | 50 | favourable |
| Virgo | 75% | +0.95% | 36 | favourable |
| Cancer | 24% | -1.13% | 53 | unfavourable |
| Libra | 43% | -0.64% | 60 | unfavourable |
| Pisces | 30% | -1.28% | 46 | unfavourable |

* full moon: 57% win rate, +0.38% mean, 65 samples, favourable
* waning crescent: 56% win rate, +0.27% mean, 63 samples, favourable
* waxing crescent: 60% win rate, +0.61% mean, 65 samples, favourable
* waxing gibbous: 63% win rate, +0.42% mean, 100 samples, favourable
* new moon: 35% win rate, -1.25% mean, 85 samples, unfavourable

Trade size tier: 0 wins so far. The ladder is 0 wins for $0.50, 3 for $1, 6 for $2, 10 for $3, 15 for $5, 25 for $10. Two losses in a row drop it a rung.

## What it costs to think

* Research (backtests bought from the orrery at a cent a call): $1.12
* Scout (outside data feeds on trial, graded against the 24h return): $0.47
* Held instead of trading: 12 times
* Errors: 14

## Paper book

Every strategy the agent is not running, tracked as if it were: same sky, real
prices, pretend money. Short means being out ahead of an unfavourable window.
A paper strategy earns a live slot the same way the real one climbs its ladder,
and only a person can promote it.

| strategy | closed | won | win rate | net return | open now |
|---|---|---|---|---|---|
| ethereum long (live) | 0 | 0 | n/a | +0.00% | yes |
| ethereum short | 0 | 0 | n/a | +0.00% | no |
| bitcoin long | 0 | 0 | n/a | +0.00% | yes |
| bitcoin short | 0 | 0 | n/a | +0.00% | no |
| solana long | 0 | 0 | n/a | +0.00% | yes |
| solana short | 0 | 0 | n/a | +0.00% | no |

Sky readings for the book so far: $0.02.

## How to read this honestly

* Sample sizes are small. A 60% win rate over 50 windows is a coin that came up heads a
  few extra times. Watch whether it holds as the count grows.
* Every trade pays gas and a spread. Small bets lose a larger share to both.
* The agent never sees this page and does not tune itself to look good on it.

Source and method in this repo. The sky comes from [The Paradox Box](https://github.com/listlessmagpie/paradox-box).
