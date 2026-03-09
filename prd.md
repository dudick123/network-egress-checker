# PRD: Network Egress Checker

## 1. Product overview

### 1.1 Document title and version

- PRD: Network Egress Checker
- Version: 1.0

### 1.2 Product summary

Tenants on a shared AKS cluster managed via ArgoCD frequently encounter network egress failures that are difficult to diagnose. These failures may stem from Azure Firewall rule changes (managed by a separate team), Kubernetes NetworkPolicy updates, DNS resolution issues, or upstream service outages. Today, tenants lack visibility into whether their workloads can reach required egress destinations until an application-level failure surfaces, often causing delayed incident detection and extended mean-time-to-resolution.

The Network Egress Checker is a lightweight, self-service tool that generates synthetic network traffic to user-defined endpoints and exposes the results as Prometheus metrics and structured container logs. The tool is implemented in Python and follows a clear separation of concerns: the platform engineering team owns the checker application — the container image, networking logic, diagnostic classification, and metrics instrumentation — while tenant development teams only need to provide a simple endpoint configuration declaring what they want to check (e.g., an HTTPS GET to `foo.com/api/bar`). Tenants define their desired egress checks through a minimal Kubernetes ConfigMap, managed via GitOps. The tool runs as a small container workload within the tenant's namespace, producing metrics that are automatically scraped by Azure Managed Prometheus and visualizable in Grafana.

This separation means the platform team can iterate on check logic, add new diagnostic capabilities, and push updated container images without requiring any changes from tenants. Tenants get continuous, proactive visibility into egress connectivity without requiring access to Azure Firewall logs, coordination with the platform networking team, or understanding of the underlying diagnostic implementation.

## 2. Goals

### 2.1 Business goals

- Reduce mean-time-to-detection (MTTD) for egress connectivity failures from hours to minutes
- Decrease cross-team support burden by enabling tenants to self-diagnose network issues before escalating to the platform or firewall team
- Provide an auditable, GitOps-driven record of which egress destinations each tenant depends on
- Standardize egress monitoring across all tenants on the shared AKS cluster

### 2.2 User goals

- Quickly determine whether a workload can reach its required egress destinations (internal cluster, private network, and internet)
- Receive alerts when egress connectivity degrades or fails, before application-level errors occur
- Configure egress checks without requiring cluster-admin privileges or platform team involvement
- View egress health dashboards alongside existing application metrics in Grafana

### 2.3 Non-goals

- Ingress connectivity monitoring (future scope)
- Replacing or duplicating Azure Firewall logging and diagnostics
- Deep packet inspection or traffic content analysis
- Managing or modifying Kubernetes NetworkPolicies or Azure Firewall rules
- Providing a general-purpose network diagnostic or troubleshooting suite

## 3. User personas

### 3.1 Key user types

- Tenant application developers deploying workloads on the shared AKS cluster
- Tenant DevOps/SRE engineers responsible for application reliability and observability
- Platform engineering team members who support the shared AKS cluster

### 3.2 Basic persona details

- **Tenant developer**: Deploys and maintains application workloads on the shared cluster. Needs to know if their app can reach external APIs, databases, or partner services. May not have deep Kubernetes networking expertise.
- **Tenant SRE**: Responsible for uptime and incident response for tenant workloads. Wants proactive alerting on egress failures and historical data for postmortem analysis.
- **Platform engineer**: Manages the shared AKS cluster, ArgoCD, and observability stack. Needs tenant egress monitoring to be self-service and low-overhead so it does not create operational burden.

### 3.3 Ownership and role-based access

- **Platform team (owns the tool)**: Designs, develops, and maintains the checker Python application and container image. Owns the Kustomize base (Deployment, Service, PodMonitor). Controls the container image tag and default configuration. Can set cluster-wide constraints (e.g., maximum check frequency, blocked target patterns). Publishes new versions without requiring tenant changes.
- **Tenant development team (owns their configuration)**: Creates and maintains the ConfigMap listing their egress targets within their namespace. Manages their Kustomize overlay (namespace, ConfigMap patch, optional resource limit overrides). Views metrics and logs for their own checks. Does not need to understand the checker internals — only the ConfigMap contract.

