## ADDED Requirements

### Requirement: Structured JSON log output
Each check result SHALL emit a single structured JSON log line to stdout. Log fields SHALL include: `timestamp`, `target`, `protocol`, `port`, `result` (success/failure), `duration_ms`, `http_status` (if applicable), and `error` (if applicable).

#### Scenario: Successful check log entry
- **WHEN** an HTTP check completes successfully
- **THEN** a JSON log line is written to stdout with `result: "success"`, `duration_ms`, `http_status`, and `timestamp`

#### Scenario: Failed check log entry
- **WHEN** a TCP check fails
- **THEN** a JSON log line is written to stdout with `result: "failure"`, `error` description, `duration_ms`, and `failure_category`

### Requirement: Diagnostics in failed check logs
Failed check log entries SHALL include a `diagnostics` JSON object with verbose connection trace data (DNS answers, TCP connection state, TLS negotiation details, HTTP response headers) and a `suggested_action` field with human-readable guidance.

#### Scenario: Failed check includes diagnostics and suggested action
- **WHEN** a check fails with category `firewall_blocked`
- **THEN** the log entry includes a `diagnostics` object with connection trace data and a `suggested_action` field with remediation guidance

### Requirement: No sensitive data in logs
Log output SHALL NOT include sensitive data such as authentication tokens, API keys, or Kubernetes Secret values. Target URLs and hostnames are permissible.

#### Scenario: Auth header excluded from logs
- **WHEN** a check is performed against a target that uses authentication
- **THEN** the log entry does not contain any authentication token or secret value
