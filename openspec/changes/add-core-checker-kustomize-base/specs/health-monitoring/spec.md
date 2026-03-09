## ADDED Requirements

### Requirement: Liveness health endpoint
The checker container SHALL expose a `/healthz` endpoint on port 8080 that returns HTTP 200 when the checker process is operational and the event loop is running.

#### Scenario: Healthy checker responds 200
- **WHEN** a GET request is sent to `/healthz`
- **AND** the checker event loop is running
- **THEN** the endpoint returns HTTP 200

### Requirement: Readiness health endpoint
The checker container SHALL expose a `/readyz` endpoint on port 8080 that returns HTTP 200 only after the configuration has been loaded and the first check cycle has completed.

#### Scenario: Not ready before first check cycle
- **WHEN** a GET request is sent to `/readyz` before the first check cycle completes
- **THEN** the endpoint returns HTTP 503

#### Scenario: Ready after first check cycle
- **WHEN** a GET request is sent to `/readyz` after the first check cycle completes
- **THEN** the endpoint returns HTTP 200

### Requirement: Self-monitoring metric
The checker SHALL expose an `egress_checker_healthy` gauge metric (1 = healthy, 0 = unhealthy) indicating the overall operational status of the checker.

#### Scenario: Healthy checker metric
- **WHEN** the checker is operating normally
- **THEN** `egress_checker_healthy` is set to 1

#### Scenario: Unhealthy checker metric
- **WHEN** the checker encounters an internal error preventing check execution
- **THEN** `egress_checker_healthy` is set to 0
