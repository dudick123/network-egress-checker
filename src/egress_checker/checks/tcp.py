"""TCP egress check implementation."""

import asyncio
import socket
import time

from egress_checker.checks.result import CheckResult
from egress_checker.config import TargetConfig
from egress_checker.diagnostics import (
    DiagnosticData,
    classify_error,
    get_suggested_action,
)


async def check_tcp(target: TargetConfig) -> CheckResult:
    """Perform a TCP connectivity check.

    Args:
        target: Target configuration with host and port.

    Returns:
        CheckResult with success/failure and diagnostic data.
    """
    host = target.effective_host
    port = target.effective_port
    start = time.monotonic()
    dns_duration_ms: float | None = None

    try:
        # Resolve DNS first to measure it separately
        dns_start = time.monotonic()
        infos = await asyncio.get_event_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
        dns_duration_ms = (time.monotonic() - dns_start) * 1000

        if not infos:
            raise OSError(f"DNS resolution returned no results for {host}")

        # Attempt TCP connection
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=target.timeout,
        )
        elapsed = time.monotonic() - start
        duration_ms = elapsed * 1000
        writer.close()
        await writer.wait_closed()

        return CheckResult(
            target=target.name,
            protocol=target.protocol.value,
            host=host,
            port=port,
            success=True,
            duration_ms=duration_ms,
            dns_duration_ms=dns_duration_ms,
        )

    except Exception as e:
        elapsed = time.monotonic() - start
        duration_ms = elapsed * 1000
        category = classify_error(e)
        diag = DiagnosticData(
            dns_result=(
                f"resolved in {dns_duration_ms:.1f}ms" if dns_duration_ms else "not resolved"
            ),
            tcp_state="failed",
            error_detail=str(e),
        )

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
        )
