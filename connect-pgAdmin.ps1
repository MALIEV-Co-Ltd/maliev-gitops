# Define variables
$namespace = "maliev-dev"
$localPort = 5432
$remotePort = 5432
# IMPORTANT: Adjust this path if your pgAdmin installation is elsewhere
$pgAdminPath = "$env:LOCALAPPDATA\Programs\pgAdmin 4\runtime\pgAdmin4.exe"
Write-Host $pgAdminPath

Write-Host "Attempting to connect to PostgreSQL in namespace '$namespace'..."

# 1. Get the primary PostgreSQL pod name
Write-Host "Finding primary PostgreSQL pod..."
# CORRECTED LABEL SELECTOR: cnpg.io/instanceRole=primary
$podName = kubectl get pods -n $namespace -l "cnpg.io/instanceRole=primary" -o jsonpath='{.items[0].metadata.name}'

if (-not $podName) {
    Write-Error "Could not find the primary PostgreSQL pod in namespace '$namespace'. Please ensure the cluster is running and healthy."
    exit 1
}

Write-Host "Found primary pod: $podName"

# 2. Start kubectl port-forward in the background
Write-Host ("Starting port-forwarding (localhost:" + $localPort + " -> " + $podName + ":" + $remotePort + ")...")
$portMapping = "${localPort}:${remotePort}"

# Using Start-Job to run kubectl in the background, with explicit variable delimiting
$portForwardJob = Start-Job -ScriptBlock { kubectl port-forward -n "${using:namespace}" "${using:podName}" "${using:portMapping}" }

# Wait a few seconds for the port-forwarding to establish
Start-Sleep -Seconds 5

# Check if the port-forwarding job started successfully
if ($portForwardJob.State -eq "Failed") {
    Write-Error "Failed to start port-forwarding job. Check kubectl configuration and permissions."
    Receive-Job $portForwardJob # Display job output for debugging
    Remove-Job $portForwardJob
    exit 1
}

Write-Host "Port-forwarding initiated. Opening pgAdmin..."

# 3. Open pgAdmin
if (Test-Path $pgAdminPath) {
    Start-Process -FilePath $pgAdminPath
    Write-Host "pgAdmin opened successfully."
} else {
    Write-Error "pgAdmin executable not found at '$pgAdminPath'. Please adjust the '$pgAdminPath' variable in the script to your pgAdmin installation path."
    exit 1
}

Write-Host "Script finished."
Write-Host "--------------------------------------------------------------------------------"
Write-Host "IMPORTANT: The port-forwarding process is running in the background."
Write-Host "To stop it, you can close this PowerShell window, or run the following commands:"
Write-Host "  Get-Job | Where-Object { $_.Name -like 'Job*' } | Stop-Job -Force"
Write-Host "  Get-Job | Remove-Job"
Write-Host "--------------------------------------------------------------------------------"