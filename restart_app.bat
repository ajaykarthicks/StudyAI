@echo off
echo ========================================================
echo Stopping existing Python processes...
echo (This kills any running backend/frontend servers)
echo ========================================================
taskkill /F /IM python.exe /T >nul 2>&1

echo.
echo ========================================================
echo Starting Backend (Port 5000)...
echo ========================================================
start "StudyAI Backend" cmd /k "call .venv\Scripts\activate && cd backend && python app.py"

echo.
echo ========================================================
echo Starting Frontend (Port 5500)...
echo ========================================================
start "StudyAI Frontend" cmd /k "call .venv\Scripts\activate && cd frontend && python -m http.server 5500"

echo.
echo ========================================================
echo App restarted successfully!
echo --------------------------------------------------------
echo Backend: http://localhost:5000
echo Frontend: http://localhost:5500
echo ========================================================
echo You can minimize this window, but don't close it.
pause