"""OpenTelemetry tracing construction and shutdown boundary."""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Tracer

from llmux.config import Settings

_INSTRUMENTATION_MODULE = "llmux"


def build_tracer(settings: Settings) -> Tracer:
    endpoint = settings.otel_exporter_otlp_endpoint.strip()
    if not endpoint:
        return trace.get_tracer(_INSTRUMENTATION_MODULE)
    resource = Resource.create({"service.name": settings.otel_service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    return trace.get_tracer(_INSTRUMENTATION_MODULE)


def shutdown_tracer() -> None:
    provider = trace.get_tracer_provider()
    if isinstance(provider, TracerProvider):
        provider.shutdown()
