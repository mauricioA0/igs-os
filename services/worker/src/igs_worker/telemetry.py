"""OpenTelemetry wiring for Temporal (client + worker interceptors)."""

from temporalio.client import Interceptor

from .settings import WorkerSettings


def tracing_interceptors(settings: WorkerSettings) -> list[Interceptor]:
    """Spans for workflow/activity start and execution, propagated through Temporal headers.

    Imported lazily: ``temporalio.contrib.opentelemetry`` needs ``opentelemetry-sdk``, which is
    only installed where tracing is exported (Cloud Trace via the collector).
    """
    if not settings.otel_enabled:
        return []
    from temporalio.contrib.opentelemetry import TracingInterceptor

    return [TracingInterceptor()]
