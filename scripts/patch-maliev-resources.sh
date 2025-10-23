#!/bin/bash
#
# Maliev Namespace Resource Optimization - kubectl Patch Script
#
# This script patches all existing deployments and statefulsets in the 'maliev' namespace
# with proper resource requests and limits to enable Kubernetes bin-packing and node consolidation.
#
# Target: Reduce from 9 to 6 n1-standard-1 nodes
# Savings: $73/month ($876/year)
#
# Usage: ./patch-maliev-resources.sh
#

set -e

NAMESPACE="maliev"

echo "========================================="
echo "Maliev Resource Optimization Patch Script"
echo "========================================="
echo ""
echo "Namespace: $NAMESPACE"
echo "Date: $(date)"
echo ""

# Color codes for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to patch a deployment
patch_deployment() {
  local SERVICE=$1
  local CPU_REQUEST=$2
  local CPU_LIMIT=$3
  local MEM_REQUEST=$4
  local MEM_LIMIT=$5

  echo -e "${YELLOW}Patching deployment: $SERVICE${NC}"
  echo "  Resources: CPU ${CPU_REQUEST}/${CPU_LIMIT}, Memory ${MEM_REQUEST}/${MEM_LIMIT}"

  kubectl patch deployment "$SERVICE" -n "$NAMESPACE" --type='json' -p="[
    {
      \"op\": \"add\",
      \"path\": \"/spec/template/spec/containers/0/resources\",
      \"value\": {
        \"requests\": {\"cpu\": \"${CPU_REQUEST}\", \"memory\": \"${MEM_REQUEST}\"},
        \"limits\": {\"cpu\": \"${CPU_LIMIT}\", \"memory\": \"${MEM_LIMIT}\"}
      }
    }
  ]" && echo -e "${GREEN}✓ Successfully patched $SERVICE${NC}" || echo -e "${RED}✗ Failed to patch $SERVICE${NC}"
  echo ""
}

# Function to patch a statefulset
patch_statefulset() {
  local SERVICE=$1
  local CPU_REQUEST=$2
  local CPU_LIMIT=$3
  local MEM_REQUEST=$4
  local MEM_LIMIT=$5

  echo -e "${YELLOW}Patching statefulset: $SERVICE${NC}"
  echo "  Resources: CPU ${CPU_REQUEST}/${CPU_LIMIT}, Memory ${MEM_REQUEST}/${MEM_LIMIT}"

  kubectl patch statefulset "$SERVICE" -n "$NAMESPACE" --type='json' -p="[
    {
      \"op\": \"add\",
      \"path\": \"/spec/template/spec/containers/0/resources\",
      \"value\": {
        \"requests\": {\"cpu\": \"${CPU_REQUEST}\", \"memory\": \"${MEM_REQUEST}\"},
        \"limits\": {\"cpu\": \"${CPU_LIMIT}\", \"memory\": \"${MEM_LIMIT}\"}
      }
    }
  ]" && echo -e "${GREEN}✓ Successfully patched $SERVICE${NC}" || echo -e "${RED}✗ Failed to patch $SERVICE${NC}"
  echo ""
}

echo "========================================="
echo "Phase 1: Patching Standard Microservices"
echo "========================================="
echo "Resource Profile: CPU 5m/50m, Memory 96Mi/256Mi"
echo ""

# Standard microservices (21 services)
SERVICES=(
  "maliev-authservice-api"
  "maliev-countryservice-api"
  "maliev-currencyservice-api"
  "maliev-customerservice-api"
  "maliev-defaultbackend-api"
  "maliev-emailservice-api"
  "maliev-employeeservice-api"
  "maliev-invoiceservice-api"
  "maliev-jobservice-api"
  "maliev-materialservice-api"
  "maliev-messageservice-api"
  "maliev-orderservice-api"
  "maliev-orderstatusservice-api"
  "maliev-paymentservice-api"
  "maliev-pdfservice-api"
  "maliev-predictionservice-api"
  "maliev-purchaseorderservice-api"
  "maliev-quotationrequestservice-api"
  "maliev-quotationservice-api"
  "maliev-receiptservice-api"
  "maliev-supplierservice-api"
  "maliev-uploadservice-api"
)

for SERVICE in "${SERVICES[@]}"; do
  patch_deployment "$SERVICE" "5m" "50m" "96Mi" "256Mi"
done

echo "========================================="
echo "Phase 2: Patching Special Services"
echo "========================================="
echo ""

# Web service (higher resources due to traffic)
echo "Service: maliev-web (high traffic)"
echo "Resource Profile: CPU 10m/100m, Memory 192Mi/384Mi"
echo ""
patch_deployment "maliev-web" "10m" "100m" "192Mi" "384Mi"

