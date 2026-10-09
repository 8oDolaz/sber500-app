# ADR 0005 — Photo capture through a vision model (VLM)

- Status: accepted · 2026-10-09
- Amends: ADR 0001 (the extraction model is now a vision model)

## Context
Families get plans as pictures as often as text: a photo of a school notice, a screenshot of a
chat, a poster, a timetable. Until now the bot answered photos with "I only understand text", and
only counted them (`capture_received` with `content_type = "photo"`). The extraction model,
`deepseek-v4.1-flash`, cannot read images.

Cloud.ru Foundation Models (tariff version 260915) offers several vision models. Prices are
₽ per 1M tokens incl. VAT, input / output:

| Model | Input | Output | Notes |
|---|---|---|---|
| **Qwen3-VL-30B-A3B-Instruct** | 34.16 | 136.64 | MoE, ~3B active params: fast; non-thinking; strong OCR incl. Cyrillic |
| Qwen3-VL-8B-Instruct | 30.74 | 119.56 | dense 8B: slightly cheaper, slower per token than the 3B-active MoE |
| Qwen3-VL-235B-A22B-Instruct | 68.32 | 273.28 | stronger, about 2× the price and slower |
| GigaChat-2-Max | 569.34 | — | Russian provider, reads images, an order of magnitude more expensive |
| Qwen3 VL Flash/Plus, GLM-4.6V Flash, Gemini | — | — | vendor-hosted APIs: user photos would leave Russia (152-FZ) |

## Decision
- **One model for all capture: `qwen3-vl-30b-a3b-instruct`** (`LLM_MODEL_EXTRACTION`). Text and
  photos go through the same extraction prompt, so drafts, fallbacks, analytics and the ledger
  stay one path. It is also cheaper per token than `deepseek-v4.1-flash` (34 / 137 vs 65 / 195 ₽).
- `ChatMessage` carries images; the OpenAI-compatible adapter sends them as base64 `image_url`
  data URLs (the proxy cannot fetch Telegram file URLs, and they contain the bot token).
- The bot accepts photos (the ~1280 px size Telegram already keeps, ~1k image tokens) and image
  files (JPEG/PNG/WebP, ≤ 5 MB). The caption is the message text. Each photo of an album is a
  separate capture. Voice, video and other files stay unsupported.
- **Images are never stored.** They are downloaded into memory, sent to the model and dropped.
  A draft from a photo without a caption keeps `source_text = "[фото]"`.
- Text on an image is untrusted data, like message text: the prompt says to ignore instructions in it.
- When extraction fails on a photo without a caption there is nothing to save as-is: the bot
  says it couldn't read the photo and asks for text instead of offering «Сохранить как задачу».
- `metrics_ai_quality.captures` counts text and photo captures; `captures_photo` breaks photos out.

## Consequences
- Photos are processed by the same Cloud.ru-backed proxy as text (ADR 0001); no new data flow abroad.
- A photo costs about 1k input tokens more than a text message: roughly +0.03 ₽ per capture.
- Text extraction quality must be re-checked on the golden set when switching models
  (`EVAL_MODELS=qwen3-vl-30b-a3b-instruct,deepseek-v4.1-flash pytest -m eval -s`).
- The model name must match what the proxy calls it (`check-models`); a wrong name fails the
  deploy smoke test (`/api/readyz` → `llm_models.ok: false`) before users see it.
- Albums produce one card set per photo, and a correction («Изменить») re-extracts from the
  corrected text only, without the photo.
