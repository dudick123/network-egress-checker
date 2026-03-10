"""Tests for configuration parsing and validation."""

from pathlib import Path

import pytest
import yaml

from egress_checker.config import (
    CheckerConfig,
    Protocol,
    TargetConfig,
    load_config,
)


class TestTargetConfig:
    """Tests for individual target configuration."""

    def test_minimal_http_target(self) -> None:
        target = TargetConfig(name="test-api", url="https://example.com/health")
        assert target.name == "test-api"
        assert target.url == "https://example.com/health"
        assert target.protocol == Protocol.HTTPS
        assert target.interval == 60
        assert target.timeout == 5
        assert target.expected_status == 200

    def test_minimal_tcp_target(self) -> None:
        target = TargetConfig(
            name="database", host="db.internal", port=5432, protocol=Protocol.TCP
        )
        assert target.name == "database"
        assert target.host == "db.internal"
        assert target.port == 5432
        assert target.protocol == Protocol.TCP

    def test_http_url_infers_protocol(self) -> None:
        target = TargetConfig(name="api", url="http://example.com/health")
        assert target.protocol == Protocol.HTTP

    def test_https_url_infers_protocol(self) -> None:
        target = TargetConfig(name="api", url="https://example.com/health")
        assert target.protocol == Protocol.HTTPS

    def test_custom_interval_and_timeout(self) -> None:
        target = TargetConfig(name="api", url="https://example.com", interval=30, timeout=10)
        assert target.interval == 30
        assert target.timeout == 10

    def test_interval_below_minimum_rejected(self) -> None:
        with pytest.raises(ValueError, match="interval"):
            TargetConfig(name="api", url="https://example.com", interval=5)

    def test_interval_at_minimum_accepted(self) -> None:
        target = TargetConfig(name="api", url="https://example.com", interval=10)
        assert target.interval == 10

    def test_timeout_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="timeout"):
            TargetConfig(name="api", url="https://example.com", timeout=0)

    def test_tcp_requires_host_and_port(self) -> None:
        with pytest.raises(ValueError, match="host"):
            TargetConfig(name="db", protocol=Protocol.TCP, port=5432)

    def test_tcp_requires_port(self) -> None:
        with pytest.raises(ValueError, match="port"):
            TargetConfig(name="db", host="db.internal", protocol=Protocol.TCP)

    def test_url_target_extracts_host_and_port(self) -> None:
        target = TargetConfig(name="api", url="https://example.com:8443/health")
        assert target.effective_host == "example.com"
        assert target.effective_port == 8443

    def test_https_default_port(self) -> None:
        target = TargetConfig(name="api", url="https://example.com/health")
        assert target.effective_port == 443

    def test_http_default_port(self) -> None:
        target = TargetConfig(name="api", url="http://example.com/health")
        assert target.effective_port == 80

    def test_custom_expected_status(self) -> None:
        target = TargetConfig(name="api", url="https://example.com", expected_status=204)
        assert target.expected_status == 204


class TestCheckerConfig:
    """Tests for the top-level checker configuration."""

    def test_valid_config_with_targets(self) -> None:
        config = CheckerConfig(
            targets=[
                TargetConfig(name="api", url="https://example.com"),
                TargetConfig(name="db", host="db.internal", port=5432, protocol=Protocol.TCP),
            ]
        )
        assert len(config.targets) == 2

    def test_empty_targets_rejected(self) -> None:
        with pytest.raises(ValueError, match="targets"):
            CheckerConfig(targets=[])

    def test_max_50_targets(self) -> None:
        targets = [
            TargetConfig(name=f"target-{i}", url=f"https://example{i}.com") for i in range(51)
        ]
        with pytest.raises(ValueError, match="50"):
            CheckerConfig(targets=targets)

    def test_exactly_50_targets_accepted(self) -> None:
        targets = [
            TargetConfig(name=f"target-{i}", url=f"https://example{i}.com") for i in range(50)
        ]
        config = CheckerConfig(targets=targets)
        assert len(config.targets) == 50

    def test_duplicate_target_names_rejected(self) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            CheckerConfig(
                targets=[
                    TargetConfig(name="api", url="https://example1.com"),
                    TargetConfig(name="api", url="https://example2.com"),
                ]
            )


class TestLoadConfig:
    """Tests for loading configuration from YAML files."""

    def test_load_valid_yaml(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "targets": [
                        {"name": "api", "url": "https://example.com/health"},
                        {
                            "name": "db",
                            "host": "db.internal",
                            "port": 5432,
                            "protocol": "tcp",
                        },
                    ]
                }
            )
        )
        config = load_config(config_file)
        assert len(config.targets) == 2
        assert config.targets[0].name == "api"
        assert config.targets[1].protocol == Protocol.TCP

    def test_load_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.yaml")

    def test_load_invalid_yaml_raises(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text("{{invalid yaml")
        with pytest.raises(ValueError, match="parse"):
            load_config(config_file)

    def test_load_missing_required_field(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({"targets": [{"url": "https://example.com"}]}))
        with pytest.raises(ValueError, match="name"):
            load_config(config_file)

    def test_load_unsupported_protocol(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "targets": [
                        {"name": "ftp", "host": "ftp.example.com", "port": 21, "protocol": "ftp"}
                    ]
                }
            )
        )
        with pytest.raises(ValueError, match="protocol"):
            load_config(config_file)
