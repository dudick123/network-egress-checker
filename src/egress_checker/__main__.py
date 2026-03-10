"""Application entrypoint for the egress checker."""

import asyncio
import os
import signal
import sys
from pathlib import Path

import structlog

from egress_checker.config import load_config
from egress_checker.health import HealthServer
from egress_checker.logging import configure_logging
from egress_checker.metrics import start_metrics_server
from egress_checker.scheduler import CheckScheduler

DEFAULT_CONFIG_PATH = "/etc/egress-checker/config.yaml"
DEFAULT_METRICS_PORT = 9090
DEFAULT_HEALTH_PORT = 8080
DEFAULT_NAMESPACE = "default"
DEFAULT_MAX_CONCURRENCY = 5


async def run() -> None:
    """Run the egress checker application."""
    configure_logging()
    logger = structlog.get_logger()

    config_path = Path(os.environ.get("EGRESS_CHECKER_CONFIG", DEFAULT_CONFIG_PATH))
    metrics_port = int(os.environ.get("EGRESS_CHECKER_METRICS_PORT", str(DEFAULT_METRICS_PORT)))
    health_port = int(os.environ.get("EGRESS_CHECKER_HEALTH_PORT", str(DEFAULT_HEALTH_PORT)))
    namespace = os.environ.get("EGRESS_CHECKER_NAMESPACE", DEFAULT_NAMESPACE)
    max_concurrency = int(
        os.environ.get("EGRESS_CHECKER_MAX_CONCURRENCY", str(DEFAULT_MAX_CONCURRENCY))
    )

    # Load configuration
    await logger.ainfo("loading_config", path=str(config_path))
    try:
        config = load_config(config_path)
    except (FileNotFoundError, ValueError) as e:
        await logger.aerror("config_error", error=str(e))
        sys.exit(1)

    await logger.ainfo(
        "config_loaded",
        target_count=len(config.targets),
        targets=[t.name for t in config.targets],
    )

    # Start metrics server
    start_metrics_server(metrics_port)
    await logger.ainfo("metrics_server_started", port=metrics_port)

    # Start health server
    health = HealthServer(port=health_port)
    await health.start()
    await logger.ainfo("health_server_started", port=health_port)

    # Start scheduler
    scheduler = CheckScheduler(
        config=config,
        namespace=namespace,
        max_concurrency=max_concurrency,
        on_first_cycle=health.set_ready,
    )

    # Handle graceful shutdown
    shutdown_event = asyncio.Event()

    def handle_signal(sig: int, frame: object) -> None:
        structlog.get_logger().warning("shutdown_signal", signal=sig)
        shutdown_event.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    await logger.ainfo("starting_checks")
    await scheduler.start()
    await logger.ainfo("first_cycle_complete", status="ready")

    # Wait for shutdown signal
    await shutdown_event.wait()

    await logger.ainfo("shutting_down")
    await scheduler.stop()
    await health.stop()
    await logger.ainfo("shutdown_complete")


def main() -> None:
    """Main entry point."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
