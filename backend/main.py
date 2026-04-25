from contextlib import asynccontextmanager
import logging
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel

# Import all routers
from agents.kyc_agent.main import router as kyc_router
from agents.underwriting_agent.main import router as underwriting_router
from agents.negotiation_agent.main import router as negotiation_router
from agents.blockchain_agent.main import router as blockchain_router
from agents.master_agent.main import router as master_router
from routers.ai_router import router as ai_router
from services.groq_service import GroqService
from services.memory import ConversationMemory
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

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("LoanEase backend starting")

    # 1) Groq service.
    app.state.groq_service = GroqService(
        api_key=settings.GROQ_API_KEY,
        primary_model=settings.GROQ_MODEL_PRIMARY,
        fallback_model=settings.GROQ_MODEL_FALLBACK,
        timeout=settings.GROQ_TIMEOUT,
    )
    await app.state.groq_service.verify_connection()

    # 2) Redis (optional) with graceful fallback.
    redis_client: Any = None
    if settings.REDIS_URL:
        try:
            import redis.asyncio as redis

            redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
            await redis_client.ping()
        except Exception:
            logger.warning("Redis unavailable — using in-process memory")
            redis_client = None
    else:
        logger.info("Redis URL not configured; running in dev mode")

    # 3) Conversation memory wired to Redis or local fallback.
    app.state.memory = ConversationMemory(redis_client)
    app.state.saved_sessions: Dict[str, Dict[str, Any]] = {}
    app.state.escalation_preferences: Dict[str, Dict[str, Any]] = {}

    yield

    # 4) Shutdown clean-up.
    if redis_client is not None:
        await redis_client.aclose()
    logger.info("LoanEase backend shutting down")

app = FastAPI(
    title="LoanEase API",
    description="Agentic AI Personal Loan System",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
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
app.include_router(ai_router)

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
    }

# Master health check across all agents
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": app.version,
        "groq": "connected",
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
