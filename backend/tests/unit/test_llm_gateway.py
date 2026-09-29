from decimal import Decimal
from typing import Any

import pytest

from planner.modules.analytics.llm_ledger import PriceBook, Priced, UsageEntry, rub_to_micros
from planner.modules.assistant.llm_gateway.fake import FakeProvider
from planner.modules.assistant.llm_gateway.gateway import LLMGateway
from planner.modules.assistant.llm_gateway.port import (
    ChatMessage,
    LLMBudgetExceeded,
    LLMQuotaExceeded,
    LLMRequest,
    LLMResult,
    LLMTimeout,
)

REQ = LLMRequest(model="deepseek-v4.1-flash", messages=[ChatMessage("user", "привет")])


class RecordingLedger:
    def __init__(self) -> None:
        self.entries: list[UsageEntry] = []

    async def record(self, entry: UsageEntry) -> None:
        self.entries.append(entry)


class StubQuota:
    def __init__(self, exceeded: bool) -> None:
        self._exceeded = exceeded

    async def exceeded(self, family_id: Any) -> bool:
        return self._exceeded


class FlakyProvider(FakeProvider):
    def __init__(self, failures: list[Exception]) -> None:
        super().__init__()
        self._failures = failures

    async def complete(self, request: LLMRequest) -> LLMResult:
        if self._failures:
            self.calls.append(request)
            raise self._failures.pop(0)
        return await super().complete(request)


async def test_success_is_metered() -> None:
    ledger = RecordingLedger()
    gw = LLMGateway(FakeProvider(), ledger)  # type: ignore[arg-type]
    result = await gw.complete(REQ, feature="extraction")
    assert result.text == "ok"
    [entry] = ledger.entries
    assert (entry.status, entry.feature, entry.provider) == ("ok", "extraction", "fake")
    assert entry.input_tokens > 0


async def test_timeout_is_retried_once_and_both_calls_metered() -> None:
    ledger = RecordingLedger()
    provider = FlakyProvider([LLMTimeout("slow")])
    gw = LLMGateway(provider, ledger)  # type: ignore[arg-type]
    await gw.complete(REQ, feature="chat")
    assert [e.status for e in ledger.entries] == ["timeout", "ok"]


async def test_budget_exceeded_is_not_retried_and_reported() -> None:
    ledger = RecordingLedger()
    seen: list[tuple[str, str]] = []

    async def on_budget(model: str, feature: str) -> None:
        seen.append((model, feature))

    provider = FlakyProvider([LLMBudgetExceeded("Budget has been exceeded"), LLMBudgetExceeded("again")])
    gw = LLMGateway(provider, ledger, on_budget_exceeded=on_budget)  # type: ignore[arg-type]
    with pytest.raises(LLMBudgetExceeded):
        await gw.complete(REQ, feature="extraction")
    assert len(provider.calls) == 1
    assert [e.status for e in ledger.entries] == ["budget_exceeded"]
    assert seen == [("deepseek-v4.1-flash", "extraction")]


async def test_family_quota_blocks_before_calling_provider() -> None:
    import uuid

    provider = FakeProvider()
    gw = LLMGateway(provider, RecordingLedger(), quota=StubQuota(exceeded=True))  # type: ignore[arg-type]
    with pytest.raises(LLMQuotaExceeded):
        await gw.complete(REQ, feature="extraction", family_id=uuid.uuid4())
    assert provider.calls == []


def test_rub_to_micros_rounds_half_up() -> None:
    assert rub_to_micros(Decimal("0.0000015")) == 2
    assert rub_to_micros(Decimal("12.5")) == 12_500_000


class _Price:
    id = None
    input_per_million = Decimal("10")
    output_per_million = Decimal("40")
    cached_input_per_million = Decimal("2.5")


class StaticPriceBook(PriceBook):
    def __init__(self, price: Any) -> None:
        self._p = price

    async def current(self, model: str) -> Any:
        return self._p


async def test_proxy_reported_cost_wins_over_price_table() -> None:
    entry = UsageEntry("chat", "accelerator", "m", "ok", 10, 1000, 100, reported_cost_rub=Decimal("0.05"))
    assert await StaticPriceBook(_Price()).price(entry) == Priced(50_000, "proxy", None)


async def test_price_table_cost_in_micro_rub() -> None:
    # 800 uncached × 10 + 200 cached × 2.5 + 100 out × 40 = 8000 + 500 + 4000 micro-RUB
    entry = UsageEntry(
        "chat", "accelerator", "m", "ok", 10, input_tokens=1000, output_tokens=100, cached_input_tokens=200
    )
    priced = await StaticPriceBook(_Price()).price(entry)
    assert (priced.cost_micros, priced.source) == (12_500, "price_table")


async def test_unpriced_when_no_price_and_no_report() -> None:
    entry = UsageEntry("chat", "accelerator", "m", "ok", 10, 1000, 100)
    assert await StaticPriceBook(None).price(entry) == Priced(None, "unpriced", None)
