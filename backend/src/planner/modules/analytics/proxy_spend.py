"""What the accelerator proxy itself says our API key has spent (LiteLLM `GET /key/info`).

The ledger (`llm_usage`) prices every call we make; the proxy counts everything charged to the key,
including evals, `llm-ping` and calls made outside this app with the same key. The proxy figure is what
the program budget is actually charged. Amounts are RUB (Cloud.ru price list) even though LiteLLM shows "$".
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx


@dataclass(frozen=True, slots=True)
class KeySpend:
    spend_rub: Decimal
    max_budget_rub: Decimal | None = None


def parse_key_info(payload: dict[str, Any]) -> KeySpend:
    info = payload.get("info", payload)
    spend = info.get("spend")
    if spend is None:
        raise ValueError(f"no spend in /key/info response: keys {sorted(info)}")
    budget = info.get("max_budget")
    return KeySpend(
        spend_rub=Decimal(str(spend)),
        max_budget_rub=Decimal(str(budget)) if budget is not None else None,
    )


def proxy_root(base_url: str) -> str:
    """LiteLLM serves key management at the root, not under the OpenAI-compatible `/v1`."""
    url = base_url.rstrip("/")
    return url.removesuffix("/v1")


async def fetch_key_spend(base_url: str, api_key: str) -> KeySpend:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{proxy_root(base_url)}/key/info", headers={"Authorization": f"Bearer {api_key}"})
        resp.raise_for_status()
        return parse_key_info(resp.json())
