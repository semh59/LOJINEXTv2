"""OpenTelemetry tracing setup for Trip Service.

Initialises a TracerProvider with an OTLP exporter (gRPC) and
provides helper functions for manual span creation and attribute
injection.
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

from trip_service.config import settings

logger = logging.getLogger("trip_service")

_tracer: trace.Tracer | None = None


def setup_tracing() -> None:
    """Configure the global TracerProvider and OTLP exporter.

    Safe to call in dev/test environments — if the OTLP endpoint is
    unreachable, spans are queued and flushed in the background.
    """
    global _tracer  # noqa: PLW0603

    resource = Resource.create(
        {
            "service.name": settings.service_name,
            "service.version": settings.service_version,
            "deployment.environment": settings.environment,
        }
    )

    provider = TracerProvider(resource=resource)

    otlp_exporter = OTLPSpanExporter(
        endpoint=settings.otel_exporter_otlp_endpoint,
        insecure=True,
    )
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(
        settings.service_name,
        settings.service_version,
    )

    logger.info(
        "OTEL tracing initialised — endpoint=%s",
        settings.otel_exporter_otlp_endpoint,
    )


def instrument_app(app: FastAPI) -> None:
    """Auto-instrument a FastAPI application and httpx clients."""
    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
    logger.info("FastAPI + httpx auto-instrumentation enabled")


def get_tracer() -> trace.Tracer:
    """Return the global tracer. Must call setup_tracing() first."""
    if _tracer is None:
        return trace.get_tracer(settings.service_name)
    return _tracer


def shutdown_tracing() -> None:
    """Gracefully flush pending spans."""
    provider = trace.get_tracer_provider()
    if hasattr(provider, "force_flush"):
        provider.force_flush(timeout_millis=5000)
        logger.info("OTEL tracing shutdown complete")