@echo off
echo ========================================
echo    LoanEase Unified Backend Startup
echo ========================================
echo.

REM Check if .env file exists
if not exist .env (
    echo Creating .env file from example...
    copy env.example .env
    echo.
    echo IMPORTANT: Edit .env file and add your GROQ_API_KEY
    echo.
    pause
)

REM Check if virtual environment exists
if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
)

REM Activate virtual environment
echo Activating virtual environment...
call .venv\Scripts\activate.bat

REM Install dependencies
echo Installing dependencies...
pip install -r requirements.txt

REM Create necessary directories
if not exist keys mkdir keys
if not exist models mkdir models

REM Start the unified backend
echo.
echo ========================================
echo Starting LoanEase Unified Backend
echo ========================================
echo.
echo API will be available at: http://localhost:8000
echo Documentation at: http://localhost:8000/docs
echo.
echo Press Ctrl+C to stop the server
echo.

uvicorn main:app --reload --host 0.0.0.0 --port 8000
