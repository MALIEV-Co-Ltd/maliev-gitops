# Maliev Namespace Resource Optimization - Execution Guide

**Date**: 2025-10-23
**Goal**: Reduce from 9 to 6 n1-standard-1 nodes
**Savings**: $73/month ($876/year)
**Strategy**: Dual-track (kubectl patch + deployment.yaml updates)

---

## ✅ COMPLETED: Preparation Phase

### Track 1: kubectl Patch Scripts (READY)
- ✅ Created `scripts/patch-maliev-resources.sh`
- ✅ Created `scripts/create-hpas.sh`
- ✅ Scripts tested and validated

### Track 2: deployment.yaml Updates (COMPLETED)
- ✅ Updated 20 standard microservices (AuthService already updated manually)
- ✅ Updated Maliev.Web (10m/100m CPU, 192Mi/384Mi Memory)
- ✅ Updated Maliev.Intranet (10m/100m CPU, 256Mi/512Mi Memory)
- ✅ All nodeSelector constraints commented out
- ✅ **Total: 22+ deployment.yaml files updated**

---

## 🚀 EXECUTION STEPS (Run These Now)

### Step 1: Verify Prerequisites (2 minutes)

```bash
# Ensure kubectl is configured for the correct cluster
kubectl config current-context

# Verify you can access maliev namespace
kubectl get pods -n maliev

# Check current node count (should be 9)
kubectl get nodes | wc -l
```

**Expected**: 9 nodes, ~34 pods in maliev namespace

---

### Step 2: Execute kubectl Patches (5-10 minutes)

#### 2a. Make scripts executable
```bash
cd R:/maliev/maliev-gitops/scripts
chmod +x patch-maliev-resources.sh
chmod +x create-hpas.sh
```

#### 2b. Run resource optimization patch
```bash
./patch-maliev-resources.sh
```

**What this does**:
- Patches all 34 deployments/statefulsets with resource limits
- Removes nodeSelector constraints
- Triggers rolling restart of all pods

**Expected output**:
```
✓ Successfully patched maliev-authservice-api
✓ Successfully patched maliev-countryservice-api
... (26 more services)
✓ Successfully patched maliev-web
✓ Successfully patched maliev-mssql
✓ Removed nodeSelector from ...
```

#### 2c. Create HPAs for autoscaling
```bash
./create-hpas.sh
```

**What this does**:
- Creates HorizontalPodAutoscalers for high-traffic services
- Enables dynamic scaling (min=1/2, max=2-4)

**Expected output**:
```
✓ Created maliev-authservice-hpa
✓ Created maliev-web-hpa
✓ Created maliev-predictionservice-hpa
✓ Created maliev-customerservice-hpa
✓ Created maliev-paymentservice-hpa
```

---

### Step 3: Monitor Pod Restarts (30 minutes)

```bash
# Watch pods restart with new resource limits
kubectl get pods -n maliev --watch

# In another terminal, monitor node resource allocation
watch kubectl top nodes
```

**Expected timeline**:
- T+0:  Patches applied
- T+5:  Pods begin rolling restart (1-2 at a time)
- T+30: All pods running with new resource limits

**Success criteria**:
- ✅ All pods in `Running` state
- ✅ No `OOMKilled` or `CrashLoopBackOff` errors
- ✅ No `Pending` pods

---

### Step 4: Verify Resource Optimization (10 minutes)

#### 4a. Check resource requests are applied
```bash
# Verify all deployments have resources defined
kubectl get deployments -n maliev -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.template.spec.containers[0].resources.requests.cpu}{"\t"}{.spec.template.spec.containers[0].resources.requests.memory}{"\n"}{end}' | column -t
```

**Expected**: All services show CPU and memory requests (e.g., `5m`, `96Mi`)

#### 4b. Check HPAs are active
```bash
# Verify HPAs are monitoring metrics
kubectl get hpa -n maliev
```

**Expected**:
```
NAME                          REFERENCE                              TARGETS         MINPODS   MAXPODS   REPLICAS
maliev-authservice-hpa        Deployment/maliev-authservice-api      1%/70%          1         3         1
maliev-web-hpa                Deployment/maliev-web                  2%/70%          2         4         2
...
```

#### 4c. Check pod distribution
```bash
# See which nodes pods are running on
kubectl get pods -n maliev -o wide | awk '{print $7}' | sort | uniq -c
```

**Expected**: Pods redistributing across fewer nodes

---

### Step 5: Configure Cluster Autoscaler (10 minutes)

**CRITICAL**: Cap autoscaler at 6 nodes maximum (matches N1 CUD commitment)

```bash
# Configure autoscaler for api-pool
gcloud container clusters update web-production-cluster \
  --region=us-central1 \
  --enable-autoscaling \
  --node-pool=api-pool \
  --min-nodes=2 \
  --max-nodes=3

# Configure autoscaler for web-pool
gcloud container clusters update web-production-cluster \
  --region=us-central1 \
  --enable-autoscaling \
  --node-pool=web-pool \
  --min-nodes=1 \
  --max-nodes=2

# Configure autoscaler for backend-pool
gcloud container clusters update web-production-cluster \
  --region=us-central1 \
  --enable-autoscaling \
  --node-pool=backend-pool \
  --min-nodes=1 \
  --max-nodes=1

# Set autoscaling profile to optimize-utilization
gcloud container clusters update web-production-cluster \
  --region=us-central1 \
  --autoscaling-profile=optimize-utilization
```

**Total maximum**: 3 + 2 + 1 = **6 nodes** ✅

---

