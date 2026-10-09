"""Provider-agnostic LLM port (ARCHITECTURE §6.1–6.2)."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal, Protocol

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class Image:
    """An image for a vision model (VLM). Kept in memory only, never stored."""

    data: bytes
    mime_type: str  # image/jpeg, image/png, image/webp


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    content: str
    images: tuple[Image, ...] = ()


@dataclass(frozen=True, slots=True)
class LLMRequest:
    model: str
    messages: list[ChatMessage]
    temperature: float = 0.0
    max_tokens: int | None = None
    json_mode: bool = False


@dataclass(frozen=True, slots=True)
class LLMResult:
    text: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    # Cost as billed by the provider/proxy when it reports one (LiteLLM: x-litellm-response-cost).
    reported_cost: Decimal | None = None
    extra: dict[str, str] = field(default_factory=dict)


class LLMError(Exception):
    status = "error"


class LLMTimeout(LLMError):
    status = "timeout"


class LLMRateLimited(LLMError):
    status = "rate_limited"


class LLMBudgetExceeded(LLMError):
    """The accelerator proxy key ran out of budget (HTTP 429 'Budget has been exceeded')."""

    status = "budget_exceeded"


class LLMQuotaExceeded(LLMError):
    """Our own per-family daily quota (ARCHITECTURE §6.5). No provider call was made."""

    status = "quota_exceeded"


class LLMProvider(Protocol):
    name: str

    async def complete(self, request: LLMRequest) -> LLMResult: ...

    async def list_models(self) -> list[str]: ...
