# Starting over: the orrery and Stargazer, done right

Written 2026-10-12 from Magpie's direction that day, after reading RETHINK.md, the ledger,
the almanac, the forecast record, and her March 2026 influence network design. This is the
design of record for the rebuild. RETHINK.md is the diagnosis; this is what we do about it.

## What the record says, in four lines

* The sky as a whole, tested against six markets since 2005 with a luck test, is not
  distinguishable from chance (41 of 2,154 tests passed, chance predicts about 36).
* Every live trade was sized from a Moon sign table the almanac had already shown to be flat.
* Thinking cost more than the stake: $15.18 on research and scout feeds against an $8.98 start.
  21 buys, 4 sells, 154 errors, and no outside buyer ever paid the orrery.
* The forward record (forecasts dated before the fact, scored after) is 19 right of 34. That
  record is the only thing built so far that an outsider has a reason to pay for.

Two conclusions follow and the rest of this file rests on them.

**First: at this size, trading cannot pay for research.** A fifty cent trade on Base pays a
0.05% pool fee, gas, and slippage, so a strategy needs an edge above roughly half a percent per
trade just to stand still, and "as many trades as possible" multiplies the fees, not the edge.
The lever that works at small size is being right about rare, large, pre registered occasions
and sizing into them, which is what the almanac's survivors (Venus retrograde, Venus opposite
Jupiter) are. Many small trades is the wrong lever until the stake is large enough that fees
stop mattering.

**Second: the thing that earns is the record, not the trades.** A dated, public, scored
forecast log across stocks, metals, oil, volatility and crypto, with the sky factors and the
people behind each call written down in advance, is a product agents and people will pay to
read. The trades are the demonstration that we believe our own record. So the trader is built
last and behind the record, not in front of it, which is exactly the mistake made in September.

## Two services, kept apart

### The orrery: the sky, as facts, for agents

What it is for: an agent asks about any moment, any chart, any range, and gets back
measurements with their lineage, never a forecast and never prose it did not ask for. Stateless,
no birth data kept, counting only (tally.py). AGPL. Cents per call over x402, with free routes
to see what is being bought.

What it already does: `/v1/stack`, `/v1/synthesize`, `/v1/interpret`, `/v1/elect`,
`/v1/hours`, `/v1/aspects`, `/v1/preview`, `/v1/systems`, `/v1/frameworks`, `/v1/schema`.

What it needs so agents get real use out of it:

1. `/v1/chart`: a full chart for any moment and place, not only a person's birth. An agent
   working on Coinbase wants the listing chart; one working on Bitcoin wants the genesis block.
   Same code path as natal, new name, documented as such.
2. `/v1/transits`: transits from the moving sky to a given chart across a date range, with
   exact timings and orbs. This is the question every electional and mundane astrologer
   actually asks, and the almanac already computes it internally; it is not served.
3. `/v1/record`: the almanac's tables and the forward forecast log, machine readable. The
   summary free (which factors passed, how many occasions, next dates). The detail paid
   (occasion by occasion with returns). This is the orrery serving what Stargazer learns, so
   the two stay siblings and the research has a buyer even if no trade is ever placed.
4. Every response carries `lineage` (which tradition says this) and `provenance`
   (measurement, derived, not computable) on every interpretive field. Already the principle;
   make it a schema check so no route can ship without it.
5. The tally deployed, and an oracles line in the 7am site report (alive, found, priced,
   bought) so she can see whether anyone comes.

Hosting, recommended: run both services from her PC behind a named Cloudflare tunnel on
catshapedparadox.com, the exact pattern that already keeps mcp.dollbrains.com alive (named
tunnel, logon task, self check). Cost nothing, and the tally plus the research already live
on this machine. Fallback if PC uptime turns out to be the problem: Railway Hobby at five
dollars a month for the orrery alone. Render's free tier spins down between requests and a
402 payment handshake needs the service awake, so it is not a fit. Fly.io no longer has a free
tier. Her choice; the tunnel is the one I would take.

Ampersend: no longer in the loop for Stargazer calling the orrery. Both run on the same
machine, so Stargazer imports the orrery as a library and pays nothing, and the stale windows
failure (no new research since 2026-09-19 because the budget ran out) cannot recur. x402 stays
as the rail outside buyers pay on, and as the rail Stargazer pays outside data feeds on, each
feed on a trial budget graded against the record before it earns a standing one.

