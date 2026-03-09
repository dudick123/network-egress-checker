## Context
This is the foundational Phase 1 of the Network Egress Checker. The platform team owns the checker application and container image. Tenants only provide a ConfigMap with their egress targets. The checker runs as a Deployment in the tenant's namespace, producing Prometheus metrics and structured JSON logs.

Key stakeholders: platform engineering team (owners), tenant developers and SREs (consumers).

## Goals / Non-Goals
- Goals:
  - Stateless, restartable checker that reads config from a mounted ConfigMap
  - Async check execution with bounded concurrency (default: 5)
  - Diagnostic failure classification using connection-level heuristics
  - Prometheus-compatible metrics with low cardinality labels
  - Kustomize base + overlay pattern for GitOps deployment via ArgoCD
- Non-Goals:
  - Ingress monitoring
  - DNS-only or ICMP check types (Phase 3)
  - Grafana dashboards or alerting rules (Phase 2)
  - Custom HTTP headers/bodies for authenticated checks (Phase 3)

## Decisions

### Application structure
- Decision: Single Python package (`egress_checker`) with modules for config, checks, diagnostics, metrics, logging, and health
- Alternatives: Monolithic single-file script → rejected for maintainability; microservice per concern → rejected as over-engineering

### HTTP client library
- Decision: Use `httpx` with async support for HTTP/HTTPS checks
- Alternatives: `aiohttp` → viable but `httpx` provides a more modern API and better TLS introspection; `requests` → no async support

### Async runtime
- Decision: Use `asyncio` with a main event loop; TCP checks use `asyncio.open_connection`
- Alternatives: `trio` → adds dependency without clear benefit for this use case

### Logging
- Decision: Use `structlog` for all log output, configured with JSON rendering to stdout
- Alternatives: stdlib `logging` with custom JSON formatter → structlog provides a cleaner API, built-in JSON rendering, and context binding out of the box

### Configuration
- Decision: YAML ConfigMap parsed with `pydantic` v2 models at startup; invalid config logs errors and exits non-zero
- Alternatives: JSON config → less human-friendly; CRD → too heavy for Phase 1

### Package management
- Decision: Use `uv` for dependency management and virtual environment creation. `uv.lock` committed for reproducible builds.
- Alternatives: pip + pip-tools → slower, no unified tool; poetry → heavier, less Dockerfile-friendly

### Metrics server
- Decision: Use `prometheus_client` built-in HTTP server on a separate port (default: 9090)
- Alternatives: Embed metrics in the health server → separating concerns is cleaner

### Health server
- Decision: Lightweight `aiohttp` or built-in `http.server` on port 8080 serving `/healthz` and `/readyz`
- Alternatives: Use the same port as metrics → risk coupling health probes to metrics scraping

### Kustomize layout
- Decision: `kustomize/base/` contains Deployment, Service, ConfigMap (default/empty), PodMonitor; tenants overlay with namespace and ConfigMap patch
- Alternatives: Helm chart → project convention is Kustomize with hydrated manifests for ArgoCD

### Container image
- Decision: Multi-stage Dockerfile — builder stage uses `uv sync --frozen --no-dev`, final stage copies venv into `python:3.14-slim`. Runs as non-root user.
- Alternatives: Single-stage → larger image; distroless → harder to debug

## Risks / Trade-offs
- Firewall detection heuristics are best-effort; TCP RST from destination may be misclassified as firewall block → mitigated by documenting heuristic nature and including raw diagnostics in logs
- `prometheus_client` default implementation uses a global registry → acceptable for single-process; if multi-process needed later, switch to multiprocess collector
- ConfigMap size limit (1 MiB) limits target count → 50 targets is well within limit; enforce max via pydantic validation

## Open Questions
- Exact container registry path for published images (to be provided by platform team)
- Whether PodMonitor or pod annotations are preferred for the specific Azure Managed Prometheus setup
