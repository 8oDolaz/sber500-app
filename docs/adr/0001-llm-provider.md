# ADR 0001 — LLM provider: Sber500 accelerator proxy (Cloud.ru Foundation Models)

- Status: accepted · 2026-09-29
- Resolves: ARCHITECTURE §14 decisions #1 (data residency, leaning) and #2 (primary LLM provider)

## Context
The Sber500 × Disrupt program gives each team an OpenAI-compatible endpoint
(`https://shared1.multitool.works:4000/v1`, a LiteLLM-style proxy) backed by Cloud.ru
Foundation Models: GigaChat 3 / 3.5 and DeepSeek v4 family. Budget: 50 000 ₽ for the first
two weeks, up to 75 000 ₽ in total. Prices are in RUB (the proxy UI shows "$" but means ₽).
Models are added and removed without notice; `GET /v1/models` is the source of truth.

## Decision
- One adapter, `OpenAICompatibleProvider` (official `openai` SDK with `base_url`), behind the
  `LLMGateway` port. Models are chosen per *feature* in config
  (`LLM_MODEL_EXTRACTION`, `LLM_MODEL_CHAT`); the extraction default is chosen in M4 by the eval set.
- Cost is taken from the proxy's `x-litellm-response-cost` header (what the budget is charged);
  `model_prices` (synced from the proxy's `/model/info`) is the fallback.
- `429 "Budget has been exceeded"` → `LLMBudgetExceeded`: never retried, ledgered, tracked as
  `llm_budget_exceeded`, and the product degrades (M4: save the message as a plain task).
- `/readyz` and `python -m planner.cli check-models` verify that configured models still exist.
- `FakeProvider` is used in tests, CI and load tests so they spend nothing.

## Consequences
- Data is processed by a Russian provider → compatible with 152-FZ if the audience is in RF.
- Switching providers later means a new adapter, not changes to product code.
- Structured output support differs by model: extraction must validate JSON with Pydantic and
  retry once rather than rely on `response_format` alone.
