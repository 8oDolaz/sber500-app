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


def main() -> None:
    parser = argparse.ArgumentParser(prog="planner")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("export-openapi")
    p.add_argument("out", type=Path)
    p = sub.add_parser("prices-sync", help="sync model_prices from the proxy /model/info or a YAML file")
    p.add_argument("--file", type=Path)
    sub.add_parser("check-models", help="verify configured LLM models exist on the proxy")
    sub.add_parser("set-webhook", help="point the Telegram bot webhook at PUBLIC_APP_URL")
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
        case "set-webhook":
            asyncio.run(set_webhook())
        case "cost-report":
            asyncio.run(cost_report(args.days))


if __name__ == "__main__":
    main()
