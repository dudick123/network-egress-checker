"""Shared test fixtures."""

from pathlib import Path

import pytest
import yaml

from egress_checker.config import CheckerConfig, Protocol, TargetConfig


@pytest.fixture
def sample_config() -> CheckerConfig:
    """A sample checker config with HTTP and TCP targets."""
    return CheckerConfig(
        targets=[
            TargetConfig(name="test-api", url="https://example.com/health", interval=10),
            TargetConfig(
                name="test-db",
                host="db.internal",
                port=5432,
                protocol=Protocol.TCP,
                interval=10,
            ),
        ]
    )


@pytest.fixture
def sample_config_file(tmp_path: Path) -> Path:
    """Write a sample config YAML file and return its path."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.dump(
            {
                "targets": [
                    {"name": "test-api", "url": "https://example.com/health", "interval": 10},
                    {
                        "name": "test-db",
                        "host": "db.internal",
                        "port": 5432,
                        "protocol": "tcp",
                        "interval": 10,
                    },
                ]
            }
        )
    )
    return config_path
