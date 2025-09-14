#!/usr/bin/env pwsh

<#
.SYNOPSIS
    Opens Grafana dashboard in browser with port forwarding

.DESCRIPTION
    This script automatically sets up port forwarding to the Grafana service
    in the monitoring namespace and opens the dashboard in your default browser.

    The script will:
    1. Check if kubectl is available
    2. Start port forwarding to Grafana (localhost:3000 -> grafana:80)
    3. Start port forwarding to Prometheus (localhost:9090 -> prometheus:9090)
    4. Display login credentials
    5. Open Grafana in browser
    6. Keep port forwarding active until user presses Ctrl+C

.PARAMETER Environment
    The environment to connect to (dev, staging, prod). Default is 'dev'.

.PARAMETER GrafanaPort
    Local port for Grafana. Default is 3000.

.PARAMETER PrometheusPort
    Local port for Prometheus. Default is 9090.

.PARAMETER SkipBrowser
    Don't automatically open browser.

.EXAMPLE
    .\open-grafana.ps1
    Opens Grafana for development environment

.EXAMPLE
    .\open-grafana.ps1 -Environment staging -GrafanaPort 3001
    Opens Grafana for staging environment on port 3001
#>

param(
    [Parameter()]
    [ValidateSet("dev", "staging", "prod")]
    [string]$Environment = "dev",

    [Parameter()]
    [int]$GrafanaPort = 3000,

    [Parameter()]
    [int]$PrometheusPort = 9090,

    [Parameter()]
    [switch]$SkipBrowser,
	
	[Parameter()]
	[string]$GrafanaUser = "admin",
	
	[Parameter()]
    [string]$GrafanaPassword
)

# Set error action preference
$ErrorActionPreference = "Stop"

function Write-ColoredOutput {
    param(
        [string]$Message,
        [ConsoleColor]$Color = 'White'
    )
    $oldColor = $Host.UI.RawUI.ForegroundColor
    $Host.UI.RawUI.ForegroundColor = $Color
    Write-Host $Message
    $Host.UI.RawUI.ForegroundColor = $oldColor
}

function Test-Prerequisites {
    Write-ColoredOutput "Checking prerequisites..." Blue

    # Check if kubectl is available
    try {
        $kubectlVersion = & kubectl version --client 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-ColoredOutput "kubectl is available" Green
        } else {
            throw "kubectl command failed"
        }
    }
    catch {
        Write-ColoredOutput "kubectl is not available. Please install kubectl first." Red
        exit 1
    }

    # Check if we can connect to cluster
    try {
        $clusterInfo = & kubectl cluster-info --request-timeout=5s 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-ColoredOutput "Connected to Kubernetes cluster" Green
        } else {
            throw "Cannot connect to cluster"
        }
    }
    catch {
        Write-ColoredOutput "Cannot connect to Kubernetes cluster. Please check your kubeconfig." Red
        exit 1
    }

    # Check if monitoring namespace exists
    try {
        $monitoringExists = & kubectl get namespace monitoring --no-headers --ignore-not-found 2>&1
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($monitoringExists)) {
            Write-ColoredOutput "Monitoring namespace not found. Please deploy Prometheus-Grafana first." Red
            exit 1
        }
        Write-ColoredOutput "Monitoring namespace exists" Green
    }
    catch {
        Write-ColoredOutput "Error checking monitoring namespace: $_" Red
        exit 1
    }
}

function Get-GrafanaCredentials {
    if ($GrafanaUser -and $GrafanaPassword) {
        return @{
            Username = $GrafanaUser
            Password = $GrafanaPassword
        }
    }

    # fallback to secret lookup if user did not provide
    try {
        $usernameBase64 = & kubectl get secret -n monitoring prometheus-grafana -o jsonpath="{.data.admin-user}" 2>&1
        $passwordBase64 = & kubectl get secret -n monitoring prometheus-grafana -o jsonpath="{.data.admin-password}" 2>&1
        $username = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($usernameBase64))
        $password = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($passwordBase64))
        return @{ Username = $username; Password = $password }
    }
    catch {
        throw "No Grafana credentials supplied and none could be retrieved."
    }
}

