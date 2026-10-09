"""Ops commands: `python -m planner.cli <command>`."""

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING

from planner.settings import get_settings

if TYPE_CHECKING:
    from planner.modules.assistant.llm_gateway.gateway import LLMGateway
    from planner.modules.assistant.llm_gateway.port import Image, LLMRequest

IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def export_openapi(out: Path) -> None:
    from planner.entrypoints.api.app import create_app

    spec = create_app().openapi()
    out.write_text(json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(f"wrote {out}")


async def prices_sync(file: Path | None) -> None:
    from planner.infra.db import Database
    from planner.modules.analytics.price_sync import apply_quotes, fetch_from_proxy, parse_yaml

    s = get_settings()
    if file:
        quotes, source = parse_yaml(file), "manual"
    else:
        quotes, source = await fetch_from_proxy(s.llm_base_url, s.llm_api_key.get_secret_value()), "proxy_model_info"
    db = Database(s.database_url)
    try:
        changed = await apply_quotes(db, quotes, provider="accelerator", source=source)
    finally:
        await db.dispose()
    print(f"{len(quotes)} quotes, changed: {changed or 'none'}")


async def check_models() -> None:
    from planner.bootstrap import build_llm_provider
    from planner.modules.assistant.llm_gateway.port import LLMError

    s = get_settings()
    try:
        available = set(await build_llm_provider(s).list_models())
    except LLMError as exc:
        raise SystemExit(f"cannot list models at {s.llm_base_url}: {exc}") from exc
    print("available:", ", ".join(sorted(available)))
    missing = sorted(s.llm_models_in_use - available)
    print("missing configured models:", missing or "none")
    if missing:
        raise SystemExit(1)


async def proxy_spend() -> None:
    from planner.modules.analytics.proxy_spend import fetch_key_spend, proxy_root

    s = get_settings()
    key = await fetch_key_spend(s.llm_base_url, s.llm_api_key.get_secret_value())
    budget = f"{key.max_budget_rub} ₽" if key.max_budget_rub is not None else "not set on the key"
    print(f"{proxy_root(s.llm_base_url)}/key/info\nspend: {key.spend_rub} ₽\nmax budget: {budget}")


async def ping(llm: "LLMGateway", request: "LLMRequest") -> str:
    """One request through the gateway (ledger, metrics, quota), formatted for a human."""
    started = time.perf_counter()
    result = await llm.complete(request, feature="ping")
    latency_ms = int((time.perf_counter() - started) * 1000)
    cost = f"{result.reported_cost} ₽" if result.reported_cost is not None else "not reported"
    return (
        f"{result.text}\n\n"
        f"model: {result.model} · {latency_ms} ms\n"
        f"tokens: in {result.input_tokens} (cached {result.cached_input_tokens}) · out {result.output_tokens}\n"
        f"cost: {cost}"
    )


def load_image(path: Path) -> "Image":
    from planner.modules.assistant.llm_gateway.port import Image

    mime_type = IMAGE_TYPES.get(path.suffix.lower())
    if mime_type is None:
        raise SystemExit(f"--image must be one of {', '.join(IMAGE_TYPES)}: {path}")
    return Image(path.read_bytes(), mime_type)


async def ping_extract(llm: "LLMGateway", model: str, message: str, tz: str, images: tuple["Image", ...] = ()) -> str:
    """The production extraction prompt on one message (and photo): validated items and their commands."""
    from datetime import UTC, datetime

    from planner.modules.assistant.extraction import ExtractionContext, Extractor, PlanningError, to_command

    ctx = ExtractionContext(reference=datetime.now(UTC), timezone=tz, member_names=[])
    result = await Extractor(llm, model).extract(message, ctx, images)
    lines = [f"model: {result.model} · {len(result.items)} item(s)"]
    for item in result.items:
        lines.append(f"- {item.model_dump_json(by_alias=True)}")
        try:
            lines.append(f"  → {to_command(item, ctx)}")
        except PlanningError as exc:
            lines.append(f"  → skipped: {exc}")
    return "\n".join(lines)


async def llm_ping(
    text: str, *, model: str | None, system: str | None, json_mode: bool, extract: bool, image: Path | None
) -> None:
    from planner.bootstrap import build_container
    from planner.modules.assistant.extraction import InvalidOutput
    from planner.modules.assistant.llm_gateway.port import ChatMessage, LLMError, LLMRequest

    s = get_settings()
    images = (load_image(image),) if image else ()
    c = build_container(s)
    try:
        if extract:
            out = await ping_extract(c.llm, model or s.llm_model_extraction, text, s.reporting_tz, images)
        else:
            system_msgs = [ChatMessage("system", system)] if system else []
            request = LLMRequest(
                model=model or (s.llm_model_extraction if images else s.llm_model_chat),
                messages=[*system_msgs, ChatMessage("user", text, images=images)],
                temperature=0.3,
                max_tokens=800,
                json_mode=json_mode,
            )
            out = await ping(c.llm, request)
    except (LLMError, InvalidOutput) as exc:
        raise SystemExit(f"{type(exc).__name__}: {exc}") from exc
    finally:
        await c.aclose()
    print(f"provider: {c.llm.provider_name}\n{out}")


async def cost_report(days: int) -> None:
    """Actual LLM spend vs. DAU from the ledger (views metrics_cost_per_dau / metrics_llm_cost)."""
    from sqlalchemy import text

    from planner.infra.db import Database

    db = Database(get_settings().database_url)
    try:
        async with db.sessions() as s:
            daily = (
                await s.execute(
                    text(
                        "SELECT day, dau, llm_calls, cost_rub, rub_per_dau FROM metrics_cost_per_dau "
                        "WHERE day > current_date - CAST(:days AS integer) ORDER BY day"
                    ),
                    {"days": days},
                )
            ).all()
            by_model = (
                await s.execute(
                    text(
                        "SELECT feature, model, sum(calls) calls, sum(unpriced_calls) unpriced, "
                        "sum(input_tokens) tin, sum(output_tokens) tout, sum(cost_rub) rub "
                        "FROM metrics_llm_cost WHERE day > current_date - CAST(:days AS integer) "
                        "GROUP BY 1, 2 ORDER BY rub DESC"
                    ),
                    {"days": days},
                )
            ).all()
    finally:
        await db.dispose()

    print(f"{'day':<12}{'DAU':>6}{'calls':>8}{'₽':>12}{'₽/DAU':>10}")
    for r in daily:
        print(f"{r.day!s:<12}{r.dau:>6}{r.llm_calls:>8}{r.cost_rub:>12}{r.rub_per_dau or '-':>10}")
    total_rub = sum(r.cost_rub for r in daily)
    dau_days = sum(r.dau for r in daily)
    print(
        f"\ntotal: {total_rub} ₽ over {dau_days} DAU-days → {(total_rub / dau_days) if dau_days else '-'} ₽ per DAU-day"
    )
    header = f"{'feature':<12}{'model':<24}{'calls':>7}{'unpriced':>9}{'in tok/call':>12}{'out tok/call':>13}"
    print(f"\n{header}{'₽/call':>10}")
    for r in by_model:
        n = r.calls or 1
        print(
            f"{r.feature:<12}{r.model:<24}{r.calls:>7}{r.unpriced:>9}{r.tin // n:>12}{r.tout // n:>13}"
            f"{round(r.rub / n, 4):>10}"
        )


async def set_webhook() -> None:
    from planner.entrypoints.bot.app import build_bot

    s = get_settings()
    bot = build_bot(s)
    if bot is None:
        raise SystemExit("BOT_TOKEN is not set")
    url = f"{s.public_app_url.rstrip('/')}/api/webhooks/telegram"
    try:
        await bot.set_webhook(
            url,
            secret_token=s.bot_webhook_secret.get_secret_value(),
            allowed_updates=["message", "callback_query", "inline_query", "chosen_inline_result", "my_chat_member"],
        )
    finally:
        await bot.session.close()
    print(f"webhook set to {url}")


async def bot_check() -> None:
    from planner.entrypoints.bot.app import build_bot

    s = get_settings()
    bot = build_bot(s)
    if bot is None:
        raise SystemExit("BOT_TOKEN is not set")
    try:
        me = await bot.get_me()
        webhook = await bot.get_webhook_info()
    finally:
        await bot.session.close()
    print(f"@{me.username} reachable via {s.telegram_proxy or 'a direct connection'}")
    print(f"webhook: {webhook.url or 'none (long polling)'}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="planner")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("export-openapi")
    p.add_argument("out", type=Path)
    p = sub.add_parser("prices-sync", help="sync model_prices from the proxy /model/info or a YAML file")
    p.add_argument("--file", type=Path)
    sub.add_parser("check-models", help="verify configured LLM models exist on the proxy")
    sub.add_parser("proxy-spend", help="what the proxy says our API key has spent (/key/info)")
    p = sub.add_parser("llm-ping", help="send one message to the configured LLM and print the reply, tokens and ₽")
    p.add_argument("text")
    p.add_argument("--model", help="default: LLM_MODEL_CHAT (LLM_MODEL_EXTRACTION with --extract or --image)")
    p.add_argument("--system", help="optional system prompt")
    p.add_argument("--json", action="store_true", help="ask for a JSON object (response_format)")
    p.add_argument("--extract", action="store_true", help="run the production extraction prompt instead")
    p.add_argument("--image", type=Path, help="attach a .jpg/.png/.webp file (the model must be a VLM)")
    sub.add_parser("set-webhook", help="point the Telegram bot webhook at PUBLIC_APP_URL")
    sub.add_parser("bot-check", help="call the Bot API (through TELEGRAM_PROXY if set) and show the webhook state")
    p = sub.add_parser("cost-report", help="LLM ₽ per DAU from the ledger for the last N days")
    p.add_argument("--days", type=int, default=7)
    args = parser.parse_args()

    match args.cmd:
        case "export-openapi":
            export_openapi(args.out)
        case "prices-sync":
            asyncio.run(prices_sync(args.file))
        case "check-models":
            asyncio.run(check_models())
        case "proxy-spend":
            asyncio.run(proxy_spend())
        case "llm-ping":
            asyncio.run(
                llm_ping(
                    args.text,
                    model=args.model,
                    system=args.system,
                    json_mode=args.json,
                    extract=args.extract,
                    image=args.image,
                )
            )
        case "set-webhook":
            asyncio.run(set_webhook())
        case "bot-check":
            asyncio.run(bot_check())
        case "cost-report":
            asyncio.run(cost_report(args.days))


if __name__ == "__main__":
    main()
