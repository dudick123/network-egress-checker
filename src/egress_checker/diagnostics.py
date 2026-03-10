"""Failure classification and diagnostic data for egress checks."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class FailureCategory(StrEnum):
    """Diagnostic categories for failed egress checks."""

    FIREWALL_BLOCKED = "firewall_blocked"
    DNS_FAILURE = "dns_failure"
    CONNECTION_TIMEOUT = "connection_timeout"
    CONNECTION_REFUSED = "connection_refused"
    TLS_ERROR = "tls_error"
    HTTP_ERROR = "http_error"
    UPSTREAM_UNREACHABLE = "upstream_unreachable"


@dataclass
class DiagnosticData:
    """Verbose connection trace data for a failed check."""

    dns_result: str | None = None
    tcp_state: str | None = None
    tls_cipher: str | None = None
    tls_cert_subject: str | None = None
    tls_alert_code: str | None = None
    http_status: int | None = None
    http_headers: dict[str, str] = field(default_factory=dict)
    error_detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to a dictionary, omitting None values."""
        return {k: v for k, v in self.__dict__.items() if v is not None and v != {}}


SUGGESTED_ACTIONS: dict[FailureCategory, str] = {
    FailureCategory.FIREWALL_BLOCKED: (
        "Connection was blocked, likely by Azure Firewall. "
        "Contact the firewall team with the target FQDN and port."
    ),
    FailureCategory.DNS_FAILURE: (
        "DNS resolution failed. Verify the hostname is correct and check CoreDNS health. "
        "For internal services, verify the service exists in the expected namespace."
    ),
    FailureCategory.CONNECTION_TIMEOUT: (
        "Connection timed out (no response to SYN). This may indicate a firewall drop rule "
        "(no RST sent) or a routing issue. Check network policies and firewall rules."
    ),
    FailureCategory.CONNECTION_REFUSED: (
        "Connection was refused (RST received from destination). "
        "The target host is reachable but the port is not listening. "
        "Verify the service is running on the expected port."
    ),
    FailureCategory.TLS_ERROR: (
        "TLS handshake failed. Check certificate validity, protocol compatibility, "
        "and SNI configuration. For internal services, ensure the CA is trusted."
    ),
    FailureCategory.HTTP_ERROR: (
        "HTTP response status did not match expected code. "
        "The target is reachable but returned an unexpected response. "
        "Check the endpoint health and expected status configuration."
    ),
    FailureCategory.UPSTREAM_UNREACHABLE: (
        "Received a 502/503/504 response indicating the upstream service is down. "
        "The target proxy or load balancer is reachable but cannot reach its backend."
    ),
}


def get_suggested_action(category: FailureCategory, target_host: str, port: int) -> str:
    """Return a human-readable suggested action for a failure category.

    Args:
        category: The failure classification.
        target_host: The FQDN or IP of the target.
        port: The target port.

    Returns:
        A human-readable suggestion string.
    """
    base = SUGGESTED_ACTIONS[category]
    return f"{base} (target: {target_host}:{port})"


def classify_error(
    error: Exception,
    http_status: int | None = None,
) -> FailureCategory:
    """Classify an exception into a failure category.

    Args:
        error: The exception from the check.
        http_status: HTTP status code if available.

    Returns:
        The classified failure category.
    """
    error_str = str(error).lower()
    error_type = type(error).__name__

    # DNS failures
    if _is_dns_error(error_str, error_type):
        return FailureCategory.DNS_FAILURE

    # TLS errors
    if _is_tls_error(error_str, error_type):
        return FailureCategory.TLS_ERROR

    # HTTP status-based classification
    if http_status is not None:
        if http_status in (502, 503, 504):
            return FailureCategory.UPSTREAM_UNREACHABLE
        if http_status in (403, 470):
            return FailureCategory.FIREWALL_BLOCKED
        return FailureCategory.HTTP_ERROR

    # Connection refused
    if _is_connection_refused(error_str, error_type):
        return FailureCategory.CONNECTION_REFUSED

    # Timeout
    if _is_timeout(error_str, error_type):
        return FailureCategory.CONNECTION_TIMEOUT

    # Connection reset (potential firewall)
    if _is_connection_reset(error_str):
        return FailureCategory.FIREWALL_BLOCKED

    # Default to connection timeout for unclassified errors
    return FailureCategory.CONNECTION_TIMEOUT


def _is_dns_error(error_str: str, error_type: str) -> bool:
    dns_indicators = [
        "getaddrinfo",
        "name or service not known",
        "nodename nor servname",
        "nxdomain",
        "dns",
        "name resolution",
    ]
    return any(indicator in error_str for indicator in dns_indicators) or (
        error_type in ("gaierror", "socket.gaierror")
    )


def _is_tls_error(error_str: str, error_type: str) -> bool:
    tls_indicators = ["ssl", "tls", "certificate", "handshake"]
    return any(indicator in error_str for indicator in tls_indicators) or (
        error_type in ("SSLError", "SSLCertVerificationError")
    )


def _is_connection_refused(error_str: str, error_type: str) -> bool:
    return (
        "connection refused" in error_str
        or "refused" in error_str
        or (error_type == "ConnectionRefusedError")
    )


def _is_timeout(error_str: str, error_type: str) -> bool:
    timeout_indicators = ["timed out", "timeout", "deadline"]
    return any(indicator in error_str for indicator in timeout_indicators) or (
        error_type in ("TimeoutError", "asyncio.TimeoutError", "ConnectTimeout")
    )


def _is_connection_reset(error_str: str) -> bool:
    return "connection reset" in error_str or "rst" in error_str
