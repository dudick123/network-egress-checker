"""Tests for HTTP and TCP check implementations."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from egress_checker.checks.http import check_http
from egress_checker.checks.tcp import check_tcp
from egress_checker.config import Protocol, TargetConfig
from egress_checker.diagnostics import FailureCategory


class TestHttpCheck:
    """Tests for HTTP/HTTPS check implementation."""

    @pytest.fixture
    def https_target(self) -> TargetConfig:
        return TargetConfig(name="test-api", url="https://example.com/health")

    @pytest.fixture
    def http_target(self) -> TargetConfig:
        return TargetConfig(name="test-api", url="http://example.com/health")

    async def test_successful_https_check(self, https_target: TargetConfig) -> None:
        mock_response = httpx.Response(200, request=httpx.Request("GET", "https://example.com"))
        with patch("egress_checker.checks.http.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = await check_http(https_target)

        assert result.success is True
        assert result.http_status == 200
        assert result.duration_ms > 0
        assert result.target == "test-api"

    async def test_http_status_mismatch(self, https_target: TargetConfig) -> None:
        mock_response = httpx.Response(
            500,
            request=httpx.Request("GET", "https://example.com"),
            headers={"content-type": "text/plain"},
        )
        with patch("egress_checker.checks.http.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = await check_http(https_target)

        assert result.success is False
        assert result.http_status == 500
        assert result.failure_category == FailureCategory.HTTP_ERROR
        assert result.suggested_action is not None

    async def test_http_502_classified_as_upstream(self, https_target: TargetConfig) -> None:
        mock_response = httpx.Response(
            502,
            request=httpx.Request("GET", "https://example.com"),
        )
        with patch("egress_checker.checks.http.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = await check_http(https_target)

        assert result.failure_category == FailureCategory.UPSTREAM_UNREACHABLE

    async def test_connection_timeout(self, https_target: TargetConfig) -> None:
        with patch("egress_checker.checks.http.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectTimeout("Connection timed out")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = await check_http(https_target)

        assert result.success is False
        assert result.failure_category == FailureCategory.CONNECTION_TIMEOUT
        assert result.diagnostics is not None

    async def test_dns_error(self, https_target: TargetConfig) -> None:
        with patch("egress_checker.checks.http.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("Name or service not known")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = await check_http(https_target)

        assert result.success is False
        assert result.failure_category == FailureCategory.DNS_FAILURE

    async def test_tls_error(self, https_target: TargetConfig) -> None:
        with patch("egress_checker.checks.http.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = Exception("SSL: CERTIFICATE_VERIFY_FAILED")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = await check_http(https_target)

        assert result.success is False
        assert result.failure_category == FailureCategory.TLS_ERROR

    async def test_2xx_range_accepted_for_default(self, https_target: TargetConfig) -> None:
        mock_response = httpx.Response(204, request=httpx.Request("GET", "https://example.com"))
        with patch("egress_checker.checks.http.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = await check_http(https_target)

        assert result.success is True

    async def test_custom_expected_status_exact_match(self) -> None:
        target = TargetConfig(name="api", url="https://example.com", expected_status=204)
        mock_response = httpx.Response(200, request=httpx.Request("GET", "https://example.com"))
        with patch("egress_checker.checks.http.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = await check_http(target)

        assert result.success is False  # 200 != 204


class TestTcpCheck:
    """Tests for TCP check implementation."""

    @pytest.fixture
    def tcp_target(self) -> TargetConfig:
        return TargetConfig(name="database", host="db.internal", port=5432, protocol=Protocol.TCP)

    async def test_successful_tcp_connection(self, tcp_target: TargetConfig) -> None:
        mock_writer = AsyncMock()
        mock_writer.close = lambda: None
        mock_writer.wait_closed = AsyncMock()

        with (
            patch("egress_checker.checks.tcp.asyncio.get_event_loop") as mock_loop,
            patch("egress_checker.checks.tcp.asyncio.open_connection"),
            patch("egress_checker.checks.tcp.asyncio.wait_for") as mock_wait_for,
        ):
            mock_loop.return_value.getaddrinfo = AsyncMock(
                return_value=[(None, None, None, None, ("1.2.3.4", 5432))]
            )
            mock_wait_for.return_value = (AsyncMock(), mock_writer)

            result = await check_tcp(tcp_target)

        assert result.success is True
        assert result.duration_ms > 0
        assert result.target == "database"

    async def test_tcp_connection_refused(self, tcp_target: TargetConfig) -> None:
        with (
            patch("egress_checker.checks.tcp.asyncio.get_event_loop") as mock_loop,
            patch("egress_checker.checks.tcp.asyncio.wait_for") as mock_wait_for,
        ):
            mock_loop.return_value.getaddrinfo = AsyncMock(
                return_value=[(None, None, None, None, ("1.2.3.4", 5432))]
            )
            mock_wait_for.side_effect = ConnectionRefusedError("Connection refused")

            result = await check_tcp(tcp_target)

        assert result.success is False
        assert result.failure_category == FailureCategory.CONNECTION_REFUSED
        assert result.diagnostics is not None

    async def test_tcp_connection_timeout(self, tcp_target: TargetConfig) -> None:
        with (
            patch("egress_checker.checks.tcp.asyncio.get_event_loop") as mock_loop,
            patch("egress_checker.checks.tcp.asyncio.wait_for") as mock_wait_for,
        ):
            mock_loop.return_value.getaddrinfo = AsyncMock(
                return_value=[(None, None, None, None, ("1.2.3.4", 5432))]
            )
            mock_wait_for.side_effect = TimeoutError("Connection timed out")

            result = await check_tcp(tcp_target)

        assert result.success is False
        assert result.failure_category == FailureCategory.CONNECTION_TIMEOUT

    async def test_tcp_dns_failure(self, tcp_target: TargetConfig) -> None:
        import socket

        with patch("egress_checker.checks.tcp.asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.getaddrinfo = AsyncMock(
                side_effect=socket.gaierror("Name or service not known")
            )

            result = await check_tcp(tcp_target)

        assert result.success is False
        assert result.failure_category == FailureCategory.DNS_FAILURE