## 4. Functional requirements

- **Tenant endpoint configuration** (Priority: High)
  - Tenants define egress checks via a Kubernetes ConfigMap within their namespace
  - The configuration contract is intentionally simple — tenants only specify *what* to check, not *how*: a list of target endpoints with a name, URL or host, port, and protocol (HTTP, HTTPS, TCP)
  - For HTTP/HTTPS targets, tenants may optionally specify the expected status code (default: 2xx) and request path
  - Each endpoint entry supports configurable check interval (default: 60 seconds, minimum: 10 seconds) and timeout (default: 5 seconds)
  - Configuration supports target types: internal cluster services, private network addresses, and internet addresses
  - Example minimal tenant configuration:
    ```yaml
    targets:
      - name: partner-api
        url: https://foo.com/api/bar
      - name: internal-auth
        url: https://auth-service.platform.svc.cluster.local/healthz
      - name: database
        host: sql-server.private.network
        port: 1433
        protocol: tcp
    ```
  - Invalid configuration (e.g., missing required fields, unsupported protocol) produces a clear error in container logs at startup

- **Platform-owned check engine** (Priority: High)
  - The platform team owns the checker application: a Python-based container image that reads the tenant-provided ConfigMap and executes all networking, diagnostic, and metrics logic
  - Supported check types: HTTP/HTTPS (status code validation), TCP connect, DNS resolution, ICMP ping (where permitted)
  - The check engine is versioned and published as a container image; platform team controls the image tag in the Kustomize base
  - Tenants do not need to understand or modify the check engine — they consume it as a black box via the ConfigMap contract
  - The platform team can add new check types, refine diagnostic heuristics, and fix bugs by publishing a new image version without requiring tenant-side changes

- **Connection diagnostics and failure classification** (Priority: High)
  - Each check captures verbose connection-level detail comparable to `curl -vv` output, including: DNS resolution result, TCP handshake timing, TLS negotiation details (cipher, certificate chain, handshake duration), HTTP response headers, and error codes
  - The checker classifies each failure into a diagnostic category to help tenants distinguish root causes:
    - `firewall_blocked`: Connection reset (TCP RST) immediately after SYN, or TLS handshake terminated by an intermediary, or HTTP 470/403 response from a transparent proxy — patterns characteristic of Azure Firewall denying traffic
    - `dns_failure`: Hostname could not be resolved (NXDOMAIN, SERVFAIL, timeout)
    - `connection_timeout`: SYN sent but no SYN-ACK received within timeout — may indicate firewall drop (no RST) or routing issue
    - `connection_refused`: TCP RST received from the destination host (port not listening)
    - `tls_error`: TLS handshake failed (certificate validation, protocol mismatch, SNI rejection)
    - `http_error`: TCP and TLS succeeded but HTTP response status did not match expected code
    - `upstream_unreachable`: Connection succeeded but response indicates upstream is down (e.g., 502, 503, 504)
  - Diagnostic category is included as a label on metrics and as a field in structured logs
  - For failed checks, the structured log includes a `diagnostics` object with the verbose connection trace (DNS answer, TCP flags observed, TLS alert code, HTTP response headers) to support troubleshooting without requiring manual `curl -vv` runs
  - Diagnostic output is human-readable and includes a suggested next action (e.g., "Connection was reset during TLS handshake. This pattern is consistent with Azure Firewall blocking the destination. Contact the firewall team with the target FQDN and port.")

- **Synthetic traffic generator** (Priority: High)
  - A lightweight container runs within the tenant's namespace and performs egress checks on the defined schedule
  - Checks execute concurrently with bounded parallelism to avoid resource spikes
  - Each check records: target endpoint, protocol, success/failure, response time (ms), HTTP status code (if applicable), error message (if failed), and timestamp
  - The container must be restartable and stateless; check history lives only in metrics and logs

