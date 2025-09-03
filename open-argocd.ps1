# This script starts port-forwarding and opens the Argo CD UI in your default browser.

# Start port-forwarding in a new PowerShell window
Write-Host "Starting port-forwarding for Argo CD..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "kubectl port-forward svc/argocd-server -n argocd 8080:443"

# Wait for a few seconds for the port-forwarding to be ready
Start-Sleep -Seconds 5

# Open the Argo CD UI in the default browser
Write-Host "Opening Argo CD UI at https://localhost:8080"
Start-Process "https://localhost:8080"

Write-Host "To stop the port-forwarding, close the new PowerShell window that was opened."
