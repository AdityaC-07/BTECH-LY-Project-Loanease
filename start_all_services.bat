@echo off
echo Starting LoanEase Services...
echo.

REM Check if .env file exists, if not create example
if not exist .env (
    echo Creating .env.example file...
    echo GROQ_API_KEY=your_key_here > .env.example
    echo GROQ_MODEL_PRIMARY=llama-3.3-70b-versatile >> .env.example
    echo GROQ_MODEL_FALLBACK=llama-3.1-8b-instant >> .env.example
    echo GROQ_TIMEOUT_SECONDS=8 >> .env.example
    echo FALLBACK_MODE=rule_based >> .env.example
    echo FRONTEND_DOMAIN=https://loanease.example.com >> .env.example
    echo Please create .env file with your actual API keys
)

echo Starting KYC Service (Port 8004)...
start "KYC Service" cmd /k "cd kyc_backend && python -m uvicorn app.main:app --port 8004 --reload"
timeout /t 3 /nobreak

echo Starting Underwriting Service (Port 8000)...
start "Underwriting Service" cmd /k "cd backend && python -m uvicorn app.main:app --port 8000 --reload"
timeout /t 3 /nobreak

echo Starting Negotiation Service (Port 8001)...
start "Negotiation Service" cmd /k "cd negotiation_backend && python -m uvicorn app.main:app --port 8001 --reload"
timeout /t 3 /nobreak

echo Starting Translation + Groq Service (Port 8003)...
start "Translation Service" cmd /k "cd translation_backend && python -m uvicorn app.main:app --port 8003 --reload"
timeout /t 3 /nobreak

echo Starting Blockchain Audit Service (Port 8005)...
start "Blockchain Service" cmd /k "cd backend && python -m uvicorn blockchain_service:app --port 8005 --reload"
timeout /t 3 /nobreak

echo Starting Pipeline Orchestrator (Port 8002)...
start "Pipeline Service" cmd /k "cd backend && python -m uvicorn pipeline:app --port 8002 --reload"
timeout /t 3 /nobreak

echo.
echo All LoanEase services started!
echo.
echo Service URLs:
echo - KYC Service: http://localhost:8004
echo - Underwriting: http://localhost:8000
echo - Negotiation: http://localhost:8001
echo - Translation+Groq: http://localhost:8003
echo - Blockchain: http://localhost:8005
echo - Pipeline: http://localhost:8002
echo.
echo Frontend should be started separately with: npm run dev (from frontend folder)
echo.
pause