- **Metrics exposure** (Priority: High)
  - Expose a Prometheus-compatible `/metrics` endpoint on the checker container
  - Key metrics:
    - `egress_check_success` (gauge, labels: target, protocol, namespace) - 1 for success, 0 for failure
    - `egress_check_duration_seconds` (histogram, labels: target, protocol, namespace) - response time
    - `egress_check_total` (counter, labels: target, protocol, namespace, result) - total checks performed
    - `egress_check_failure_category` (gauge, labels: target, protocol, namespace, category) - 1 when the most recent failure matches the category (firewall_blocked, dns_failure, connection_timeout, connection_refused, tls_error, http_error, upstream_unreachable), 0 otherwise
    - `egress_check_dns_duration_seconds` (histogram, labels: target, namespace) - DNS resolution time, isolated from overall check duration
    - `egress_check_tls_duration_seconds` (histogram, labels: target, namespace) - TLS handshake time, isolated from overall check duration
  - Metrics endpoint must be scrapable by Azure Managed Prometheus via PodMonitor or ServiceMonitor annotation

- **Structured logging** (Priority: Medium)
  - Each check result emits a structured JSON log line to stdout
  - Log fields: timestamp, target, protocol, port, result (success/failure), failure_category (if failed), duration_ms, dns_duration_ms, tls_duration_ms, http_status (if applicable), error (if applicable)
  - Failed checks include an additional `diagnostics` JSON object with verbose connection trace data: DNS answers, TCP connection state, TLS negotiation details (cipher, cert subject, alert codes), and HTTP response headers
  - Failed checks include a `suggested_action` field with a human-readable interpretation and recommended next step (e.g., escalate to firewall team with FQDN and port)
  - Logs are automatically collected by the existing cluster log pipeline

- **GitOps integration** (Priority: High)
  - Egress check configuration is stored in Git and deployed via ArgoCD
  - Provide a Kustomize base that tenants reference via an overlay in their ArgoCD application repository
  - All manifests are hydrated (fully rendered) at commit time; no server-side processing or templating occurs during sync
  - Tenants use Kustomize overlays to patch the base with their namespace, endpoint configuration, and any resource limit overrides
  - Configuration changes are applied through standard GitOps workflow (commit, PR, sync)
  - The overlay should be minimal: tenants only need to provide a ConfigMap patch with their endpoint list and a namespace transformer

- **Grafana dashboard template** (Priority: Medium)
  - Provide a pre-built Grafana dashboard JSON that tenants can import
  - Dashboard shows: current egress status (up/down per target), response time trends, failure history timeline, and failure category breakdown (firewall_blocked, dns_failure, connection_timeout, etc.)
  - Dashboard includes a dedicated panel for firewall-classified failures to surface blocked traffic at a glance
  - Dashboard is filterable by namespace, target endpoint, and failure category

- **Health and self-monitoring** (Priority: Medium)
  - The checker container exposes a `/healthz` endpoint for Kubernetes liveness and readiness probes
  - If the checker itself is unhealthy or unable to run checks, it emits a self-diagnostic metric (`egress_checker_healthy` gauge)

## 5. User experience

### 5.1 Entry points and first-time user flow

- Tenant discovers the Network Egress Checker through internal platform documentation or the shared Kustomize base catalog
- Tenant adds a Kustomize overlay referencing the egress checker base to their ArgoCD application repository
- Tenant creates a minimal configuration file listing their egress targets
- ArgoCD syncs the configuration and deploys the checker to the tenant's namespace
- Within one check interval, metrics and logs begin flowing to Azure Managed Prometheus and the log pipeline

### 5.2 Core experience

- **Configure**: Tenant authors a YAML configuration file with a list of endpoints to check. The configuration is intentionally minimal, requiring only a name and target URL/host per entry, with sensible defaults for everything else.
  - This ensures low friction for adoption; tenants can start with a two-line config and refine later.

- **Deploy**: Tenant commits the configuration to their GitOps repository and ArgoCD deploys it. No manual kubectl commands or cluster-admin requests needed.
  - This aligns with existing tenant workflows and requires no new tooling or access patterns.

- **Observe**: Tenant opens their Grafana dashboard and sees real-time egress health for all configured targets. Failed checks surface immediately as red indicators.
  - This provides the proactive visibility that is currently missing.

