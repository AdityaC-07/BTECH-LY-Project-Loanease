# LoanEase Backend Services Status

## 🚀 Current Service Configuration

### 📋 **Service Port Mapping**

| Port | Service | Status | Health Endpoint | Description |
|------|---------|--------|-----------------|-------------|
| **8000** | Underwriting Service | ⚠️ Not Running | `/health` | Credit assessment with XGBoost + SHAP |
| **8001** | Negotiation Service | ⚠️ Not Running | `/health` | Dynamic loan rate negotiation |
| **8002** | Translation + Groq Service | ⚠️ Not Running | `/health` | Multi-language + AI chat |
| **8003** | Translation + Groq Service | ✅ Running | `/health` | Multi-language + AI chat (moved from 8002) |
| **8004** | KYC OCR Service | ✅ Running | `/health` | PAN/Aadhaar extraction + verification |
| **8005** | Blockchain Audit Service | ⚠️ Not Running | `/health` | Document signing + verification |

### 🔍 **Service Details**

#### ✅ **Port 8003: Translation + Groq Service**
- **Status**: ✅ Running
- **Response**: `{"status":"healthy","uptime_seconds":2986,"groq_api_reachable":true,"primary_model":"llama-3.3-70b-versible"}`
- **Features**: Multi-language support, Groq LLaMA integration, Hinglish detection

#### ✅ **Port 8004: KYC OCR Service** 
- **Status**: ✅ Running
- **Response**: `{"status":"ok","uptime_seconds":207,"ocr_engine":"rapidocr-onnxruntime"}`
- **Features**: PAN extraction, Aadhaar extraction, PDF processing, name matching

#### ⚠️ **Port 8000: Underwriting Service**
- **Status**: ❌ Not Running (timeout)
- **Expected**: Credit scoring with XGBoost model
- **Features**: Risk assessment, SHAP explanations, credit scoring

#### ⚠️ **Port 8001: Negotiation Service**
- **Status**: ❌ Not Running (timeout)  
- **Expected**: Rate negotiation logic
- **Features**: EMI calculation, concession steps, negotiation limits

#### ⚠️ **Port 8002: Empty**
- **Status**: ❌ Not Running
- **Note**: Translation service moved to port 8003

#### ⚠️ **Port 8005: Blockchain Audit Service**
- **Status**: ❌ Not Running (timeout)
- **Expected**: Document signing and verification
- **Features**: RSA cryptography, PDF generation, QR codes

## 🛠️ **Commands to Start All Services**

### **Option 1: Startup Script (Recommended)**
```bash
# From project root
start_all_services.bat
```

### **Option 2: Manual Commands**

```powershell
# Terminal 1 - Underwriting Service (Port 8000)
cd "c:\Users\Agniv Dutta\BTECH-LY-Project-Loanease\backend"
python -m uvicorn app.main:app --port 8000 --reload --host 0.0.0.0

# Terminal 2 - Negotiation Service (Port 8001)
cd "c:\Users\Agniv Dutta\BTECH-LY-Project-Loanease\negotiation_backend"
python -m uvicorn app.main:app --port 8001 --reload --host 0.0.0.0

# Terminal 3 - Translation + Groq Service (Port 8003)
cd "c:\Users\Agniv Dutta\BTECH-LY-Project-Loanease\translation_backend"
python -m uvicorn app.main:app --port 8003 --reload --host 0.0.0.0

# Terminal 4 - KYC OCR Service (Port 8004)
cd "c:\Users\Agniv Dutta\BTECH-LY-Project-Loanease\kyc_backend"
python -m uvicorn app.main:app --port 8004 --reload --host 0.0.0.0

# Terminal 5 - Blockchain Audit Service (Port 8005)
cd "c:\Users\Agniv Dutta\BTECH-LY-Project-Loanease\backend"
python -m uvicorn blockchain_service:app --port 8005 --reload --host 0.0.0.0

# Terminal 6 - Pipeline Orchestrator (Port 8002)
cd "c:\Users\Agniv Dutta\BTECH-LY-Project-Loanease\backend"
python -m uvicorn pipeline:app --port 8002 --reload --host 0.0.0.0
```

## 🌐 **Frontend API Configuration**

The frontend should be configured to use these endpoints:

```typescript
// API Endpoints Configuration
const API_ENDPOINTS = {
  // Underwriting
  UNDERWRITING: 'http://localhost:8000',
  
  // Negotiation  
  NEGOTIATION: 'http://localhost:8001',
  
  // Translation + Groq
  TRANSLATION: 'http://localhost:8003',
  
  // KYC OCR
  KYC: 'http://localhost:8004',
  
  // Blockchain Audit
  BLOCKCHAIN: 'http://localhost:8005',
  
  // Pipeline Orchestrator
  PIPELINE: 'http://localhost:8002'
};
```

## 📊 **Service Dependencies**

```
Frontend (Port 5173)
    ↓
┌─────────────────┬─────────────────┬─────────────────┬─────────────────┬─────────────────┐
│   Underwriting  │   Negotiation   │   Translation   │     KYC OCR     │   Blockchain    │
│     8000        │      8001       │      8003       │      8004       │      8005        │
└─────────────────┴─────────────────┴─────────────────┴─────────────────┴─────────────────┘
                              ↓
                        Pipeline Orchestrator (Port 8002)
```

## 🔧 **Troubleshooting**

### **Common Issues:**
1. **Port Conflicts**: Services may conflict if not properly shut down
2. **Timeout Issues**: Services starting up may need more time
3. **Missing Dependencies**: Ensure all requirements.txt are installed

### **Health Check Commands:**
```bash
curl http://localhost:8000/health  # Underwriting
curl http://localhost:8001/health  # Negotiation
curl http://localhost:8003/health  # Translation + Groq
curl http://localhost:8004/health  # KYC OCR
curl http://localhost:8005/health  # Blockchain
curl http://localhost:8002/health  # Pipeline Orchestrator
```

## 📝 **Notes**

- Port 8002 is currently unused (translation moved to 8003)
- KYC service was moved from 8003 to 8004 to fix conflicts
- Only 2 out of 6 services are currently running
- Frontend needs to be updated to use correct ports
