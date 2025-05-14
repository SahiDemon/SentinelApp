# Sentinel App Startup Script
# This script requests admin privileges, activates the Python virtual environment, and starts the application

# Self-elevate the script if not already running as administrator
if (-Not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)) {
    Write-Host "Requesting administrator privileges..." -ForegroundColor Yellow
    Start-Process PowerShell -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

# Set the working directory to the script location
Set-Location $PSScriptRoot

# Check if virtual environment exists, create if it doesn't
if (-Not (Test-Path ".venv")) {
    Write-Host "Python virtual environment not found. Setting up now..." -ForegroundColor Yellow
    & ".\setup-python.ps1"
}

# Activate the Python virtual environment
Write-Host "Activating Python virtual environment..." -ForegroundColor Green
& ".\.venv\Scripts\Activate.ps1"

# Set PYTHONPATH environment variable
$env:PYTHONPATH = "$PSScriptRoot;$PSScriptRoot\src\python"
Write-Host "Set PYTHONPATH to: $env:PYTHONPATH" -ForegroundColor Green

# Disable proxy settings that might interfere with OpenSearch connections
$env:HTTP_PROXY = ""
$env:HTTPS_PROXY = ""
$env:NO_PROXY = "localhost,127.0.0.1,search-sentinelprimeregistry-re5i27ttwnf44njaayopo6vouq.aos.us-east-1.on.aws"
Write-Host "Disabled proxy settings for OpenSearch connectivity" -ForegroundColor Green

# Set OpenSearch connection timeout
$env:OPENSEARCH_TIMEOUT = "60"
$env:OPENSEARCH_RETRY = "3"
Write-Host "Set OpenSearch connection parameters" -ForegroundColor Green

# Create logs directory if it doesn't exist
if (-Not (Test-Path "logs")) {
    New-Item -ItemType Directory -Path "logs" -Force | Out-Null
    Write-Host "Created logs directory" -ForegroundColor Green
}

# Start the application
Write-Host "Starting Sentinel Application..." -ForegroundColor Blue
npm start

# Keep the window open if there are errors
if ($LASTEXITCODE -ne 0) {
    Write-Host "Application exited with error code: $LASTEXITCODE" -ForegroundColor Red
    Write-Host "Press any key to exit..." -ForegroundColor Yellow
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
} 