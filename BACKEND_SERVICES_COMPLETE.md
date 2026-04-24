# 🚀 LoanEase Backend Services - Complete Configuration

## 📋 **Service Port Mapping (Final)**

| Port | Service | Status | Module | Description |
|------|---------|--------|--------|-------------|
| **8000** | Underwriting Service | ⚠️ Not Running | `app.main:app` | Credit assessment with XGBoost + SHAP |
| **8001** | Negotiation Service | ⚠️ Not Running | `app.main:app` | Dynamic loan rate negotiation |
| **8002** | Pipeline Orchestrator | ⚠️ Not Running | `pipeline:app` | Coordinates all backend agents |
| **8003** | Translation + Groq Service | ✅ Running | `app.main:app` | Multi-language + AI chat |
| **8004** | KYC OCR Service | ✅ Running | `app.main:app` | PAN/Aadhaar extraction + verification |
| **8005** | Blockchain Audit Service | ⚠️ Not Running | `blockchain_service:app` | Document signing + verification |

## 🌐 **Service Details & Endpoints**

### ✅ **Port 8003: Translation + Groq Service**
- **Path**: `translation_backend/app/main.py`
- **Module**: `app.main:app`
- **Features**: Multi-language support, Groq LLaMA integration, Hinglish detection
- **Health**: `http://localhost:8003/health`
- **Docs**: `http://localhost:8003/docs`
- **Endpoints**: `/translate`, `/detect-hinglish-intent`, `/chat`, `/groq/health`

### ✅ **Port 8004: KYC OCR Service**
- **Path**: `kyc_backend/app/main.py`
- **Module**: `app.main:app`
- **Features**: PAN extraction, Aadhaar extraction, PDF processing, name matching
- **Health**: `http://localhost:8004/health`
- **Docs**: `http://localhost:8004/docs`
- **Endpoints**: `/kyc/extract/pan`, `/kyc/extract/aadhaar`, `/kyc/verify`, `/kyc/extract/auto`

### ⚠️ **Port 8000: Underwriting Service**
- **Path**: `backend/app/main.py`
- **Module**: `app.main:app`
- **Features**: Credit scoring, risk assessment, SHAP explanations
- **Health**: `http://localhost:8000/health`
- **Docs**: `http://localhost:8000/docs`
- **Endpoints**: `/assess`, `/credit-score/{pan}`, `/explain/{application_id}`, `/health`

### ⚠️ **Port 8001: Negotiation Service**
- **Path**: `negotiation_backend/app/main.py`
- **Module**: `app.main:app`
- **Features**: Rate negotiation, EMI calculation, concession logic
- **Health**: `http://localhost:8001/health`
- **Docs**: `http://localhost:8001/docs`
- **Endpoints**: `/negotiate/start`, `/negotiate/counter`, `/negotiate/accept`, `/health`

### ⚠️ **Port 8002: Pipeline Orchestrator**
- **Path**: `backend/pipeline.py`
- **Module**: `pipeline:app`
- **Features**: Agent orchestration, workflow management
- **Health**: `http://localhost:8002/health`
- **Docs**: `http://localhost:8002/docs`
- **Endpoints**: `/pipeline/process`, `/pipeline/status`, `/health`

### ⚠️ **Port 8005: Blockchain Audit Service**
- **Path**: `backend/blockchain_service.py`
- **Module**: `blockchain_service:app`
- **Features**: RSA cryptography, PDF generation, QR codes, document signing
- **Health**: `http://localhost:8005/health`
- **Docs**: `http://localhost:8005/docs`
- **Endpoints**: `/blockchain/sanction`, `/blockchain/verify/{reference}`, `/blockchain/chain`, `/health`

## 🛠️ **Complete Startup Commands**

### **Option 1: Startup Script (Recommended)**
```bash
# Windows
start_all_services.bat

# Linux/Mac
chmod +x start_all_services.sh
./start_all_services.sh
```

### **Option 2: Manual Commands (7 Terminals)**