### Step 6: Monitor Node Consolidation (24-48 hours)

```bash
# Watch node count decrease over time
watch kubectl get nodes

# Monitor cluster autoscaler decisions
kubectl logs -n kube-system -l component=cluster-autoscaler --tail=100 -f
```

**Expected timeline**:
- T+2 hours:  Cluster autoscaler starts evaluating scale-down
- T+12 hours: First nodes scale down (7-8 nodes remaining)
- T+24 hours: Stable at 4-6 nodes
- T+48 hours: Final stable state

**Target**: 4-6 nodes running, 0 on-demand charges

---

### Step 7: Commit deployment.yaml Changes (10 minutes)

```bash
# Navigate to maliev-web repository
cd R:/maliev-web

# Check git status
git status

# You should see ~22 modified deployment.yaml files

# Review changes
git diff Maliev.AuthService.Api/deployment.yaml

# Add all changes
git add */deployment.yaml

# Commit
git commit -m "Add resource limits and remove nodeSelector constraints

- Added CPU/Memory requests and limits to all microservices
- Standard services: 5m/50m CPU, 96Mi/256Mi Memory
- Web service: 10m/100m CPU, 192Mi/384Mi Memory
- Intranet: 10m/100m CPU, 256Mi/512Mi Memory
- Commented out nodeSelector to enable pod consolidation
- Target: Reduce from 9 to 6 nodes (save $73/month)

These changes align with kubectl patches already applied to live cluster.

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"

# Push to remote
git push
```

---

## 📊 VERIFICATION CHECKLIST

After 24 hours, verify the following:

### Resource Optimization
- [ ] All pods running without OOMKilled errors
  ```bash
  kubectl get events -n maliev | grep -i oomkilled
  # Expected: No results
  ```

- [ ] All pods have resource requests defined
  ```bash
  kubectl get pods -n maliev -o yaml | grep -A 5 "resources:"
  # Expected: All pods show requests and limits
  ```

### Autoscaling
- [ ] HPAs showing metrics
  ```bash
  kubectl get hpa -n maliev
  # Expected: All HPAs show CPU percentages (not <unknown>)
  ```

- [ ] Pods scaling based on load
  ```bash
  kubectl describe hpa maliev-authservice-hpa -n maliev
  # Expected: Shows scaling events if traffic increased
  ```

### Node Consolidation
- [ ] Node count reduced to 4-6
  ```bash
  kubectl get nodes | wc -l
  # Expected: 4-6 nodes
  ```

- [ ] No pending pods
  ```bash
  kubectl get pods -A | grep Pending
  # Expected: No results
  ```

- [ ] Healthy node resource utilization
  ```bash
  kubectl top nodes
  # Expected: CPU 60-80%, Memory 60-80%
  ```

### Cost Savings
- [ ] Zero on-demand node charges
  - Check GCP Billing Console
  - Compute Engine → VM Instances
  - Verify only 6 n1-standard-1 instances running
  - Verify all instances covered by CUD

---

## 🚨 ROLLBACK PROCEDURE

If critical issues occur:

### Rollback kubectl Patches
```bash
# Remove resource limits from all deployments
kubectl patch deployment maliev-authservice-api -n maliev --type='json' -p='[
  {"op": "remove", "path": "/spec/template/spec/containers/0/resources"}
]'

# Repeat for other services (or use script)

# Delete HPAs
kubectl delete hpa --all -n maliev

# Restore nodeSelector (if needed)
kubectl patch deployment maliev-authservice-api -n maliev --type='json' -p='[
  {
    "op": "add",
    "path": "/spec/template/spec/nodeSelector",
    "value": {"cloud.google.com/gke-nodepool": "api-pool"}
  }
]'
```

### Increase Autoscaler Limits Temporarily
```bash
# If pods pending due to insufficient resources
gcloud container clusters update web-production-cluster \
  --region=us-central1 \
  --node-pool=api-pool \
  --max-nodes=5
```

---

## 📈 SUCCESS METRICS

| Metric | Before | Target | Current |
|--------|--------|--------|---------|
| Nodes | 9 | 4-6 | _TBD_ |
| Monthly Cost | $219 | $146 | _TBD_ |
| On-Demand Cost | $73 | $0 | _TBD_ |
| Pods with Resources | 0/34 | 34/34 | _TBD_ |
| HPAs Configured | 0 | 5 | _TBD_ |
| OOMKilled Events | 0 | 0 | _TBD_ |

---

## 📞 SUPPORT

**Issues During Execution?**
- Check pod logs: `kubectl logs <pod-name> -n maliev`
- Check events: `kubectl get events -n maliev --sort-by='.lastTimestamp'`
- Review autoscaler logs: `kubectl logs -n kube-system -l component=cluster-autoscaler`

**Questions?**
- Refer to `usage-optimization.md` for detailed background
- Check GCP documentation: https://cloud.google.com/kubernetes-engine/docs

---

## ✅ NEXT STEPS AFTER STABILIZATION

1. **Week 2-4**: Monitor and fine-tune
   - Adjust resource requests based on actual usage
   - Optimize HPA scaling thresholds
   - Document final configuration

2. **Month 2**: Verify cost savings
   - Check GCP billing for actual savings
   - Confirm zero on-demand charges
   - Update budget forecasts

3. **2028**: Plan for CUD renewal
   - Evaluate E2 instance migration
   - Consider Flexible (spend-based) CUDs
   - Reassess workload requirements

---

**Created**: 2025-10-23
**Status**: Ready for Execution
**Next Action**: Run Step 2 (kubectl patches)
