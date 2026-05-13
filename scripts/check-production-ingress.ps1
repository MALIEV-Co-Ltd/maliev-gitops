param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$productionIngresses = @(
    "2-environments/0-live-production/ingress.yaml",
    "2-environments/3-production/ingress.yaml"
)

$productionKustomizeOverlays = @(
    "3-apps/maliev-quote-engine/overlays/production"
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

foreach ($relativePath in $productionKustomizeOverlays) {
    $path = Join-Path $Root $relativePath
    if (-not (Test-Path -LiteralPath $path)) {
        Write-Error "Missing production kustomize overlay: $relativePath"
        $failed = $true
        continue
    }

    $content = & kustomize build $path 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to build production kustomize overlay: $relativePath`n$content"
        $failed = $true
        continue
    }

    if (($content -join "`n") -match 'kubernetes\.io/ingress\.allow-http:\s*"true"') {
        Write-Error "Production kustomize overlay allows plaintext HTTP: $relativePath"
        $failed = $true
    }
}

if ($failed) {
    exit 1
}

Write-Host "Production ingress HTTP exposure check passed."
