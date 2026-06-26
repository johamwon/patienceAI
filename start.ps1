# HuanAiZhiGuang - One-Click Startup Script (PowerShell)
# Usage: .\start.ps1

param(
    [switch]$Help
)

if ($Help) {
    Write-Host @"
HuanAiZhiGuang - One-Click Startup Script

Usage:
  .\start.ps1              # Normal startup
  .\start.ps1 -Help        # Show help

Prerequisites:
  - Python 3.10+
  - Node.js 18+
  - .env file configured (see .env.example)

After startup:
  - Frontend: http://localhost:3000
  - Backend API: http://localhost:8000
  - API Docs: http://localhost:8000/docs
"@
    exit 0
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  HuanAiZhiGuang - Startup Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check Python
try {
    $pythonVersion = python --version 2>&1
    Write-Host "[OK] Python: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Python is not installed. Please install Python 3.10+" -ForegroundColor Red
    Write-Host "Download: https://www.python.org/downloads/"
    pause
    exit 1
}

# Check Node.js
try {
    $nodeVersion = node --version 2>&1
    Write-Host "[OK] Node.js: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Node.js is not installed. Please install Node.js 18+" -ForegroundColor Red
    Write-Host "Download: https://nodejs.org/"
    pause
    exit 1
}

# Check .env file
if (-not (Test-Path ".env")) {
    Write-Host "[INFO] .env file not found. Creating from .env.example..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host "[INFO] Please edit .env and add your SiliconFlow API Key" -ForegroundColor Yellow
    Write-Host ""
    pause
    exit 1
}
Write-Host "[OK] .env file is ready" -ForegroundColor Green

# Install backend dependencies
Write-Host ""
Write-Host "[1/4] Installing backend dependencies..." -ForegroundColor Cyan

if (-not (Test-Path "backend\venv")) {
    Write-Host "  Creating Python virtual environment..."
    python -m venv backend\venv
}

$venvPython = "backend\venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "[ERROR] Failed to create virtual environment" -ForegroundColor Red
    pause
    exit 1
}

& $venvPython -m pip install -r backend\requirements.txt --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to install backend dependencies" -ForegroundColor Red
    pause
    exit 1
}
Write-Host "[OK] Backend dependencies installed" -ForegroundColor Green

# Install frontend dependencies
Write-Host ""
Write-Host "[2/4] Installing frontend dependencies..." -ForegroundColor Cyan

if (-not (Test-Path "frontend\node_modules")) {
    Set-Location frontend
    npm install
    Set-Location ..
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to install frontend dependencies" -ForegroundColor Red
        pause
        exit 1
    }
}
Write-Host "[OK] Frontend dependencies installed" -ForegroundColor Green

# Start backend service
Write-Host ""
Write-Host "[3/4] Starting backend service (port 8000)..." -ForegroundColor Cyan

$backendLog = "backend\server.log"
Start-Process -NoNewWindow -FilePath $venvPython -ArgumentList "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload" -RedirectStandardOutput $backendLog -RedirectStandardError "$backendLog.err"
Start-Sleep -Seconds 3
Write-Host "[OK] Backend service started (log: $backendLog)" -ForegroundColor Green

# Start frontend service
Write-Host ""
Write-Host "[4/4] Starting frontend service (port 3000)..." -ForegroundColor Cyan

$frontendLog = "frontend\dev-server.log"
Set-Location frontend
Start-Process -NoNewWindow -FilePath "npm" -ArgumentList "run", "dev" -RedirectStandardOutput $frontendLog -RedirectStandardError "$frontendLog.err"
Set-Location ..
Start-Sleep -Seconds 2
Write-Host "[OK] Frontend service started (log: $frontendLog)" -ForegroundColor Green

# Done
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Startup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Frontend: http://localhost:3000" -ForegroundColor White
Write-Host "  Backend API: http://localhost:8000" -ForegroundColor White
Write-Host "  API Docs: http://localhost:8000/docs" -ForegroundColor White
Write-Host ""
Write-Host "  Press any key to close this window (services will keep running)" -ForegroundColor Yellow
pause >nul
