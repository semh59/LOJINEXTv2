"""Standard platform middleware for Identity Service."""

from __future__ import annotations

import json
import re
import time
from uuid import uuid4

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from identity_service.observability import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
    correlation_id,
    get_standard_labels,
)


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        correlation_id_val = (
            headers.get(b"x-correlation-id", b"").decode()
            or headers.get(b"x-request-id", b"").decode()
            or str(uuid4())
        )

        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["correlation_id"] = correlation_id_val
        scope["state"]["request_id"] = correlation_id_val

        token = correlation_id.set(correlation_id_val)

        async def send_with_ids(message: Message) -> None:
            if message["type"] == "http.response.start":
                existing_headers = list(message.get("headers", []))
                existing_headers.append(
                    (b"X-Correlation-ID", correlation_id_val.encode())
                )
                existing_headers.append((b"X-Request-Id", correlation_id_val.encode()))
                message["headers"] = existing_headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_ids)
        finally:
            correlation_id.reset(token)


class PrometheusMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        if path == "/metrics":
            body = generate_latest()
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        [b"content-type", CONTENT_TYPE_LATEST.encode()],
                        [b"content-length", str(len(body)).encode()],
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        method = scope["method"]
        endpoint = path

        start_time = time.perf_counter()
        status_code = [500]

        async def wrapped_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_code[0] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        except Exception:
            _record_metrics(
                method, _normalize_path(endpoint), status_code[0], start_time
            )
            raise
        else:
            _record_metrics(
                method, _normalize_path(endpoint), status_code[0], start_time
            )


def _normalize_path(path: str) -> str:
    """Normalize path by replacing ULID, UUID and common numeric IDs with placeholders."""
    # Replace ULIDs (26 chars, uppercase/alphanumeric)
    path = re.sub(r"/[0-9A-HJKMNP-TV-Z]{26}", "/{id}", path)
    # Replace UUIDs
    path = re.sub(
        r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "/{uuid}",
        path,
    )
    # Replace numeric IDs
    path = re.sub(r"/\d+", "/{id}", path)
    return path


def _record_metrics(
    method: str, endpoint: str, status_code: int, start_time: float
) -> None:
    duration = time.perf_counter() - start_time
    labels = get_standard_labels()
    HTTP_REQUESTS_TOTAL.labels(
        method=method, endpoint=endpoint, status_code=status_code, **labels
    ).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(
        method=method, endpoint=endpoint, **labels
    ).observe(duration)


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
            "type": f"https://identity-service/errors/{error_code}",
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

        from identity_service.config import settings

        path = scope.get("path", "")

        if path not in ("/auth/v1/login", "/auth/v1/token/service"):
            await self._app(scope, receive, send)
            return

        # Buffer the body so both this middleware and the router can read it
        body_chunks: list[bytes] = []

        async def cached_receive() -> dict:
            message = await receive()
            if message["type"] == "http.request":
                body_chunks.append(message.get("body", b""))
            return message

        # We need to read the body to extract username for login lockout.
        # Consume the receive stream once, then replay it via a closure.
        raw_body = b""
        more_body = True
        messages: list[dict] = []
        while more_body:
            msg = await receive()
            messages.append(msg)
            if msg["type"] == "http.request":
                raw_body += msg.get("body", b"")
                more_body = msg.get("more_body", False)

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

        from identity_service.redis_client import get_redis

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
            # /auth/v1/token/service — IP-only window
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
