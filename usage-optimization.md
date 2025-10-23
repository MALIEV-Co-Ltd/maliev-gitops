# Maliev Production Namespace - Resource Optimization Plan

**Goal**: Reduce from 9 to 6 n1-standard-1 nodes by optimizing resource usage to fit within existing N1 Committed Use Discount (CUD).

**Target Savings**: $73/month ($876/year) by eliminating 3 on-demand nodes

**Timeline**: 4 weeks

**CUD Constraint**: 6 vCPU cores + 22.5GB memory (N1 General-Purpose, expires 2028)

---

## 📊 Current State Snapshot

- **Nodes**: 9× n1-standard-1 (6 CUD + 3 on-demand)
- **Pods**: 34 in maliev namespace
- **Resource Config**: `resources: {}` (NO limits or requests!)
- **Monthly Cost**: $219 ($146 CUD + $73 on-demand)
- **Node Pools**: 3 separate pools (api, web, backend)

---

## Phase 1: Resource Right-Sizing (Week 1)

### 🎯 Goal: Add resource requests/limits to enable proper pod bin-packing

#### Task 1.1: Add Resource Limits to Microservices
- [ ] Create resource-limits patch for all 26 services
  - CPU request: 5m, limit: 50m
  - Memory request: 96Mi, limit: 256Mi

**Services to update**:
- [ ] maliev-authservice-api
- [ ] maliev-countryservice-api
- [ ] maliev-currencyservice-api
- [ ] maliev-customerservice-api
- [ ] maliev-defaultbackend-api
- [ ] maliev-emailservice-api
- [ ] maliev-employeeservice-api
- [ ] maliev-invoiceservice-api
- [ ] maliev-jobservice-api
- [ ] maliev-materialservice-api
- [ ] maliev-messageservice-api
- [ ] maliev-orderservice-api
- [ ] maliev-orderstatusservice-api
- [ ] maliev-paymentservice-api
- [ ] maliev-pdfservice-api
- [ ] maliev-purchaseorderservice-api
- [ ] maliev-quotationrequestservice-api
- [ ] maliev-quotationservice-api
- [ ] maliev-receiptservice-api
- [ ] maliev-supplierservice-api
- [ ] maliev-uploadservice-api
- [ ] line-chatbot-deployment (CPU: 5m/50m, Mem: 256Mi/512Mi)
- [ ] redis-deployment (CPU: 10m/100m, Mem: 32Mi/128Mi)
- [ ] maliev-intranet (CPU: 10m/100m, Mem: 256Mi/512Mi)

#### Task 1.2: Add Resource Limits to Web Service
- [ ] maliev-web (currently 3 replicas)
  - CPU request: 10m, limit: 100m
  - Memory request: 192Mi, limit: 384Mi

#### Task 1.3: Add Resource Limits to Prediction Service
- [ ] maliev-predictionservice-api (currently 2 replicas)
  - CPU request: 5m, limit: 50m
  - Memory request: 128Mi, limit: 256Mi

#### Task 1.4: Add Resource Limits to MSSQL StatefulSet
- [ ] maliev-mssql (critical, needs more resources)
  - CPU request: 20m, limit: 500m
  - Memory request: 2Gi, limit: 3Gi

#### Task 1.5: Deploy and Monitor
- [ ] Apply resource limit changes via kubectl or GitOps
- [ ] Monitor pod restarts for OOMKilled errors
- [ ] Check node consolidation progress
  ```bash
  kubectl get nodes
  kubectl top nodes
  kubectl top pods -n maliev
  ```

**Success Criteria**:
- ✅ All pods running without OOMKilled errors
- ✅ Pods redistributing across nodes
- ✅ Node count starts reducing (expect 7-8 nodes)

**Rollback**: Remove resource limits if widespread OOMKilled

---

## Phase 2: Autoscaling Configuration (Week 2)

### 🎯 Goal: Enable dynamic scaling with hard cap at 6 nodes

#### Task 2.1: Create HorizontalPodAutoscalers (HPAs)

- [ ] **maliev-authservice-api** HPA
  ```yaml
  apiVersion: autoscaling/v2
  kind: HorizontalPodAutoscaler
  metadata:
    name: maliev-authservice-hpa
    namespace: maliev
  spec:
    scaleTargetRef:
      apiVersion: apps/v1
      kind: Deployment
      name: maliev-authservice-api
    minReplicas: 1
    maxReplicas: 3
    metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
  ```

- [ ] **maliev-web** HPA
  ```yaml
  minReplicas: 2
  maxReplicas: 4
  targetCPUUtilizationPercentage: 70
  ```

- [ ] **maliev-predictionservice-api** HPA
  ```yaml
  minReplicas: 1
  maxReplicas: 3
  targetCPUUtilizationPercentage: 70
  ```

- [ ] Apply HPAs and verify autoscaling works
  ```bash
  kubectl get hpa -n maliev
  kubectl describe hpa maliev-authservice-hpa -n maliev
  ```