function Start-PortForwarding {
    param(
        [string]$ServiceName,
        [string]$Namespace,
        [int]$LocalPort,
        [int]$ServicePort,
        [string]$DisplayName
    )

    Write-ColoredOutput "Starting port forwarding for ${DisplayName}..." Blue

    # Check if port is already in use
    $portInUse = Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue
    if ($portInUse) {
        Write-ColoredOutput "WARNING: Port $LocalPort is already in use. Attempting to kill existing process..." Yellow
        $process = Get-Process -Id $portInUse.OwningProcess -ErrorAction SilentlyContinue
        if ($process) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
        }
    }

    # Start port forwarding
    $job = Start-Job -ScriptBlock {
        param($ServiceName, $Namespace, $LocalPort, $ServicePort)
        & kubectl port-forward -n $Namespace svc/$ServiceName "${LocalPort}:${ServicePort}"
    } -ArgumentList $ServiceName, $Namespace, $LocalPort, $ServicePort

    # Wait for port forwarding to be ready
    $timeout = 30
    $elapsed = 0
    do {
        Start-Sleep -Seconds 1
        $elapsed++
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:$LocalPort" -Method Head -TimeoutSec 2 -ErrorAction SilentlyContinue
            if ($response) {
                Write-ColoredOutput "SUCCESS: ${DisplayName} port forwarding is ready on localhost:$LocalPort" Green
                return $job
            }
        }
        catch {
            # Still waiting
        }
    } while ($elapsed -lt $timeout)

    Write-ColoredOutput "${DisplayName} port forwarding might not be ready yet, but continuing..." Yellow
    return $job
}

function Open-Browser {
    param([string]$Url)

    if ($SkipBrowser) {
        return
    }

    Write-ColoredOutput "Opening browser..." Blue

    try {
        if ($IsWindows -or $env:OS -eq "Windows_NT") {
            Start-Process $Url
        }
        elseif ($IsLinux) {
            xdg-open $Url
        }
        elseif ($IsMacOS) {
            open $Url
        }
        else {
            Write-ColoredOutput "Cannot detect OS. Please open $Url manually." Yellow
        }
    }
    catch {
        Write-ColoredOutput "Could not open browser automatically. Please open $Url manually." Yellow
    }
}

function Show-Instructions {
    param($Credentials)

    Write-ColoredOutput "Access Information:" Blue
    Write-ColoredOutput "============================================================================" Blue
    Write-ColoredOutput "Grafana Dashboard:  http://localhost:$GrafanaPort" Green
    Write-ColoredOutput "Prometheus:         http://localhost:$PrometheusPort" Green
    Write-ColoredOutput "Login Credentials:" Blue
    Write-ColoredOutput "Username: $($Credentials.Username)" Yellow
    Write-ColoredOutput "Password: $($Credentials.Password)" Yellow
    Write-ColoredOutput "Quick Start:" Blue
    Write-ColoredOutput "1. Login to Grafana with the credentials above" White
    Write-ColoredOutput "2. Go to Dashboards -> Browse" White
    Write-ColoredOutput "3. Import dashboard ID 315 for Kubernetes monitoring" White
    Write-ColoredOutput "4. Create custom dashboards for Maliev services" White
    Write-ColoredOutput "Press Ctrl+C to stop port forwarding and exit" Yellow
    Write-ColoredOutput "============================================================================" Blue
}

# Main execution
try {
    Write-ColoredOutput "Maliev Grafana Access Script" Blue
    Write-ColoredOutput "Environment: $Environment" Yellow

    Test-Prerequisites
    $credentials = Get-GrafanaCredentials

    # Start port forwarding for both services
    $grafanaJob = Start-PortForwarding -ServiceName "prometheus-grafana" -Namespace "monitoring" -LocalPort $GrafanaPort -ServicePort 80 -DisplayName "Grafana"
    $prometheusJob = Start-PortForwarding -ServiceName "prometheus-kube-prometheus-prometheus" -Namespace "monitoring" -LocalPort $PrometheusPort -ServicePort 9090 -DisplayName "Prometheus"

    # Open browser
    Open-Browser -Url "http://localhost:$GrafanaPort"

    # Show instructions
    Show-Instructions -Credentials $credentials

    # Keep running until user stops
    try {
        while ($true) {
            Start-Sleep -Seconds 5

            # Check if jobs are still running
            if ($grafanaJob.State -eq "Failed") {
                Write-ColoredOutput "Grafana port forwarding failed!" Red
                break
            }
            if ($prometheusJob.State -eq "Failed") {
                Write-ColoredOutput "Prometheus port forwarding failed!" Red
                break
            }
        }
    }
    catch [System.Management.Automation.PipelineStoppedException] {
        Write-ColoredOutput "Stopping port forwarding..." Yellow
    }
}
catch {
    Write-ColoredOutput "An error occurred: $_" Red
    exit 1
}
finally {
    # Clean up jobs
    if ($grafanaJob) { Stop-Job $grafanaJob -ErrorAction SilentlyContinue; Remove-Job $grafanaJob -ErrorAction SilentlyContinue }
    if ($prometheusJob) { Stop-Job $prometheusJob -ErrorAction SilentlyContinue; Remove-Job $prometheusJob -ErrorAction SilentlyContinue }
    Write-ColoredOutput "Port forwarding stopped. Goodbye!" Green
}