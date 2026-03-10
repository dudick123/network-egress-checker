"""Health and readiness HTTP server."""

import asyncio
from http import HTTPStatus

from egress_checker.metrics import EGRESS_CHECKER_HEALTHY


class HealthServer:
    """Async HTTP server for /healthz and /readyz endpoints."""

    def __init__(self, port: int = 8080) -> None:
        self._port = port
        self._ready = False
        self._server: asyncio.Server | None = None

    @property
    def ready(self) -> bool:
        """Whether the checker is ready (config loaded, first check done)."""
        return self._ready

    def set_ready(self) -> None:
        """Mark the checker as ready."""
        self._ready = True
        EGRESS_CHECKER_HEALTHY.set(1)

    def set_unhealthy(self) -> None:
        """Mark the checker as unhealthy."""
        EGRESS_CHECKER_HEALTHY.set(0)

    async def start(self) -> None:
        """Start the health HTTP server."""
        self._server = await asyncio.start_server(
            self._handle_connection,
            "0.0.0.0",  # noqa: S104
            self._port,
        )
        EGRESS_CHECKER_HEALTHY.set(1)

    async def stop(self) -> None:
        """Stop the health HTTP server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle an incoming HTTP connection."""
        try:
            data = await asyncio.wait_for(reader.read(1024), timeout=5.0)
            request_line = data.decode().split("\r\n")[0] if data else ""
            path = request_line.split(" ")[1] if len(request_line.split(" ")) > 1 else ""

            if path == "/healthz":
                await self._send_response(writer, HTTPStatus.OK, "ok")
            elif path == "/readyz":
                if self._ready:
                    await self._send_response(writer, HTTPStatus.OK, "ready")
                else:
                    await self._send_response(writer, HTTPStatus.SERVICE_UNAVAILABLE, "not ready")
            else:
                await self._send_response(writer, HTTPStatus.NOT_FOUND, "not found")
        except Exception:  # noqa: S110
            pass  # Connection errors are expected for health probes
        finally:
            writer.close()
            await writer.wait_closed()

    async def _send_response(
        self,
        writer: asyncio.StreamWriter,
        status: HTTPStatus,
        body: str,
    ) -> None:
        """Send an HTTP response."""
        response = (
            f"HTTP/1.1 {status.value} {status.phrase}\r\n"
            f"Content-Type: text/plain\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"\r\n"
            f"{body}"
        )
        writer.write(response.encode())
        await writer.drain()