### Stargazer: the study and the record

What it is for: compare what the sky was doing with what actually happened, across everything,
and let the record judge. Her September words. The trader was built in front of this; now it
goes behind it.

Three ledgers, kept as dated facts in the DollBrains manner (nothing overwritten, nothing
scored at the storage layer):

**The sky ledger.** Already exists: 287 factors per day since 2005, from the ephemeris. Add
transits to every chart in the chart library (below), not only Bitcoin and Ethereum.

**The web: every point has a chart, and the connections are the unit.** Her sharpening,
2026-10-12, second pass. Anything we trade has a birth moment, so it has a chart, and the
transits to that chart matter as much as the sky alone: when Ethereum gains or loses, what was
touching Ethereum's chart, and how. Then the people who act on that thing have charts, and what
they are currently trading has charts, and those read the same way. So the study is a web, not
three lists: instrument, the people connected to it, what those people are doing right now,
each node with a chart, each edge an act (founded, runs, holds, trades, decides, says), and the
sky read against every node at once while the event ledger records what actually happened.

Two rules fall out of this and bind the code:

* **Every point, every contact.** The almanac today reads transits to a chart as two buckets
  per pair, hard or soft, with the transiting Moon left out, no angles, no minor aspects, no
  midpoints or antiscia. That is the reduction the Paradox Box forbids. The rebuild reads each
  aspect separately (conjunction, opposition, square, trine, sextile, and the orrery's full
  inventory down to septiles, noviles, quintiles, antiscia and midpoints), each transiting body
  including the Moon, and the angles and houses whenever the birth time is recorded. Nothing
  is pre selected as mattering; the record selects. Where the number of factors multiplies,
  the luck test and the occasion count get stricter, never the inventory smaller.
* **Read the edge, not only the node.** A transit to Saylor's chart on the day Strategy buys
  Bitcoin is one fact; the same transit to Strategy's chart and to Bitcoin's chart on that day
  are two more, and the question is how they sit together, which is the synthesis layer the
  orrery already does for one person applied across connected charts.

**The chart library.** Every node in the web that has a real moment of birth.

* Markets and instruments: Bitcoin genesis, Ethereum genesis, Buttonwood (hour unknown, Moon
  left out, as now). Add the Federal Reserve (act signed 1913-12-23), Nasdaq's first trading
  day, the Coinbase listing (2021-04-14), the first spot Bitcoin ETF approval (2024-01-10),
  Tesla's and Nvidia's IPOs, Strategy's first Bitcoin purchase (2020-08-11), each Bitcoin
  halving. Dates to be confirmed against a source when entered; times only when recorded.
* People who move markets: the Fed chair, the Treasury secretary, the president, Musk,
  Saylor, Buffett, Dalio, Vitalik, CZ, the heads of BlackRock and JPMorgan, the most active
  members of Congress by disclosed trades. Birth data only from Astro Databank with its
  Rodden rating recorded; an unknown time means no Moon sign and no houses for that person,
  never a guessed one. Public figures, public records, nothing private.
* Companies: the top ten by index weight plus whatever a person in the library runs.

**The event ledger.** What happened, when, to whom, and what the market did after.

* Fortune moves: dated gains and losses for each person (Forbes real time list, 13F filings
  for funds, Form 4 for insiders, STOCK Act disclosures for Congress via Capitol Trades and
  Quiver, the sources her March 2026 design already picked out).
* Statements and decisions: FOMC decisions, rate moves, policy posts, Musk's coin posts,
  earnings dates, listings, collapses (Terra, FTX). Her March 2026 finding that public
  statements function as manipulation signals belongs here as a tested claim, not an assumption.
* Market returns at 1, 5 and 20 days for the instruments involved.

### The questions, as test families

Each family gets a written rule before any data is looked at, a historical test with the luck
test, a forward log, and a paper book, in that order. Nothing skips a stage.

1. **Timing windows (electional).** Does entering during window type X beat entering at a
   random time in the same week? The almanac's whole sky test, extended to every chart in the
   library. Expected answer from the record so far: mostly no, with a short list of survivors.
