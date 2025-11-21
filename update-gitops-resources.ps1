# Update resource-limits-patch.yaml in maliev-gitops for all services

# Define service tiers (optimized 2025-11-21)
$tier1Services = @(
    "maliev-auth-service",
    "maliev-country-service",
    "maliev-currency-service",
    "maliev-supplier-service",
    "maliev-email-service",
    "maliev-career-service",
    "maliev-contact-service"
)

$tier2Services = @(
    "maliev-customer-service",
    "maliev-invoice-service",
    "maliev-material-service",
    "maliev-order-service",
    "maliev-payment-service",
    "maliev-employee-service",
    "maliev-message-service",
    "maliev-orderstatus-service",
    "maliev-quotation-service",
    "maliev-quotationrequest-service",
    "maliev-purchaseorder-service",
    "maliev-receipt-service"
)

$tier3Services = @(
    "maliev-upload-service",
    "maliev-pdf-service",
    "maliev-prediction-service"
)

$tier4Services = @(
    "maliev-web",
    "maliev-intranet"
)

function Update-ResourceLimitsPatch {
    param(
        [string]$FilePath,
        [string]$Environment,
        [string]$CpuRequest,
        [string]$MemoryRequest,
        [string]$CpuLimit,
        [string]$MemoryLimit
    )

    if (Test-Path $FilePath) {
        $content = @"
apiVersion: apps/v1
kind: Deployment
metadata:
  name: placeholder
spec:
  template:
    spec:
      containers:
        - name: placeholder
          resources:
            requests:
              cpu: $CpuRequest
              memory: $MemoryRequest
            limits:
              cpu: $CpuLimit
              memory: $MemoryLimit
"@
        Set-Content -Path $FilePath -Value $content
        Write-Host "Updated: $FilePath"
    } else {
        Write-Host "Not found: $FilePath" -ForegroundColor Yellow
    }
}

function Get-ResourcesForEnvironment {
    param(
        [string]$Environment,
        [string]$Tier
    )

    # Optimized resource allocations based on actual usage analysis (2025-11-21)
    if ($Environment -eq "development") {
        switch ($Tier) {
            "1" { return @("5m", "64Mi", "15m", "96Mi") }
            "2" { return @("10m", "96Mi", "25m", "128Mi") }
            "3" { return @("15m", "128Mi", "35m", "192Mi") }
            "4" { return @("10m", "128Mi", "25m", "192Mi") }
        }
    } elseif ($Environment -eq "staging") {
        switch ($Tier) {
            "1" { return @("10m", "96Mi", "25m", "128Mi") }
            "2" { return @("15m", "128Mi", "40m", "192Mi") }
            "3" { return @("20m", "192Mi", "50m", "256Mi") }
            "4" { return @("15m", "192Mi", "40m", "256Mi") }
        }
    } else { # production
        switch ($Tier) {
            "1" { return @("10m", "96Mi", "25m", "128Mi") }
            "2" { return @("15m", "128Mi", "40m", "192Mi") }
            "3" { return @("20m", "192Mi", "50m", "256Mi") }
            "4" { return @("15m", "192Mi", "40m", "256Mi") }
        }
    }
}

$environments = @("development", "staging", "production")

foreach ($env in $environments) {
    Write-Host "`nUpdating $env environment..." -ForegroundColor Cyan

    # Tier 1
    foreach ($service in $tier1Services) {
        $filePath = "R:\maliev\maliev-gitops\3-apps\$service\overlays\$env\resource-limits-patch.yaml"
        $resources = Get-ResourcesForEnvironment -Environment $env -Tier "1"
        Update-ResourceLimitsPatch -FilePath $filePath -Environment $env `
            -CpuRequest $resources[0] -MemoryRequest $resources[1] `
            -CpuLimit $resources[2] -MemoryLimit $resources[3]
    }

    # Tier 2
    foreach ($service in $tier2Services) {
        $filePath = "R:\maliev\maliev-gitops\3-apps\$service\overlays\$env\resource-limits-patch.yaml"
        $resources = Get-ResourcesForEnvironment -Environment $env -Tier "2"
        Update-ResourceLimitsPatch -FilePath $filePath -Environment $env `
            -CpuRequest $resources[0] -MemoryRequest $resources[1] `
            -CpuLimit $resources[2] -MemoryLimit $resources[3]
    }

    # Tier 3
    foreach ($service in $tier3Services) {
        $filePath = "R:\maliev\maliev-gitops\3-apps\$service\overlays\$env\resource-limits-patch.yaml"
        $resources = Get-ResourcesForEnvironment -Environment $env -Tier "3"
        Update-ResourceLimitsPatch -FilePath $filePath -Environment $env `
            -CpuRequest $resources[0] -MemoryRequest $resources[1] `
            -CpuLimit $resources[2] -MemoryLimit $resources[3]
    }

    # Tier 4
    foreach ($service in $tier4Services) {
        $filePath = "R:\maliev\maliev-gitops\3-apps\$service\overlays\$env\resource-limits-patch.yaml"
        $resources = Get-ResourcesForEnvironment -Environment $env -Tier "4"
        Update-ResourceLimitsPatch -FilePath $filePath -Environment $env `
            -CpuRequest $resources[0] -MemoryRequest $resources[1] `
            -CpuLimit $resources[2] -MemoryLimit $resources[3]
    }
}

Write-Host "`nAll resource-limits-patch.yaml files have been updated!" -ForegroundColor Green
