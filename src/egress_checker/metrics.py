"""Prometheus metrics definitions and instrumentation."""

from prometheus_client import Counter, Gauge, Histogram, start_http_server

EGRESS_CHECK_SUCCESS = Gauge(
    "egress_check_success",
    "Whether the most recent check succeeded (1) or failed (0)",
    ["target", "protocol", "namespace"],
)

EGRESS_CHECK_DURATION = Histogram(
    "egress_check_duration_seconds",
    "Total check duration in seconds",
    ["target", "protocol", "namespace"],
)

EGRESS_CHECK_TOTAL = Counter(
    "egress_check_total",
    "Total number of checks performed",
    ["target", "protocol", "namespace", "result"],
)

EGRESS_CHECK_FAILURE_CATEGORY = Gauge(
    "egress_check_failure_category",
    "Whether the most recent failure matches this category (1 or 0)",
    ["target", "protocol", "namespace", "category"],
)

EGRESS_CHECK_DNS_DURATION = Histogram(
    "egress_check_dns_duration_seconds",
    "DNS resolution duration in seconds",
    ["target", "namespace"],
)

EGRESS_CHECK_TLS_DURATION = Histogram(
    "egress_check_tls_duration_seconds",
    "TLS handshake duration in seconds",
    ["target", "namespace"],
)

EGRESS_CHECKER_HEALTHY = Gauge(
    "egress_checker_healthy",
    "Whether the checker is healthy (1) or unhealthy (0)",
)


def start_metrics_server(port: int = 9090) -> None:
    """Start the Prometheus metrics HTTP server.

    Args:
        port: Port to listen on for metrics scraping.
    """
    start_http_server(port)


def record_check_result(
    *,
    target: str,
    protocol: str,
    namespace: str,
    success: bool,
    duration_seconds: float,
    failure_category: str | None = None,
    dns_duration_seconds: float | None = None,
    tls_duration_seconds: float | None = None,
) -> None:
    """Record the result of an egress check in Prometheus metrics.

    Args:
        target: Target name.
        protocol: Check protocol.
        namespace: Kubernetes namespace.
        success: Whether the check succeeded.
        duration_seconds: Total check duration.
        failure_category: Failure category if check failed.
        dns_duration_seconds: DNS resolution duration if measured.
        tls_duration_seconds: TLS handshake duration if measured.
    """
    labels = {"target": target, "protocol": protocol, "namespace": namespace}

    EGRESS_CHECK_SUCCESS.labels(**labels).set(1 if success else 0)
    EGRESS_CHECK_DURATION.labels(**labels).observe(duration_seconds)

    result = "success" if success else "failure"
    EGRESS_CHECK_TOTAL.labels(**labels, result=result).inc()

    # Update failure category gauges
    from egress_checker.diagnostics import FailureCategory

    for category in FailureCategory:
        cat_val = 1 if (not success and failure_category == category.value) else 0
        EGRESS_CHECK_FAILURE_CATEGORY.labels(**labels, category=category.value).set(cat_val)

    # Phase-level durations
    phase_labels = {"target": target, "namespace": namespace}
    if dns_duration_seconds is not None:
        EGRESS_CHECK_DNS_DURATION.labels(**phase_labels).observe(dns_duration_seconds)
    if tls_duration_seconds is not None:
        EGRESS_CHECK_TLS_DURATION.labels(**phase_labels).observe(tls_duration_seconds)
