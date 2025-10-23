#!/bin/bash
#
# Create HorizontalPodAutoscalers for Maliev Namespace
#
# This script creates HPAs for high-traffic services to enable dynamic scaling
# while respecting the 6-node maximum (N1 CUD commitment)
#
# Usage: ./create-hpas.sh
#

set -e

NAMESPACE="maliev"

echo "========================================="
echo "Maliev HPA Creation Script"
echo "========================================="
echo ""
echo "Namespace: $NAMESPACE"
echo "Date: $(date)"
echo ""

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "Creating HorizontalPodAutoscalers for high-traffic services..."
echo ""

# Auth Service (currently 2 replicas)
echo -e "${YELLOW}Creating HPA: maliev-authservice-hpa${NC}"
kubectl autoscale deployment maliev-authservice-api -n "$NAMESPACE" \
  --min=1 --max=3 --cpu-percent=70 \
  --name=maliev-authservice-hpa 2>/dev/null && \
  echo -e "${GREEN}✓ Created maliev-authservice-hpa${NC}" || \
  echo -e "${YELLOW}⚠ HPA already exists or failed to create${NC}"
echo ""

# Web Service (currently 3 replicas)
echo -e "${YELLOW}Creating HPA: maliev-web-hpa${NC}"
kubectl autoscale deployment maliev-web -n "$NAMESPACE" \
  --min=2 --max=4 --cpu-percent=70 \
  --name=maliev-web-hpa 2>/dev/null && \
  echo -e "${GREEN}✓ Created maliev-web-hpa${NC}" || \
  echo -e "${YELLOW}⚠ HPA already exists or failed to create${NC}"
echo ""

# Prediction Service (currently 2 replicas)
echo -e "${YELLOW}Creating HPA: maliev-predictionservice-hpa${NC}"
kubectl autoscale deployment maliev-predictionservice-api -n "$NAMESPACE" \
  --min=1 --max=3 --cpu-percent=70 \
  --name=maliev-predictionservice-hpa 2>/dev/null && \
  echo -e "${GREEN}✓ Created maliev-predictionservice-hpa${NC}" || \
  echo -e "${YELLOW}⚠ HPA already exists or failed to create${NC}"
echo ""

# Customer Service (critical service)
echo -e "${YELLOW}Creating HPA: maliev-customerservice-hpa${NC}"
kubectl autoscale deployment maliev-customerservice-api -n "$NAMESPACE" \
  --min=1 --max=2 --cpu-percent=70 \
  --name=maliev-customerservice-hpa 2>/dev/null && \
  echo -e "${GREEN}✓ Created maliev-customerservice-hpa${NC}" || \
  echo -e "${YELLOW}⚠ HPA already exists or failed to create${NC}"
echo ""

# Payment Service (critical service)
echo -e "${YELLOW}Creating HPA: maliev-paymentservice-hpa${NC}"
kubectl autoscale deployment maliev-paymentservice-api -n "$NAMESPACE" \
  --min=1 --max=2 --cpu-percent=70 \
  --name=maliev-paymentservice-hpa 2>/dev/null && \
  echo -e "${GREEN}✓ Created maliev-paymentservice-hpa${NC}" || \
  echo -e "${YELLOW}⚠ HPA already exists or failed to create${NC}"
echo ""

echo "========================================="
echo "Verification"
echo "========================================="
echo ""

echo "Current HPAs:"
kubectl get hpa -n "$NAMESPACE"

echo ""
echo "========================================="
echo "✓ HPA creation complete!"
echo "========================================="
echo ""
echo "Monitor autoscaling:"
echo "  kubectl get hpa -n maliev --watch"
echo "  kubectl describe hpa <hpa-name> -n maliev"
echo ""
echo "Note: It may take a few minutes for HPAs to show metrics"
echo ""
