"""Tests for health and readiness endpoints."""

import asyncio

import pytest

from egress_checker.health import HealthServer
from egress_checker.metrics import EGRESS_CHECKER_HEALTHY


class TestHealthServer:
    """Tests for the health HTTP server."""

    @pytest.fixture
    async def server(self) -> HealthServer:
        """Create and start a health server on a random port."""
        health = HealthServer(port=0)
        await health.start()
        yield health
        await health.stop()

    def _get_port(self, server: HealthServer) -> int:
        """Extract the actual port from the server."""
        assert server._server is not None
        sockets = server._server.sockets
        assert sockets
        return sockets[0].getsockname()[1]

    async def _http_get(self, port: int, path: str) -> tuple[int, str]:
        """Make a simple HTTP GET request and return (status, body)."""
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        request = f"GET {path} HTTP/1.1\r\nHost: localhost\r\n\r\n"
        writer.write(request.encode())
        await writer.drain()
        response = await asyncio.wait_for(reader.read(4096), timeout=5.0)
        writer.close()
        await writer.wait_closed()
        decoded = response.decode()
        status_line = decoded.split("\r\n")[0]
        status_code = int(status_line.split(" ")[1])
        body = decoded.split("\r\n\r\n")[1] if "\r\n\r\n" in decoded else ""
        return status_code, body

    async def test_healthz_returns_200(self, server: HealthServer) -> None:
        port = self._get_port(server)
        status, body = await self._http_get(port, "/healthz")
        assert status == 200
        assert body == "ok"

    async def test_readyz_returns_503_before_ready(self, server: HealthServer) -> None:
        port = self._get_port(server)
        status, body = await self._http_get(port, "/readyz")
        assert status == 503
        assert body == "not ready"

    async def test_readyz_returns_200_after_ready(self, server: HealthServer) -> None:
        server.set_ready()
        port = self._get_port(server)
        status, body = await self._http_get(port, "/readyz")
        assert status == 200
        assert body == "ready"

    async def test_unknown_path_returns_404(self, server: HealthServer) -> None:
        port = self._get_port(server)
        status, _ = await self._http_get(port, "/unknown")
        assert status == 404

    async def test_set_unhealthy_updates_metric(self, server: HealthServer) -> None:
        server.set_unhealthy()
        assert EGRESS_CHECKER_HEALTHY._value.get() == 0

    async def test_set_ready_updates_metric(self, server: HealthServer) -> None:
        server.set_ready()
        assert EGRESS_CHECKER_HEALTHY._value.get() == 1
