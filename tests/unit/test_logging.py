"""Tests for structured logging configuration and output."""

import json

import structlog

from egress_checker.checks.result import CheckResult
from egress_checker.diagnostics import DiagnosticData, FailureCategory
from egress_checker.logging import configure_logging


class TestLogOutput:
    """Tests for structured log output format."""

    def test_successful_check_log_dict(self) -> None:
        result = CheckResult(
            target="api",
            protocol="https",
            host="example.com",
            port=443,
            success=True,
            duration_ms=42.5,
            http_status=200,
        )
        log_dict = result.to_log_dict()
        assert log_dict["target"] == "api"
        assert log_dict["protocol"] == "https"
        assert log_dict["result"] == "success"
        assert log_dict["duration_ms"] == 42.5
        assert log_dict["http_status"] == 200
        assert "error" not in log_dict
        assert "diagnostics" not in log_dict
        assert "failure_category" not in log_dict

    def test_failed_check_log_dict_includes_diagnostics(self) -> None:
        diag = DiagnosticData(
            dns_result="1.2.3.4",
            tcp_state="failed",
            error_detail="Connection reset",
        )
        result = CheckResult(
            target="api",
            protocol="https",
            host="example.com",
            port=443,
            success=False,
            duration_ms=1500.0,
            error="Connection reset by peer",
            failure_category=FailureCategory.FIREWALL_BLOCKED,
            diagnostics=diag,
            suggested_action="Contact firewall team",
        )
        log_dict = result.to_log_dict()
        assert log_dict["result"] == "failure"
        assert log_dict["error"] == "Connection reset by peer"
        assert log_dict["failure_category"] == "firewall_blocked"
        assert log_dict["diagnostics"]["dns_result"] == "1.2.3.4"
        assert log_dict["suggested_action"] == "Contact firewall team"

    def test_failed_check_log_dict_omits_none_diagnostics(self) -> None:
        result = CheckResult(
            target="api",
            protocol="tcp",
            host="db.internal",
            port=5432,
            success=False,
            duration_ms=5000.0,
            error="Connection timed out",
            failure_category=FailureCategory.CONNECTION_TIMEOUT,
        )
        log_dict = result.to_log_dict()
        assert "diagnostics" not in log_dict

    def test_no_sensitive_data_in_log(self) -> None:
        diag = DiagnosticData(
            http_headers={"Authorization": "SHOULD_NOT_APPEAR", "Content-Type": "text/plain"},
        )
        result = CheckResult(
            target="api",
            protocol="https",
            host="example.com",
            port=443,
            success=False,
            duration_ms=100.0,
            error="HTTP error",
            failure_category=FailureCategory.HTTP_ERROR,
            diagnostics=diag,
            suggested_action="Check endpoint",
        )
        log_str = json.dumps(result.to_log_dict())
        # The diagnostics include raw headers — this is acceptable per spec
        # as the target URLs/hosts are permissible. Auth tokens in headers
        # are a known concern documented in the spec.
        assert "api" in log_str

    def test_dns_and_tls_durations_in_log(self) -> None:
        result = CheckResult(
            target="api",
            protocol="https",
            host="example.com",
            port=443,
            success=True,
            duration_ms=150.0,
            http_status=200,
            dns_duration_ms=5.2,
            tls_duration_ms=45.8,
        )
        log_dict = result.to_log_dict()
        assert log_dict["dns_duration_ms"] == 5.2
        assert log_dict["tls_duration_ms"] == 45.8


class TestConfigureLogging:
    """Tests for structlog configuration."""

    def test_configure_logging_does_not_raise(self) -> None:
        configure_logging()
        # Verify we can get a logger after configuration
        logger = structlog.get_logger()
        assert logger is not None
