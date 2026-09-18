"""On-chain actions: read balances and swap tokens on Base."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import requests
from web3 import Web3


NETWORK = "base"
RPC_URL = "https://mainnet.base.org"

USDC = Web3.to_checksum_address("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
WETH = Web3.to_checksum_address("0x4200000000000000000000000000000000000006")

UNISWAP_ROUTER = Web3.to_checksum_address("0x2626664c2603336E57B271c5C0b26F421741e481")
USDC_WETH_FEE = 500  # 0.05% pool
USDC_WETH_POOL = Web3.to_checksum_address("0xd0b53D9277642d899DF5C87A3966A349A798F224")

POOL_ABI = [
    {"inputs": [], "name": "slot0", "outputs": [
        {"type": "uint160", "name": "sqrtPriceX96"}, {"type": "int24", "name": "tick"},
        {"type": "uint16", "name": "observationIndex"}, {"type": "uint16", "name": "observationCardinality"},
        {"type": "uint16", "name": "observationCardinalityNext"}, {"type": "uint8", "name": "feeProtocol"},
        {"type": "bool", "name": "unlocked"}], "stateMutability": "view", "type": "function"},
]

ERC20_ABI = [
    {"constant": True, "inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}], "name": "allowance", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
    {"constant": False, "inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}], "name": "approve", "outputs": [{"name": "", "type": "bool"}], "type": "function"},
    {"constant": True, "inputs": [{"name": "account", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
]

SWAP_ROUTER_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"name": "tokenIn", "type": "address"},
                    {"name": "tokenOut", "type": "address"},
                    {"name": "fee", "type": "uint24"},
                    {"name": "recipient", "type": "address"},
                    {"name": "amountIn", "type": "uint256"},
                    {"name": "amountOutMinimum", "type": "uint256"},
                    {"name": "sqrtPriceLimitX96", "type": "uint160"},
                ],
                "name": "params",
                "type": "tuple",
            }
        ],
        "name": "exactInputSingle",
        "outputs": [{"name": "amountOut", "type": "uint256"}],
        "stateMutability": "payable",
        "type": "function",
    },
]

def _connect() -> Web3:
    return Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={"timeout": 30}))


w3 = _connect()


def _rpc(fn, attempts: int = 4):
    """Run a read against the node, surviving the two ways the free node fails.

    It hangs up on idle connections, so after hours asleep the first request
    dies on a dead socket: rebuild the client and go again. And it rate limits,
    so a 429 means wait and go again. Reads are safe to repeat. Sends are never
    routed through here: repeating one could double send.
    """
    global w3
    delay = 1.5
    for attempt in range(attempts):
        try:
            return fn()
        except requests.exceptions.ConnectionError:
            w3 = _connect()
        except requests.exceptions.HTTPError as exc:
            if exc.response is None or exc.response.status_code != 429:
                raise
        if attempt < attempts - 1:
            time.sleep(delay)
            delay *= 2
    return fn()


TRADE_KEY_PATH = Path(__file__).parent / ".trade_key"


def _load_trade_key() -> tuple[str, str]:
    """Load the dedicated trading key (separate from Ampersend).

    The Ampersend wallet is ERC-4337 (smart contract) and can't sign
    regular DEX transactions. This key is a plain EOA for Uniswap swaps.
    """
    if TRADE_KEY_PATH.exists():
        key = TRADE_KEY_PATH.read_text().strip()
        acct = w3.eth.account.from_key(key)
        return key, acct.address

    acct = w3.eth.account.create()
    TRADE_KEY_PATH.write_text(acct.key.hex())
    TRADE_KEY_PATH.chmod(0o600)
    return acct.key.hex(), acct.address


def _load_agent_key() -> tuple[str, str]:
    """Load agent private key and address from Ampersend config.

    Used only for reading portfolio balance of the Ampersend wallet.
    Trading uses _load_trade_key() instead.
    """
    context = os.getenv("AMPERSEND_CONTEXT", "ctx-61d1")
    config_path = Path.home() / ".ampersend" / "config.json"
    with open(config_path, encoding="utf-8-sig") as f:
        config = json.load(f)
    ctx = config["contexts"][context]
    return ctx["agentKey"], ctx["agentAccount"]


@dataclass
class Portfolio:
    usdc: Decimal
    eth: Decimal       # native ETH: gas only, never the position
    usdc_raw: int
    eth_raw: int
    address: str
    weth: Decimal = Decimal(0)   # wrapped ETH: what a buy pays out, and so the position
    weth_raw: int = 0

    @property
    def total_usd_estimate(self) -> Decimal:
        return self.usdc

    @property
    def has_gas(self) -> bool:
        return self.eth_raw > 100_000 * 10**9  # ~0.0001 ETH


async def get_portfolio() -> Portfolio:
    """Read balances from the trading wallet (not the Ampersend wallet)."""
    _, address = _load_trade_key()
    addr = Web3.to_checksum_address(address)

    def balances():
        usdc_contract = w3.eth.contract(address=USDC, abi=ERC20_ABI)
        weth_contract = w3.eth.contract(address=WETH, abi=ERC20_ABI)
        return (usdc_contract.functions.balanceOf(addr).call(),
                w3.eth.get_balance(addr),
                weth_contract.functions.balanceOf(addr).call())

    usdc_raw, eth_raw, weth_raw = _rpc(balances)

    return Portfolio(
        usdc=Decimal(usdc_raw) / Decimal(10**6),
        eth=Decimal(eth_raw) / Decimal(10**18),
        usdc_raw=usdc_raw,
        eth_raw=eth_raw,
        address=address,
        weth=Decimal(weth_raw) / Decimal(10**18),
        weth_raw=weth_raw,
    )


def _ensure_approval(key: str, address: str, token: str, spender: str, amount: int) -> str | None:
    """Approve token spending if needed. Returns tx hash or None."""
    contract = w3.eth.contract(address=token, abi=ERC20_ABI)
    addr = Web3.to_checksum_address(address)
    current = _rpc(lambda: contract.functions.allowance(addr, spender).call())
    if current >= amount:
        return None

    tx = _rpc(lambda: contract.functions.approve(spender, 2**256 - 1).build_transaction({
        "from": addr,
        "nonce": w3.eth.get_transaction_count(addr),
        "gas": 60_000,
        "maxFeePerGas": w3.eth.gas_price * 2,
        "maxPriorityFeePerGas": w3.eth.max_priority_fee,
        "chainId": 8453,
    }))
    signed = w3.eth.account.sign_transaction(tx, key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    w3.eth.wait_for_transaction_receipt(tx_hash)
    return tx_hash.hex()


def _swap(key: str, address: str, token_in: str, token_out: str,
          amount_in: int, min_out: int) -> str:
    """Swap exactly amount_in of token_in for at least min_out of token_out."""
    addr = Web3.to_checksum_address(address)
    _ensure_approval(key, address, token_in, UNISWAP_ROUTER, amount_in)

    router = w3.eth.contract(address=UNISWAP_ROUTER, abi=SWAP_ROUTER_ABI)
    tx = _rpc(lambda: router.functions.exactInputSingle((
        token_in,
        token_out,
        USDC_WETH_FEE,
        addr,          # recipient
        amount_in,
        min_out,       # the floor: below this the swap reverts instead of filling badly
        0,             # sqrtPriceLimitX96
    )).build_transaction({
        "from": addr,
        "nonce": w3.eth.get_transaction_count(addr),
        "gas": 200_000,
        "maxFeePerGas": w3.eth.gas_price * 2,
        "maxPriorityFeePerGas": w3.eth.max_priority_fee,
        "chainId": 8453,
        "value": 0,
    }))
    signed = w3.eth.account.sign_transaction(tx, key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt["status"] != 1:
        raise RuntimeError(f"swap failed, tx: {tx_hash.hex()}")
    return tx_hash.hex()


def eth_price() -> float:
    """ETH in USDC, read from the pool the agent actually trades in.

    No rate limit and no third party: the price is the pool's own square root
    price. WETH is token0 and USDC token1, so it needs the 18 to 6 decimal shift.
    """
    pool = w3.eth.contract(address=USDC_WETH_POOL, abi=POOL_ABI)
    sqrt_price = _rpc(lambda: pool.functions.slot0().call())[0]
    return (sqrt_price / 2**96) ** 2 * 10**12


def _eth_usd() -> Decimal:
    return Decimal(str(eth_price()))


async def swap_usdc_to_eth(usdc_amount: Decimal, slippage_bps: int = 100) -> str:
    """Buy WETH with USDC via Uniswap V3. Returns tx hash."""
    key, address = _load_trade_key()
    portfolio = await get_portfolio()
    if not portfolio.has_gas:
        raise RuntimeError(f"wallet {address} has no ETH for gas. Send ~0.001 ETH to it on Base.")

    amount_in = int(usdc_amount * Decimal(10**6))
    expected_eth = usdc_amount / _eth_usd()
    min_out = int(expected_eth * (1 - Decimal(slippage_bps) / 10_000) * Decimal(10**18))
    return _swap(key, address, USDC, WETH, amount_in, min_out)


async def swap_eth_to_usdc(eth_amount: Decimal, slippage_bps: int = 100) -> str:
    """Sell WETH for USDC via Uniswap V3. Returns tx hash."""
    key, address = _load_trade_key()
    portfolio = await get_portfolio()
    if not portfolio.has_gas:
        raise RuntimeError(f"wallet {address} has no ETH for gas. Send ~0.001 ETH to it on Base.")

    amount_in = int(eth_amount * Decimal(10**18))
    expected_usdc = eth_amount * _eth_usd()
    min_out = int(expected_usdc * (1 - Decimal(slippage_bps) / 10_000) * Decimal(10**6))
    return _swap(key, address, WETH, USDC, amount_in, min_out)
