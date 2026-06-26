@echo off
taskkill /F /IM python.exe >nul 2>&1
timeout /t 2 /nobreak >nul
cd /d E:\patienceAI
backend\venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 > backend\stdout.log 2> backend\stderr.log
pause
