"""Keep `model_prices` in sync with the proxy's price list.

LiteLLM exposes per-token prices via `GET /model/info`; the accelerator notice says all
amounts are RUB (Cloud.ru price list), even though the proxy UI shows "$".
A YAML file can be used instead when the proxy doesn't return prices:

    - model: deepseek-v4.1-flash
      input_per_million: 12.5
      output_per_million: 50
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import yaml
from sqlalchemy import select

from planner.infra.db import Database
from planner.infra.ids import new_id
from planner.modules.analytics.tables import ModelPrice

MILLION = Decimal(1_000_000)


@dataclass(frozen=True, slots=True)
class PriceQuote:
    model: str
    input_per_million: Decimal
    output_per_million: Decimal
    cached_input_per_million: Decimal | None = None


def parse_model_info(payload: dict[str, Any]) -> list[PriceQuote]:
    quotes: list[PriceQuote] = []
    for item in payload.get("data", []):
        info = item.get("model_info") or {}
        inp, out = info.get("input_cost_per_token"), info.get("output_cost_per_token")
        if inp is None or out is None:
            continue
        cached = info.get("cache_read_input_token_cost")
        quotes.append(
            PriceQuote(
                model=item["model_name"],
                input_per_million=Decimal(str(inp)) * MILLION,
                output_per_million=Decimal(str(out)) * MILLION,
                cached_input_per_million=Decimal(str(cached)) * MILLION if cached is not None else None,
            )
        )
    return quotes


def parse_yaml(path: Path) -> list[PriceQuote]:
    rows = yaml.safe_load(path.read_text()) or []
    return [
        PriceQuote(
            model=r["model"],
            input_per_million=Decimal(str(r["input_per_million"])),
            output_per_million=Decimal(str(r["output_per_million"])),
            cached_input_per_million=(
                Decimal(str(r["cached_input_per_million"])) if r.get("cached_input_per_million") is not None else None
            ),
        )
        for r in rows
    ]


async def fetch_from_proxy(base_url: str, api_key: str) -> list[PriceQuote]:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{base_url.rstrip('/')}/model/info", headers={"Authorization": f"Bearer {api_key}"})
        resp.raise_for_status()
        return parse_model_info(resp.json())


async def apply_quotes(db: Database, quotes: list[PriceQuote], *, provider: str, source: str) -> list[str]:
    """Insert a new price version only when a model's price changed. Returns changed models."""
    now = datetime.now(UTC)
    changed: list[str] = []
    async with db.transaction() as session:
        for q in quotes:
            current = await session.scalar(
                select(ModelPrice)
                .where(ModelPrice.model == q.model, ModelPrice.effective_to.is_(None))
                .with_for_update()
            )
            if current and (
                current.input_per_million == q.input_per_million
                and current.output_per_million == q.output_per_million
                and current.cached_input_per_million == q.cached_input_per_million
            ):
                continue
            if current:
                current.effective_to = now
            session.add(
                ModelPrice(
                    id=new_id(),
                    provider=provider,
                    model=q.model,
                    currency="RUB",
                    input_per_million=q.input_per_million,
                    output_per_million=q.output_per_million,
                    cached_input_per_million=q.cached_input_per_million,
                    effective_from=now,
                    source=source,
                )
            )
            changed.append(q.model)
    return changed
