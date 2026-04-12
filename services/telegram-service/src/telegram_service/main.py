"""Telegram Service FastAPI application entry point — standardized with tracing."""

import asyncio
import logging
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from aiogram.types import Update
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from telegram_service.bot import build_bot, build_dispatcher
from telegram_service.config import settings, validate_prod_settings
from telegram_service.http_clients import http_manager
from telegram_service.middleware import PrometheusMiddleware, RequestIdMiddleware
from platform_common import setup_tracing, instrument_app, shutdown_tracing

logger = logging.getLogger("telegram_service")

# Bot/Dispatcher instances
_bot = build_bot()
_dp = build_dispatcher()
_polling_task: asyncio.Task[None] | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    global _polling_task
    from telegram_service.observability import setup_logging

    setup_logging(settings.environment == "dev" and logging.DEBUG or logging.INFO)
    validate_prod_settings(settings)

    # Initialise Core Platform Components
    setup_tracing(
        service_name="telegram-service",
        service_version=settings.service_version,
        environment=settings.environment,
        otlp_endpoint=settings.otel_exporter_otlp_endpoint,
    )
    instrument_app(app)

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

    # Shutdown sequence
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
    shutdown_tracing()
    logger.info("Telegram-service shutdown complete")


async def _run_polling() -> None:
    from telegram_service.observability import correlation_id

    correlation_id.set(f"polling-{uuid.uuid4().hex[:8]}")
    await _dp.start_polling(_bot, handle_signals=False)


app = FastAPI(
    title="Telegram Service",
    version=settings.service_version,
    description="Notification gateway and Telegram bot interface for LOJINEXT",
    lifespan=lifespan,
    docs_url=None if settings.environment == "prod" else "/docs",
)

# Standard Middleware
app.add_middleware(RequestIdMiddleware)
app.add_middleware(PrometheusMiddleware)


@app.get("/health", tags=["Infra"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", tags=["Infra"])
async def ready() -> Response:
    """Readiness probe checking upstream dependencies."""
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


@app.post("/webhook", tags=["Telegram"])
async def webhook(request: Request) -> Response:
    """Aiogram webhook receiver."""
    if not settings.webhook_url:
        return Response(status_code=404)

    if settings.webhook_secret:
        token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if token != settings.webhook_secret:
            return Response(status_code=403)

    body = await request.json()
    update = Update.model_validate(body)
    await _dp.feed_update(_bot, update)
    return Response(status_code=200)


def run() -> None:
    """Console entrypoint."""
    import uvicorn

    uvicorn.run(
        "telegram_service.main:app",
        host="0.0.0.0",
        port=settings.service_port,
        reload=settings.environment == "dev",
    )
