"""Deterministic provider for tests, local dev and load tests (spends no budget)."""

import json
import re
from collections.abc import Callable

from planner.modules.assistant.llm_gateway.port import LLMError, LLMRequest, LLMResult

Responder = Callable[[LLMRequest], str]


class FakeProvider:
    name = "fake"

    def __init__(
        self,
        responder: Responder | None = None,
        *,
        models: list[str] | None = None,
        fail_with: LLMError | None = None,
    ) -> None:
        self._responder = responder or (lambda req: "{}" if req.json_mode else "ok")
        self._models = models
        self.fail_with = fail_with
        self.calls: list[LLMRequest] = []

    async def complete(self, request: LLMRequest) -> LLMResult:
        self.calls.append(request)
        if self.fail_with is not None:
            raise self.fail_with
        text = self._responder(request)
        prompt_chars = sum(len(m.content) for m in request.messages)
        return LLMResult(
            text=text,
            provider=self.name,
            model=request.model,
            input_tokens=max(1, prompt_chars // 4),
            output_tokens=max(1, len(text) // 4),
        )

    async def list_models(self) -> list[str]:
        return list(self._models) if self._models is not None else []


_MESSAGE = re.compile(r"<message>\n(.*?)\n</message>", re.S)


def echo_task_responder(request: LLMRequest) -> str:
    """For local dev, e2e and load tests: the message's first line becomes one task."""
    found = _MESSAGE.search(request.messages[-1].content if request.messages else "")
    text = found.group(1).strip() if found else ""
    if not text:
        return json.dumps({"items": []})
    return json.dumps({"items": [{"kind": "task", "title": text.splitlines()[0][:120]}]}, ensure_ascii=False)
