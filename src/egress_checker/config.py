"""Configuration models and YAML loader for egress checker."""

from enum import StrEnum
from pathlib import Path
from typing import Self
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, field_validator, model_validator


class Protocol(StrEnum):
    """Supported check protocols."""

    HTTP = "http"
    HTTPS = "https"
    TCP = "tcp"


class TargetConfig(BaseModel):
    """Configuration for a single egress check target."""

    name: str
    url: str | None = None
    host: str | None = None
    port: int | None = None
    protocol: Protocol = Protocol.HTTPS
    expected_status: int = 200
    interval: int = 60
    timeout: int = 5

    @field_validator("interval")
    @classmethod
    def interval_minimum(cls, v: int) -> int:
        """Ensure interval is at least 10 seconds."""
        if v < 10:
            raise ValueError("interval must be at least 10 seconds")
        return v

    @field_validator("timeout")
    @classmethod
    def timeout_positive(cls, v: int) -> int:
        """Ensure timeout is positive."""
        if v <= 0:
            raise ValueError("timeout must be positive")
        return v

    @model_validator(mode="after")
    def validate_target_fields(self) -> Self:
        """Validate that target has either url or host+port depending on protocol."""
        if self.url:
            parsed = urlparse(self.url)
            if parsed.scheme in ("http", "https"):
                self.protocol = Protocol(parsed.scheme)
        elif self.protocol == Protocol.TCP:
            if not self.host:
                raise ValueError("TCP target requires 'host' field")
            if not self.port:
                raise ValueError("TCP target requires 'port' field")
        else:
            if not self.url:
                raise ValueError("HTTP/HTTPS target requires 'url' field")
        return self

    @property
    def effective_host(self) -> str:
        """Return the hostname for this target."""
        if self.host:
            return self.host
        if self.url:
            parsed = urlparse(self.url)
            return parsed.hostname or ""
        return ""

    @property
    def effective_port(self) -> int:
        """Return the port for this target."""
        if self.port:
            return self.port
        if self.url:
            parsed = urlparse(self.url)
            if parsed.port:
                return parsed.port
            if parsed.scheme == "https":
                return 443
            if parsed.scheme == "http":
                return 80
        return 0


class CheckerConfig(BaseModel):
    """Top-level configuration for the egress checker."""

    targets: list[TargetConfig]

    @field_validator("targets")
    @classmethod
    def targets_not_empty(cls, v: list[TargetConfig]) -> list[TargetConfig]:
        """Ensure at least one target is configured."""
        if not v:
            raise ValueError("targets must not be empty")
        if len(v) > 50:
            raise ValueError("Maximum 50 targets per checker instance")
        return v

    @model_validator(mode="after")
    def no_duplicate_names(self) -> Self:
        """Ensure no duplicate target names."""
        names = [t.name for t in self.targets]
        if len(names) != len(set(names)):
            raise ValueError("Target names must be unique; found duplicate names")
        return self


def load_config(path: Path) -> CheckerConfig:
    """Load and validate checker configuration from a YAML file.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        Validated CheckerConfig instance.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If the YAML is invalid or config validation fails.
    """
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    raw = path.read_text()
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise ValueError(f"Failed to parse YAML configuration: {e}") from e

    if not isinstance(data, dict):
        raise ValueError("Configuration must be a YAML mapping")

    try:
        return CheckerConfig.model_validate(data)
    except Exception as e:
        raise ValueError(str(e)) from e