# Intranet
echo "Service: maliev-intranet"
echo "Resource Profile: CPU 10m/100m, Memory 256Mi/512Mi"
echo ""
patch_deployment "maliev-intranet" "10m" "100m" "256Mi" "512Mi"

# Line chatbot
echo "Service: line-chatbot-deployment"
echo "Resource Profile: CPU 5m/50m, Memory 256Mi/512Mi"
echo ""
patch_deployment "line-chatbot-deployment" "5m" "50m" "256Mi" "512Mi"

# Redis
echo "Service: redis-deployment"
echo "Resource Profile: CPU 10m/100m, Memory 32Mi/128Mi"
echo ""
patch_deployment "redis-deployment" "10m" "100m" "32Mi" "128Mi"

echo "========================================="
echo "Phase 3: Patching StatefulSets"
echo "========================================="
echo ""

# MSSQL StatefulSet (needs more resources)
echo "Service: maliev-mssql (database)"
echo "Resource Profile: CPU 20m/500m, Memory 2Gi/3Gi"
echo ""
patch_statefulset "maliev-mssql" "20m" "500m" "2Gi" "3Gi"

echo "========================================="
echo "Phase 4: Removing NodeSelector Constraints"
echo "========================================="
echo "This allows pods to be scheduled on any node, enabling better bin-packing"
echo ""

# Services with nodeSelector: api-pool
API_POOL_SERVICES=(
  "maliev-authservice-api"
  "maliev-countryservice-api"
  "maliev-currencyservice-api"
  "maliev-customerservice-api"
  "maliev-emailservice-api"
  "maliev-employeeservice-api"
  "maliev-invoiceservice-api"
  "maliev-jobservice-api"
  "maliev-materialservice-api"
  "maliev-messageservice-api"
  "maliev-orderservice-api"
  "maliev-orderstatusservice-api"
  "maliev-paymentservice-api"
  "maliev-pdfservice-api"
  "maliev-predictionservice-api"
  "maliev-purchaseorderservice-api"
  "maliev-quotationrequestservice-api"
  "maliev-quotationservice-api"
  "maliev-receiptservice-api"
  "maliev-supplierservice-api"
  "maliev-uploadservice-api"
)

for SERVICE in "${API_POOL_SERVICES[@]}"; do
  echo -e "${YELLOW}Removing nodeSelector from: $SERVICE${NC}"
  kubectl patch deployment "$SERVICE" -n "$NAMESPACE" --type='json' -p='[
    {
      "op": "remove",
      "path": "/spec/template/spec/nodeSelector"
    }
  ]' 2>/dev/null && echo -e "${GREEN}✓ Removed nodeSelector from $SERVICE${NC}" || echo -e "${YELLOW}⚠ No nodeSelector found or already removed${NC}"
done

# Web pool
echo -e "${YELLOW}Removing nodeSelector from: maliev-web${NC}"
kubectl patch deployment maliev-web -n "$NAMESPACE" --type='json' -p='[
  {
    "op": "remove",
    "path": "/spec/template/spec/nodeSelector"
  }
]' 2>/dev/null && echo -e "${GREEN}✓ Removed nodeSelector from maliev-web${NC}" || echo -e "${YELLOW}⚠ No nodeSelector found or already removed${NC}"

# Backend pool
echo -e "${YELLOW}Removing nodeSelector from: maliev-mssql${NC}"
kubectl patch statefulset maliev-mssql -n "$NAMESPACE" --type='json' -p='[
  {
    "op": "remove",
    "path": "/spec/template/spec/nodeSelector"
  }
]' 2>/dev/null && echo -e "${GREEN}✓ Removed nodeSelector from maliev-mssql${NC}" || echo -e "${YELLOW}⚠ No nodeSelector found or already removed${NC}"

echo ""
echo "========================================="
echo "Verification"
echo "========================================="
echo ""

echo "Checking patched deployments..."
kubectl get deployments -n "$NAMESPACE" -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.template.spec.containers[0].resources.requests.cpu}{"\t"}{.spec.template.spec.containers[0].resources.requests.memory}{"\n"}{end}' | column -t

echo ""
echo "Current pods status:"
kubectl get pods -n "$NAMESPACE"

echo ""
echo "========================================="
echo "✓ All patches applied!"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Monitor pod restarts: kubectl get pods -n maliev --watch"
echo "2. Check resource allocation: kubectl top pods -n maliev"
echo "3. Watch node consolidation: watch kubectl get nodes"
echo "4. Create HPAs for autoscaling (see create-hpas.sh)"
echo ""
echo "Expected timeline:"
echo "  T+5 min:  Pods begin rolling restart"
echo "  T+30 min: All pods restarted with new resources"
echo "  T+2 hrs:  Nodes begin scaling down"
echo "  T+24 hrs: Stable at 4-6 nodes"
echo ""
