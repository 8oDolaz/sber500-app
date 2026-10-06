import json

from planner.cli import ping, ping_extract
from planner.modules.analytics.llm_ledger import UsageEntry
from planner.modules.assistant.llm_gateway.fake import FakeProvider, echo_task_responder
from planner.modules.assistant.llm_gateway.gateway import LLMGateway
from planner.modules.assistant.llm_gateway.port import ChatMessage, LLMRequest


class RecordingLedger:
    def __init__(self) -> None:
        self.entries: list[UsageEntry] = []

    async def record(self, entry: UsageEntry) -> None:
        self.entries.append(entry)


async def test_ping_prints_reply_tokens_and_is_ledgered() -> None:
    ledger = RecordingLedger()
    gw = LLMGateway(FakeProvider(lambda req: "Привет!"), ledger)  # type: ignore[arg-type]
    out = await ping(gw, LLMRequest(model="gigachat-3-pro", messages=[ChatMessage("user", "Скажи привет")]))
    assert out.startswith("Привет!")
    assert "model: gigachat-3-pro" in out
    assert "cost: not reported" in out
    [entry] = ledger.entries
    assert (entry.feature, entry.status) == ("ping", "ok")


async def test_ping_extract_shows_items_and_commands() -> None:
    def responder(req: LLMRequest) -> str:
        return json.dumps({"items": [{"kind": "event", "title": "Танцы", "date": "2026-10-08", "time": "18:00"}]})

    gw = LLMGateway(FakeProvider(responder), RecordingLedger())  # type: ignore[arg-type]
    out = await ping_extract(gw, "deepseek-v4.1-flash", "Танцы в четверг в 18:00", "Europe/Moscow")
    assert "1 item(s)" in out
    assert "NewEvent" in out and "Танцы" in out


async def test_ping_extract_with_no_items() -> None:
    gw = LLMGateway(FakeProvider(echo_task_responder), RecordingLedger())  # type: ignore[arg-type]
    out = await ping_extract(gw, "deepseek-v4.1-flash", "", "Europe/Moscow")
    assert "0 item(s)" in out