2. **Occasions (mundane).** Rare transits (Venus retrograde, Venus opposite Jupiter, Saturn
   stations, eclipses in a market's chart) as single bets. Few, large, pre dated. The two
   survivors are live forward tests now: Venus retrograde to 2026-11-14 (Bitcoin down 1.4% so
   far, as expected), Venus opposite Jupiter 2027-03-14 to 03-19.
3. **The connected charts.** When a market mover acts (speaks, trades, decides), what is the
   sky doing to their chart, to the chart of the thing they acted on, and to the charts of
   what they currently hold, and does the market move more under some contacts than others?
   This is the question she asked for and nobody serves. It is testable because the acts are
   dated and public. Shuffle the act dates against the transits for the luck test.
4. **The fortune question.** At each dated jump or fall in a person's wealth, what was transiting
   their chart, and does the same transit precede jumps for other people in the library? This
   is electional astrology read backwards: did the people who got richest act, knowingly or
   not, on good elections. Expect small samples; report occasions, never percentages alone.
5. **Combination.** Only once 1 to 4 have forward records: does a window plus a person plus an
   occasion do better than any alone. Not before.

Many trades or exact timing: the families answer that. Family 1 is the many trades thesis,
family 2 the exact timing thesis. The record decides which gets money, and at the current
stake the fee arithmetic already says family 2.

### How a finding earns the right to move money

* **Stage 0, written first.** The rule, the market, the window, the expected direction, the
  minimum occasions, committed to the repo with a date before the test runs.
* **Stage 1, history.** Learned before 2021, confirmed after. The luck test: shift the sky
  against the calendar 100 times; the finding must beat the 95th percentile of the shifted
  runs. And across the whole study, the count of passes must beat what the shifted skies
  produce, otherwise the study found nothing even if single rows look good. Count occasions,
  not days; days inside one occurrence move together (the "82% over 50 samples" that was seven
  Moon passages is the lesson).
* **Stage 2, forward paper.** Alpaca paper account (free, email only, real time data, stocks,
  ETFs, shorts, crypto in paper), so gold, oil, the VIX and the S&P are reachable for the
  first time, and shorting exists. At least ten independent occasions on the forward log,
  right more often than the market's own base rate over the same days, before anything goes
  live. The forward log is published as it happens; that is the product.
* **Stage 3, live, smallest size, on the venue the finding is about.** ETH and BTC on Base as
  now (after the nonce and gas bug in trader.py is fixed, on her say); stocks and ETFs through
  Alpaca live with fractional shares; crypto shorts through a perpetuals venue later if a
  short finding survives. Magpie wires live money herself; the code stops at paper.
* **The cost rule.** Research and feed spend in a month may not exceed the amount at stake in
  the live book. Beyond that line, research is funded by selling the record, not by trading.

### The learning loop, so it never goes stale again

Daily, from idle time on her PC: refresh prices and the event ledger, extend the sky ledger
one day, write the next forecasts before the fact, score the ones that came due, regrade every
paid outside feed against the returns that followed, and republish the record. Research that
costs money runs only when the free sources are exhausted and the cost rule allows it.
Everything the loop learns is written as dated facts; nothing is a hidden weight.

### Selling the record to other agents

Her question, 2026-10-12: once it works and makes money, we sell its predictions to agents. Yes,
and the shelf opens earlier than that. What is sold is the record, and the record exists from
the first day the loop writes a forecast before the fact. Money made is the proof that raises
the price, not the gate.

* **What is sold.** Dated forecasts with their scored history and occasion counts, the
  connected chart research behind each call, and the backtest run on a buyer's own asset. Never
  a bare direction. Over x402 on the orrery's `/v1/record` and Stargazer's own service, summary
  free, detail paid.
* **What the price climbs on.** First a scored record over enough occasions that chance is ruled
  out. Then a live book that backed the same calls with our own money and grew. Then the
  research nobody else serves, which an agent can test against its own data whether or not it
  believes in the sky.
* **Separation.** If buyers trade the same call, their orders move the price before ours. At
  any real size, sell after our own entry or sell the research rather than the exact trade.
  Irrelevant at the current stake; written down now so it is not forgotten later.

### Discovery, and demand as a signal

Her question, 2026-10-12: how does an agent find that we sell a prediction on a certain stock,
and can what they buy be a signal itself.

**Discovery.** Agents find services by words: registry search (x402scan, Agentic.Market,
Heurist and the directories in docs/buyers.md) and free index pages they read before paying.
Today the orrery is registered with Bazaar metadata and the tags astrology, timing, natal
chart, trading, divination, so "astrology timing" finds it and "Nvidia forecast" finds nothing.
The rebuild publishes a free index naming every instrument and every person in the chart
library, one line each: last forecast date, occasion count, scored hit rate, and the paid route
to the detail. The Bazaar metadata carries the same list. Stargazer's own service is deployed
beside the orrery with the same index. Every name in the library becomes a word a registry
indexes.

**Demand.** The tally counts per route per day. Extend it per instrument and per person: found
(free line read), priced (402 shown), bought. These counts become an attention column in the
event ledger, a factor like any sky factor. Requests for an instrument not in the library are
counted too; they are the queue for what to add next. Attention earns nothing by assumption: it
goes through the luck test and the occasion count like everything else, is read against the
registry's own traffic where visible so our marketing is not mistaken for the market, and stays
a count, never a record of any agent, address or payer.

### The pie: people's astrology on the orrery

Her direction, 2026-10-12, third pass. The orrery's facts also flow to the pie (the Paradox
Box's people facing astrology, four and twenty magpies, the King as the Sun and the Queen as
the Moon, built in the Sophist folder and reached from Cat Shaped Paradox). People cast their
own charts there, read dates, and over time every kind of astrology the orrery serves; the pie
only needs an overlay on top to show it. With accounts, it becomes a new AstroSeek that does
what AstroSeek will not: every factor kept, frameworks side by side, the derivation shown.

