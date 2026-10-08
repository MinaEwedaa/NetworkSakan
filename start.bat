@echo off
title NetworkSakan Launcher
echo ======================================================
echo           NetworkSakan - Bandwidth Monitor
echo ======================================================
echo.

:: Check for administrative rights
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [!] Requesting Administrator privileges to capture packets...
    powershell -Command "Start-Process cmd -ArgumentList '/c \"%~f0\"' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"

echo [*] Installing dependencies if needed...
python -m pip install -r requirements.txt

echo [*] Starting Web Dashboard (http://localhost:5000)...
start "NetworkSakan Dashboard" python dashboard.py

echo [*] Starting Packet Monitor Daemon...
timeout /t 2 /nobreak >nul
start "NetworkSakan Monitor" python monitor.py

timeout /t 2 /nobreak >nul
echo [*] Opening Dashboard in browser...
start http://localhost:5000

echo.
echo [OK] NetworkSakan is running!
echo Keep the terminal windows open or minimize them.
echo Dashboard is available at: http://localhost:5000
echo.
pause
