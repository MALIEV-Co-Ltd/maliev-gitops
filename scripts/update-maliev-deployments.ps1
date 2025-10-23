#
# Bulk Update Maliev deployment.yaml Files
#
# This script adds resource requests/limits and comments out nodeSelector
# in all deployment.yaml files in the R:\maliev-web repository
#
# Usage: .\update-maliev-deployments.ps1
#

$ErrorActionPreference = "Stop"

# Base path to maliev-web repository
$MALIEV_WEB_ROOT = "R:\maliev-web"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Maliev deployment.yaml Bulk Update Script" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# Standard microservices with 5m/96Mi resources
$standardServices = @(
    "Maliev.CountryService.Api",
    "Maliev.CurrencyService.Api",
    "Maliev.CustomerService.Api",
    "Maliev.EmailService.Api",
    "Maliev.EmployeeService.Api",
    "Maliev.InvoiceService.Api",
    "Maliev.JobService.Api",
    "Maliev.MaterialService.Api",
    "Maliev.MessageService.Api",
    "Maliev.OrderService.Api",
    "Maliev.OrderStatusService.Api",
    "Maliev.PaymentService.Api",
    "Maliev.PdfService.Api",
    "Maliev.PredictionService.Api",
    "Maliev.PurchaseOrderService.Api",
    "Maliev.QuotationRequestService.Api",
    "Maliev.QuotationService.Api",
    "Maliev.ReceiptService.Api",
    "Maliev.SupplierService.Api",
    "Maliev.UploadService.Api"
)

# Function to update a deployment file
function Update-DeploymentFile {
    param(
        [string]$FilePath,
        [string]$CpuRequest,
        [string]$CpuLimit,
        [string]$MemRequest,
        [string]$MemLimit
    )

    if (-not (Test-Path $FilePath)) {
        Write-Host "  [SKIP] File not found: $FilePath" -ForegroundColor Yellow
        return
    }

    Write-Host "  Processing: $FilePath" -ForegroundColor Gray

    # Read file content
    $content = Get-Content $FilePath -Raw

    # Check if resources already exist
    if ($content -match "resources:") {
        Write-Host "  [SKIP] Resources already defined" -ForegroundColor Yellow
        return
    }

    # Define the resource block to add
    $resourceBlock = @"
        resources:
          requests:
            cpu: $CpuRequest
            memory: $MemRequest
          limits:
            cpu: $CpuLimit
            memory: $MemLimit
"@

    # Pattern to find: after readinessProbe, before terminationGracePeriodSeconds
    $pattern = "(\s+timeoutSeconds:\s+\d+\r?\n)(      terminationGracePeriodSeconds:)"

    if ($content -match $pattern) {
        $replacement = "`$1$resourceBlock`r`n`$2"
        $content = $content -replace $pattern, $replacement
        Write-Host "  [OK] Added resources block" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] Could not find insertion point for resources" -ForegroundColor Yellow
    }

    # Comment out nodeSelector
    $nodeSelectorPattern = "(\r?\n      )(nodeSelector:\r?\n\s+cloud\.google\.com/gke-nodepool: \w+-pool)"
    if ($content -match $nodeSelectorPattern) {
        $replacement = "`$1# nodeSelector removed to enable pod consolidation across all nodes`r`n`$1# `$2"
        $content = $content -replace $nodeSelectorPattern, $replacement
        $content = $content -replace "(\r?\n      # )(cloud\.google\.com)", "`$1#   `$2"
        Write-Host "  [OK] Commented out nodeSelector" -ForegroundColor Green
    } else {
        Write-Host "  [INFO] No nodeSelector found" -ForegroundColor Gray
    }

    # Write updated content back
    Set-Content -Path $FilePath -Value $content -NoNewline
    Write-Host "  [DONE] Updated successfully" -ForegroundColor Green
    Write-Host ""
}

Write-Host "Phase 1: Updating Standard Microservices (5m/50m CPU, 96Mi/256Mi Memory)" -ForegroundColor Cyan
Write-Host ""

foreach ($service in $standardServices) {
    $deploymentPath = Join-Path $MALIEV_WEB_ROOT "$service\deployment.yaml"
    Update-DeploymentFile -FilePath $deploymentPath -CpuRequest "5m" -CpuLimit "50m" -MemRequest "96Mi" -MemLimit "256Mi"
}

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Update Complete!" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Summary:" -ForegroundColor Yellow
Write-Host "  - Updated $($standardServices.Count) standard microservices"
Write-Host "  - Added resource requests and limits"
Write-Host "  - Commented out nodeSelector constraints"
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "  1. Review changes in R:\maliev-web"
Write-Host "  2. Commit changes to git repository"
Write-Host "  3. Execute kubectl patch script for immediate effect"
Write-Host ""
Write-Host "Note: These changes will take effect on next manual deployment" -ForegroundColor Cyan
Write-Host ""
