# Script to set up the Python virtual environment for SentinelApp

Write-Host "Setting up Python virtual environment for SentinelApp..." -ForegroundColor Blue

# Create virtual environment if it doesn't exist
if (!(Test-Path ".venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Green
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to create virtual environment. Please make sure Python is installed." -ForegroundColor Red
        exit 1
    }
}

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Green
if ($PSVersionTable.PSVersion.Major -ge 3) {
    # PowerShell 3.0+
    & ".venv\Scripts\Activate.ps1"
} else {
    # Older PowerShell versions
    & ".venv\Scripts\activate.bat"
}

# Install required packages
Write-Host "Installing required packages..." -ForegroundColor Green
$pythonPath = ".venv\Scripts\python.exe"
& $pythonPath -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to upgrade pip. Continuing with installation..." -ForegroundColor Yellow
}

# Install packages from requirements.txt
if (Test-Path "src\python\requirements.txt") {
    & $pythonPath -m pip install -r src\python\requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to install packages from requirements.txt. Please check the file and try again." -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "requirements.txt not found. Installing individual packages..." -ForegroundColor Yellow
    & $pythonPath -m pip install opensearch-py psutil python-dotenv requests
}

Write-Host "Python environment setup complete!" -ForegroundColor Blue
Write-Host "To activate the environment, run: .venv\Scripts\Activate.ps1" -ForegroundColor Green 