@echo off
echo Setting up Python virtual environment for SentinelApp...

REM Create virtual environment if it doesn't exist
if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
    if %ERRORLEVEL% neq 0 (
        echo Failed to create virtual environment. Please make sure Python is installed.
        exit /b 1
    )
)

REM Activate virtual environment
echo Activating virtual environment...
call .venv\Scripts\activate.bat

REM Install required packages
echo Installing required packages...
python -m pip install --upgrade pip
if %ERRORLEVEL% neq 0 (
    echo Failed to upgrade pip. Continuing with installation...
)

REM Install packages from requirements.txt
if exist src\python\requirements.txt (
    python -m pip install -r src\python\requirements.txt
    if %ERRORLEVEL% neq 0 (
        echo Failed to install packages from requirements.txt. Please check the file and try again.
        exit /b 1
    )
) else (
    echo requirements.txt not found. Installing individual packages...
    python -m pip install opensearch-py psutil python-dotenv requests
)

echo Python environment setup complete!
echo To activate the environment, run: .venv\Scripts\activate.bat 