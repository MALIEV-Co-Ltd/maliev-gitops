param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$productionIngresses = @(
    "2-environments/0-live-production/ingress.yaml",
    "2-environments/3-production/ingress.yaml"
)

$failed = $false

foreach ($relativePath in $productionIngresses) {
    $path = Join-Path $Root $relativePath
    if (-not (Test-Path -LiteralPath $path)) {
        Write-Error "Missing production ingress: $relativePath"
        $failed = $true
        continue
    }

    $content = Get-Content -LiteralPath $path -Raw
    if ($content -match 'kubernetes\.io/ingress\.allow-http:\s*"true"') {
        Write-Error "Production ingress allows plaintext HTTP: $relativePath"
        $failed = $true
    }
}

if ($failed) {
    exit 1
}

Write-Host "Production ingress HTTP exposure check passed."
