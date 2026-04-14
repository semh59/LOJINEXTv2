"""Standard platform middleware for Auth Service."""

from __future__ import annotations

import json
from typing import cast
from uuid import uuid4

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send
from platform_common import RequestIdMiddleware, PrometheusMiddleware

__all__ = ["RequestIdMiddleware", "PrometheusMiddleware", "RateLimitMiddleware"]


def _rate_limit_error(
    error_code: str,
    message: str,
    request_id: str,
    path: str,
    retry_after: int | None = None,
) -> JSONResponse:
    headers = {"Retry-After": str(retry_after)} if retry_after else {}
    return JSONResponse(
        status_code=429,
        content={
            "type": f"https://auth-service/errors/{error_code}",
            "title": "Rate limited",
            "status": 429,
            "detail": message,
            "instance": path,
            "code": error_code,
            "request_id": request_id,
        },
        headers=headers,
        media_type="application/problem+json",
    )


class RateLimitMiddleware:
    """Distributed Redis-backed rate limiter for auth endpoints.

    Protects:
    - /auth/v1/login: per-IP sliding window + per-username failure lockout
    - /auth/v1/token/service: per-IP sliding window

    Uses a raw ASGI middleware (not BaseHTTPMiddleware) to safely read
    and re-buffer the request body without consuming the stream.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        from auth_service.config import settings

        path = scope.get("path", "")

        if path not in ("/auth/v1/login", "/auth/v1/token/service"):
            await self._app(scope, receive, send)
            return

        # We need to read the body to extract username for login lockout.
        # Consume the receive stream once, then replay it via a closure.
        body_chunks: list[bytes] = []
        more_body = True
        messages: list[dict] = []
        while more_body:
            msg = await receive()
            messages.append(msg)
            if msg["type"] == "http.request":
                body_chunks.append(cast(bytes, msg.get("body", b"")))
                more_body = msg.get("more_body", False)

        raw_body = b"".join(body_chunks)

        # Build a replay receive so the downstream handler gets the same body
        msg_iter = iter(messages)

        async def replay_receive() -> dict:
            try:
                return next(msg_iter)
            except StopIteration:
                return {"type": "http.disconnect"}

        # Extract correlation id from headers if already set
        headers_dict = {k.decode(): v.decode() for k, v in scope.get("headers", [])}
        request_id = (
            headers_dict.get("x-correlation-id")
            or headers_dict.get("x-request-id")
            or str(uuid4())
        )
        client_ip = (scope.get("client") or ("unknown", 0))[0]

        from auth_service.redis_client import get_redis

        redis = await get_redis()

        if path == "/auth/v1/login":
            limit = settings.rate_limit_login_per_minute

            # Per-IP window
            ip_key = f"rl:login:ip:{client_ip}"
            count = await redis.incr(ip_key)
            if count == 1:
                await redis.expire(ip_key, 60)
            if count > limit:
                await _send_json_response(
                    send,
                    scope,
                    _rate_limit_error(
                        "RATE_LIMITED",
                        "Too many login attempts. Try again later.",
                        request_id,
                        path,
                        retry_after=60,
                    ),
                )
                return

            # Per-username lockout check
            username = _extract_username(raw_body)
            if username:
                lockout_key = f"rl:login:lockout:{username}"
                if await redis.exists(lockout_key):
                    ttl = await redis.ttl(lockout_key)
                    await _send_json_response(
                        send,
                        scope,
                        _rate_limit_error(
                            "ACCOUNT_LOCKED",
                            f"Account temporarily locked. Try again in {max(ttl, 1)} seconds.",
                            request_id,
                            path,
                            retry_after=max(ttl, 1),
                        ),
                    )
                    return
            else:
                username = None

            # Call downstream
            status_holder: list[int] = []
            patched_send = _status_capturing_send(send, status_holder)
            await self._app(scope, replay_receive, patched_send)

            # Track failures for lockout
            if username and status_holder and status_holder[0] == 401:
                fail_key = f"rl:login:fail:{username}"
                failures = await redis.incr(fail_key)
                if failures == 1:
                    await redis.expire(
                        fail_key, settings.rate_limit_login_lockout_seconds
                    )
                if failures >= settings.rate_limit_login_failures_before_lockout:
                    await redis.setex(
                        f"rl:login:lockout:{username}",
                        settings.rate_limit_login_lockout_seconds,
                        "1",
                    )
            elif username and status_holder and status_holder[0] == 200:
                # Successful login clears failure counter
                await redis.delete(f"rl:login:fail:{username}")

        else:
            # /auth/v1/token/service ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â IP-only window
            limit = settings.rate_limit_service_token_per_minute
            ip_key = f"rl:service_token:ip:{client_ip}"
            count = await redis.incr(ip_key)
            if count == 1:
                await redis.expire(ip_key, 60)
            if count > limit:
                await _send_json_response(
                    send,
                    scope,
                    _rate_limit_error(
                        "RATE_LIMITED",
                        "Too many token requests. Try again later.",
                        request_id,
                        path,
                        retry_after=60,
                    ),
                )
                return

            await self._app(scope, replay_receive, send)


def _extract_username(raw_body: bytes) -> str | None:
    """Best-effort JSON parse to extract the username field."""
    try:
        data = json.loads(raw_body)
        return str(data.get("username", "")).strip() or None
    except Exception:
        return None


def _status_capturing_send(original_send: Send, holder: list[int]):
    """Wrap send to capture the HTTP status code from the response start message."""

    async def patched_send(message: dict) -> None:
        if message.get("type") == "http.response.start":
            holder.append(message.get("status", 0))
        await original_send(message)

    return patched_send


async def _send_json_response(send: Send, scope: Scope, response: JSONResponse) -> None:
    """Send a JSONResponse through the raw ASGI send channel."""
    await response(scope, _noop_receive, send)


async def _noop_receive() -> dict:
    return {"type": "http.disconnect"}
