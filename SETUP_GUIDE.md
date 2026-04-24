# LoanEase AI-Powered Backend Setup Guide

## Overview

LoanEase is an AI-powered personal loan system for Indian borrowers with intelligent agent orchestration using Groq's LLaMA models.

## Architecture

```
PORT 8000 — Underwriting Agent (XGBoost + SHAP + credit score)
PORT 8001 — Negotiation Agent (rate logic + EMI calc)
PORT 8002 — Translation + Chat Service (Groq LLaMA + fallbacks)
PORT 8003 — KYC OCR Service (RapidOCR + PAN/Aadhaar)
PORT 8004 — Pipeline Orchestrator (5 agents + activity log)
PORT 8005 — Blockchain Audit Service (SHA-256 + RSA signing + PDF + QR)
Frontend: PORT 5173 (Vite) or 3000 (CRA)
```

## Prerequisites

1. **Python 3.8+** installed
2. **Node.js 16+** and **npm** installed
3. **Git** for cloning

## Installation Steps

### 1. Clone and Setup Environment

```bash
git clone <repository-url>
cd BTECH-LY-Project-Loanease
```

### 2. Create Environment File

Create `.env` file in root directory:

```bash
# Groq Configuration
GROQ_API_KEY=your_actual_groq_api_key_here
GROQ_MODEL_PRIMARY=llama-3.3-70b-versatile
GROQ_MODEL_FALLBACK=llama-3.1-8b-instant
GROQ_TIMEOUT_SECONDS=8
FALLBACK_MODE=rule_based

# Service Configuration
FRONTEND_DOMAIN=https://loanease.example.com
```

