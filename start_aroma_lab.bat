@echo off
title Aroma-Lab - Aromachemical Database
cd /d C:\Users\pwong\projects\aroma-lab
call .venv\Scripts\activate
echo.
echo ========================================
echo   Aroma-Lab - Aromachemical Database
echo ========================================
echo.
echo Starting server at http://localhost:8001
echo Web UI at http://localhost:8001
echo API docs at http://localhost:8001/docs
echo.
echo Press Ctrl+C to stop the server
echo.

REM Open browser after delay (in background)
start /b cmd /c "timeout /t 4 /nobreak >nul && start http://localhost:8001"

REM Start the server (this keeps the window open)
.venv\Scripts\uvicorn.exe api.main:app --reload --port 8001