- **Alert**: Tenant configures Prometheus alerting rules (via their existing AlertManager setup) to fire when `egress_check_success` drops to 0 for a target.
  - This integrates with existing incident response workflows rather than introducing a new alerting channel.

### 5.3 Advanced features and edge cases

- Tenants can define custom HTTP headers or request bodies for checks that require authentication tokens or specific payloads
- Checks against internal cluster services use Kubernetes DNS (e.g., `service.namespace.svc.cluster.local`)
- If a target endpoint is temporarily unreachable, the checker continues checking all other targets on schedule
- If the checker pod is OOMKilled or evicted, Kubernetes restarts it and checks resume from scratch (stateless design)
- Tenants with many endpoints (50+) may need resource limit adjustments; document recommended resource requests per endpoint count

### 5.4 UI/UX highlights

- Minimal configuration surface: a single YAML file with a list of targets
- No custom CRDs required in the initial version; uses standard Kubernetes ConfigMap
- Pre-built Grafana dashboard provides immediate value without custom query authoring
- Structured JSON logs enable ad-hoc querying in any log analytics tool

## 6. Narrative

A tenant SRE, Jamie, deploys a payment processing service on the shared AKS cluster. The service calls three external APIs, connects to an Azure SQL database over a private endpoint, and communicates with an internal authentication service. One morning, the Azure Firewall team applies a rule change that inadvertently blocks traffic to one of the external APIs. Without the Network Egress Checker, Jamie would only discover this when customers start reporting payment failures, potentially 30 minutes or more after the rule change.

With the Network Egress Checker deployed, Jamie has a lightweight container in their namespace that pings all five egress targets every 60 seconds. Within one minute of the firewall change, the `egress_check_success` metric for the affected API drops to 0. Jamie's Prometheus alert fires, their Grafana dashboard turns red for that target, and they can immediately identify the issue and coordinate with the firewall team, all before a single customer is impacted.

## 7. Success metrics

### 7.1 User-centric metrics

- 80% of tenants on the shared cluster adopt the egress checker within 3 months of launch
- Tenant-reported MTTD for egress failures decreases by 70% compared to pre-adoption baseline
- Tenant satisfaction score (via survey) of 4/5 or higher for ease of setup and usefulness

### 7.2 Business metrics

- 50% reduction in egress-related support tickets to the platform engineering team
- 30% reduction in incident duration for egress-related outages
- Zero increase in platform team operational burden from supporting the egress checker

### 7.3 Technical metrics

- Checker container resource usage remains under 50Mi memory and 50m CPU per instance with up to 20 targets
- Check execution latency overhead (time to perform check minus actual network round-trip) stays under 10ms
- Metrics endpoint response time under 100ms at p99
- 99.9% uptime for the checker container across all tenant namespaces

## 8. Technical considerations

### 8.1 Technology stack

- **Language**: Python 3.12+. The platform team's core language skill. Use `aiohttp`/`httpx` for async HTTP checks, standard library `asyncio` for TCP/DNS, and `prometheus_client` for metrics exposition.
- **Container image**: Minimal Python base image (e.g., `python:3.12-slim`). Multi-stage build to keep image size small. Platform team owns the Dockerfile and publishes versioned images to the shared container registry.
- **Configuration contract**: The tenant-facing interface is a YAML-formatted ConfigMap. The checker application parses this at startup using `pydantic` for validation, providing clear error messages for invalid configurations.

### 8.2 Integration points

- **Azure Managed Prometheus**: Metrics are scraped via PodMonitor or pod annotations (`prometheus.io/scrape`, `prometheus.io/port`). The checker exposes metrics via `prometheus_client` in a format compatible with Azure Monitor managed service for Prometheus.
- **ArgoCD**: Deployment is managed as part of the tenant's ArgoCD Application. Manifests are hydrated (fully rendered via Kustomize) at commit time and committed to Git. ArgoCD syncs the pre-rendered manifests with no server-side processing, ensuring what is in Git is exactly what is applied to the cluster.
- **Grafana (Azure Managed)**: Dashboard templates query Azure Managed Prometheus as the data source. PromQL queries must be compatible with Azure's Prometheus implementation.
- **Kubernetes cluster DNS**: Internal cluster target resolution depends on CoreDNS. DNS resolution failures are a distinct check type from connectivity failures.
- **Existing cluster log pipeline**: JSON logs to stdout are picked up by the existing Fluent Bit / log collection agent with no additional configuration.

