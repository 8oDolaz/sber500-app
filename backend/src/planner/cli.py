"""Ops commands: `python -m planner.cli <command>`."""

import argparse
import asyncio
import json
from pathlib import Path

from planner.settings import get_settings


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

    s = get_settings()
    available = set(await build_llm_provider(s).list_models())
    print("available:", ", ".join(sorted(available)))
    missing = sorted(s.llm_models_in_use - available)
    print("missing configured models:", missing or "none")
    if missing:
        raise SystemExit(1)


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


def main() -> None:
    parser = argparse.ArgumentParser(prog="planner")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("export-openapi")
    p.add_argument("out", type=Path)
    p = sub.add_parser("prices-sync", help="sync model_prices from the proxy /model/info or a YAML file")
    p.add_argument("--file", type=Path)
    sub.add_parser("check-models", help="verify configured LLM models exist on the proxy")
    sub.add_parser("set-webhook", help="point the Telegram bot webhook at PUBLIC_APP_URL")
    args = parser.parse_args()

    match args.cmd:
        case "export-openapi":
            export_openapi(args.out)
        case "prices-sync":
            asyncio.run(prices_sync(args.file))
        case "check-models":
            asyncio.run(check_models())
        case "set-webhook":
            asyncio.run(set_webhook())


if __name__ == "__main__":
    main()
