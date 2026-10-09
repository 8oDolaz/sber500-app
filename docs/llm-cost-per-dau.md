# LLM cost per DAU

Acceptance criterion: an LLM cost-per-DAU analysis in the context of how the product is used.

**Bottom line (estimate):** with `deepseek-v4.1-flash` for extraction, kainem costs about **0.14 ₽ per daily active user per day** at 3 forwarded messages per user per day. The realistic range is **0.03–0.40 ₽**, depending on usage and model. The whole program budget (75 000 ₽) covers roughly **half a million DAU-days** at the base rate.

**Update (ADR 0005):** extraction now uses the vision model `qwen3-vl-30b-a3b-instruct` so it can read photos. It is cheaper per token, about **0.023 ₽ per text call**, which puts the base rate near 0.08 ₽ per DAU-day. A photo adds about 1 000 input tokens (+0.034 ₽), so a photo capture costs about **0.06 ₽**.

These are estimates: there is no production traffic yet. The ledger measures the real number from the first real call (see "Measuring it for real" below).

## Where the product spends LLM money

Only one feature calls the LLM: **turning a message sent to the bot into a draft task or event** (`feature = "extraction"`).

The rest costs nothing:
- Opening the app, viewing lists and ticking tasks don't call the LLM.
- Invites and login don't either.
- Photos and voice aren't processed yet.
- The «save as-is» fallback runs without the LLM.

One capture = one call, plus:
- one retry when the model returns invalid JSON (estimated 3–5% of captures);
- one extra call per «Изменить» correction (estimated ~10% of drafts).

This gives **≈ 1.15 calls per capture**.

## Cost of one call

**Measured prompt** (`planner.modules.assistant.extraction`):
- The fixed system prompt is 1 052 characters: rules plus the JSON format.
- The user part averages 183 characters: date, timezone, member names, and the message (37 characters on average in the eval set).
- The output is about 130 characters of JSON per item, ~1.3 items on average.

**Tokens:** Russian text plus JSON at ~3 characters per token (range 2.5–4), plus ~20 tokens of chat template, gives **~430 input and ~60 output tokens per call**. The proxy reports exact token counts for every call; these estimates are replaced by measured values after the first eval run.

**Prices:** Cloud.ru Foundation Models catalog, ₽ per 1M tokens, checked 2026-09-30. VAT isn't stated in the catalog. The accelerator budget is charged at these prices.

| Model | Input | Output | **₽ per call** | ₽ per capture (×1.15) |
|---|---|---|---|---|
| deepseek-v4-flash | 43.30 | 86.58 | **0.024** | 0.027 |
| **qwen3-vl-30b-a3b-instruct** (default, reads photos) | 34.16 | 136.64 | **0.023** (photo: ~0.057) | 0.026 |
| deepseek-v4.1-flash (previous default, text only) | 64.94 | 194.81 | **0.040** | 0.046 |
| gigachat-3-pro | 73.03 | 176.39 | **0.042** | 0.048 |
| gigachat3.5-432b-a28b-reasoning | 96.22 | 288.60 | 0.059 + reasoning tokens* | ≥ 0.07 |
| deepseek-v4-pro | 183.00 | 732.00 | **0.123** | 0.142 |

\* Reasoning models also bill hidden "thinking" output. At a few hundred such tokens a call costs 0.15–0.2 ₽, which is overkill for extraction.

With 2.5 or 4 characters per token instead of 3, the per-call cost moves by about ±20%.

## Cost per DAU

₽ per DAU per day = captures per active user per day × 1.15 calls × ₽ per call.

Not every active user forwards messages. Some only open the app to look at the list, so captures per DAU is the number to watch.

| Usage scenario | Captures per DAU per day | v4-flash | **v4.1-flash** | gigachat-3-pro | v4-pro |
|---|---|---|---|---|---|
| Light (mostly viewing) | 1 | 0.03 ₽ | **0.05 ₽** | 0.05 ₽ | 0.14 ₽ |
| **Base** | 3 | 0.08 ₽ | **0.14 ₽** | 0.15 ₽ | 0.42 ₽ |
| Heavy (the family's planner) | 8 | 0.22 ₽ | **0.37 ₽** | 0.39 ₽ | 1.13 ₽ |

### What that means

- **Per family:** a family of three with two daily active members at the base rate spends about 0.27 ₽ a day, or about **8 ₽ a month**.
- **Program budget:** at the base rate, 75 000 ₽ ≈ 550 000 DAU-days, which is 1 000 DAU for about 18 months. The budget is not a constraint for the MVP.
- **Evals:** one run of the 30-case eval set costs ~1.5 ₽ per model.
- **Per-family quota:** the guard (`LLM_FAMILY_DAILY_QUOTA_RUB = 50`) sits two orders of magnitude above normal use, so it only stops abuse or bugs. The spend alerts fire at 50% and 80% of `LLM_PROGRAM_BUDGET_RUB`.

## How to keep it low

1. **Model choice** is the biggest lever. Pick the cheapest model that passes the eval set: v4-flash costs about 60% of v4.1-flash. Run `pytest -m eval` against the candidates and compare accuracy and ₽ per call in `eval-report.json`.
2. **The fixed system prompt is ~85% of the input.** If the proxy or Cloud.ru supports prompt caching, cached input is billed cheaper. `model_prices.cached_input_per_million` and `llm_usage.cached_input_tokens` already account for it. Otherwise, shortening the prompt has a direct effect.
3. **No LLM where it isn't needed:** the fallback, lists and invites stay free. If the assistant chat is added later, it is metered as its own `feature`.

## Measuring it for real

Every provider call writes a row to `llm_usage`: tokens, latency, status, and **the cost the proxy reports** (`x-litellm-response-cost`, what the budget is actually charged). Rows fall back to the `model_prices` table when the proxy doesn't report a cost.

- **Dashboard:** "kainem — product" → "₽ per DAU and per active family", "LLM cost per day by feature" and "LLM tokens per day". "kainem — technical" → "LLM tokens, total" and "LLM spend (proxy /key/info)": the total the proxy itself has charged to our key, which also counts evals, `llm-ping` and any other use of the key, so it can exceed the ledger.
- **Proxy total:** `python -m planner.cli proxy-spend` prints what LiteLLM `GET /key/info` reports for `LLM_API_KEY` (the worker exports it as `llm_proxy_spend_rub` every 5 minutes).
- **CLI:** `python -m planner.cli cost-report --days 7` prints daily DAU, calls, ₽ and ₽/DAU, then tokens and ₽ per call by model.
- **SQL:** views `metrics_cost_per_dau` and `metrics_llm_cost`. They exclude test users, the fake provider and eval runs. Calls with no known cost are counted in `unpriced_calls`, so a gap in pricing is visible rather than silently zero.

Once the key is available, the first eval run replaces the token estimates above with measured values. After launch, `cost-report` replaces the usage scenarios with real ones.
