# Stargazer, a running experiment

Does the sky say anything about ETH? This agent buys electional windows from the
orrery, correlates six months of them with what the price did next, and bets fifty
cents at a time on what held up. It earns bigger bets only by winning. Everything
below is generated from its own ledger; nothing is typed by hand.

Updated 2026-09-24 17:00 UTC.

## The number

| | USDC | position (wrapped ETH) | gas (ETH) |
|---|---|---|---|
| started 2026-09-11 00:34 UTC | 8.98 | 0 | 0 |
| now 2026-09-24 16:00 UTC | 14.805593 | 0.000979377459293489 | 0.000594449277913247 |

Holding 17 lots bought for $2.56 at an average of $2612.21, worth $2.63 at $2683.36 (+2.72%, unrealised).

USDC is the stake. Wrapped ETH is the position, what it holds between a buy and a
sell. Plain ETH is only gas. Money it spends on research and the scout comes from a
separate wallet and is counted below, not here.

Until 2026-09-18 the agent could not see its own wrapped ETH, so it believed it held
nothing, bought again at every favourable window, and could never have sold. Eleven
lots went in that way. It sees them now, holds to a ceiling set by each sign's measured
edge (half the Kelly fraction, never more than 60% of the wallet), and sells the whole
position when the sky turns against it.

## Trades

11 trades, 0 closed, 0 won.

| when | action | amount | sky | result |
|---|---|---|---|---|
| 2026-09-16 01:58 UTC | usdc to eth | 0.5 USDC at $2389.64 | Moon in Scorpio, waxing crescent | open |
| 2026-09-16 03:59 UTC | usdc to eth | 0.5 USDC at $2400.10 | Moon in Scorpio, waxing crescent | open |
| 2026-09-16 05:59 UTC | usdc to eth | 0.5 USDC at $2404.75 | Moon in Scorpio, waxing crescent | open |
| 2026-09-16 07:58 UTC | usdc to eth | 0.5 USDC at $2395.57 | Moon in Scorpio, waxing crescent | open |
| 2026-09-16 09:59 UTC | usdc to eth | 0.5 USDC at $2403.91 | Moon in Scorpio, waxing crescent | open |
| 2026-09-17 19:58 UTC | usdc to eth | 0.5 USDC at $2448.59 | Moon in Sagittarius, waxing crescent | open |
| 2026-09-17 21:59 UTC | usdc to eth | 0.5 USDC at $2446.52 | Moon in Sagittarius, waxing crescent | open |
| 2026-09-17 23:59 UTC | usdc to eth | 0.5 USDC at $2447.05 | Moon in Sagittarius, waxing crescent | open |
| 2026-09-18 01:59 UTC | usdc to eth | 0.5 USDC at $2455.45 | Moon in Sagittarius, waxing crescent | open |
| 2026-09-18 08:07 UTC | usdc to eth | 0.5 USDC at $2491.77 | Moon in Sagittarius, waxing crescent | open |
| 2026-09-18 09:59 UTC | usdc to eth | 0.5 USDC at $2505.83 | Moon in Sagittarius, waxing crescent | open |

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

* Research (backtests bought from the orrery at a cent a call): $10.20
* Scout (outside data feeds on trial, graded against the 24h return): $1.70
* Held instead of trading: 12 times
* Errors: 19

## Paper book

Every strategy the agent is not running, tracked as if it were: same sky, real
prices, pretend money. Short means being out ahead of an unfavourable window.
A paper strategy earns a live slot the same way the real one climbs its ladder,
and only a person can promote it.

| strategy | closed | won | win rate | net return | open now |
|---|---|---|---|---|---|
| ethereum long (live) | 1 | 1 | 100% | +6.51% | no |
| ethereum short | 0 | 0 | n/a | +0.00% | yes |
| bitcoin long | 2 | 1 | 50% | +1.87% | no |
| bitcoin short | 1 | 0 | 0% | -6.17% | yes |
| solana long | 2 | 1 | 50% | +8.00% | no |
| solana short | 1 | 0 | 0% | -3.83% | yes |
| ethereum dip | 0 | 0 | n/a | +0.00% | yes |
| ethereum dip_fair_sky | 0 | 0 | n/a | +0.00% | no |
| bitcoin dip | 0 | 0 | n/a | +0.00% | yes |
| bitcoin dip_fair_sky | 0 | 0 | n/a | +0.00% | no |
| solana dip | 1 | 1 | 100% | +6.87% | yes |
| solana dip_fair_sky | 0 | 0 | n/a | +0.00% | no |
| aerodrome-finance long | 1 | 0 | 0% | -0.49% | no |
| aerodrome-finance short | 0 | 0 | n/a | +0.00% | yes |
| aerodrome-finance dip | 1 | 1 | 100% | +9.65% | yes |
| aerodrome-finance dip_fair_sky | 0 | 0 | n/a | +0.00% | no |
| virtual-protocol long | 1 | 1 | 100% | +10.67% | no |
| virtual-protocol short | 0 | 0 | n/a | +0.00% | yes |
| virtual-protocol dip | 1 | 1 | 100% | +12.26% | yes |
| virtual-protocol dip_fair_sky | 1 | 1 | 100% | +12.26% | no |
| chainlink long | 1 | 0 | 0% | -5.54% | no |
| chainlink short | 0 | 0 | n/a | +0.00% | yes |
| chainlink dip | 1 | 1 | 100% | +8.04% | yes |
| chainlink dip_fair_sky | 0 | 0 | n/a | +0.00% | yes |

Sky readings for the book so far: $0.11.

## Scout

Outside feeds being graded. A candidate is a proposal to a person, never adopted by the agent.

Written 2026-09-18 13:34 UTC. Horizon 24h. Trial budget $0.25 a day, one round of 2 sources costs $0.03.

## mycelia_basis
ETH spot to futures basis, carry and funding across exchanges. $0.02 a call.
Samples aged: 14. Spent so far: $0.40. Verdict: too early: 14 of 15 samples aged.

| feature | corr with 24h return | direction hit |
|---|---|---|
| basis_pct | +0.04 | 0% |
| carry_pct | -0.11 | 64% |
| funding_mean | +0.14 | 43% |

## nansen_score
Nansen composite performance and risk scores for large caps. $0.01 a call.
Samples aged: 14. Spent so far: $0.20. Verdict: too early: 14 of 15 samples aged.

| feature | corr with 24h return | direction hit |
|---|---|---|
| performance | n/a | 71% |
| risk_neg | -0.26 | 29% |
| momentum | n/a | 71% |

A candidate is a proposal. Adding it to the live signals, and to the Ampersend seller allowlist, is a decision for a person.

## How to read this honestly

* Sample sizes are small. A 60% win rate over 50 windows is a coin that came up heads a
  few extra times. Watch whether it holds as the count grows.
* Every trade pays gas and a spread. Small bets lose a larger share to both.
* The agent never sees this page and does not tune itself to look good on it.

Source and method in this repo. The sky comes from [The Paradox Box](https://github.com/listlessmagpie/paradox-box).