### 8.3 Data storage and privacy

- No persistent storage required; the checker is stateless
- No sensitive application data is transmitted; checks use synthetic requests (e.g., HTTP HEAD/GET to a health endpoint)
- Target endpoint URLs are stored in ConfigMaps within the tenant's namespace, subject to existing RBAC
- If checks require authentication tokens (e.g., API keys for external services), these should be referenced via Kubernetes Secrets, not stored in the ConfigMap

### 8.4 Scalability and performance

- Each checker instance runs independently within its namespace; no cross-namespace coordination needed
- Resource requests and limits are overridable per tenant via Kustomize overlay patches to accommodate varying endpoint counts
- Default resource profile: 32Mi memory request / 64Mi limit, 25m CPU request / 50m limit
- Check concurrency is bounded (default: 5 concurrent checks) to prevent resource spikes
- At cluster scale (100+ namespaces with checkers), the primary scaling concern is Prometheus cardinality; label design intentionally limits cardinality

### 8.5 Potential challenges

- **Azure Firewall detection heuristics**: The checker uses connection-level signals (TCP RST timing, TLS termination patterns, HTTP response codes from transparent proxies) to classify failures as likely firewall blocks. These are heuristics, not definitive — a TCP RST could originate from the destination host rather than the firewall. Documentation should clearly state that failure categories are best-effort classifications and recommend confirming with the firewall team's logs for definitive root cause.
- **Network policy interference**: Kubernetes NetworkPolicies in the tenant namespace may block the checker's own egress. Documentation must cover how to allow egress for the checker pod.
- **Prometheus metric cardinality**: Tenants with many targets could produce high cardinality. Enforce a configurable maximum target count per instance (default: 50).
- **Rate limiting and abuse**: Checks against external endpoints at high frequency could trigger rate limiting. Default intervals are conservative (60s) and documentation should warn about external rate limits.
- **ICMP restrictions**: ICMP ping may be blocked by Azure networking or NetworkPolicies. ICMP checks should be optional and clearly documented as best-effort.

## 9. Milestones and sequencing

### 9.1 Project estimate

- Medium: 4-6 weeks for initial release (MVP through Grafana dashboard)

### 9.2 Team size and composition

- 1-2 platform engineers: 1 Python developer (core checker application, diagnostics, container image), 1 SRE/observability engineer (Kustomize base, metrics, dashboards, tenant onboarding documentation)

### 9.3 Suggested phases

- **Phase 1**: Core checker and Kustomize base (2-3 weeks) — *platform team*
  - Implement the Python checker application with HTTP/HTTPS and TCP check support using `aiohttp`/`httpx` and `asyncio`
  - Implement verbose connection diagnostics with failure classification (firewall_blocked, dns_failure, connection_timeout, connection_refused, tls_error, http_error, upstream_unreachable)
  - Expose Prometheus metrics endpoint via `prometheus_client` with core metrics including failure category gauges and phase-level duration histograms (DNS, TLS)
  - Define the tenant ConfigMap contract: YAML schema with `pydantic` validation and clear error messages
  - Build and publish the container image (multi-stage Dockerfile, `python:3.12-slim` base)
  - Create Kustomize base with Deployment, ConfigMap, Service, and PodMonitor manifests
  - Provide an example tenant overlay with ConfigMap patch and namespace transformer
  - Structured JSON logging to stdout with diagnostics object and suggested_action on failures
  - Basic documentation: tenant config schema reference and example configuration

