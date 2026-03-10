"""Integration tests for the application lifecycle."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

from egress_checker.checks.result import CheckResult
from egress_checker.config import load_config
from egress_checker.health import HealthServer
from egress_checker.logging import configure_logging
from egress_checker.metrics import EGRESS_CHECK_SUCCESS
from egress_checker.scheduler import CheckScheduler


class TestAppLifecycle:
    """Integration tests for the full app lifecycle."""

    async def test_config_load_scheduler_start_health_ready(
        self, sample_config_file: Path
    ) -> None:
        """Verify: load config -> start scheduler -> health becomes ready."""
        configure_logging()
        config = load_config(sample_config_file)
        assert len(config.targets) == 2

        health = HealthServer(port=0)
        await health.start()
        assert health.ready is False

        http_result = CheckResult(
            target="test-api",
            protocol="https",
            host="example.com",
            port=443,
            success=True,
            duration_ms=10.0,
        )
        tcp_result = CheckResult(
            target="test-db",
            protocol="tcp",
            host="db.internal",
            port=5432,
            success=True,
            duration_ms=10.0,
        )

        with (
            patch(
                "egress_checker.scheduler.check_http",
                new_callable=AsyncMock,
                return_value=http_result,
            ),
            patch(
                "egress_checker.scheduler.check_tcp",
                new_callable=AsyncMock,
                return_value=tcp_result,
            ),
        ):
            scheduler = CheckScheduler(
                config=config,
                namespace="integration-test",
                on_first_cycle=health.set_ready,
            )
            await scheduler.start()
            assert health.ready is True

            # Verify metrics were updated
            val = EGRESS_CHECK_SUCCESS.labels(
                target="test-api", protocol="https", namespace="integration-test"
            )._value.get()
            assert val == 1.0

            await scheduler.stop()

        await health.stop()

    async def test_health_endpoints_during_lifecycle(self, sample_config_file: Path) -> None:
        """Verify health endpoints respond correctly before and after readiness."""
        health = HealthServer(port=0)
        await health.start()

        port = health._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]

        # Before ready
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"GET /readyz HTTP/1.1\r\nHost: localhost\r\n\r\n")
        await writer.drain()
        data = await asyncio.wait_for(reader.read(4096), timeout=5.0)
        writer.close()
        await writer.wait_closed()
        assert b"503" in data

        # After ready
        health.set_ready()
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"GET /readyz HTTP/1.1\r\nHost: localhost\r\n\r\n")
        await writer.drain()
        data = await asyncio.wait_for(reader.read(4096), timeout=5.0)
        writer.close()
        await writer.wait_closed()
        assert b"200" in data

        await health.stop()
