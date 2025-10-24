# Remove nodeSelector lines entirely from deployment.yaml files

$files = @(
    "R:\maliev-web\Maliev.CountryService.Api\deployment.yaml",
    "R:\maliev-web\Maliev.CurrencyService.Api\deployment.yaml",
    "R:\maliev-web\Maliev.CustomerService.Api\deployment.yaml",
    "R:\maliev-web\Maliev.EmailService.Api\deployment.yaml",
    "R:\maliev-web\Maliev.EmployeeService.Api\deployment.yaml",
    "R:\maliev-web\Maliev.InvoiceService.Api\deployment.yaml",
    "R:\maliev-web\Maliev.JobService.Api\deployment.yaml",
    "R:\maliev-web\Maliev.MaterialService.Api\deployment.yaml",
    "R:\maliev-web\Maliev.MessageService.Api\deployment.yaml",
    "R:\maliev-web\Maliev.OrderService.Api\deployment.yaml",
    "R:\maliev-web\Maliev.OrderStatusService.Api\deployment.yaml",
    "R:\maliev-web\Maliev.PaymentService.Api\deployment.yaml",
    "R:\maliev-web\Maliev.PdfService.Api\deployment.yaml",
    "R:\maliev-web\Maliev.PredictionService.Api\deployment.yaml",
    "R:\maliev-web\Maliev.PurchaseOrderService.Api\deployment.yaml",
    "R:\maliev-web\Maliev.QuotationRequestService.Api\deployment.yaml",
    "R:\maliev-web\Maliev.QuotationService.Api\deployment.yaml",
    "R:\maliev-web\Maliev.ReceiptService.Api\deployment.yaml",
    "R:\maliev-web\Maliev.SupplierService.Api\deployment.yaml",
    "R:\maliev-web\Maliev.UploadService.Api\deployment.yaml",
    "R:\maliev-web\Maliev.AuthService.Api\deployment.yaml",
    "R:\maliev-web\Maliev.Intranet\deployment.yaml",
    "R:\maliev-web\Maliev.Web\deployment.yaml"
)

foreach ($file in $files) {
    if (Test-Path $file) {
        Write-Host "Processing: $file"
        $lines = Get-Content $file

        # Filter out lines that are nodeSelector related
        $filteredLines = $lines | Where-Object {
            $_ -notmatch '^\s*#?\s*nodeSelector:' -and
            $_ -notmatch '^\s*#?\s*cloud\.google\.com/gke-nodepool:' -and
            $_ -notmatch '^\s+cloud\.google\.com/gke-nodepool:\s*(api-pool|web-pool|backend-pool)' -and
            $_ -notmatch '# nodeSelector removed to enable pod consolidation'
        }

        Set-Content -Path $file -Value $filteredLines
        Write-Host "  ✓ Removed nodeSelector lines"
    }
}

Write-Host "`nAll nodeSelector lines removed!"
