@echo off
REM ══════════════════════════════════════════════════════════════════════════
REM n8n Unified MCP Server — Windows Quick Start
REM ══════════════════════════════════════════════════════════════════════════

echo ══════════════════════════════════════
echo   n8n Unified MCP Server — Starting
echo ══════════════════════════════════════

REM Check if .env exists
if not exist ".env" (
    echo [WARNING] No .env file found. Copying .env.example...
    copy .env.example .env
    echo [ACTION] Edit .env with your n8n API key then re-run this script.
    pause
    exit /b 1
)

REM Check if venv exists
if not exist "venv" (
    echo [INFO] Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate.bat
    pip install --quiet --upgrade pip
    pip install --quiet -r requirements.txt
    echo [OK] Dependencies installed
) else (
    call venv\Scripts\activate.bat
)

echo [OK] Starting MCP Server...
echo      MCP endpoint: http://localhost:8000/mcp
echo      Health check: http://localhost:8000/health
echo      API docs:     http://localhost:8000/docs
echo.

python main.py

pause
