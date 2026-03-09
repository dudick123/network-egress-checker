## ADDED Requirements

### Requirement: Failure classification
The checker SHALL classify each failed check into one of the following diagnostic categories: `firewall_blocked`, `dns_failure`, `connection_timeout`, `connection_refused`, `tls_error`, `http_error`, or `upstream_unreachable`. The classification SHALL be included as a label on metrics and as a field in structured logs.

#### Scenario: Firewall block detection
- **WHEN** a TCP connection receives an immediate RST after SYN, or TLS handshake is terminated by an intermediary, or HTTP response is 470/403 from a transparent proxy
- **THEN** the failure is classified as `firewall_blocked`

#### Scenario: DNS failure detection
- **WHEN** hostname resolution fails with NXDOMAIN, SERVFAIL, or timeout
- **THEN** the failure is classified as `dns_failure`

#### Scenario: Upstream unreachable detection
- **WHEN** TCP and TLS succeed but HTTP response status is 502, 503, or 504
- **THEN** the failure is classified as `upstream_unreachable`

### Requirement: Verbose connection diagnostics
For each failed check, the checker SHALL capture verbose connection-level trace data including: DNS resolution result, TCP connection state, TLS negotiation details (cipher, certificate subject, alert codes), and HTTP response headers. This data SHALL be included in a `diagnostics` object in the structured log entry.

#### Scenario: Failed check includes diagnostics
- **WHEN** an HTTPS check fails with a TLS error
- **THEN** the log entry includes a `diagnostics` object with TLS alert code, cipher offered, and certificate subject if available

#### Scenario: TCP failure includes connection trace
- **WHEN** a TCP check fails with connection timeout
- **THEN** the log entry includes a `diagnostics` object with TCP connection state and timing information

### Requirement: Suggested action for failures
Each failed check log entry SHALL include a `suggested_action` field with a human-readable interpretation and recommended next step based on the failure category.

#### Scenario: Firewall block suggested action
- **WHEN** a check is classified as `firewall_blocked`
- **THEN** the `suggested_action` includes guidance to contact the firewall team with the target FQDN and port

#### Scenario: DNS failure suggested action
- **WHEN** a check is classified as `dns_failure`
- **THEN** the `suggested_action` includes guidance to verify DNS configuration and check CoreDNS health

### Requirement: Heuristic classification disclaimer
Failure classification SHALL be documented as best-effort heuristic. The documentation SHALL acknowledge that classifications (particularly `firewall_blocked`) may produce false positives and recommend confirming with firewall team logs for definitive root cause.

#### Scenario: Documentation acknowledges heuristics
- **WHEN** a user reads the configuration schema reference documentation
- **THEN** the documentation clearly states that failure categories are best-effort classifications