- **Phase 2**: Observability and GitOps integration (1-2 weeks) — *platform team*
  - PodMonitor / annotation support for Azure Managed Prometheus
  - Pre-built Grafana dashboard template (including firewall-blocked failure panel)
  - Example ArgoCD Application manifest pointing to hydrated manifests and GitOps workflow documentation
  - CI pipeline example for running `kustomize build` and committing hydrated output
  - Example Prometheus alerting rules (including firewall-specific alert)
  - Tenant onboarding guide: step-by-step instructions for creating an overlay with a ConfigMap patch

- **Phase 3**: Hardening and advanced features (1-2 weeks) — *platform team*
  - DNS resolution check type
  - ICMP ping check type (best-effort)
  - Custom HTTP headers and request body support for authenticated endpoint checks
  - Resource tuning guidance based on endpoint count
  - Platform catalog entry and self-service onboarding automation

## 10. User stories

### 10.1 Configure egress check targets

- **ID**: GH-001
- **Description**: As a tenant developer, I want to define a list of egress endpoints to check so that I can monitor connectivity to all services my application depends on.
- **Acceptance criteria**:
  - Tenant can create a YAML configuration file listing one or more target endpoints
  - Each endpoint entry supports: name, URL or host, port, protocol (HTTP, HTTPS, TCP), and expected status code (for HTTP/HTTPS)
  - Configuration supports optional fields for check interval and timeout with sensible defaults
  - Configuration supports internal cluster, private network, and internet target addresses
  - Invalid configuration (e.g., missing required fields, unsupported protocol) produces a clear error in container logs at startup

### 10.2 Deploy egress checker via GitOps

- **ID**: GH-002
- **Description**: As a tenant DevOps engineer, I want to deploy the egress checker through my existing ArgoCD GitOps workflow so that I do not need to learn a new deployment process.
- **Acceptance criteria**:
  - A Kustomize base is available that tenants reference via an overlay in their ArgoCD Application repository
  - Tenants create a Kustomize overlay that patches the base ConfigMap with their endpoint list and sets their namespace
  - Hydrated (fully rendered) manifests are committed to Git; ArgoCD applies them with no server-side templating
  - The only required input is the egress target configuration; all other values have working defaults
  - ArgoCD can sync, diff, and health-check the egress checker deployment
  - Configuration changes committed to Git are applied on the next ArgoCD sync without manual intervention

### 10.3 View egress health metrics in Prometheus

- **ID**: GH-003
- **Description**: As a tenant SRE, I want egress check results exposed as Prometheus metrics so that I can query them and set up alerts using my existing monitoring tools.
- **Acceptance criteria**:
  - The checker container exposes a `/metrics` endpoint with `egress_check_success`, `egress_check_duration_seconds`, and `egress_check_total` metrics
  - Metrics include labels for target name, protocol, and namespace
  - Metrics are scrapable by Azure Managed Prometheus via PodMonitor or pod annotations
  - Metrics update after each check cycle completes

### 10.4 View egress health in Grafana dashboard

- **ID**: GH-004
- **Description**: As a tenant SRE, I want a pre-built Grafana dashboard so that I can visualize egress health without writing custom queries.
- **Acceptance criteria**:
  - A Grafana dashboard JSON template is provided and documented
  - The dashboard displays current up/down status for each target endpoint
  - The dashboard shows response time trends over a configurable time window
  - The dashboard shows a failure history timeline
  - The dashboard supports filtering by namespace and target endpoint

### 10.5 Receive alerts on egress failure

- **ID**: GH-005
- **Description**: As a tenant SRE, I want to receive alerts when an egress check fails so that I can investigate before application users are impacted.
- **Acceptance criteria**:
  - Example Prometheus alerting rules are provided in the documentation
  - Alert fires when `egress_check_success` is 0 for a configurable duration (default: 2 consecutive failures)
  - Alert includes the target name, namespace, protocol, and failure category in the alert labels
  - A dedicated example alert rule is provided for `egress_check_failure_category{category="firewall_blocked"}` to surface firewall-specific blocks
  - Alert integrates with existing AlertManager configuration without modification

### 10.6 Diagnose firewall-blocked egress traffic

