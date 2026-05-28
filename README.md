# 🏦 LoanEase

> **B.Tech Project 2026-2027**  
> A modern, intelligent loan management platform designed to simplify and streamline the loan application and management process.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![React](https://img.shields.io/badge/React-18.3-61DAFB?logo=react)](https://reactjs.org/)
[![Vite](https://img.shields.io/badge/Vite-5.4-646CFF?logo=vite)](https://vitejs.dev/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind-3.4-38B2AC?logo=tailwind-css)](https://tailwindcss.com/)

---

## 🎯 Vision
Traditional loan management systems are cumbersome and archaic. **LoanEase** redefines the experience by combining an intuitive AI-powered interface with enterprise-grade security, making credit accessible and the application process effortless.

---

## ✨ Key Features

### 🤖 AI-Powered Assistant
Experience a seamless, conversational loan journey. Our AI assistant guides you from the first "Hello" to the final sanction letter.
- **Natural Language Interaction**: No complex forms; just chat.
- **Instant Eligibility Assessment**: Real-time credit evaluation.
- **Smart Offer Generation**: Personalized loan terms based on your profile.
- **Multi-Channel Support**: Web chat and WhatsApp share the same loan journey and channel-aware prompts.

### 📊 Decision Dashboard
The post-decision flow now surfaces a richer underwriting summary.
- **Live Credit Insights**: Credit score, risk tier, and SHAP factors are shown with updated banding.
- **Post-Sanction Analytics**: EMI, total payable, total interest, and benchmark comparisons come from the analytics endpoint.
- **Sanction Letter Export**: The sanction letter now has a working PDF download action and an analytics shortcut.
## ⚙️ Unified Backend Schema

LoanEase exposes one orchestrated backend surface in the unified app, with the supporting service modules below it. The backend is intentionally modular, but the documentation below groups the pieces by role instead of repeating separate agent pages.

### Unified Backend Core (`backend/app/main.py`)

#### Responsibilities
- Serves the primary FastAPI application used by the frontend.
- Orchestrates underwriting, KYC, negotiation, translation, blockchain, and chat routes.
- Initializes shared services at startup, including VLM and Twilio Verify.

#### Core APIs

| Method | Endpoint | Purpose |
| :--- | :--- | :--- |
| `GET` | `/` | Service banner / root health entry |
| `GET` | `/health` | Unified backend health |
| `POST` | `/session/save` | Persist chat/session state |
| `GET` | `/session/{session_id}` | Load stored session data |
| `POST` | `/escalation/preferences` | Save escalation callback preferences |
| `GET` | `/analytics/{session_id}` | EMI, payoff, risk, and benchmark analytics |
| `POST` | `/pipeline/start` | Start the orchestrated pipeline |
| `GET` | `/pipeline/log/{session_id}` | Fetch pipeline step log |
| `GET` | `/credit-score/{pan_number}` | Credit score simulation and banding |
| `GET` | `/credit/credit-score` | Legacy credit-score alias |
| `POST` | `/assess` | Risk assessment and decision generation |
| `POST` | `/credit/assess` | Legacy assessment alias |
| `POST` | `/explain/{application_id}` | Stored-application explanation and SHAP waterfall |
| `POST` | `/kyc/extract/pan` | PAN OCR extraction and validation |
| `POST` | `/kyc/extract/aadhaar` | Aadhaar OCR extraction and validation |
| `POST` | `/kyc/verify` | Cross-document KYC verification |
| `POST` | `/kyc/send-otp` | Send Aadhaar verification OTP via Twilio Verify |
| `POST` | `/kyc/resend-otp` | Resend Aadhaar verification OTP via Twilio Verify |
| `POST` | `/kyc/verify-otp` | Verify Aadhaar OTP or QR-backed identity proof |
| `POST` | `/negotiate/start` | Start a negotiation session |
| `POST` | `/negotiate/start-from-underwriting` | Start negotiation from underwriting context |
| `POST` | `/negotiate/counter` | Submit a counter-offer |
| `POST` | `/negotiate/accept` | Accept the current offer |
| `POST` | `/negotiate/escalate` | Escalate to a human officer |
| `GET` | `/negotiate/history/{session_id}` | Negotiation history and current state |
| `POST` | `/translate` | Translate between English and Hindi |
| `POST` | `/detect-hinglish-intent` | Detect Hinglish intent |
| `POST` | `/chat` | Channel-aware chat endpoint |
| `POST` | `/chat/stream` | Streaming chat endpoint |
| `POST` | `/intent/classify` | Classify the current user intent |
| `POST` | `/explain/credit` | Credit explanation helper |
| `POST` | `/explain/negotiation` | Negotiation explanation helper |
| `POST` | `/generate/rejection` | Generate rejection messaging |
| `GET` | `/groq/health` | Groq integration health |

### Unified Backend Modules

#### Credit Underwriting Module (`backend/`)
- Trains the underwriting model from `backend/data/loan_train.csv`.
- Produces artifacts in `backend/artifacts/`.
- Exposes the assessment, explanation, credit-score, and analytics routes.

#### KYC Module (`backend/agents/kyc.py` and `backend/services/vlm_kyc.py`)
- Extracts PAN and Aadhaar fields with the VLM abstraction.
- Decodes Aadhaar Secure QR payloads and stores QR metadata in session state.
- Verifies Aadhaar-linked mobile numbers via QR hash first, then Twilio Verify OTP.
- Returns KYC status and reference IDs for the downstream credit flow.

#### Negotiation Module (`backend/agents/negotiation_agent/`)
- Runs stateful, risk-aware loan-rate negotiation.
- Computes EMI, total payable, and savings with reducing-balance math.
- Returns plain-English reasoning for each step.

#### Translation Module (`backend/routers/ai_router.py` and translation routes)
- Provides multilingual translation and Hinglish intent detection.
- Supports the chat experience without requiring a separate manual workflow.

#### Blockchain Module (`backend/blockchain_service.py` and blockchain agent)
- Registers and verifies sanction records.
- Exposes chain state, explorer data, and tamper-test routes.
- Supports the audit trail used by the sanction flow.

### Module Setup Summary

Run the unified backend from the backend directory:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Docs: `http://localhost:8000/docs`

### Service Notes
- `backend/services/vlm_kyc.py` is provider-agnostic and can be mapped to a Qwen-compatible multimodal backend if needed.
- `backend/services/aadhaar_qr.py` adds offline Aadhaar Secure QR decoding and mobile-hash verification.
- `backend/services/otp_service.py` uses Twilio Verify and falls back to demo mode when credentials are absent.
- Typical interest-rate guidance: `Low Risk` 9-11%, `Medium Risk` 11-13%, `High Risk` 13-15%.

### Frontend Decision Flow

- **Agent Activity Panel**: Collapsible floating sidebar that expands only when it is visible or opened manually.
- **Credit Score Card**: Score 592 is treated as Medium Risk in the UI thresholding.
- **Sanction Letter**: Download PDF now triggers a real export flow.
- **Analytics Dashboard**: Pulls live session analytics from `/analytics/{session_id}` and renders charts from backend data.

---

## 🌍 Running All Services Locally

### 🚀 Quick Start (Recommended)

```bash
# From project root with activated virtual environment
start_all_services.bat
```

### 🖥️ Manual Setup (6 Terminals)

**Terminal 1 - Frontend (Port 5173):**

```powershell
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173
```

**Terminal 2 - Underwriting Backend (Port 8000):**

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python train_model.py --data data/loan_train.csv --artifacts artifacts
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 3 - Negotiation Backend (Port 8001):**

```powershell
cd negotiation_backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

**Terminal 4 - Translation + Groq Service (Port 8003):**

```powershell
cd translation_backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8003
```

**Terminal 5 - KYC OCR Service (Port 8004):**

```powershell
cd kyc_backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8004
```

**Terminal 6 - Blockchain Audit Service (Port 8005):**

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn blockchain_service:app --reload --host 0.0.0.0 --port 8005
```

**Terminal 7 - Pipeline Orchestrator (Port 8002):**

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn pipeline:app --reload --host 0.0.0.0 --port 8002
```

### 📋 Service URLs

All services are now running:
- **Frontend**: http://localhost:5173
- **Underwriting**: http://localhost:8000/docs
- **Negotiation**: http://localhost:8001/docs
- **Translation + Groq**: http://localhost:8003/docs
- **KYC OCR**: http://localhost:8004/docs
- **Blockchain Audit**: http://localhost:8005/docs
- **Pipeline Orchestrator**: http://localhost:8002/docs

### 🔧 Prerequisites

1. **Python 3.8+** installed
2. **Node.js 16+** and **npm** installed
3. **Virtual environment** activated:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

### 📦 Dependencies Installation

If dependencies are not installed, run in each backend directory:
```bash
pip install -r requirements.txt
```

For the KYC stack, ensure the backend environment includes the OCR/QR and OTP packages used by the new flow:

- `twilio`
- `pyzbar`
- `opencv-python`

On Linux, `pyzbar` may also require `libzbar0`.

### KYC Verification Usage

The KYC journey now runs in three layers:

1. PAN extraction validates document text and identity fields.
2. Aadhaar extraction decodes the Secure QR when present and stores QR metadata in session state.
3. QR hash verification is attempted first; Twilio OTP is used when the QR hash check is unavailable or inconclusive.

Recommended environment variables:

```powershell
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_VERIFY_SERVICE_SID=VAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
OTP_EXPIRY_MINUTES=10
```

The VLM layer is provider-agnostic. If you deploy a Qwen-compatible multimodal model, wire it behind `backend/services/vlm_kyc.py` using the same extraction contract.

Typical demo flow:

1. Upload PAN.
2. Upload Aadhaar.
3. If the Aadhaar Secure QR is decoded, the UI shows an offline verification status.
4. If QR hash verification cannot complete, the flow continues with Twilio OTP.
5. On success, the application advances to credit assessment.

### 🎯 Service Startup Order

The startup script automatically handles the correct order:
1. **KYC Service** (Port 8004) - Must start first for PAN upload
2. **Underwriting** (Port 8000) - Credit assessment
3. **Negotiation** (Port 8001) - Rate negotiation
4. **Translation + Groq** (Port 8003) - AI-powered responses
5. **Blockchain Audit** (Port 8005) - Document signing and verification
6. **Pipeline Orchestrator** (Port 8002) - Coordinates all agents

### 🔍 Health Checks

Verify all services are running:
```bash
curl http://localhost:8004/health  # KYC
curl http://localhost:8000/health  # Underwriting
curl http://localhost:8001/health  # Negotiation
curl http://localhost:8003/health  # Translation+Groq
curl http://localhost:8005/health  # Blockchain Audit
curl http://localhost:8002/health  # Pipeline Orchestrator
```

---

## 👥 Contributors
- **Aditya Choudhuri** - [GitHub](https://github.com/AdityaC-07)
- **Agniv Dutta** - [GitHub](https://github.com/agniv-dutta)
- **Akshat Kunder** - [GitHub](https://github.com/AkshatKunder)
- **Aaryan Dubey** - [GitHub](https://github.com/aaryan-r-dubey)

---
© 2026 LoanEase - A BFSI Innovation Solution.
