[CmdletBinding()]
param(
    [string]$RepositoryRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'

$expected = [ordered]@{
    auth = @{
        Repository = 'Legacy.Maliev.AuthService'
        Commit = 'abbe40e494ee77ba10c82331847073f97f2ab6e7'
    }
    employee = @{
        Repository = 'Legacy.Maliev.EmployeeService'
        Commit = 'f901f601f661d54d394d263191a9180d0c37182a'
    }
    intranet = @{
        Repository = 'Legacy.Maliev.Intranet'
        Commit = '9d23f25cc965d98876e20aabed480560d0b653a4'
    }
}

foreach ($entry in $expected.GetEnumerator()) {
    $name = $entry.Key
    $values = $entry.Value
    $kustomizationPath = Join-Path $RepositoryRoot "3-apps/_legacy-cutover/$name/kustomization.yaml"
    $applicationPath = Join-Path $RepositoryRoot "argocd/environments/_disabled_apps/legacy/legacy-maliev-$name.yaml"

    if (-not (Test-Path -LiteralPath $kustomizationPath -PathType Leaf)) {
        throw "Missing dormant Kustomize source: $kustomizationPath"
    }
    if (-not (Test-Path -LiteralPath $applicationPath -PathType Leaf)) {
        throw "Missing disabled ArgoCD application: $applicationPath"
    }

    $kustomization = Get-Content -LiteralPath $kustomizationPath -Raw
    if ($kustomization -notmatch [regex]::Escape($values.Repository)) {
        throw "$name does not reference $($values.Repository)."
    }
    if ($kustomization -notmatch [regex]::Escape($values.Commit)) {
        throw "$name is not pinned to $($values.Commit)."
    }

    $application = Get-Content -LiteralPath $applicationPath -Raw
    if ($application -notmatch 'namespace:\s+maliev-legacy') {
        throw "$name does not target maliev-legacy."
    }
    if ($application -match 'automated:|CreateNamespace=true|resources-finalizer') {
        throw "$name must remain disabled without automated sync, namespace creation, or a deletion finalizer."
    }
}

$activeFiles = @(
    Join-Path $RepositoryRoot 'argocd/kustomization.yaml'
    Get-ChildItem -LiteralPath (Join-Path $RepositoryRoot '2-environments') -Filter kustomization.yaml -Recurse |
        Select-Object -ExpandProperty FullName
)

foreach ($path in $activeFiles) {
    $source = Get-Content -LiteralPath $path -Raw
    if ($source -match '_legacy-cutover|legacy-maliev-(auth|employee|intranet)-service-cutover') {
        throw "Dormant legacy cutover wiring became active through $path."
    }
}

Write-Output 'Dormant legacy cutover pins and fail-closed activation boundary verified.'
