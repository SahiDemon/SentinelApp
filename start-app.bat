@echo off
:: Sentinel App Startup Script
:: This script requests admin privileges, activates the Python virtual environment, and starts the application

:: Check for admin privileges and request them if needed
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"
if %errorlevel% neq 0 (
    echo Requesting administrator privileges...
    goto UACPrompt
) else (
    goto GotAdmin
)

:UACPrompt
    echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\getadmin.vbs"
    echo UAC.ShellExecute "%~s0", "", "", "runas", 1 >> "%temp%\getadmin.vbs"
    "%temp%\getadmin.vbs"
    exit /B

:GotAdmin
    if exist "%temp%\getadmin.vbs" ( del "%temp%\getadmin.vbs" )
    cd /d "%~dp0"

:: Check if virtual environment exists, create if it doesn't
if not exist .venv (
    echo Python virtual environment not found. Setting up now...
    call setup-python.bat
)

:: Activate the Python virtual environment
echo Activating Python virtual environment...
call .venv\Scripts\activate.bat

:: Set PYTHONPATH environment variable
set PYTHONPATH=%~dp0;%~dp0src\python
echo Set PYTHONPATH to: %PYTHONPATH%

:: Disable proxy settings that might interfere with OpenSearch connections
set HTTP_PROXY=
set HTTPS_PROXY=
set NO_PROXY=localhost,127.0.0.1,search-sentinelprimeregistry-re5i27ttwnf44njaayopo6vouq.aos.us-east-1.on.aws
echo Disabled proxy settings for OpenSearch connectivity

:: Set OpenSearch connection timeout
set OPENSEARCH_TIMEOUT=60
set OPENSEARCH_RETRY=3
echo Set OpenSearch connection parameters

:: Create logs directory if it doesn't exist
if not exist logs (
    mkdir logs
    echo Created logs directory
)

:: Start the application
echo Starting Sentinel Application...
npm start

:: Keep the window open if there are errors
if %errorlevel% neq 0 (
    echo Application exited with error code: %errorlevel%
    echo Press any key to exit...
    pause > nul
) 