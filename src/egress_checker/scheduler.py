"""Async check scheduler with bounded concurrency."""

import asyncio
from collections.abc import Callable

import structlog

from egress_checker.checks.http import check_http
from egress_checker.checks.result import CheckResult
from egress_checker.checks.tcp import check_tcp
from egress_checker.config import CheckerConfig, Protocol, TargetConfig
from egress_checker.metrics import record_check_result

logger = structlog.get_logger()


class CheckScheduler:
    """Schedules and executes egress checks with bounded concurrency."""

    def __init__(
        self,
        config: CheckerConfig,
        namespace: str,
        max_concurrency: int = 5,
        on_first_cycle: Callable[[], None] | None = None,
    ) -> None:
        self._config = config
        self._namespace = namespace
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._on_first_cycle = on_first_cycle
        self._first_cycle_done = False
        self._tasks: list[asyncio.Task[None]] = []
        self._running = True

    async def start(self) -> None:
        """Start all target check loops."""
        for target in self._config.targets:
            task = asyncio.create_task(self._check_loop(target))
            self._tasks.append(task)

        # Wait for first cycle to complete for all targets
        await self._run_first_cycle()

    async def _run_first_cycle(self) -> None:
        """Run the first check for all targets and signal readiness."""
        await asyncio.gather(
            *[self._run_check(target) for target in self._config.targets],
            return_exceptions=True,
        )
        self._first_cycle_done = True
        if self._on_first_cycle:
            self._on_first_cycle()

    async def stop(self) -> None:
        """Stop all check loops."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _check_loop(self, target: TargetConfig) -> None:
        """Run checks for a single target on its configured interval."""
        # Skip first interval since _run_first_cycle already ran the first check
        try:
            while self._running:
                await asyncio.sleep(target.interval)
                if not self._running:
                    break
                await self._run_check(target)
        except asyncio.CancelledError:
            return

    async def _run_check(self, target: TargetConfig) -> CheckResult | None:
        """Run a single check with concurrency limiting."""
        async with self._semaphore:
            try:
                result = await self._execute_check(target)
                self._record_result(result)
                return result
            except Exception as e:
                await logger.aerror(
                    "check_execution_error",
                    target=target.name,
                    error=str(e),
                )
                return None

    async def _execute_check(self, target: TargetConfig) -> CheckResult:
        """Execute the appropriate check type for a target."""
        if target.protocol in (Protocol.HTTP, Protocol.HTTPS):
            return await check_http(target)
        return await check_tcp(target)

    def _record_result(self, result: CheckResult) -> None:
        """Record check result in metrics and logs."""
        log_data = result.to_log_dict()
        if result.success:
            structlog.get_logger().info("egress_check", **log_data)
        else:
            structlog.get_logger().warning("egress_check", **log_data)

        record_check_result(
            target=result.target,
            protocol=result.protocol,
            namespace=self._namespace,
            success=result.success,
            duration_seconds=result.duration_ms / 1000,
            failure_category=(result.failure_category.value if result.failure_category else None),
            dns_duration_seconds=(
                result.dns_duration_ms / 1000 if result.dns_duration_ms else None
            ),
            tls_duration_seconds=(
                result.tls_duration_ms / 1000 if result.tls_duration_ms else None
            ),
        )
