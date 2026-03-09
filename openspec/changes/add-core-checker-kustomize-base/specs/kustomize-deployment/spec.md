## ADDED Requirements

### Requirement: Kustomize base manifests
A Kustomize base SHALL be provided containing: Deployment, Service, ConfigMap (default empty targets), and PodMonitor manifests. The Deployment SHALL include container image reference, ports (metrics 9090, health 8080), liveness and readiness probes, resource requests/limits (32Mi/64Mi memory, 25m/50m CPU), and a ConfigMap volume mount.

#### Scenario: Kustomize build succeeds
- **WHEN** `kustomize build` is run against the base directory
- **THEN** it produces valid Kubernetes manifests without errors

#### Scenario: Default resource limits applied
- **WHEN** a tenant uses the base without overrides
- **THEN** the Deployment has resource requests of 32Mi memory and 25m CPU, with limits of 64Mi memory and 50m CPU

### Requirement: Tenant overlay pattern
An example tenant overlay SHALL be provided demonstrating: namespace transformer, ConfigMap patch with sample egress targets, and optional resource limit overrides. Tenants SHALL reference the base via a Kustomize overlay in their ArgoCD application repository.

#### Scenario: Tenant overlay with namespace and ConfigMap patch
- **WHEN** a tenant creates an overlay with a namespace and ConfigMap patch containing their targets
- **AND** runs `kustomize build` against the overlay
- **THEN** the output contains manifests in the tenant's namespace with the patched ConfigMap

#### Scenario: Tenant overrides resource limits
- **WHEN** a tenant adds a resource limit patch to their overlay
- **THEN** the built manifests reflect the custom resource limits

### Requirement: PodMonitor for Prometheus scraping
The Kustomize base SHALL include a PodMonitor resource configured to scrape the metrics endpoint (port 9090) of the checker pods.

#### Scenario: PodMonitor targets checker pods
- **WHEN** the PodMonitor is applied to the cluster
- **THEN** it selects checker pods by label and scrapes the metrics port

### Requirement: Hydrated manifests for ArgoCD
All manifests SHALL be fully rendered (hydrated) at commit time via `kustomize build`. ArgoCD SHALL apply pre-rendered manifests with no server-side processing or templating.

#### Scenario: ArgoCD syncs hydrated manifests
- **WHEN** hydrated manifests are committed to Git
- **THEN** ArgoCD applies them directly without running Kustomize or any server-side templating
