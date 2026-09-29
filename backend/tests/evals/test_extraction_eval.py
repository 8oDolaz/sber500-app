"""Extraction quality and cost against the real accelerator proxy (spends budget!).

    LLM_API_KEY=… EVAL_MODELS=deepseek-v4.1-flash,gigachat-3-pro uv run pytest -m eval -s

Prints accuracy, failures and ₽ per call for each model and writes eval-report.json.
Used to choose LLM_MODEL_EXTRACTION (ADR 0001).
"""

import contextlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

from planner.domain.planning import NewEvent, NewTask, PlanningError
from planner.modules.analytics.llm_ledger import UsageEntry
from planner.modules.assistant.extraction import ExtractionContext, Extractor, InvalidOutput, to_command
from planner.modules.assistant.llm_gateway.gateway import LLMGateway
from planner.modules.assistant.llm_gateway.openai_compatible import OpenAICompatibleProvider
from planner.modules.assistant.llm_gateway.port import LLMError
from planner.settings import Settings

pytestmark = pytest.mark.eval

TZ = "Europe/Moscow"
CASES = yaml.safe_load((Path(__file__).parent / "extraction_cases.yaml").read_text())
MIN_ACCURACY = float(os.getenv("EVAL_MIN_ACCURACY", "0.8"))


@dataclass
class CostLedger:
    entries: list[UsageEntry] = field(default_factory=list)

    async def record(self, entry: UsageEntry) -> None:
        self.entries.append(entry)

    @property
    def rub(self) -> Decimal:
        return sum((e.reported_cost_rub or Decimal(0) for e in self.entries), Decimal(0))


def facts(cmd: NewTask | NewEvent) -> dict[str, str | None]:
    zone = ZoneInfo(TZ)
    if isinstance(cmd, NewTask):
        when = cmd.due_at.astimezone(zone) if cmd.due_at else None
        return {
            "kind": "task",
            "date": str(cmd.due_date) if cmd.due_date else None,
            "time": f"{when:%H:%M}" if when else None,
        }
    if cmd.starts_at:
        start = cmd.starts_at.astimezone(zone)
        return {"kind": "event", "date": str(start.date()), "time": f"{start:%H:%M}"}
    return {"kind": "event", "date": str(cmd.start_date), "time": None}


def matches(expected: dict, got: dict) -> bool:
    if expected["kind"] != "any" and expected["kind"] != got["kind"]:
        return False
    return all(expected[k] == got[k] for k in ("date", "time") if k in expected)


def judge(case: dict, got: list[dict]) -> bool:
    expected = case["expect"]
    if not expected:
        return not got
    remaining = list(got)
    for exp in expected:
        hit = next((g for g in remaining if matches(exp, g)), None)
        if hit is None:
            return False
        remaining.remove(hit)
    return case.get("allow_extra", False) or not remaining


def write_report(model: str, report: dict) -> None:
    """Merge into eval-report.json so several models can be compared side by side."""
    out = Path(os.getenv("EVAL_REPORT", "eval-report.json"))
    existing = json.loads(out.read_text()) if out.exists() else {}
    existing[model] = report
    out.write_text(json.dumps(existing, ensure_ascii=False, indent=2))


def models() -> list[str]:
    return [m.strip() for m in os.getenv("EVAL_MODELS", Settings().llm_model_extraction).split(",") if m.strip()]


@pytest.mark.parametrize("model", models())
async def test_extraction_quality(model: str) -> None:
    settings = Settings()
    if not settings.llm_api_key.get_secret_value():
        pytest.skip("LLM_API_KEY is not set")
    ledger = CostLedger()
    provider = OpenAICompatibleProvider(
        base_url=settings.llm_base_url, api_key=settings.llm_api_key.get_secret_value(), timeout_s=60
    )
    extractor = Extractor(LLMGateway(provider, ledger), model)  # type: ignore[arg-type]

    passed, failures = 0, []
    for case in CASES:
        ctx = ExtractionContext(
            reference=datetime.fromisoformat(case["reference"]).replace(tzinfo=ZoneInfo(TZ)),
            timezone=TZ,
            member_names=["Дима", "Даша", "Маша", "Петя", "Соня"],
        )
        try:
            result = await extractor.extract(case["text"], ctx)
            got = []
            for item in result.items:
                with contextlib.suppress(PlanningError):  # unusable items are skipped, as in production
                    got.append(facts(to_command(item, ctx)))
        except (LLMError, InvalidOutput) as exc:
            got = [{"error": repr(exc)[:200]}]
        if judge(case, got):
            passed += 1
        else:
            failures.append({"text": case["text"], "expected": case["expect"], "got": got})

    accuracy = passed / len(CASES)
    calls = len(ledger.entries)
    report = {
        "model": model,
        "accuracy": round(accuracy, 3),
        "cases": len(CASES),
        "calls": calls,
        "cost_rub": str(ledger.rub),
        "rub_per_call": str((ledger.rub / calls).quantize(Decimal("0.0001")) if calls else 0),
        "avg_latency_ms": sum(e.latency_ms for e in ledger.entries) // max(calls, 1),
        "failures": failures,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    write_report(model, report)
    assert accuracy >= MIN_ACCURACY, f"{model}: {accuracy:.0%} < {MIN_ACCURACY:.0%}"
