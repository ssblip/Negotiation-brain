@echo off
echo Stopping any running servers...
taskkill /f /im uvicorn.exe >nul 2>&1
taskkill /f /im node.exe >nul 2>&1
timeout /t 2 /nobreak >nul

echo Starting Backend...
start "Negotiation Brain - Backend" cmd /k "cd /d "%~dp0backend" && echo Activating venv... && .venv\Scripts\activate.bat && echo Starting uvicorn... && uvicorn app.main:app --reload --port 8000 || (echo BACKEND FAILED - see error above && pause)"

echo Waiting for backend...
timeout /t 5 /nobreak >nul

echo Starting Frontend...
start "Negotiation Brain - Frontend" cmd /k "cd /d "%~dp0frontend" && echo Starting frontend... && npm.cmd run dev || (echo FRONTEND FAILED - see error above && pause)"

echo Waiting for frontend...
timeout /t 6 /nobreak >nul

echo Opening browser...
start http://localhost:5173
