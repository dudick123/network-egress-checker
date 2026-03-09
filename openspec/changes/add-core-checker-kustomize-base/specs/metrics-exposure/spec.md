## ADDED Requirements

### Requirement: Prometheus metrics endpoint
The checker SHALL expose a Prometheus-compatible `/metrics` endpoint on port 9090. The endpoint SHALL be scrapable by Azure Managed Prometheus via PodMonitor or pod annotations.

#### Scenario: Metrics endpoint accessible
- **WHEN** a Prometheus scraper sends a GET request to `/metrics` on port 9090
- **THEN** the checker returns a valid Prometheus text exposition format response

### Requirement: Core egress check metrics
The checker SHALL expose the following metrics with labels for `target`, `protocol`, and `namespace`:
- `egress_check_success` (gauge): 1 for success, 0 for failure
- `egress_check_duration_seconds` (histogram): response time
- `egress_check_total` (counter, additional label: `result`): total checks performed
- `egress_check_failure_category` (gauge, additional label: `category`): 1 when the most recent failure matches the category, 0 otherwise

#### Scenario: Successful check updates metrics
- **WHEN** an HTTP check completes successfully
- **THEN** `egress_check_success` is set to 1, `egress_check_duration_seconds` is observed, and `egress_check_total` with `result=success` is incremented

#### Scenario: Failed check updates failure category
- **WHEN** a check fails with category `dns_failure`
- **THEN** `egress_check_success` is set to 0, `egress_check_failure_category` with `category=dns_failure` is set to 1, and all other category values for that target are set to 0

### Requirement: Phase-level duration metrics
The checker SHALL expose isolated phase-level duration histograms:
- `egress_check_dns_duration_seconds` (histogram, labels: `target`, `namespace`): DNS resolution time
- `egress_check_tls_duration_seconds` (histogram, labels: `target`, `namespace`): TLS handshake time

#### Scenario: DNS and TLS durations recorded separately
- **WHEN** an HTTPS check completes
- **THEN** `egress_check_dns_duration_seconds` records the DNS resolution time and `egress_check_tls_duration_seconds` records the TLS handshake time, independent of overall check duration
