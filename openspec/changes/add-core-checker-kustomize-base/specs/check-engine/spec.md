## ADDED Requirements

### Requirement: HTTP and HTTPS egress checks
The checker SHALL perform HTTP GET requests to configured HTTP/HTTPS target URLs. A check SHALL be marked successful when the response status code matches the expected code (default: 2xx range). HTTPS checks SHALL validate TLS certificates by default. Each check SHALL record response time in milliseconds.

#### Scenario: Successful HTTPS check
- **WHEN** the checker performs an HTTPS GET to a configured URL
- **AND** the response status code is 200
- **AND** the expected status is 2xx (default)
- **THEN** the check is recorded as successful with the response time in milliseconds

#### Scenario: HTTP status mismatch
- **WHEN** the checker performs an HTTP GET and receives status 500
- **AND** the expected status is 2xx
- **THEN** the check is recorded as failed with failure category `http_error`

#### Scenario: HTTPS TLS certificate validation failure
- **WHEN** the checker performs an HTTPS check and TLS certificate validation fails
- **THEN** the check is recorded as failed with failure category `tls_error`

### Requirement: TCP connectivity checks
The checker SHALL open a TCP connection to the configured host and port. A check SHALL be marked successful when the TCP handshake completes within the timeout. Each check SHALL record connection time in milliseconds. Failed connections SHALL include the error reason.

#### Scenario: Successful TCP connection
- **WHEN** the checker opens a TCP connection to a configured host and port
- **AND** the TCP handshake completes within the timeout
- **THEN** the check is recorded as successful with the connection time in milliseconds

#### Scenario: TCP connection refused
- **WHEN** the checker attempts a TCP connection and receives a RST
- **THEN** the check is recorded as failed with failure category `connection_refused`

#### Scenario: TCP connection timeout
- **WHEN** the checker attempts a TCP connection and no SYN-ACK is received within the timeout
- **THEN** the check is recorded as failed with failure category `connection_timeout`

### Requirement: Concurrent check execution with bounded parallelism
The checker SHALL execute checks concurrently with bounded parallelism (default: 5 concurrent checks) to avoid resource spikes. Each target SHALL be checked independently on its configured interval schedule.

#### Scenario: Bounded concurrency
- **WHEN** 10 targets are configured and the concurrency limit is 5
- **THEN** at most 5 checks execute simultaneously

#### Scenario: Independent scheduling
- **WHEN** target A has interval 30s and target B has interval 60s
- **THEN** target A is checked twice as often as target B

### Requirement: Stateless check execution
The checker SHALL be stateless and restartable. Check history SHALL live only in metrics and logs. If the pod is restarted, checks SHALL resume from scratch without requiring persistent state.

#### Scenario: Pod restart
- **WHEN** the checker pod is restarted
- **THEN** it reloads configuration from the ConfigMap and begins a new check cycle without errors
