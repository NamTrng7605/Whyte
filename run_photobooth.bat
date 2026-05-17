@echo off
title Photobooth System - Automated Starter
echo Starting Photobooth System...
echo.

:: Define the specific Python path used on this machine
set PYTHON_EXE="C:\Users\23520\AppData\Local\Programs\Python\Python313\python.exe"

:: Check if the Python executable exists
if not exist %PYTHON_EXE% (
    echo [ERROR] Python not found at %PYTHON_EXE%
    echo Please check the path in run_photobooth.bat
    pause
    exit /b
)

:: Install/Update dependencies using the specific Python instance
echo [1/2] Checking and installing dependencies...
%PYTHON_EXE% -m pip install -r requirements.txt --quiet

:: Start the main application
echo [2/2] Launching FastAPI Server ^& Watcher...
echo Dashboard available at: http://localhost:8000
echo.
echo [PRESS CTRL+C TO STOP THE SYSTEM]
echo.

%PYTHON_EXE% main.py

pause
