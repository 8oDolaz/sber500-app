"""Checks that the configured models still exist on the proxy (it drops models without notice)."""

import time
from dataclasses import dataclass

from planner.modules.assistant.llm_gateway.gateway import LLMGateway
from planner.modules.assistant.llm_gateway.port import LLMError


@dataclass(frozen=True, slots=True)
class ModelsStatus:
    ok: bool
    missing: list[str]
    error: str | None = None


class ModelsHealth:
    def __init__(self, gateway: LLMGateway, required: set[str], ttl_s: float = 300) -> None:
        self._gateway = gateway
        self._required = required
        self._ttl = ttl_s
        self._cached: tuple[float, ModelsStatus] | None = None

    async def status(self) -> ModelsStatus:
        if self._cached and time.monotonic() - self._cached[0] < self._ttl:
            return self._cached[1]
        try:
            available = set(await self._gateway.list_models())
        except LLMError as exc:
            result = ModelsStatus(ok=False, missing=sorted(self._required), error=str(exc)[:300])
        else:
            missing = sorted(self._required - available)
            result = ModelsStatus(ok=not missing, missing=missing)
        self._cached = (time.monotonic(), result)
        return result