> **Get Groq API Key**: Sign up at [console.groq.com](https://console.groq.com) and get your free API key

### 3. Install Python Dependencies

Install dependencies for each service:

```bash
# Backend (Underwriting + Groq Client)
cd backend
pip install -r requirements.txt
cd ..

# KYC Service
cd kyc_backend
pip install -r requirements.txt
cd ..

# Translation Service (with Groq)
cd translation_backend
pip install -r requirements.txt
cd ..

# Negotiation Service
cd negotiation_backend
pip install -r requirements.txt
cd ..
```

### 4. Install Frontend Dependencies

```bash
cd frontend
npm install
cd ..
```

## Starting Services

### Option 1: Use Startup Scripts (Recommended)

**Windows:**
```bash
start_all_services.bat
```

**Linux/Mac:**
```bash
chmod +x start_all_services.sh
./start_all_services.sh
```

### Option 2: Manual Startup

Start services in this order:

```bash
# Terminal 1 - KYC Service (MUST START FIRST)
cd kyc_backend
python -m uvicorn app.main:app --port 8003 --reload

# Terminal 2 - Underwriting Service
cd backend
python -m uvicorn app.main:app --port 8000 --reload

# Terminal 3 - Negotiation Service
cd negotiation_backend
python -m uvicorn app.main:app --port 8001 --reload

# Terminal 4 - Translation + Groq Service
cd translation_backend
python -m uvicorn app.main:app --port 8002 --reload

# Terminal 5 - Blockchain Service
cd backend
python -m uvicorn blockchain:app --port 8005 --reload

# Terminal 6 - Pipeline Orchestrator
cd backend
python -m uvicorn pipeline:app --port 8004 --reload

# Terminal 7 - Frontend
cd frontend
npm run dev
```

## Service Health Checks

Once services are running, check their health:

- **KYC Service**: http://localhost:8003/health
- **Underwriting**: http://localhost:8000/health
- **Negotiation**: http://localhost:8001/health
- **Translation+Groq**: http://localhost:8002/health
- **Groq Health**: http://localhost:8002/groq/health
- **Blockchain**: http://localhost:8005/health
- **Pipeline**: http://localhost:8004/health

## Testing PAN Upload Issue

The PAN upload issue should now be resolved. Test it:

1. Open frontend (usually http://localhost:5173)
2. Start chat with loan agent
3. When prompted for KYC, upload PAN card
4. Should process successfully via KYC service on port 8003

## Groq Integration Features

### 1. Intelligent Agent Orchestration
- Master Agent decides which specialized agent to invoke
- Context-aware responses in English/Hindi/Hinglish
- Automatic fallback to rule-based responses

### 2. Streaming Responses
- Token-by-token streaming for better UX
- Real-time chat experience
- Automatic timeout handling

### 3. Intent Classification
- Groq-powered intent detection
- Fallback to keyword matching
- Extracts amounts, rates, tenures

### 4. Health Monitoring
- Real-time API status tracking
- Usage statistics and error logging
- Fallback activation monitoring

## API Endpoints

### Translation + Groq Service (Port 8002)

```bash
# Chat with AI agent
POST /chat
{
  "message": "I want a loan",
  "session_id": "user123",
  "language": "en"
}

# Stream chat response
POST /chat/stream
{
  "message": "What are your rates?",
  "session_id": "user123",
  "language": "hi"
}

# Classify intent
POST /intent/classify
{
  "text": "muje 5 lakh loan chahiye"
}

# Generate credit explanation
POST /explain/credit
{
  "credit_score": 750,
  "risk_score": 85,
  "decision": "approved",
  "rate": 12.5,
  "shap_factors": ["high_income", "good_payment_history"],
  "language": "en"
}

# Groq health status
GET /groq/health
```

### Blockchain Audit Service (Port 8005)

```bash
# Process loan sanction and record on blockchain
POST /blockchain/sanction
{
  "session_id": "abc-123",
  "applicant_name": "Rahul Sharma",
  "pan_masked": "ABCDE****F",
  "loan_amount": 500000,
  "sanctioned_rate": 11.0,
  "tenure_months": 60,
  "emi": 10747,
  "total_payable": 644820,
  "kyc_reference": "KYC-2026-00291",
  "risk_score": 87
}

# Verify document authenticity
GET /blockchain/verify/{reference}

# Get complete blockchain
GET /blockchain/chain

# Get blockchain statistics
GET /blockchain/stats

# Service health check
GET /health
```

### KYC Service (Port 8003)

```bash
# Extract PAN details
POST /kyc/extract/pan
Content-Type: multipart/form-data
document: [file]
language: en

# Extract Aadhaar details
POST /kyc/extract/aadhaar
Content-Type: multipart/form-data
document: [file]

# Complete KYC verification
POST /kyc/verify
Content-Type: multipart/form-data
pan: [file]
aadhaar: [file]
```

## Troubleshooting

### PAN Upload "Not Found" Issue
**Cause**: KYC service not running on port 8003
**Solution**: Start KYC service first before other services

### Groq API Errors
**Cause**: Missing or invalid GROQ_API_KEY
**Solution**: 
1. Get API key from console.groq.com
2. Add to .env file
3. Restart services

### Port Conflicts
**Cause**: Services already running on ports
**Solution**: 
```bash
# Kill existing services
pkill -f 'uvicorn.*LoanEase'  # Linux/Mac
# or check Task Manager and kill processes manually on Windows
```

### Dependency Issues
**Cause**: Missing Python packages
**Solution**: 
```bash
pip install -r requirements.txt
```

### Frontend Connection Issues
**Cause**: CORS or wrong URLs
**Solution**: Check that all backend services are running and accessible

## Development Notes

- All services have CORS enabled for localhost
- Each service has a `/health` endpoint
- Groq client includes automatic fallback mechanisms
- Services can be developed and tested independently
- Frontend connects to multiple backend services

## Production Deployment

For production deployment:
1. Use environment variables instead of .env file
2. Set up proper load balancing
3. Configure SSL certificates
4. Set up monitoring and logging
5. Use process managers like PM2 or systemd
6. Configure reverse proxy (nginx)

## Support

If you encounter issues:
1. Check service health endpoints
2. Review console logs for errors
3. Verify .env configuration
4. Ensure all dependencies are installed
5. Check network connectivity to Groq API
