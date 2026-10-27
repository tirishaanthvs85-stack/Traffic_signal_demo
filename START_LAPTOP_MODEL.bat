@echo off
title AI Traffic Signal - Laptop Working Model
color 0B
echo =====================================================================
echo    🚦 NEURA-TRAFFIC AI 4.0 - COMPLETE LAPTOP WORKING MODEL
echo =====================================================================
echo.
echo Select your preferred Demonstration Mode:
echo   [1] Interactive Web Laptop Model (Recommended - Browser, Laptop Webcam, Audio)
echo   [2] Python OpenCV Desktop GUI Model (Tkinter + MOG2 Background Subtraction)
echo   [3] Run Automated Performance Benchmark (Headless 60s Test)
echo.
set /p choice="Enter choice (1, 2, or 3) [Default: 1]: "

if "%choice%"=="2" goto run_desktop
if "%choice%"=="3" goto run_benchmark
goto run_web

:run_web
echo.
echo Starting Local Web Server and Launching Interactive Laptop Model...
python run_laptop_server.py
goto end

:run_desktop
echo.
echo Launching Python OpenCV Desktop Application...
python main.py
goto end

:run_benchmark
echo.
echo Running Automated AI vs Fixed-Timer Benchmark...
python main.py --benchmark --duration 60
pause
goto end

:end
