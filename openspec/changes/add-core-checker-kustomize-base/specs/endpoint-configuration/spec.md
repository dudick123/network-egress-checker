## ADDED Requirements

### Requirement: Tenant endpoint configuration via ConfigMap
Tenants SHALL define egress checks via a Kubernetes ConfigMap containing a YAML `targets` list. Each target entry MUST include a `name` and either a `url` (for HTTP/HTTPS) or `host` + `port` + `protocol` (for TCP). Optional fields include `expected_status` (default: 2xx), `interval` (default: 60s, minimum: 10s), and `timeout` (default: 5s).

#### Scenario: Minimal HTTP target configuration
- **WHEN** a tenant provides a target with only `name` and `url` fields
- **THEN** the checker accepts the configuration with default values for interval (60s), timeout (5s), and expected_status (2xx)

#### Scenario: TCP target configuration
- **WHEN** a tenant provides a target with `name`, `host`, `port`, and `protocol: tcp`
- **THEN** the checker accepts the configuration and performs TCP connectivity checks

#### Scenario: Custom check interval and timeout
- **WHEN** a tenant specifies `interval: 30` and `timeout: 10` on a target
- **THEN** the checker uses the custom values for that target's check schedule and timeout

#### Scenario: Interval below minimum rejected
- **WHEN** a tenant specifies `interval: 5` (below the 10-second minimum)
- **THEN** the checker rejects the configuration with a clear validation error at startup

### Requirement: Configuration validation at startup
The checker SHALL validate the ConfigMap YAML against the pydantic schema at startup. Invalid configuration (missing required fields, unsupported protocol, invalid values) SHALL produce a clear error message in container logs and the process SHALL exit with a non-zero status code.

#### Scenario: Missing required field
- **WHEN** a target entry is missing the `name` field
- **THEN** the checker logs a validation error identifying the missing field and exits non-zero

#### Scenario: Unsupported protocol
- **WHEN** a target specifies `protocol: ftp`
- **THEN** the checker logs a validation error stating the protocol is unsupported and exits non-zero

#### Scenario: Valid configuration accepted
- **WHEN** all target entries pass validation
- **THEN** the checker starts successfully and begins executing checks
