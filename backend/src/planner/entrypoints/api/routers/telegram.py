import hmac

from fastapi import APIRouter, Header, HTTPException, Request, Response

router = APIRouter(tags=["webhooks"], include_in_schema=False)


@router.post("/webhooks/telegram")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> Response:
    bot, dp = request.app.state.bot, request.app.state.dispatcher
    if bot is None:
        raise HTTPException(503, "bot is not configured")
    expected = request.app.state.container.settings.bot_webhook_secret.get_secret_value()
    if not expected or not hmac.compare_digest(x_telegram_bot_api_secret_token or "", expected):
        raise HTTPException(401)
    await dp.feed_webhook_update(bot, await request.json())
    return Response(status_code=200)
