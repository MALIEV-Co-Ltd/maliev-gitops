# Tasks: GitOps Processes and Validation

**Input**: Design documents from `/specs/001-create-a-gitops/`
**Prerequisites**: plan.md, spec.md

## Phase 1: Foundational (Documentation)

**Purpose**: Ensure the process documentation is complete and accurate before validation begins.

- [x] T001: [P] **Finalize Onboarding Documentation**: Ensure the `README.md` contains the complete and accurate step-by-step guide for onboarding a new application.
- [x] T002: [P] **Finalize Promotion/Rollback Documentation**: Ensure the `README.md` clearly explains the process for promoting and rolling back applications.

---

## Phase 2: User Story 1 - Onboarding a New Application (Process Validation)

**Goal**: Manually execute the documented onboarding process to ensure it is accurate and effective.
**NOTE**: These tasks represent a manual validation that should be performed by a developer.

**Independent Test**: Follow the "Onboarding a New Application" guide in the `README.md` for a sample "hello-world" application and verify its successful deployment.

### Validation Tasks for User Story 1

- [ ] T003: [US1] **Create Sample App**: Create a sample application directory `3-apps/hello-world` with a `base` and `overlays/development` structure.
- [ ] T004: [US1] **Create Manifests**: Create a `deployment.yaml`, `service.yaml`, and `kustomization.yaml` for a simple "hello-world" container in the `base` directory.
- [ ] T005: [US1] **Create Overlay**: Create the `kustomization.yaml` in the `overlays/development` directory, setting the namespace to `maliev-dev`.
- [ ] T006: [US1] **Create ArgoCD App**: Create the ArgoCD `Application` manifest `argocd/environments/dev/apps/hello-world.yaml`.
- [ ] T007: [US1] **Submit PR**: Commit all new files, create a Pull Request, and merge it.
- [ ] T008: [US1] **Verify Deployment**: Verify that the `hello-world` application appears in the ArgoCD UI, becomes `Healthy` and `Synced`, and that the pods are running in the `maliev-dev` namespace.

**Checkpoint**: The onboarding process is validated.

---

## Phase 3: User Story 2 - Promoting an Application (Process Validation)

**Goal**: Manually execute the documented promotion process.
**NOTE**: These tasks represent a manual validation that should be performed by a developer.

**Independent Test**: Follow the "Promoting a Release" guide to promote the "hello-world" application to the `staging` environment.

### Validation Tasks for User Story 2

- [ ] T009: [US2] **Create Staging Overlay**: Create the `staging` overlay for the `hello-world` application at `3-apps/hello-world/overlays/staging`.
- [ ] T010: [US2] **Create Staging Kustomization**: Create the `kustomization.yaml` in the `staging` overlay, setting the namespace to `maliev-staging` and specifying a new image tag.
- [ ] T011: [US2] **Create Staging ArgoCD App**: Create the ArgoCD `Application` manifest `argocd/environments/staging/apps/hello-world.yaml`.
- [ ] T012: [US2] **Submit PR**: Commit, push, and merge the changes.
- [ ] T013: [US2] **Verify Promotion**: Verify that the `hello-world` application is deployed to the `maliev-staging` namespace with the updated image tag.

**Checkpoint**: The promotion process is validated.

---

## Phase 4: User Story 3 - Automated Validation Workflow (Implementation) 🎯 MVP

**Goal**: Implement a CI pipeline that automatically validates the correctness and consistency of the GitOps repository.

**Independent Test**: Open a pull request with an intentional error (e.g., a malformed `kustomization.yaml`). The GitHub Actions workflow should fail and prevent the PR from being merged.

### Implementation for User Story 3

- [x] T014: [US3] **Create Workflow File**: Create a new GitHub Actions workflow file at `.github/workflows/validate.yml`.
- [x] T015: [US3] **Configure Trigger**: Configure the workflow in `validate.yml` to trigger on `pull_request` events targeting the `main` branch.
- [x] T016: [US3] **Add Linting Job**: Create a new job named `lint` in `validate.yml`.
- [x] T017: [US3] **Implement YAML Linting**: [P] Add a step to the `lint` job to install a YAML linter (e.g., `yamllint`) and run it against all `.yaml` files in the repository.
- [x] T018: [US3] **Implement K8s Best Practices Check**: [P] Add a step to the `lint` job to use a static analysis tool (e.g., `kube-linter`) to check manifests for best practice violations.
- [x] T019: [US3] **Add Validation Job**: Create a new job named `validate` in `validate.yml` that runs after the `lint` job.
- [x] T020: [US3] **Implement Kustomize Build Validation**: Add a step to the `validate` job to install `kustomize` and run `kustomize build` on all overlays found in `3-apps/*/overlays/*`.
- [x] T021: [US3] **Implement Secret Check**: Add a step to the `validate` job to search for files containing `kind: Secret` and fail if any are found.
- [x] T022: [US3] **Implement Structural Validation**: Add a step to the `validate` job to run a script that verifies the `base`/`overlays` structure for all applications in `3-apps/`.
- [x] T023: [US3] **Implement ArgoCD Path Validation**: Add a step to the `validate` job to run a script that parses all `Application` manifests and confirms their `spec.source.path` points to an existing directory.

---

## Implementation Strategy

1.  First, complete the documentation tasks in **Phase 1**.
2.  Next, manually execute the validation tasks in **Phase 2** and **Phase 3** to ensure the documented processes are correct.
3.  Finally, implement the automated validation workflow in **Phase 4** to enforce these processes automatically for all future changes.