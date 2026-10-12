"""What Stargazer can hold: every asset it can really swap on Base, verified on chain.

Each entry was checked against the chain on 2026-09-18: the token answers to its
symbol and decimals, the pool exists in the Uniswap v3 factory, and the depth on
the dollar side is enough that a cent sized trade does not move it.

`live` means real money. An asset earns that the way everything here earns
anything: by its record. Until then it trades on paper only. ETH is home: it
keeps a floor share of the wallet whatever the sky says, halved under skies
its own record calls bad.
"""

from __future__ import annotations

from dataclasses import dataclass

from web3 import Web3

import trader


@dataclass(frozen=True)
class Asset:
    id: str            # CoinGecko id: what the backtest and the tables are keyed by
    symbol: str
    token: str
    decimals: int
    pool: str          # Uniswap v3 pool against USDC
    fee: int           # pool fee in hundredths of a basis point
    live: bool
    home_floor: float = 0.0


def _a(x: str) -> str:
    return Web3.to_checksum_address(x)


REGISTRY: dict[str, Asset] = {
    "ethereum": Asset("ethereum", "WETH", trader.WETH, 18,
                      _a("0xd0b53D9277642d899DF5C87A3966A349A798F224"), 500, live=True, home_floor=0.30),
    "bitcoin": Asset("bitcoin", "cbBTC", _a("0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf"), 8,
                     _a("0xfBB6Eed8e7aa03B138556eeDaF5D271A5E1e43ef"), 500, live=True),
    "aerodrome-finance": Asset("aerodrome-finance", "AERO", _a("0x940181a94A35A4569E4529A3CDfB74e38FD98631"), 18,
                               _a("0xE5B5f522E98B5a2baAe212d4dA66b865B781DB97"), 500, live=False),
    "virtual-protocol": Asset("virtual-protocol", "VIRTUAL", _a("0x0b3e328455c4059EEb9e3f84b5543F74E24e7E1b"), 18,
                              _a("0x529d2863a1521d0b57db028168fdE2E97120017C"), 3000, live=False),
    "chainlink": Asset("chainlink", "LINK", _a("0x88Fb150BDc53A65fe94Dea0c9BA0a6dAf8C6e196"), 18,
                       _a("0x08C049F958E7d1f1b7ae44466b80d7773cA09c8e"), 3000, live=False),
}

LIVE = [a for a in REGISTRY.values() if a.live]


def price_usd(asset: Asset) -> float:
    """The asset in dollars, from the pool it trades in.

    A v3 pool stores the square root of token1 per token0 in raw units, and
    token0 is whichever address sorts lower. So the asset's side decides whether
    the ratio is used as is or turned over, and both need the decimal shift.
    """
    pool = trader.w3.eth.contract(address=asset.pool, abi=trader.POOL_ABI)
    sqrt_price = trader._rpc(lambda: pool.functions.slot0().call())[0]
    raw = (sqrt_price / 2**96) ** 2
    asset_is_token0 = int(asset.token, 16) < int(trader.USDC, 16)
    per_asset = raw if asset_is_token0 else 1 / raw
    return per_asset * 10**asset.decimals / 10**6


def balance(asset: Asset, address: str) -> float:
    token = trader.w3.eth.contract(address=asset.token, abi=trader.ERC20_ABI)
    raw = trader._rpc(lambda: token.functions.balanceOf(Web3.to_checksum_address(address)).call())
    return raw / 10**asset.decimals
