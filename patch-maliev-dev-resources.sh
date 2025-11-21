#!/bin/bash

echo "=========================================="
echo "Patching maliev-dev namespace resources"
echo "=========================================="

# Development namespace - minimal resources
# Tier 1: Lightweight services
tier1_services=(
  "maliev-auth-service"
  "maliev-country-service"
  "maliev-currency-service"
  "maliev-employee-service"
  "maliev-supplier-service"
  "maliev-career-service"
  "maliev-contact-service"
)

# Tier 2: Medium services
tier2_services=(
  "maliev-customer-service"
  "maliev-invoice-service"
  "maliev-material-service"
  "maliev-order-service"
  "maliev-payment-service"
)

# Tier 3: Heavy services
tier3_services=(
  "maliev-upload-service"
  "maliev-purchaseorder-service"
)

# Patch function
patch_deployment() {
  local deployment=$1
  local cpu_request=$2
  local memory_request=$3
  local cpu_limit=$4
  local memory_limit=$5

  echo "Patching $deployment..."
  kubectl patch deployment "$deployment" -n maliev-dev --type='json' -p='[
    {
      "op": "add",
      "path": "/spec/template/spec/containers/0/resources",
      "value": {
        "requests": {
          "cpu": "'"$cpu_request"'",
          "memory": "'"$memory_request"'"
        },
        "limits": {
          "cpu": "'"$cpu_limit"'",
          "memory": "'"$memory_limit"'"
        }
      }
    }
  ]' 2>&1 | grep -E "patched|not found" || true
}

echo "Patching Tier 1 services (Lightweight)..."
for service in "${tier1_services[@]}"; do
  patch_deployment "$service" "25m" "64Mi" "100m" "128Mi"
done

echo ""
echo "Patching Tier 2 services (Medium)..."
for service in "${tier2_services[@]}"; do
  patch_deployment "$service" "50m" "96Mi" "150m" "192Mi"
done

echo ""
echo "Patching Tier 3 services (Heavy)..."
for service in "${tier3_services[@]}"; do
  patch_deployment "$service" "75m" "128Mi" "250m" "256Mi"
done

echo ""
echo "=========================================="
echo "Resource limits applied to maliev-dev!"
echo "=========================================="
echo ""
kubectl get deployments -n maliev-dev
