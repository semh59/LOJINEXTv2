import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from aiogram.types import Update
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from telegram_service.bot import build_bot, build_dispatcher
from telegram_service.config import settings, validate_prod_settings
from telegram_service.http_clients import http_manager
from telegram_service.middleware import PrometheusMiddleware, RequestIdMiddleware
from telegram_service.observability import setup_logging

logger = logging.getLogger(__name__)

_bot = build_bot()
_dp = build_dispatcher()
_polling_task: asyncio.Task[None] | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    global _polling_task
    setup_logging(settings.log_level)
    validate_prod_settings(settings)
    await http_manager.start()

    if settings.webhook_url:
        await _bot.set_webhook(
            url=f"{settings.webhook_url}/webhook",
            secret_token=settings.webhook_secret or None,
            drop_pending_updates=True,
        )
        logger.info("Webhook registered: %s/webhook", settings.webhook_url)
    else:
        await _bot.delete_webhook(drop_pending_updates=True)
        _polling_task = asyncio.create_task(_run_polling())
        logger.info("Bot started in polling mode")

    yield

    if _polling_task and not _polling_task.done():
        _polling_task.cancel()
        try:
            await _polling_task
        except asyncio.CancelledError:
            pass

    if settings.webhook_url:
        await _bot.delete_webhook()

    await http_manager.stop()
    await _bot.session.close()
    logger.info("Telegram-service shutdown complete")


async def _run_polling() -> None:
    from telegram_service.observability import correlation_id

    correlation_id.set(f"polling-{uuid.uuid4().hex[:8]}")
    await _dp.start_polling(_bot, handle_signals=False)


app = FastAPI(
    title="telegram-service",
    version=settings.service_version,
    lifespan=lifespan,
)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(PrometheusMiddleware)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> Response:
    """Readiness probe — checks trip-service and driver-service reachability."""
    checks: dict[str, str] = {}
    all_ok = True
    client = http_manager.get_client()

    for name, url in [
        ("trip_service", settings.trip_service_url),
        ("driver_service", settings.driver_service_url),
    ]:
        try:
            resp = await client.get(f"{url}/health", timeout=2.0)
            checks[name] = "ok" if resp.status_code == 200 else "fail"
        except Exception:
            checks[name] = "fail"
        if checks[name] != "ok":
            all_ok = False

    status_code = 200 if all_ok else 503
    return JSONResponse({"status": "ok" if all_ok else "fail", "checks": checks}, status_code=status_code)


@app.post("/webhook")
async def webhook(request: Request) -> Response:
    """Aiogram webhook receiver — only active when TELEGRAM_WEBHOOK_URL is set."""
    if not settings.webhook_url:
        return Response(status_code=404)

    # Verify secret token header if configured
    if settings.webhook_secret:
        token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if token != settings.webhook_secret:
            return Response(status_code=403)

    body = await request.json()
    update = Update.model_validate(body)
    await _dp.feed_update(_bot, update)
    return Response(status_code=200)


def run() -> None:
    import uvicorn

    setup_logging(settings.log_level)

    uvicorn.run(
        "telegram_service.main:app",
        host="0.0.0.0",
        port=settings.service_port,
        reload=settings.environment == "dev",
    )
