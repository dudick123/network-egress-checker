# Change: Add core egress checker application and Kustomize base

## Why
Tenants on the shared AKS cluster lack visibility into egress connectivity failures until application-level errors surface, leading to delayed incident detection and extended MTTR. A lightweight, self-service checker that generates synthetic traffic and exposes Prometheus metrics will reduce MTTD from hours to minutes.

## What Changes
- Add Python 3.14+ checker application with HTTP/HTTPS and TCP check support using `httpx` and `asyncio`, managed via `uv`
- Add verbose connection diagnostics with failure classification (firewall_blocked, dns_failure, connection_timeout, connection_refused, tls_error, http_error, upstream_unreachable)
- Add Prometheus metrics endpoint via `prometheus_client` with core metrics including failure category gauges and phase-level duration histograms
- Define tenant ConfigMap contract: YAML schema with `pydantic` validation and clear startup error messages
- Add structured JSON logging via `structlog` to stdout with diagnostics object and suggested_action on failures
- Add health endpoints (`/healthz`, `/readyz`) and self-monitoring metric
- Create multi-stage Dockerfile with `python:3.14-slim` base and `uv sync --frozen`
- Create Kustomize base with Deployment, ConfigMap, Service, and PodMonitor manifests
- Provide example tenant overlay with ConfigMap patch and namespace transformer

## Impact
- Affected specs: endpoint-configuration, check-engine, connection-diagnostics, metrics-exposure, structured-logging, kustomize-deployment, health-monitoring (all new)
- Affected code: entire application is new — `src/`, `Dockerfile`, `kustomize/base/`, `kustomize/overlays/example/`