**The line that must hold.** The orrery keeps no one's birth data; that is the promise. So
accounts do not mean the orrery stores charts. A person's chart lives on their side: in their
own account that they control and can take with them, or in their browser, and the orrery
stays a stateless calculator behind the pie, asked fresh each time. Counting stays counting.
This is the DollBrains and Hal sovereignty line applied to astrology, and it is what makes the
AstroSeek comparison a difference and not a copy.

Not built in the restart. Noted here so the orrery's routes are shaped for it (chart for any
moment, transits over a range, the stack and synthesis the pie will draw) and so the account
piece, when it comes, is built on the person's side from the start.

## Order of work

1. Hosting: tunnel plus logon task for the orrery and Shuffle Up, tally deployed, oracles line
   in the 7am report. One session. Her decision on tunnel versus Railway first.
2. Stargazer imports the orrery directly; Ampersend removed from the research path; the stale
   window mode deleted.
3. Chart library and event ledger as data files with sources, starting with the markets and
   the ten people who move them most.
4. Families 1 to 4 pre registered, run historically, written up occasion by occasion. This is
   the research she asked for and it is weeks, not days.
5. Alpaca paper book wired to the forward log; the old Moon sign allocator retired.
6. `/v1/chart`, `/v1/transits`, `/v1/record` on the orrery. The record becomes something sold.
7. Live money only where stage 2 is passed, and only by her hand.

## No trades for now (her rule, 2026-10-12, evening)

"Maybe for a little while, they don't need to make any trades at all. They need to keep track of
predictions and see how much would have been made if they did." So stage 3 is parked without a
date. The record keeps two counterfactuals, both in pretend dollars with fees ignored: what
following every scored forecast would have made, and the paper book on the occasions. Real
money returns only when she says, and then by her hand.

"And learn from that. Then we'll add some money in, when we have like a week of data, or more."
How it learns: the forecaster refits every day on everything scored so far, the occasions table
rereads the whole history weekly, and the record states each line's standing in plain words
(still learning under 10 scored calls; earning trust when more right than wrong and the pretend
dollars are above zero; not earned otherwise). Honest note on the week: a week scores about five
calls per market, which cannot be told from luck. The registered gate for real money stays ten
forward occasions on the paper book; a week is when she looks, not when the gate opens.

## Her decisions, open

* Hosting: PC and tunnel (recommended) or Railway Hobby.
* An Alpaca paper account, which she creates herself (email only, no money).
* The $17 still on Base: leave it as the live stake for family 2, or pull it.
* Which people go in the first ten of the chart library.
