# Starting over, 2026-10-12

Magpie paused Stargazer on 2026-10-12 to start over with more research. Read this first in the new chat.

## State when paused

* The Windows task `Stargazer` is **disabled** and its `agent.py --loop` process was stopped. Turn it back on with `Enable-ScheduledTask -TaskName Stargazer` only when she says.
* The trading wallet (`.trade_key`, separate from Ampersend) still holds about $17: about $8.39 USDC, $4.94 in wrapped ETH, $3.65 in cbBTC. She took her money out of Ampersend the same day.
* The orrery and Shuffle Up have been offline since about 2026-10-11 20:00 UTC: Railway's free trial ended. They had run about a month. Hosting is undecided (pay Railway, or run them from her PC behind a Cloudflare tunnel on catshapedparadox.com).
* A count of found, priced and bought now exists in both services (`tally.py` in paradox-box), built and tested, not deployed.

## What was wrong, from its own ledger

* **It was not learning.** It last paid for new research on 2026-09-19. Every rebuild after that reused the same stale saved windows.
* **It traded on a finding the almanac had already disproved.** The live allocator sizes by Moon sign tables (Scorpio "82%" over what was really about seven Moon passages). The almanac (2026-09-18, 287 sky factors against BTC, ETH, S&P 500, gold, oil, VIX since 2005, learned before 2021 and confirmed after, luck measured by shifting the sky 100 times) found the sky as a whole indistinguishable from chance by that test, and the Moon sign edge flat over the long run.
* **The almanac's survivors never reached a trade:** Venus retrograde (BTC down, VIX up, both halves; live now 2026-10-03 to 2026-11-14, BTC down about 1.4% so far) and Venus opposite Jupiter (next 2027-03-14 to 03-19).
* **The daily forecasts did not drive trades.** Scored 19 of 34 right: Bitcoin "down" right every day since 2026-10-03, Ethereum "up" wrong while it fell 5 to 7%.
* **It could not reach the markets it studied.** Only ETH and cbBTC on one Uniswap pool on Base; no shorting, no stocks, gold, oil or VIX. Those exist only in the paper book.
* **A stuck Bitcoin sell** failed every two hours since about 2026-10-01 ("replacement transaction underpriced", plus "nonce too low"): a nonce and gas pricing bug in the trader. 154 errors.
* **Thinking cost more than the stake:** research $10.20 and scout feeds $4.19 against an $8.98 start.

## Her intent, from September, in her words as recorded

Compare what the sky was doing with what actually happened, across everything, and let the record judge. The almanac is that; the trader was built in front of it.

## Open for the new chat

* Research first: what to measure, across which markets, how a finding earns the right to move money.
* Whether Ampersend belongs in it at all, and where trading should happen so it can reach the markets a finding is about.
* Whether the forward record (forecasts written before the fact, scored after) is the product itself.
* Hosting for the oracles, and whether outside agents ever found them (Railway's logs, if still kept; the chain for payments).

## Then

The design that answers this is RESTART.md, written the same day from Magpie's direction.