- **ID**: GH-006
- **Description**: As a tenant SRE, I want the checker to classify connection failures and identify patterns consistent with Azure Firewall blocks so that I can quickly determine root cause without running manual `curl -vv` commands or requesting firewall logs from another team.
- **Acceptance criteria**:
  - Each failed check is classified into a diagnostic category: firewall_blocked, dns_failure, connection_timeout, connection_refused, tls_error, http_error, or upstream_unreachable
  - Firewall block detection recognizes: TCP RST received immediately after SYN (before handshake completes), TLS handshake terminated by an intermediary, and HTTP 470/403 responses from transparent proxy infrastructure
  - Failed check logs include a `diagnostics` object containing verbose connection trace data: DNS resolution result, TCP handshake state and flags, TLS negotiation details (cipher offered, alert code received, certificate subject if available), and HTTP response headers
  - Failed check logs include a `suggested_action` field with human-readable guidance (e.g., "TCP connection was reset before TLS handshake. This is consistent with Azure Firewall denying this destination. Escalate to the firewall team with target FQDN: api.example.com, port: 443")
  - The `egress_check_failure_category` metric is populated with the classification, enabling Grafana dashboards and Prometheus alerts to filter by failure type
  - Classification is best-effort and documented as heuristic; false positives (e.g., destination server RST misclassified as firewall) are acknowledged in documentation

### 10.7 View structured check logs

- **ID**: GH-007
- **Description**: As a tenant developer, I want egress check results written as structured JSON logs so that I can search and filter them in my log analytics tool.
- **Acceptance criteria**:
  - Each check result produces a single JSON log line on stdout
  - Log includes: timestamp, target, protocol, port, result, duration_ms, http_status (if applicable), error (if applicable)
  - Logs are collected by the existing cluster log pipeline without additional configuration
  - Log output does not include sensitive data (e.g., authentication tokens)

### 10.8 Perform HTTP/HTTPS egress checks

- **ID**: GH-008
- **Description**: As a tenant developer, I want the checker to perform HTTP and HTTPS requests to my configured endpoints so that I can validate web API connectivity.
- **Acceptance criteria**:
  - Checker performs HTTP GET (default) or HEAD requests to the configured URL
  - Check is marked successful when the response status code matches the expected code (default: 2xx range)
  - Check records response time in milliseconds
  - HTTPS checks validate TLS certificates by default, with an option to skip validation for internal services
  - Connection timeout and response timeout are independently configurable

### 10.9 Perform TCP connectivity checks

- **ID**: GH-009
- **Description**: As a tenant developer, I want the checker to perform TCP connection tests so that I can validate connectivity to non-HTTP services like databases and message brokers.
- **Acceptance criteria**:
  - Checker opens a TCP connection to the configured host and port
  - Check is marked successful when the TCP handshake completes within the timeout
  - Check records connection time in milliseconds
  - Failed connections include the error reason (e.g., connection refused, timeout, DNS resolution failure)

### 10.10 Perform DNS resolution checks

- **ID**: GH-010
- **Description**: As a tenant developer, I want the checker to verify DNS resolution for my egress targets so that I can distinguish DNS failures from connectivity failures.
- **Acceptance criteria**:
  - Checker resolves the hostname of the configured target and records success/failure
  - Check records resolution time in milliseconds
  - Failed resolution includes the error type (e.g., NXDOMAIN, timeout, SERVFAIL)
  - DNS checks work for both internal cluster DNS names and external hostnames

### 10.11 Self-monitor checker health

- **ID**: GH-011
- **Description**: As a platform engineer, I want the checker container to expose health endpoints so that Kubernetes can detect and restart unhealthy instances.
- **Acceptance criteria**:
  - Container exposes a `/healthz` endpoint that returns 200 when the checker is operational
  - Container exposes a `/readyz` endpoint that returns 200 when the checker has loaded its configuration and is ready to perform checks
  - Kubernetes liveness and readiness probes are configured in the Kustomize base Deployment manifest
  - A `egress_checker_healthy` gauge metric is exposed (1 = healthy, 0 = unhealthy)

---

After reviewing this PRD, let me know if you'd like any changes. Once approved, I can create GitHub issues for each user story.
