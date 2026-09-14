"""The paying side of x402, so the service can buy windows from the orrery.

Copied from paradox-box/orrery/x402_client.py (same author, AGPL). The service
runs on a host with no Ampersend CLI, so it pays the orrery directly with a
small funded key instead.
"""

from __future__ import annotations

import base64
import json
import secrets
import time

import httpx
from eth_account import Account
from eth_account.messages import encode_typed_data

CHAIN_IDS = {"base-sepolia": 84532, "base": 8453}

TRANSFER_WITH_AUTHORIZATION = {
    "TransferWithAuthorization": [
        {"name": "from", "type": "address"},
        {"name": "to", "type": "address"},
        {"name": "value", "type": "uint256"},
        {"name": "validAfter", "type": "uint256"},
        {"name": "validBefore", "type": "uint256"},
        {"name": "nonce", "type": "bytes32"},
    ]
}


class PaymentRefused(RuntimeError):
    """The facilitator declined, with its reason attached.

    Kept distinct from transport failures so a caller can tell "you have no money"
    apart from "the server is down", which are different problems with different fixes.
    """


def sign_payment(account: Account, reqs: dict) -> str:
    """Sign an EIP-3009 authorisation matching a 402 quote.

    Gasless for the signer: this authorises a transfer, and the facilitator is what
    submits it and pays the gas. That is what lets a caller pay without holding
    native currency on the chain.
    """
    network = reqs["network"]
    if network not in CHAIN_IDS:
        raise PaymentRefused(f"unsupported network {network!r}")

    now = int(time.time())
    authorization = {
        "from": account.address,
        "to": reqs["payTo"],
        "value": int(reqs["maxAmountRequired"]),
        "validAfter": 0,
        "validBefore": now + reqs.get("maxTimeoutSeconds", 60),
        "nonce": "0x" + secrets.token_hex(32),
    }

    signable = encode_typed_data(
        domain_data={
            "name": reqs["extra"]["name"],
            "version": reqs["extra"]["version"],
            "chainId": CHAIN_IDS[network],
            "verifyingContract": reqs["asset"],
        },
        message_types=TRANSFER_WITH_AUTHORIZATION,
        message_data=authorization,
    )
    signed = account.sign_message(signable)

    payload = {
        "x402Version": 1,
        "scheme": reqs["scheme"],
        "network": network,
        "payload": {
            # eth-account 0.13 returns bare hex; the wire format wants 0x.
            "signature": "0x" + signed.signature.hex(),
            "authorization": {
                **authorization,
                "value": str(authorization["value"]),
                "validAfter": str(authorization["validAfter"]),
                "validBefore": str(authorization["validBefore"]),
            },
        },
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


async def paid_post(
    client: httpx.AsyncClient, url: str, body: dict, account: Account | None
) -> dict:
    """POST, and pay if asked to.

    A 402 without a wallet is not an error worth swallowing: it means the caller was
    quoted a price and has no way to accept, so it says exactly that and what it costs.
    """
    first = await client.post(url, json=body)
    if first.status_code != 402:
        first.raise_for_status()
        return first.json()

    offer = first.json()
    reqs = offer["accepts"][0]
    price = int(reqs["maxAmountRequired"]) / 10**6

    if account is None:
        raise PaymentRefused(
            f"this endpoint costs {price} USDC on {reqs['network']} and no wallet is "
            "configured. Set STARGAZER_PAY_KEY to a funded key to pay automatically."
        )

    header = sign_payment(account, reqs)
    paid = await client.post(url, json=body, headers={"X-PAYMENT": header})

    if paid.status_code == 402:
        raise PaymentRefused(paid.json().get("error", "payment refused"))
    paid.raise_for_status()
    return paid.json()