#### Task 2.2: Create PodDisruptionBudgets (PDBs)

- [ ] Create PDB for auth service
  ```yaml
  apiVersion: policy/v1
  kind: PodDisruptionBudget
  metadata:
    name: maliev-authservice-pdb
    namespace: maliev
  spec:
    minAvailable: 1
    selector:
      matchLabels:
        app: maliev-authservice-api
  ```

- [ ] Create PDBs for other critical services (web, payment, customer)
- [ ] Verify PDBs are active
  ```bash
  kubectl get pdb -n maliev
  ```

**Success Criteria**:
- ✅ HPAs showing current/target metrics
- ✅ Pods scaling based on CPU usage
- ✅ PDBs preventing complete service outages during node drain

---

## Phase 3: Node Pool Consolidation (Week 3)

### 🎯 Goal: Consolidate to single N1 pool capped at 6 nodes

#### Task 3.1: Remove NodeSelector Constraints

Currently, pods are forced to specific pools:
```yaml
nodeSelector:
  cloud.google.com/gke-nodepool: api-pool  # Forces api-pool only
```

- [ ] **Option A**: Remove nodeSelector entirely (recommended)
  - Edit all deployments/statefulsets to remove nodeSelector
  - Allow scheduler to bin-pack optimally

- [ ] **Option B**: Replace with soft affinity (if separation needed)
  ```yaml
  affinity:
    nodeAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        preference:
          matchExpressions:
          - key: cloud.google.com/gke-nodepool
            operator: In
            values: [api-pool]
  ```

- [ ] Apply changes to all deployments
- [ ] Monitor pod rescheduling across nodes

#### Task 3.2: Configure GKE Cluster Autoscaler

**CRITICAL**: Set maximum to 6 nodes to match CUD commitment

For each node pool:
```bash
gcloud container clusters update web-production-cluster \
  --region=us-central1 \
  --enable-autoscaling \
  --node-pool=api-pool \
  --min-nodes=2 \
  --max-nodes=3

gcloud container clusters update web-production-cluster \
  --region=us-central1 \
  --enable-autoscaling \
  --node-pool=web-pool \
  --min-nodes=1 \
  --max-nodes=2

gcloud container clusters update web-production-cluster \
  --region=us-central1 \
  --enable-autoscaling \
  --node-pool=backend-pool \
  --min-nodes=1 \
  --max-nodes=1
```

Total max: 3 + 2 + 1 = **6 nodes** (matches CUD!)

- [ ] Enable autoscaling on api-pool (min: 2, max: 3)
- [ ] Enable autoscaling on web-pool (min: 1, max: 2)
- [ ] Enable autoscaling on backend-pool (min: 1, max: 1)
- [ ] Configure autoscaler profile for aggressive scale-down
  ```bash
  gcloud container clusters update web-production-cluster \
    --region=us-central1 \
    --autoscaling-profile=optimize-utilization
  ```

- [ ] Set scale-down delays
  ```bash
  gcloud container clusters update web-production-cluster \
    --region=us-central1 \
    --autoscaling-profile=optimize-utilization
  ```

#### Task 3.3: Monitor Node Consolidation

- [ ] Watch node count reduce over 24-48 hours
  ```bash
  watch kubectl get nodes
  ```

- [ ] Verify pods not pending due to insufficient resources
  ```bash
  kubectl get pods -A | grep Pending
  kubectl get events -A --sort-by='.lastTimestamp' | grep -i "insufficient\|failedscheduling"
  ```

- [ ] Check node utilization stays healthy (60-80%)
  ```bash
  kubectl top nodes
  ```

**Success Criteria**:
- ✅ Stable at 6 nodes or fewer
- ✅ No pending pods
- ✅ Node CPU: 60-80%, Memory: 60-80%
- ✅ Zero on-demand node charges

**Rollback**: Temporarily increase max-nodes if pods pending

---

## Phase 4: Monitoring & Fine-Tuning (Week 4)

### 🎯 Goal: Verify stability and optimize resource usage

#### Task 4.1: Monitor for 7 Days

- [ ] **Day 1-3**: Watch for OOMKilled or CrashLoopBackOff
  ```bash
  kubectl get pods -n maliev --watch
  kubectl get events -n maliev --sort-by='.lastTimestamp' | grep -i "oomkilled\|killed"
  ```

- [ ] **Day 4-7**: Monitor resource utilization patterns
  ```bash
  # Check actual vs requested resources
  kubectl top pods -n maliev --containers

  # Check node pressure
  kubectl describe nodes | grep -A 5 "Allocated resources"
  ```

- [ ] Create monitoring dashboard (optional)
  - GKE Workloads → maliev namespace
  - Track: CPU utilization, Memory utilization, Pod restarts
  - Alert on: OOMKilled, Pending pods, Node count > 6

#### Task 4.2: Adjust Resource Requests Based on Actuals

