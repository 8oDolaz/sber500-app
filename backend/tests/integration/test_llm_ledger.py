import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from planner.bootstrap import Container
from planner.modules.analytics.price_sync import PriceQuote, apply_quotes
from planner.modules.analytics.tables import AnalyticsEventRow, LlmUsage, ModelPrice
from planner.modules.assistant.llm_gateway.fake import FakeProvider
from planner.modules.assistant.llm_gateway.port import ChatMessage, LLMBudgetExceeded, LLMRequest, LLMResult


class CostReportingProvider(FakeProvider):
    name = "accelerator"

    async def complete(self, request: LLMRequest) -> LLMResult:
        return LLMResult(
            text="ok",
            provider=self.name,
            model=request.model,
            input_tokens=100,
            output_tokens=10,
            reported_cost=Decimal("0.0125"),
        )


REQ = LLMRequest(model="deepseek-v4.1-flash", messages=[ChatMessage("user", "hi")])


async def test_gateway_writes_ledger_row_with_proxy_cost(container: Container) -> None:
    container.llm._provider = CostReportingProvider()
    family = uuid.uuid4()
    await container.llm.complete(REQ, feature="extraction", family_id=family)
    async with container.db.sessions() as s:
        row = (await s.scalars(select(LlmUsage))).one()
    assert (row.status, row.cost_micros, row.cost_source, row.family_id) == ("ok", 12_500, "proxy", family)
    assert await container.redis.get(next(iter(await container.redis.keys("llm:spent:*")))) == "12500"


async def test_price_table_used_when_proxy_reports_nothing(container: Container) -> None:
    await apply_quotes(
        container.db,
        [PriceQuote("deepseek-v4.1-flash", Decimal(10), Decimal(40))],
        provider="accelerator",
        source="manual",
    )
    container.llm._provider = type("P", (FakeProvider,), {"name": "accelerator"})()
    await container.llm.complete(REQ, feature="chat")
    async with container.db.sessions() as s:
        row = (await s.scalars(select(LlmUsage))).one()
    assert row.cost_source == "price_table" and row.cost_micros and row.price_id is not None


async def test_price_versions_only_on_change(container: Container) -> None:
    q = [PriceQuote("m1", Decimal(1), Decimal(2))]
    assert await apply_quotes(container.db, q, provider="a", source="manual") == ["m1"]
    assert await apply_quotes(container.db, q, provider="a", source="manual") == []
    assert await apply_quotes(
        container.db, [PriceQuote("m1", Decimal(1), Decimal(3))], provider="a", source="manual"
    ) == ["m1"]
    async with container.db.sessions() as s:
        rows = (await s.scalars(select(ModelPrice).order_by(ModelPrice.effective_from))).all()
    assert [r.effective_to is None for r in rows] == [False, True]


async def test_budget_exceeded_is_ledgered_and_tracked(container: Container, fake_llm: FakeProvider) -> None:
    fake_llm.fail_with = LLMBudgetExceeded("Budget has been exceeded")
    with pytest.raises(LLMBudgetExceeded):
        await container.llm.complete(REQ, feature="extraction")
    await container.dispatcher.dispatch_batch()
    async with container.db.sessions() as s:
        usage = (await s.scalars(select(LlmUsage))).one()
        event = (await s.scalars(select(AnalyticsEventRow))).one()
    assert usage.status == "budget_exceeded"
    assert event.name == "llm_budget_exceeded"


async def test_spend_monitor_alerts_once_per_threshold(container: Container) -> None:
    container.llm._provider = CostReportingProvider()
    container.spend_monitor._budget = 0
    await container.llm.complete(REQ, feature="chat")
    assert await container.spend_monitor.check() == Decimal("0.0125")
    assert sorted(await container.redis.keys("llm:budget_alert:*")) == [
        "llm:budget_alert:0:0.5",
        "llm:budget_alert:0:0.8",
    ]
