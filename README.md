# Network Egress Checker

A lightweight, self-service egress connectivity checker for tenants on a shared AKS cluster. It generates synthetic network traffic to user-defined endpoints and exposes results as Prometheus metrics and structured JSON logs.

**Ownership model**: The platform engineering team owns the checker application and container image. Tenant teams only provide a ConfigMap declaring which endpoints to check.

## Table of Contents

- [How It Works](#how-it-works)
- [Architecture](#architecture)
- [Target Configuration](#target-configuration)
- [Failure Diagnostics](#failure-diagnostics)
- [Prometheus Metrics](#prometheus-metrics)
- [Structured Logging](#structured-logging)
- [Local Development](#local-development)
- [Python Development Patterns](#python-development-patterns)
- [Testing](#testing)
- [Kubernetes Deployment](#kubernetes-deployment)
- [Environment Variables](#environment-variables)

## How It Works

1. Tenant authors a YAML configuration listing egress targets (URLs, hosts, ports).
2. Configuration is deployed as a Kubernetes ConfigMap via Kustomize + ArgoCD.
3. The checker container reads the ConfigMap at startup, validates it, and begins checking every target on its configured interval.
4. Each check result is recorded as a Prometheus metric and emitted as a structured JSON log line to stdout.
5. Failed checks are classified into diagnostic categories (e.g., `firewall_blocked`, `dns_failure`) with suggested remediation actions.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Tenant Namespace                                       │
│                                                         │
│  ┌──────────────┐    ┌─────────────────────────────┐    │
│  │  ConfigMap    │───>│  egress-checker Pod          │    │
│  │  (targets)   │    │                              │    │
│  └──────────────┘    │  ┌────────────────────────┐  │    │
│                      │  │  Check Scheduler       │  │    │
│                      │  │  (asyncio + semaphore) │  │    │
│                      │  └──────┬─────────────────┘  │    │
│                      │         │                    │    │
│                      │   ┌─────┴─────┐              │    │
│                      │   │           │              │    │
│                      │  HTTP/S     TCP              │    │
│                      │  checker   checker           │    │
│                      │   │           │              │    │
│                      │   └─────┬─────┘              │    │
│                      │         │                    │    │
│                      │   ┌─────▼──────────────┐     │    │
│                      │   │ Diagnostics        │     │    │
│                      │   │ (classify failure) │     │    │
│                      │   └─────┬──────────────┘     │    │
│                      │         │                    │    │
│                      │   ┌─────▼─────┐ ┌────────┐  │    │
│                      │   │ structlog │ │ Prom   │  │    │
│                      │   │ (stdout)  │ │ metrics│  │    │
│                      │   └───────────┘ └───┬────┘  │    │
│                      │       :8080   :9090 │       │    │
│                      │     (health) (metrics)      │    │
│                      └─────────────────────────────┘    │
│                                        │                │
└────────────────────────────────────────┼────────────────┘
                                         │
                              ┌──────────▼──────────┐
                              │  Azure Managed      │
                              │  Prometheus          │
                              │  (PodMonitor scrape) │
                              └─────────────────────┘
```

### Module Structure

```
src/egress_checker/
├── __main__.py        # Entrypoint — wires config, scheduler, metrics, health
├── config.py          # Pydantic v2 models, YAML loader, validation
├── checks/
│   ├── http.py        # Async HTTP/HTTPS checker (httpx)
│   ├── tcp.py         # Async TCP checker (asyncio.open_connection)
│   └── result.py      # CheckResult dataclass
├── diagnostics.py     # Failure classification, suggested actions
├── metrics.py         # Prometheus metric definitions + recording
├── logging.py         # structlog JSON configuration
├── health.py          # /healthz and /readyz async HTTP server
└── scheduler.py       # Bounded-concurrency check scheduler
```

**Key design decisions:**

- **Single async process** — one `asyncio` event loop runs the check scheduler, metrics server, and health server concurrently.
- **Separation of concerns** — checks, diagnostics, metrics, and logging are fully decoupled modules.
- **Dependency injection via arguments** — no global mutable state; config and collectors are passed explicitly.
- **Pydantic for all external data** — ConfigMap input is validated through pydantic models with clear error messages at startup.

## Target Configuration

Targets are defined in a YAML file mounted from a Kubernetes ConfigMap:

```yaml
targets:
  # HTTP/HTTPS — just provide a URL
  - name: partner-api
    url: https://api.example.com/health

  # Internal cluster service
  - name: internal-auth
    url: https://auth-service.platform.svc.cluster.local/healthz

  # TCP connectivity (databases, message brokers, etc.)
  - name: database
    host: sql-server.private.network
    port: 1433
    protocol: tcp

  # Full options
  - name: custom-api
    url: https://api.example.com/v2/status
    expected_status: 204
    interval: 30       # seconds (default: 60, minimum: 10)
    timeout: 10        # seconds (default: 5)
```

### Target Fields

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `name` | Yes | — | Unique identifier for this target (used in metrics and logs) |
| `url` | Yes (HTTP/S) | — | Full URL for HTTP/HTTPS checks |
| `host` | Yes (TCP) | — | Hostname or IP for TCP checks |
| `port` | Yes (TCP) | — | Port number for TCP checks |
| `protocol` | No | Inferred from URL | `http`, `https`, or `tcp` |
| `expected_status` | No | `200` (any 2xx) | Expected HTTP status code |
| `interval` | No | `60` | Check interval in seconds (minimum: 10) |
| `timeout` | No | `5` | Connection timeout in seconds |

### Constraints

- Maximum **50 targets** per checker instance.
- Minimum check interval: **10 seconds**.
- Target names must be **unique** within a configuration.
- Invalid configuration logs a clear error and exits non-zero at startup.

## Failure Diagnostics

Each failed check is classified into a diagnostic category using connection-level heuristics:

| Category | Trigger | Suggested Action |
|----------|---------|------------------|
| `firewall_blocked` | TCP RST immediately after SYN, TLS terminated by intermediary, HTTP 403/470 from proxy | Contact the firewall team with FQDN and port |
| `dns_failure` | NXDOMAIN, SERVFAIL, resolution timeout | Verify hostname; check CoreDNS health |
| `connection_timeout` | No SYN-ACK within timeout | Check network policies and firewall drop rules |
| `connection_refused` | TCP RST from destination | Verify service is running on expected port |
| `tls_error` | Certificate validation failure, protocol mismatch | Check cert validity and CA trust |
| `http_error` | Status code does not match expected | Check endpoint health |
| `upstream_unreachable` | HTTP 502, 503, or 504 | Backend behind proxy/LB is down |

> **Note:** Classifications are best-effort heuristics. A TCP RST could originate from the destination rather than the firewall. Confirm with firewall team logs for definitive root cause analysis.

Failed checks include a `diagnostics` object in the log with verbose connection trace data (DNS result, TCP state, TLS details, HTTP headers) and a `suggested_action` field with human-readable remediation guidance.

## Prometheus Metrics

The checker exposes a `/metrics` endpoint on port **9090** compatible with Azure Managed Prometheus.

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `egress_check_success` | Gauge | target, protocol, namespace | 1 = success, 0 = failure |
| `egress_check_duration_seconds` | Histogram | target, protocol, namespace | Total check duration |
| `egress_check_total` | Counter | target, protocol, namespace, result | Total checks performed |
| `egress_check_failure_category` | Gauge | target, protocol, namespace, category | 1 if most recent failure matches category |
| `egress_check_dns_duration_seconds` | Histogram | target, namespace | DNS resolution time |
| `egress_check_tls_duration_seconds` | Histogram | target, namespace | TLS handshake time |
| `egress_checker_healthy` | Gauge | — | 1 = healthy, 0 = unhealthy |

### Example PromQL Queries

```promql
# All failing targets in a namespace
egress_check_success{namespace="my-team"} == 0

# Targets blocked by firewall
egress_check_failure_category{category="firewall_blocked"} == 1

# p99 check duration
histogram_quantile(0.99, rate(egress_check_duration_seconds_bucket[5m]))

# Alert: target down for 2+ minutes
egress_check_success == 0 and on() (time() - egress_check_total > 120)
```

## Structured Logging

Every check result emits a single JSON log line to stdout. Logs are collected automatically by the existing cluster log pipeline.

### Successful check

```json
{
  "target": "partner-api",
  "protocol": "https",
  "port": 443,
  "result": "success",
  "duration_ms": 42.5,
  "http_status": 200,
  "event": "egress_check",
  "level": "info",
  "timestamp": "2026-03-10T12:00:00.000000Z"
}
```

### Failed check (with diagnostics)

```json
{
  "target": "partner-api",
  "protocol": "https",
  "port": 443,
  "result": "failure",
  "duration_ms": 5012.3,
  "error": "Connection reset by peer",
  "failure_category": "firewall_blocked",
  "diagnostics": {
    "tcp_state": "failed",
    "error_detail": "Connection reset by peer"
  },
  "suggested_action": "Connection was blocked, likely by Azure Firewall. Contact the firewall team with the target FQDN and port. (target: api.example.com:443)",
  "event": "egress_check",
  "level": "warning",
  "timestamp": "2026-03-10T12:01:00.000000Z"
}
```

## Local Development

### Prerequisites

- **Python 3.14+** (managed automatically by uv)
- **[uv](https://docs.astral.sh/uv/)** — package manager
- **Docker** (for container builds)
- **kustomize** (for manifest validation)

### Quick Start

```bash
# Clone and install dependencies
git clone <repo-url>
cd network-egress-checker
uv sync

# Run all quality checks (lint + format + typecheck + tests)
make check

# Run the checker locally with a sample config
export EGRESS_CHECKER_CONFIG=path/to/your/config.yaml
uv run python -m egress_checker
```

### Makefile Commands

| Command | Description |
|---------|-------------|
| `make lint` | Run Ruff linter |
| `make format` | Auto-format with Ruff |
| `make format-check` | Verify formatting (CI mode) |
| `make typecheck` | Run mypy in strict mode |
| `make test` | Run all tests with coverage |
| `make test-unit` | Run unit tests only |
| `make test-int` | Run integration tests only |
| `make check` | Full CI equivalent: lint + format-check + typecheck + test |
| `make build` | Build the Docker image |

### Dev Containers

The project includes a `.devcontainer/devcontainer.json` for a consistent development environment.

**VS Code:**

1. Install the [Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) extension.
2. Open the project folder.
3. VS Code prompts "Reopen in Container" — accept.
4. Dependencies install automatically via `uv sync`.

**JetBrains PyCharm (2023.3+):**

1. Go to File > Remote Development > Dev Containers.
2. Select the project directory.
3. PyCharm builds and connects to the dev container.

The dev container includes Python 3.14, uv, Ruff, mypy, pytest, kustomize, and kubectl.

### IDE Setup (without Dev Containers)

**VS Code** — recommended extensions are defined in `.vscode/extensions.json` and auto-suggested on open:

- `charliermarsh.ruff` — linting and formatting
- `ms-python.mypy-type-checker` — type checking
- `ms-python.python` — Python language support

Format-on-save and organize-imports-on-save are pre-configured in `.vscode/settings.json`.

**JetBrains PyCharm:**

1. Set the project interpreter to `.venv/bin/python` (created by `uv sync`).
2. Mark `src/` as Sources Root and `tests/` as Test Sources Root.
3. Configure Ruff as an external tool or file watcher for format-on-save.
4. Enable mypy via the Mypy plugin with `--strict`.

## Python Development Patterns

### Dependency Management

- **uv** is the sole package manager. Never use `pip install` directly.
- `uv.lock` is committed for reproducible builds. CI and Docker use `uv sync --frozen`.
- Add dependencies: `uv add <package>`. Add dev dependencies: `uv add --group dev <package>`.

### Code Style

- All code follows **PEP 8** (style), **PEP 257** (docstrings), and **PEP 484** (type annotations).
- **Ruff** is the single source of truth for formatting and linting (line length: 99).
- **mypy** runs in strict mode — all functions require complete type annotations.
- **No `Any` types** except at true integration boundaries.
- Imports are sorted by Ruff: standard library, then third-party, then local.
- Docstrings use Google style.
- Naming: `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants.

### Linting Rules

Ruff is configured with these rule sets in `pyproject.toml`:

| Rule Set | Purpose |
|----------|---------|
| `E`, `F`, `W` | Core pycodestyle and pyflakes |
| `I` | Import sorting (isort) |
| `UP` | pyupgrade — modern Python syntax |
| `S` | Security (bandit) |
| `B` | Bugbear — common pitfalls |
| `A` | Shadowing builtins |
| `C4` | Comprehension improvements |
| `PT` | Pytest style |
| `RUF` | Ruff-specific rules |

Linting and formatting run both locally (`make lint`, `make format`) and in the CI pipeline.

### Logging

All logging goes through **structlog** configured with JSON rendering. No `print()` statements. No stdlib `logging` direct usage.

```python
import structlog

logger = structlog.get_logger()
await logger.ainfo("check_complete", target="api", duration_ms=42.5)
```

### Configuration Validation

All external data is validated through **pydantic v2** models:

```python
from egress_checker.config import load_config

config = load_config(Path("/etc/egress-checker/config.yaml"))
# Raises ValueError with clear message on invalid input
```

### Async Patterns

The application uses a single `asyncio` event loop. Checks execute concurrently with a bounded semaphore (default: 5):

```python
# Bounded concurrency prevents resource spikes
self._semaphore = asyncio.Semaphore(max_concurrency)

async with self._semaphore:
    result = await execute_check(target)
```

## Testing

This project follows **test-driven development (TDD)**. Tests are written before implementation. No implementation is considered complete unless all tests pass.

### Running Tests

```bash
make test          # All tests with coverage report
make test-unit     # Unit tests only (fast, isolated)
make test-int      # Integration tests only
```

### Test Structure

```
tests/
├── conftest.py              # Shared fixtures (sample configs, paths)
├── unit/
│   ├── test_config.py       # 24 tests — validation, parsing, edge cases
│   ├── test_diagnostics.py  # 23 tests — classification for every category
│   ├── test_checks.py       # 12 tests — HTTP/TCP mock scenarios
│   ├── test_metrics.py      #  5 tests — metric labels and values
│   ├── test_logging.py      #  6 tests — log format and content
│   ├── test_health.py       #  6 tests — endpoint responses and lifecycle
│   └── test_scheduler.py    #  4 tests — concurrency and dispatch
└── integration/
    └── test_app.py          #  2 tests — full lifecycle: config → schedule → health → metrics
```

**82 tests total** | Target: 90%+ line coverage

### Conventions

- Test files mirror source files: `src/egress_checker/config.py` -> `tests/unit/test_config.py`.
- Test functions: `test_<behavior_under_test>`.
- Mock at boundaries (HTTP responses, TCP connections, file I/O). Never mock the unit under test.
- Async tests use `@pytest.mark.asyncio` (auto mode enabled in `pyproject.toml`).
- Shared fixtures live in `conftest.py`. Prefer factory fixtures over complex setup.

## Kubernetes Deployment

### Kustomize Base

The platform team maintains a Kustomize base in `kustomize/base/` containing:

| Manifest | Purpose |
|----------|---------|
| `deployment.yaml` | Pod spec with health probes, resource limits, ConfigMap mount |
| `service.yaml` | Exposes metrics port 9090 for Prometheus scraping |
| `configmap.yaml` | Default empty targets (overridden by tenant overlay) |
| `podmonitor.yaml` | PodMonitor for Azure Managed Prometheus |

Default resource profile:

| Resource | Request | Limit |
|----------|---------|-------|
| Memory | 32Mi | 64Mi |
| CPU | 25m | 50m |

### Tenant Overlay

Tenants create a Kustomize overlay that patches the base with their namespace and target configuration:

```
kustomize/overlays/my-team/
├── kustomization.yaml
└── configmap-patch.yaml
```

**kustomization.yaml:**

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: my-team

resources:
  - ../../base

patches:
  - path: configmap-patch.yaml
```

**configmap-patch.yaml:**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: egress-checker-config
data:
  config.yaml: |
    targets:
      - name: partner-api
        url: https://api.example.com/health
      - name: database
        host: sql-server.private.network
        port: 1433
        protocol: tcp
```

### Build and Deploy

```bash
# Validate manifests
kustomize build kustomize/overlays/my-team/

# Hydrate and commit (for ArgoCD GitOps)
kustomize build kustomize/overlays/my-team/ > deploy/my-team/manifests.yaml
git add deploy/my-team/manifests.yaml
git commit -m "chore(my-team): update egress checker targets"
```

ArgoCD syncs the hydrated manifests — no server-side Kustomize or Helm processing.

### Overriding Resource Limits

Tenants with many targets (20+) may need larger resource limits. Add a patch to the overlay:

```yaml
# resource-patch.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: egress-checker
spec:
  template:
    spec:
      containers:
        - name: egress-checker
          resources:
            requests:
              memory: "64Mi"
              cpu: "50m"
            limits:
              memory: "128Mi"
              cpu: "100m"
```

### Container Image

Build and publish:

```bash
# Build
make build
# or
docker build -t egress-checker:latest .

# Tag and push to your registry
docker tag egress-checker:latest <registry>/egress-checker:v0.1.0
docker push <registry>/egress-checker:v0.1.0
```

The Dockerfile uses a multi-stage build:
1. **Builder stage** — installs dependencies with `uv sync --frozen --no-dev`.
2. **Runtime stage** — copies the venv into `python:3.14-slim`, runs as non-root user (UID 1000).

Ports exposed: **8080** (health) and **9090** (metrics).

### Health Probes

| Endpoint | Port | Purpose |
|----------|------|---------|
| `/healthz` | 8080 | Liveness — returns 200 when the event loop is running |
| `/readyz` | 8080 | Readiness — returns 200 after config loads and first check cycle completes |

Both are configured as Kubernetes liveness and readiness probes in the base Deployment manifest.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `EGRESS_CHECKER_CONFIG` | `/etc/egress-checker/config.yaml` | Path to the YAML configuration file |
| `EGRESS_CHECKER_METRICS_PORT` | `9090` | Prometheus metrics server port |
| `EGRESS_CHECKER_HEALTH_PORT` | `8080` | Health endpoint server port |
| `EGRESS_CHECKER_NAMESPACE` | `default` | Kubernetes namespace (auto-set via downward API in the Deployment) |
| `EGRESS_CHECKER_MAX_CONCURRENCY` | `5` | Maximum concurrent checks |

## License

See [LICENSE](LICENSE) for details.
