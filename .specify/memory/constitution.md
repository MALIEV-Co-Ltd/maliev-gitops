<!--
SYNC IMPACT REPORT
- Version: 0.0.0 -> 1.0.0
- Rationale: Initial ratification of the constitution.
- Modified Principles:
  - NEW: I. No Secrets in Git
  - NEW: II. Git as the Single Source of Truth
  - NEW: III. Environment Configuration via Kustomize Overlays
  - NEW: IV. Declarative, Automated Deployments with ArgoCD
- Templates requiring updates:
  - ✅ .specify/templates/plan-template.md (No changes needed, but Constitution Check is now enabled)
  - ✅ .specify/templates/spec-template.md (No changes needed)
  - ✅ .specify/templates/tasks-template.md (No changes needed)
-->
# maliev-gitops Constitution

## Core Principles

### I. No Secrets in Git
This repository is public. It MUST NOT contain any secrets, private keys, or sensitive credentials in any file or commit history. All secrets MUST be managed through the External Secrets Operator and stored in a secure, external vault (e.g., Google Secret Manager).

### II. Git as the Single Source of Truth
This Git repository is the single, declarative source of truth for all application and infrastructure configurations. All changes to the desired state of the system MUST be made via a pull request to this repository. Manual changes to the cluster (`kubectl apply/edit/delete`) are strictly forbidden for routine operations.

### III. Environment Configuration via Kustomize Overlays
All environment-specific configurations (e.g., image tags, resource limits, domain names, secret versions) MUST be managed using Kustomize overlays. A `base` configuration should contain the common, environment-agnostic manifests, and each environment (`development`, `staging`, `production`) MUST have its own overlay to patch the base. Duplication of entire manifest files between environments is forbidden.

### IV. Declarative, Automated Deployments with ArgoCD
Application and infrastructure deployments MUST be managed declaratively by ArgoCD. The desired state is defined by the manifests in this Git repository, and ArgoCD is responsible for automatically synchronizing the cluster's live state to match it. All new applications MUST be onboarded by creating an ArgoCD `Application` resource.

## Governance
All pull requests and feature plans will be reviewed for compliance with these principles. Amendments to this constitution require a pull request, must be documented in the Sync Impact Report, and must follow semantic versioning.

**Version**: 1.0.0 | **Ratified**: 2025-10-08 | **Last Amended**: 2025-10-08
