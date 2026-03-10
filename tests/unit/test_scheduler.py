"""Tests for the check scheduler."""

from unittest.mock import AsyncMock, patch

import pytest

from egress_checker.checks.result import CheckResult
from egress_checker.config import CheckerConfig, Protocol, TargetConfig
from egress_checker.scheduler import CheckScheduler


class TestCheckScheduler:
    """Tests for scheduler functionality."""

    @pytest.fixture
    def config(self) -> CheckerConfig:
        return CheckerConfig(
            targets=[
                TargetConfig(name="api", url="https://example.com/health", interval=10),
                TargetConfig(
                    name="db",
                    host="db.internal",
                    port=5432,
                    protocol=Protocol.TCP,
                    interval=10,
                ),
            ]
        )

    def _make_success_result(self, target_name: str, protocol: str) -> CheckResult:
        return CheckResult(
            target=target_name,
            protocol=protocol,
            host="example.com",
            port=443,
            success=True,
            duration_ms=42.0,
        )

    async def test_first_cycle_calls_on_first_cycle(self, config: CheckerConfig) -> None:
        called = False

        def sync_callback() -> None:
            nonlocal called
            called = True

        with (
            patch(
                "egress_checker.scheduler.check_http",
                new_callable=AsyncMock,
                return_value=self._make_success_result("api", "https"),
            ),
            patch(
                "egress_checker.scheduler.check_tcp",
                new_callable=AsyncMock,
                return_value=self._make_success_result("db", "tcp"),
            ),
        ):
            scheduler = CheckScheduler(
                config=config,
                namespace="test-ns",
                on_first_cycle=sync_callback,
            )
            await scheduler._run_first_cycle()
            await scheduler.stop()

        assert called is True

    async def test_bounded_concurrency(self, config: CheckerConfig) -> None:
        scheduler = CheckScheduler(config=config, namespace="test-ns", max_concurrency=1)
        assert scheduler._semaphore._value == 1

    async def test_executes_http_check_for_http_target(self) -> None:
        config = CheckerConfig(
            targets=[TargetConfig(name="api", url="https://example.com/health", interval=10)]
        )
        expected_result = self._make_success_result("api", "https")

        with patch(
            "egress_checker.scheduler.check_http",
            new_callable=AsyncMock,
            return_value=expected_result,
        ) as mock_http:
            scheduler = CheckScheduler(config=config, namespace="test-ns")
            result = await scheduler._execute_check(config.targets[0])

        assert result.target == "api"
        mock_http.assert_called_once()

    async def test_executes_tcp_check_for_tcp_target(self) -> None:
        config = CheckerConfig(
            targets=[
                TargetConfig(
                    name="db",
                    host="db.internal",
                    port=5432,
                    protocol=Protocol.TCP,
                    interval=10,
                )
            ]
        )
        expected_result = self._make_success_result("db", "tcp")

        with patch(
            "egress_checker.scheduler.check_tcp",
            new_callable=AsyncMock,
            return_value=expected_result,
        ) as mock_tcp:
            scheduler = CheckScheduler(config=config, namespace="test-ns")
            result = await scheduler._execute_check(config.targets[0])

        assert result.target == "db"
        mock_tcp.assert_called_once()
