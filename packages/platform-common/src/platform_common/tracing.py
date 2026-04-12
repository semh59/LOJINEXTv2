"""OpenTelemetry tracing setup for LOJINEXT services.

Provides:
- ``setup_tracing(service_name, ...)`` — configures TracerProvider + OTLP exporter
- ``instrument_app(app)`` — auto-instruments FastAPI + httpx
- ``get_tracer()`` — returns the global tracer
- ``shutdown_tracing()`` — flushes pending spans
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger("platform_common.tracing")

_tracer: trace.Tracer | None = None


def setup_tracing(
    *,
    service_name: str,
    service_version: str = "0.0.0",
    environment: str = "development",
    otlp_endpoint: str = "http://localhost:4317",
    insecure: bool = True,
) -> None:
    """Configure the global TracerProvider and OTLP/gRPC exporter.

    Safe to call in dev/test environments — if the OTLP endpoint is
    unreachable, spans are queued and flushed in the background.
    """
    global _tracer  # noqa: PLW0603

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": service_version,
            "deployment.environment": environment,
        }
    )

    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=insecure)
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(service_name, service_version)

    logger.info(
        "OTEL tracing initialised — service=%s endpoint=%s",
        service_name,
        otlp_endpoint,
    )


def instrument_app(app: FastAPI) -> None:
    """Auto-instrument a FastAPI application and httpx clients."""
    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
    logger.info("FastAPI + httpx auto-instrumentation enabled")


def get_tracer() -> trace.Tracer:
    """Return the global tracer.

    If ``setup_tracing()`` has not been called, returns a no-op tracer.
    """
    if _tracer is None:
        return trace.get_tracer("platform_common")
    return _tracer


def shutdown_tracing() -> None:
    """Gracefully flush pending spans."""
    provider = trace.get_tracer_provider()
    if hasattr(provider, "force_flush"):
        provider.force_flush(timeout_millis=5000)
        logger.info("OTEL tracing shutdown complete")
