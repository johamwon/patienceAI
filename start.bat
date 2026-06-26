@echo off
chcp 65001 >nul 2>nul
echo ========================================
echo   HuanAiZhiGuang - One-Click Startup
echo ========================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed. Please install Python 3.10+
    pause
    exit /b 1
)
echo [OK] Python is installed

:: Check Node.js
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js is not installed. Please install Node.js 18+
    pause
    exit /b 1
)
echo [OK] Node.js is installed

:: Check .env file
if not exist ".env" (
    echo [INFO] .env file not found. Creating from .env.example...
    copy .env.example .env
    echo [INFO] Please edit .env and add your SiliconFlow API Key
    echo.
    pause
    exit /b 1
)
echo [OK] .env file is ready

:: Install backend dependencies
echo.
echo [1/4] Installing backend dependencies...
if not exist "backend\venv" (
    echo   Creating Python virtual environment...
    python -m venv backend\venv
)
call backend\venv\Scripts\activate.bat
pip install -r backend\requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] Failed to install backend dependencies
    pause
    exit /b 1
)
echo [OK] Backend dependencies installed

:: Install frontend dependencies
echo.
echo [2/4] Installing frontend dependencies...
if not exist "frontend\node_modules" (
    cd frontend
    call npm install
    cd ..
)
echo [OK] Frontend dependencies installed

:: Start backend service
echo.
echo [3/4] Starting backend service (port 8000)...
start "HuanAiZhiGuang-Backend" cmd /c "cd /d %CD% && call backend\venv\Scripts\activate.bat && python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload"
timeout /t 3 /nobreak >nul
echo [OK] Backend service started

:: Start frontend service
echo.
echo [4/4] Starting frontend service (port 3000)...
cd frontend
start "HuanAiZhiGuang-Frontend" cmd /c "npm run dev"
cd ..
timeout /t 2 /nobreak >nul
echo [OK] Frontend service started

:: Done
echo.
echo ========================================
echo   Startup Complete!
echo ========================================
echo.
echo   Frontend: http://localhost:3000
echo   Backend API: http://localhost:8000
echo   API Docs: http://localhost:8000/docs
echo.
echo   Press any key to close this window (services will keep running)
pause >nul
