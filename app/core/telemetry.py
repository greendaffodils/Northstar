"""Optional OpenTelemetry wiring; the application remains runnable without a collector."""
import logging
import os

from app.core.config import settings

log = logging.getLogger("northstar.telemetry")


def configure_api_telemetry(app) -> None:
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        log.info("OpenTelemetry dependencies unavailable; tracing disabled")
        return

    if isinstance(trace.get_tracer_provider(), TracerProvider):
        provider = trace.get_tracer_provider()
    else:
        provider = TracerProvider(resource=Resource.create({"service.name": settings.otel_service_name}))
        trace.set_tracer_provider(provider)
    endpoint = settings.otel_exporter_otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if endpoint:
        trace_endpoint = endpoint.rstrip("/")
        if not trace_endpoint.endswith("/v1/traces"):
            trace_endpoint += "/v1/traces"
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=trace_endpoint)))
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider, excluded_urls="health")


def tracer(name: str):
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        from contextlib import nullcontext

        class NoopTracer:
            @staticmethod
            def start_as_current_span(_name, **_kwargs):
                return nullcontext()
        return NoopTracer()