```powershell
# Terminal 1 - Underwriting Service (Port 8000)
cd "c:\Users\Agniv Dutta\BTECH-LY-Project-Loanease\backend"
python -m uvicorn app.main:app --port 8000 --reload --host 0.0.0.0

# Terminal 2 - Negotiation Service (Port 8001)
cd "c:\Users\Agniv Dutta\BTECH-LY-Project-Loanease\negotiation_backend"
python -m uvicorn app.main:app --port 8001 --reload --host 0.0.0.0

# Terminal 3 - Pipeline Orchestrator (Port 8002)
cd "c:\Users\Agniv Dutta\BTECH-LY-Project-Loanease\backend"
python -m uvicorn pipeline:app --port 8002 --reload --host 0.0.0.0

# Terminal 4 - Translation + Groq Service (Port 8003)
cd "c:\Users\Agniv Dutta\BTECH-LY-Project-Loanease\translation_backend"
python -m uvicorn app.main:app --port 8003 --reload --host 0.0.0.0

# Terminal 5 - KYC OCR Service (Port 8004)
cd "c:\Users\Agniv Dutta\BTECH-LY-Project-Loanease\kyc_backend"
python -m uvicorn app.main:app --port 8004 --reload --host 0.0.0.0

# Terminal 6 - Blockchain Audit Service (Port 8005)
cd "c:\Users\Agniv Dutta\BTECH-LY-Project-Loanease\backend"
python -m uvicorn blockchain_service:app --port 8005 --reload --host 0.0.0.0

# Terminal 7 - Frontend (Port 5173)
cd "c:\Users\Agniv Dutta\BTECH-LY-Project-Loanease\frontend"
npm run dev
```

## 🔍 **Health Check Commands**

```bash
# Check all services
curl http://localhost:8000/health  # Underwriting
curl http://localhost:8001/health  # Negotiation
curl http://localhost:8002/health  # Pipeline Orchestrator
curl http://localhost:8003/health  # Translation + Groq
curl http://localhost:8004/health  # KYC OCR
curl http://localhost:8005/health  # Blockchain Audit

# Frontend
curl http://localhost:5173         # Frontend (if running)
```

## 📊 **Service Dependencies**

```
Frontend (Port 5173)
    ↓
┌─────────────────┬─────────────────┬─────────────────┬─────────────────┬─────────────────┬─────────────────┐
│   Underwriting  │   Negotiation   │   Pipeline      │   Translation   │     KYC OCR     │   Blockchain    │
│     8000        │      8001       │      8002       │      8003       │      8004       │      8005        │
└─────────────────┴─────────────────┴─────────────────┴─────────────────┴─────────────────┴─────────────────┘
                              ↓
                        All services coordinated by Pipeline (8002)
```

## 🎯 **Frontend API Configuration**

The frontend should use these endpoints:

```typescript
const API_ENDPOINTS = {
  // Core services
  UNDERWRITING: 'http://localhost:8000',
  NEGOTIATION: 'http://localhost:8001',
  
  // Agent services
  TRANSLATION: 'http://localhost:8003',
  KYC: 'http://localhost:8004',
  BLOCKCHAIN: 'http://localhost:8005',
  
  // Orchestration
  PIPELINE: 'http://localhost:8002'
};
```

## 📝 **Important Notes**

### **Port Changes Made:**
- **KYC Service**: Moved from 8003 → 8004 (to fix conflicts)
- **Translation Service**: Moved from 8002 → 8003 (to avoid conflicts)
- **Pipeline Orchestrator**: Moved from 8004 → 8002 (to occupy freed port)

### **Current Status:**
- ✅ **2 services running**: Translation (8003), KYC (8004)
- ⚠️ **4 services not running**: Underwriting (8000), Negotiation (8001), Pipeline (8002), Blockchain (8005)

### **Files Updated:**
- `README.md` - Updated all port references
- `start_all_services.bat` - Updated Windows startup script
- `start_all_services.sh` - Updated Linux/Mac startup script
- `frontend/src/components/ChatInterface.tsx` - Updated KYC endpoints to port 8004

### **Troubleshooting:**
1. **Port conflicts**: Ensure services are properly shut down before restarting
2. **Dependencies**: Install requirements.txt in each backend directory
3. **Virtual environment**: Activate before starting services
4. **Health checks**: Use curl commands to verify service status

## 🚀 **Next Steps**

1. **Start missing services** using the manual commands above
2. **Verify all health endpoints** are responding
3. **Test frontend integration** with correct ports
4. **Run complete workflow** to ensure all services work together

This configuration ensures no port conflicts and proper service orchestration for the LoanEase platform! 🎯
