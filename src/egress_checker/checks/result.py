"""Check result data model."""

from dataclasses import dataclass
from typing import Any

from egress_checker.diagnostics import DiagnosticData, FailureCategory


@dataclass
class CheckResult:
    """Result of a single egress check."""

    target: str
    protocol: str
    host: str
    port: int
    success: bool
    duration_ms: float
    http_status: int | None = None
    error: str | None = None
    failure_category: FailureCategory | None = None
    diagnostics: DiagnosticData | None = None
    suggested_action: str | None = None
    dns_duration_ms: float | None = None
    tls_duration_ms: float | None = None

    def to_log_dict(self) -> dict[str, Any]:
        """Convert to a dictionary suitable for structured logging."""
        data: dict[str, Any] = {
            "target": self.target,
            "protocol": self.protocol,
            "port": self.port,
            "result": "success" if self.success else "failure",
            "duration_ms": round(self.duration_ms, 2),
        }
        if self.http_status is not None:
            data["http_status"] = self.http_status
        if self.dns_duration_ms is not None:
            data["dns_duration_ms"] = round(self.dns_duration_ms, 2)
        if self.tls_duration_ms is not None:
            data["tls_duration_ms"] = round(self.tls_duration_ms, 2)
        if not self.success:
            if self.error:
                data["error"] = self.error
            if self.failure_category:
                data["failure_category"] = self.failure_category.value
            if self.diagnostics:
                data["diagnostics"] = self.diagnostics.to_dict()
            if self.suggested_action:
                data["suggested_action"] = self.suggested_action
        return data
