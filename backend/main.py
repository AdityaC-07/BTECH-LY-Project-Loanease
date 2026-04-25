from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import time
from datetime import datetime
from typing import Any, Dict

from pydantic import BaseModel

# Import all routers
from agents.kyc_agent.main import router as kyc_router
from agents.underwriting_agent.main import router as underwriting_router
from agents.negotiation_agent.main import router as negotiation_router
from agents.blockchain_agent.enhanced_main import router as blockchain_router
from agents.master_agent.main import router as master_router
from core.groq_client import router as groq_router
from core.config import settings
from core.session import session_store

logger = logging.getLogger("loanease")


class SessionSaveRequest(BaseModel):
    session_id: str
    messages: list[dict]
    stage: str
    applicant_data: dict


class SessionResponse(BaseModel):
    session_id: str
    messages: list[dict]
    stage: str
    applicant_data: dict


class EscalationPreferenceRequest(BaseModel):
    session_id: str
    preferred_time: str
    whatsapp_opt_in: bool

# Global uptime tracking
_start_time = time.time()

def get_uptime() -> int:
    return int(time.time() - _start_time)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP — runs once when server starts
    logger.info("🚀 LoanEase backend starting...")
    
    # Load XGBoost model into memory once
    from agents.underwriting_agent.main import load_model
    load_model()
    logger.info("✅ XGBoost model loaded")
    
    # Initialize enhanced blockchain ledger
    from agents.blockchain_agent.enhanced_main import init_ledger
    init_ledger()
    logger.info("✅ Enhanced blockchain ledger initialized")
    
    # Generate/load RSA keys (included in init_ledger)
    logger.info("✅ Cryptographic keys ready")
    
    # Initialize RapidOCR engine
    from services.ocr import init_ocr
    init_ocr()
    logger.info("✅ OCR engine ready")
    
    # Skip Groq API verification during startup to avoid initialization issues
    # Groq service will be initialized lazily when needed
    logger.info("ℹ️  Groq API service will be initialized on first use")
    
    logger.info("🎯 All 5 agents ready")
    logger.info("📡 LoanEase API running on http://localhost:8000")
    
    yield  # Server runs here
    
    # SHUTDOWN
    logger.info("🛑 LoanEase backend shutting down")

app = FastAPI(
    title="LoanEase API",
    description="Agentic AI Personal Loan System",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://localhost:8081",
        "http://localhost:8082"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Mount all routers with clean prefixes
app.include_router(kyc_router, prefix="/kyc", tags=["KYC Agent"])
app.include_router(underwriting_router, prefix="/credit", tags=["Credit Agent"])
app.include_router(negotiation_router, prefix="/negotiate", tags=["Negotiation Agent"])
app.include_router(blockchain_router, prefix="/blockchain", tags=["Blockchain Agent"])
app.include_router(master_router, prefix="/pipeline", tags=["Master Orchestrator"])
app.include_router(groq_router, prefix="/ai", tags=["AI Agent"])

# Root health check
@app.get("/")
async def root():
    return {
        "service": "LoanEase Agentic AI Backend",
        "version": "1.0.0",
        "status": "running",
        "agents": [
            "KYCVerificationAgent",
            "CreditUnderwritingAgent", 
            "NegotiationAgent",
            "BlockchainAuditAgent",
            "MasterOrchestratorAgent"
        ],
        "docs": "http://localhost:8000/docs",
        "started_at": datetime.fromtimestamp(_start_time).isoformat()
    }

# Master health check across all agents
@app.get("/health")
async def health():
    from agents.underwriting_agent.main import model_loaded
    from agents.blockchain_agent.enhanced_main import ledger_ready
    from services.ocr import ocr_ready
    
    return {
        "status": "healthy",
        "uptime_seconds": get_uptime(),
        "agents": {
            "kyc_agent": "ready" if ocr_ready() else "degraded",
            "underwriting_agent": "ready" if model_loaded() else "error",
            "negotiation_agent": "ready",
            "blockchain_agent": "ready" if ledger_ready() else "error",
            "master_agent": "ready"
        },
        "groq": app.state.groq_service.status(),
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/session/save", response_model=SessionResponse)
async def save_session(payload: SessionSaveRequest):
    app.state.saved_sessions[payload.session_id] = payload.model_dump()
    session_store.get_or_create(
        payload.session_id,
        {
            "stage": payload.stage,
            "data": payload.applicant_data,
        },
    )
    return SessionResponse(**app.state.saved_sessions[payload.session_id])


@app.get("/session/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    if session_id not in app.state.saved_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionResponse(**app.state.saved_sessions[session_id])


@app.post("/escalation/preferences")
async def save_escalation_preferences(payload: EscalationPreferenceRequest):
    app.state.escalation_preferences[payload.session_id] = payload.model_dump()
    return {"status": "saved", "session_id": payload.session_id}
