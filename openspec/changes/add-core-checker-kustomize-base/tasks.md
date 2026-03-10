## 1. Project scaffolding
- [x] 1.1 Initialize Python project structure (`src/egress_checker/`) with `pyproject.toml` and dependencies (`httpx`, `pydantic`, `prometheus_client`, `pyyaml`, `structlog`) using `uv init` and `uv add`
- [x] 1.2 Configure Ruff (`.ruff.toml` or `pyproject.toml` section) and mypy (`mypy --strict`) settings
- [x] 1.3 Create `.devcontainer/devcontainer.json` with Python 3.14, uv, Ruff, mypy, pytest, kustomize, kubectl
- [x] 1.4 Create multi-stage Dockerfile (`python:3.14-slim` base, `uv sync --frozen --no-dev`, non-root user)
- [x] 1.5 Add `.dockerignore` and `Makefile` (lint, format, typecheck, test, check, build targets)
- [x] 1.6 Add `.vscode/settings.json` and `.vscode/extensions.json` for recommended IDE configuration

## 2. Configuration
- [x] 2.1 Define pydantic v2 models for target configuration (name, url/host, port, protocol, expected_status, interval, timeout)
- [x] 2.2 Implement ConfigMap YAML loader with startup validation and clear error messages on invalid config
- [x] 2.3 Add unit tests for config parsing (valid configs, missing fields, unsupported protocols, boundary values)

## 3. Check engine
- [x] 3.1 Implement HTTP/HTTPS checker using `httpx` async client (GET/HEAD, status validation, TLS cert validation, timeout handling)
- [x] 3.2 Implement TCP checker using `asyncio.open_connection` (handshake validation, timeout handling)
- [x] 3.3 Implement check scheduler with configurable intervals and bounded concurrency (default: 5)
- [x] 3.4 Add unit tests for check engine (mock HTTP responses, TCP connections, timeout scenarios)

## 4. Connection diagnostics
- [x] 4.1 Implement failure classifier (firewall_blocked, dns_failure, connection_timeout, connection_refused, tls_error, http_error, upstream_unreachable)
- [x] 4.2 Capture verbose connection trace data (DNS result, TCP state, TLS details, HTTP headers) into diagnostics object
- [x] 4.3 Generate suggested_action text for each failure category
- [x] 4.4 Add unit tests for failure classification (simulate each category)

## 5. Metrics exposure
- [x] 5.1 Define Prometheus metrics: `egress_check_success` (gauge), `egress_check_duration_seconds` (histogram), `egress_check_total` (counter), `egress_check_failure_category` (gauge), `egress_check_dns_duration_seconds` (histogram), `egress_check_tls_duration_seconds` (histogram)
- [x] 5.2 Instrument check results to update metrics after each check cycle
- [x] 5.3 Start `prometheus_client` HTTP server on port 9090
- [x] 5.4 Add tests verifying metric labels and values after check execution

## 6. Structured logging
- [x] 6.1 Configure structlog with JSON rendering to stdout (timestamp, target, protocol, port, result, duration_ms, dns_duration_ms, tls_duration_ms, http_status, error, failure_category)
- [x] 6.2 Add diagnostics object and suggested_action to failed check log entries via structlog context binding
- [x] 6.3 Ensure no sensitive data (auth tokens, secrets) appears in log output
- [x] 6.4 Add tests for log output format and content

## 7. Health monitoring
- [x] 7.1 Implement `/healthz` endpoint (returns 200 when event loop is running)
- [x] 7.2 Implement `/readyz` endpoint (returns 200 after config loaded and first check cycle complete)
- [x] 7.3 Expose `egress_checker_healthy` gauge metric
- [x] 7.4 Add tests for health endpoints

## 8. Application entrypoint
- [x] 8.1 Wire together config loading, check scheduler, metrics server, health server, and logging in `__main__.py`
- [x] 8.2 Handle graceful shutdown (SIGTERM/SIGINT)
- [x] 8.3 Add integration test: start app with sample config, verify metrics endpoint and log output

## 9. Kustomize manifests
- [x] 9.1 Create `kustomize/base/kustomization.yaml` referencing Deployment, Service, ConfigMap, PodMonitor
- [x] 9.2 Create base Deployment manifest (container image, ports, liveness/readiness probes, resource requests/limits, ConfigMap volume mount)
- [x] 9.3 Create base Service manifest (expose metrics port 9090)
- [x] 9.4 Create base ConfigMap manifest (default empty targets)
- [x] 9.5 Create base PodMonitor manifest (scrape metrics port)
- [x] 9.6 Create example tenant overlay (`kustomize/overlays/example/`) with namespace transformer and ConfigMap patch
- [x] 9.7 Validate manifests with `kustomize build`
