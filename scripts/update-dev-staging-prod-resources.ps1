# Update resource limits for development, staging, and production overlays

$services = @(
    "maliev-auth-service",
    "maliev-career-service",
    "maliev-contact-service",
    "maliev-country-service",
    "maliev-currency-service",
    "maliev-customer-service",
    "maliev-employee-service",
    "maliev-material-service",
    "maliev-order-service",
    "maliev-purchaseorder-service",
    "maliev-supplier-service",
    "maliev-upload-service",
    "maliev-chat-service"
)

$environments = @("development", "staging", "production")

# Minimal resources for dev/staging/prod (these are not production workloads)
$minimalResources = @"
apiVersion: apps/v1
kind: Deployment
metadata:
  name: SERVICE_NAME
spec:
  template:
    spec:
      containers:
        - name: SERVICE_NAME
          resources:
            requests:
              cpu: 5m
              memory: 64Mi
            limits:
              cpu: 50m
              memory: 128Mi
"@

foreach ($service in $services) {
    foreach ($env in $environments) {
        $path = "R:\maliev\maliev-gitops\3-apps\$service\overlays\$env\resource-limits-patch.yaml"

        if (Test-Path $path) {
            $content = $minimalResources -replace "SERVICE_NAME", $service
            Set-Content -Path $path -Value $content
            Write-Host "✓ Updated $service / $env"
        } else {
            Write-Host "⊘ Skipped $service / $env (file not found)"
        }
    }
}

Write-Host "`n✓ All resource limits updated to minimal (5m CPU, 64Mi RAM)!"