Review actual usage and adjust if needed:

- [ ] If services consistently use <50% of requests → reduce requests
- [ ] If services hit limits frequently → increase limits
- [ ] Document right-sized values for future reference

Example adjustment:
```yaml
# If actual usage shows 2m CPU / 80Mi memory:
resources:
  requests:
    cpu: 3m      # Was: 5m
    memory: 96Mi # Keep same
  limits:
    cpu: 30m     # Was: 50m
    memory: 256Mi # Keep same
```

#### Task 4.3: Verify Cost Savings

- [ ] Check GCP billing for current month
  ```bash
  gcloud billing accounts list
  gcloud billing projects describe maliev-website
  ```

- [ ] Verify Compute Engine charges:
  - Committed Use: $146/month (baseline)
  - On-demand: **$0/month** (target achieved!)

- [ ] Document savings: $73/month = $876/year ✅

**Success Criteria**:
- ✅ 7 days with no OOMKilled errors
- ✅ Node count stable at 4-6 nodes
- ✅ Zero on-demand node charges
- ✅ All services responding normally

---

## Alternative Optimization (Optional)

### Option: Consolidate to Single Node Pool

Instead of 3 pools, create 1 unified N1 pool:

#### Benefits:
- Better bin-packing efficiency
- Simpler autoscaling configuration
- More flexible pod placement

#### Steps:
- [ ] Create new unified node pool
  ```bash
  gcloud container node-pools create general-pool \
    --cluster=web-production-cluster \
    --region=us-central1 \
    --machine-type=n1-standard-1 \
    --num-nodes=4 \
    --enable-autoscaling \
    --min-nodes=4 \
    --max-nodes=6
  ```

- [ ] Gradually migrate workloads (cordon old pools)
  ```bash
  kubectl cordon <node-name>
  kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data
  ```

- [ ] Delete old node pools after migration
  ```bash
  gcloud container node-pools delete api-pool --cluster=web-production-cluster --region=us-central1
  gcloud container node-pools delete web-pool --cluster=web-production-cluster --region=us-central1
  gcloud container node-pools delete backend-pool --cluster=web-production-cluster --region=us-central1
  ```

**Risk**: Medium (requires careful migration)

---

## 🚨 Rollback Procedures

### If pods fail to schedule:
```bash
# Temporarily increase max nodes
gcloud container clusters update web-production-cluster \
  --region=us-central1 \
  --node-pool=api-pool \
  --max-nodes=5
```

### If services experience OOMKilled:
```bash
# Increase memory limits for affected service
kubectl edit deployment maliev-<service>-api -n maliev
# Update memory limit: 256Mi → 512Mi
```

### If autoscaler too aggressive:
```bash
# Change to balanced profile
gcloud container clusters update web-production-cluster \
  --region=us-central1 \
  --autoscaling-profile=balanced
```

---

## 📈 Success Metrics

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| Node Count | 9 | 4-6 | ⏳ |
| On-Demand Nodes | 3 | 0 | ⏳ |
| Monthly Cost | $219 | $146 | ⏳ |
| Pod Restarts/day | TBD | <5 | ⏳ |
| OOMKilled Events | TBD | 0 | ⏳ |
| Pending Pods | 0 | 0 | ✅ |

---

## 📝 Notes & Observations

### Week 1:
- [ ] Record baseline metrics (node count, cost, pod distribution)
- [ ] Note any services that struggle with new limits
- [ ] Document actual vs requested resource ratios

### Week 2:
- [ ] Track HPA scaling events
- [ ] Note peak traffic times for replica scaling
- [ ] Document any PDB-blocked operations

### Week 3:
- [ ] Track node count over time
- [ ] Record autoscaler scale-down events
- [ ] Note final stable node count

### Week 4:
- [ ] Calculate actual cost savings
- [ ] Document final resource configurations
- [ ] Plan for 2028 CUD renewal (consider E2 or Flex CUD)

---

## 🎯 Final Checklist

- [ ] All 34 deployments/statefulsets have resource requests
- [ ] HPAs configured for high-traffic services (3+)
- [ ] PDBs configured for critical services (3+)
- [ ] Cluster autoscaler capped at 6 nodes maximum
- [ ] NodeSelector constraints removed or relaxed
- [ ] 7 days stable operation with 4-6 nodes
- [ ] Zero on-demand node charges verified in billing
- [ ] Resource usage documented for future reference

**Optimization Complete!** 🎉

**Cost Savings Achieved**: $73/month = $876/year

**Next Review**: 2028 when CUD expires (consider E2 migration)

---

## 📞 Support & Resources

- **GKE Documentation**: https://cloud.google.com/kubernetes-engine/docs
- **Resource Requests**: https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/
- **HPA Guide**: https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/
- **GKE Cluster Autoscaler**: https://cloud.google.com/kubernetes-engine/docs/concepts/cluster-autoscaler

**Questions?** Contact your GCP account manager or file support ticket.
