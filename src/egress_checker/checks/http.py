"""HTTP/HTTPS egress check implementation."""

import time

import httpx

from egress_checker.checks.result import CheckResult
from egress_checker.config import TargetConfig
from egress_checker.diagnostics import (
    DiagnosticData,
    classify_error,
    get_suggested_action,
)


async def check_http(target: TargetConfig) -> CheckResult:
    """Perform an HTTP/HTTPS egress check.

    Args:
        target: Target configuration.

    Returns:
        CheckResult with success/failure and diagnostic data.
    """
    assert target.url is not None  # noqa: S101

    host = target.effective_host
    port = target.effective_port
    start = time.monotonic()
    dns_duration_ms: float | None = None
    tls_duration_ms: float | None = None

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(target.timeout),
            verify=True,
        ) as client:
            dns_start = time.monotonic()
            response = await client.get(target.url)
            elapsed = time.monotonic() - start
            duration_ms = elapsed * 1000

            # Estimate DNS duration from httpx extensions if available
            dns_duration_ms = _extract_phase_duration(dns_start, elapsed)

            # Check status code
            status = response.status_code
            expected = target.expected_status
            is_success = _status_matches(status, expected)

            if is_success:
                return CheckResult(
                    target=target.name,
                    protocol=target.protocol.value,
                    host=host,
                    port=port,
                    success=True,
                    duration_ms=duration_ms,
                    http_status=status,
                    dns_duration_ms=dns_duration_ms,
                    tls_duration_ms=tls_duration_ms,
                )

            # Failed — classify the error
            category = classify_error(Exception(f"HTTP {status}"), http_status=status)
            diag = DiagnosticData(
                http_status=status,
                http_headers=dict(response.headers),
            )
            return CheckResult(
                target=target.name,
                protocol=target.protocol.value,
                host=host,
                port=port,
                success=False,
                duration_ms=duration_ms,
                http_status=status,
                error=f"Expected status {expected}, got {status}",
                failure_category=category,
                diagnostics=diag,
                suggested_action=get_suggested_action(category, host, port),
                dns_duration_ms=dns_duration_ms,
                tls_duration_ms=tls_duration_ms,
            )

    except Exception as e:
        elapsed = time.monotonic() - start
        duration_ms = elapsed * 1000
        category = classify_error(e)
        diag = DiagnosticData(error_detail=str(e))

        return CheckResult(
            target=target.name,
            protocol=target.protocol.value,
            host=host,
            port=port,
            success=False,
            duration_ms=duration_ms,
            error=str(e),
            failure_category=category,
            diagnostics=diag,
            suggested_action=get_suggested_action(category, host, port),
            dns_duration_ms=dns_duration_ms,
            tls_duration_ms=tls_duration_ms,
        )


def _status_matches(actual: int, expected: int) -> bool:
    """Check if an HTTP status matches the expected status.

    If expected is 200, we accept any 2xx status.
    Otherwise, exact match is required.
    """
    if expected == 200:
        return 200 <= actual < 300
    return actual == expected


def _extract_phase_duration(start: float, total_elapsed: float) -> float | None:
    """Estimate phase duration (placeholder for future httpx extension support)."""
    # httpx doesn't expose individual phase timings in a simple way.
    # Return None for now; can be enhanced with event hooks later.
    return None
