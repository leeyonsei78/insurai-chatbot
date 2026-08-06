@echo off
title Insurance AI

cd /d "%~dp0"

if not exist ".env" (
    echo [Error] .env file not found.
    echo Please copy .env.example to .env and enter your OPENAI_API_KEY.
    pause
    exit /b 1
)

python --version >nul 2>&1
if errorlevel 1 (
    set PYTHON=C:\Users\admin\AppData\Local\Programs\Python\Python313\python.exe
) else (
    set PYTHON=python
)

%PYTHON% -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo Installing packages...
    %PYTHON% -m pip install -r requirements.txt
)

for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":5000 " ^| findstr "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)

echo.
echo ====================================
echo   Insurance AI - http://localhost:5000
echo   Press Ctrl+C to stop
echo ====================================
echo.

start "" cmd /c "timeout /t 2 >nul && start http://localhost:5000"

%PYTHON% web_app.py

echo.
echo Server stopped.
pause