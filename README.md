# Stargazer

An agent that trades ETH by the sky, in public, with real money, fifty cents at a time.

The running results are in [EXPERIMENT.md](EXPERIMENT.md). That page is written by the agent from its own ledger and pushed every few hours. If the idea works, the number goes up. If it doesn't, you will watch it not.

## What it does

1. Buys electional windows from [the orrery](https://github.com/listlessmagpie/paradox-box), the astrology service in The Paradox Box, at a cent a call over x402.
2. Correlates six months of those windows with what ETH actually did over the next 4 to 48 hours (`backtest.py`).
3. Turns what held up into a strategy: which moon signs and phases have paid, at what win rate, over how many samples (`strategy.py`, `signals.py`).
4. Plans a week ahead and sleeps until a favourable window, then buys or sells on Uniswap on Base (`planner.py`, `trader.py`, `agent.py`).
5. Earns bigger bets only by winning. It starts at fifty cents and climbs a ladder of tiers; two losses in a row drop it a rung.
6. Spends idle time on research, and runs a scout that tries outside data feeds on a small trial budget and grades them against the return that followed (`research.py`, `scout.py`). The scout proposes; a person decides.

It also sells what it learned over x402 (`service.py`): the strategy, the same training run on any asset, and the forward plan.

## What this is not

Advice. A promise. A large sample. Read the caveats at the bottom of the experiment page.

## Running it

Python 3.12. `pip install -r requirements.txt` for the agent, `requirements-service.txt` for the service. Copy `.env.example` to `.env`. Payments go through the [Ampersend](https://ampersend.ai) CLI; trading uses a plain key the agent creates in `.trade_key` on first run, which you fund with a little USDC and a sliver of ETH for gas on Base.

`python agent.py` plans once. `python agent.py --loop` runs. `--plan`, `--strategy`, `--budget`, `--position`, `--scout` show state. `python experiment.py` writes the page.

Part of [The Paradox Box](https://github.com/listlessmagpie/paradox-box). AGPL v3.
