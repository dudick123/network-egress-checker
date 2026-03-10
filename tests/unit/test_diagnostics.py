"""Tests for failure classification and diagnostics."""

import socket
import ssl

from egress_checker.diagnostics import (
    DiagnosticData,
    FailureCategory,
    classify_error,
    get_suggested_action,
)


class TestClassifyError:
    """Tests for error classification into failure categories."""

    def test_dns_gaierror(self) -> None:
        error = socket.gaierror("Name or service not known")
        assert classify_error(error) == FailureCategory.DNS_FAILURE

    def test_dns_nxdomain_message(self) -> None:
        error = OSError("NXDOMAIN for example.com")
        assert classify_error(error) == FailureCategory.DNS_FAILURE

    def test_dns_name_resolution_message(self) -> None:
        error = OSError("[Errno -2] Name resolution failed")
        assert classify_error(error) == FailureCategory.DNS_FAILURE

    def test_tls_ssl_error(self) -> None:
        error = ssl.SSLError("SSL: CERTIFICATE_VERIFY_FAILED")
        assert classify_error(error) == FailureCategory.TLS_ERROR

    def test_tls_certificate_message(self) -> None:
        error = OSError("certificate verify failed")
        assert classify_error(error) == FailureCategory.TLS_ERROR

    def test_connection_refused(self) -> None:
        error = ConnectionRefusedError("Connection refused")
        assert classify_error(error) == FailureCategory.CONNECTION_REFUSED

    def test_connection_refused_message(self) -> None:
        error = OSError("Connection refused by host")
        assert classify_error(error) == FailureCategory.CONNECTION_REFUSED

    def test_timeout(self) -> None:
        error = TimeoutError("Connection timed out")
        assert classify_error(error) == FailureCategory.CONNECTION_TIMEOUT

    def test_timeout_message(self) -> None:
        error = OSError("Operation timed out")
        assert classify_error(error) == FailureCategory.CONNECTION_TIMEOUT

    def test_connection_reset_as_firewall(self) -> None:
        error = ConnectionResetError("Connection reset by peer")
        assert classify_error(error) == FailureCategory.FIREWALL_BLOCKED

    def test_http_403_as_firewall(self) -> None:
        error = Exception("HTTP error")
        assert classify_error(error, http_status=403) == FailureCategory.FIREWALL_BLOCKED

    def test_http_470_as_firewall(self) -> None:
        error = Exception("HTTP error")
        assert classify_error(error, http_status=470) == FailureCategory.FIREWALL_BLOCKED

    def test_http_502_as_upstream(self) -> None:
        error = Exception("Bad gateway")
        assert classify_error(error, http_status=502) == FailureCategory.UPSTREAM_UNREACHABLE

    def test_http_503_as_upstream(self) -> None:
        error = Exception("Service unavailable")
        assert classify_error(error, http_status=503) == FailureCategory.UPSTREAM_UNREACHABLE

    def test_http_504_as_upstream(self) -> None:
        error = Exception("Gateway timeout")
        assert classify_error(error, http_status=504) == FailureCategory.UPSTREAM_UNREACHABLE

    def test_http_500_as_http_error(self) -> None:
        error = Exception("Internal server error")
        assert classify_error(error, http_status=500) == FailureCategory.HTTP_ERROR

    def test_unknown_error_defaults_to_timeout(self) -> None:
        error = Exception("Something unknown happened")
        assert classify_error(error) == FailureCategory.CONNECTION_TIMEOUT


class TestDiagnosticData:
    """Tests for diagnostic data serialization."""

    def test_to_dict_omits_none(self) -> None:
        diag = DiagnosticData(dns_result="1.2.3.4", tcp_state="established")
        result = diag.to_dict()
        assert "dns_result" in result
        assert "tcp_state" in result
        assert "tls_cipher" not in result

    def test_to_dict_omits_empty_dict(self) -> None:
        diag = DiagnosticData(dns_result="1.2.3.4")
        result = diag.to_dict()
        assert "http_headers" not in result

    def test_to_dict_includes_headers_when_populated(self) -> None:
        diag = DiagnosticData(http_headers={"Content-Type": "text/html"})
        result = diag.to_dict()
        assert "http_headers" in result


class TestSuggestedAction:
    """Tests for suggested action generation."""

    def test_firewall_action_includes_target(self) -> None:
        action = get_suggested_action(FailureCategory.FIREWALL_BLOCKED, "api.example.com", 443)
        assert "firewall" in action.lower()
        assert "api.example.com:443" in action

    def test_dns_action_includes_target(self) -> None:
        action = get_suggested_action(FailureCategory.DNS_FAILURE, "unknown.host", 443)
        assert "dns" in action.lower()
        assert "unknown.host:443" in action

    def test_all_categories_have_actions(self) -> None:
        for category in FailureCategory:
            action = get_suggested_action(category, "host", 80)
            assert len(action) > 0
