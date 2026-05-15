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
from routers.demo_router import router as demo_router
from startup_selftest import run_startup_selftest
from services.groq_service import GroqService
from services.memory import ConversationMemory
from services.ocr import init_ocr, ocr_ready
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

    # 0) OCR engine (best effort; degraded mode if unavailable)
    try:
        init_ocr()
        if ocr_ready():
            logger.info("OCR engine initialized")
        else:
            logger.warning("OCR engine unavailable; KYC OCR endpoints may return degraded status")
    except Exception as exc:
        logger.warning("OCR initialization failed; continuing in degraded mode: %s", str(exc))

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

    # ── Startup self-test ────────────────────────────────────────
    await run_startup_selftest(app)

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
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Mount all routers with clean prefixes
app.include_router(kyc_router, prefix="/kyc", tags=["KYC Agent"])
app.include_router(underwriting_router, prefix="/credit", tags=["Credit Agent"])
app.include_router(negotiation_router, prefix="/negotiate", tags=["Negotiation Agent"])
app.include_router(blockchain_router, prefix="/blockchain", tags=["Blockchain Agent"])
app.include_router(master_router, prefix="/pipeline/agent", tags=["Master Orchestrator"])
app.include_router(ai_router)
app.include_router(demo_router, prefix="/demo", tags=["Demo Utilities"])

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


@app.get("/analytics/{session_id}")
async def get_analytics(session_id: str):
    """Get comprehensive analytics data for post-sanction dashboard"""
    try:
        # Get session data
        session = session_store.get(session_id)
        session_data = {}
        
        if session:
            session_data = session.get("data", {})
        elif session_id in app.state.saved_sessions:
            session_data = app.state.saved_sessions[session_id].get("applicant_data", {})
        else:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Extract loan data
        loan_amount = session_data.get("loan_amount", 500000)
        interest_rate = session_data.get("offered_rate", 11.0)
        tenure_months = session_data.get("loan_term", 60)
        
        # Calculate EMI using standard formula
        monthly_rate = interest_rate / 12 / 100
        emi = loan_amount * monthly_rate * (1 + monthly_rate) ** tenure_months / ((1 + monthly_rate) ** tenure_months - 1)
        total_payable = emi * tenure_months
        total_interest = total_payable - loan_amount
        
        # Get credit assessment data
        credit_score = session_data.get("credit_score", 720)
        risk_score = session_data.get("risk_score", 75)
        
        # Determine risk tier
        if risk_score >= 75:
            risk_tier = "Low Risk"
        elif risk_score >= 50:
            risk_tier = "Medium Risk"
        else:
            risk_tier = "High Risk"
        
        # SHAP factors (mock data if not available)
        shap_factors = session_data.get("shap_explanation", [
            {"feature": "Credit History", "value": 0.42, "direction": "positive"},
            {"feature": "Income Level", "value": 0.28, "direction": "positive"},
            {"feature": "Loan Amount", "value": -0.15, "direction": "negative"},
            {"feature": "Employment Stability", "value": 0.18, "direction": "positive"},
            {"feature": "Debt-to-Income", "value": -0.08, "direction": "negative"}
        ])
        
        # Negotiation summary
        opening_rate = session_data.get("initial_rate", 11.5)
        final_rate = interest_rate
        rounds_taken = session_data.get("negotiation_rounds", 2)
        monthly_savings = (opening_rate - final_rate) * loan_amount / 12 / 100
        total_savings = monthly_savings * tenure_months
        
        # Benchmark data (static averages)
        benchmark = {
            "avg_credit_score": 720,
            "avg_income_normalized": 70,
            "avg_loan_to_income": 65,
            "avg_employment": 75,
            "avg_repayment": 80,
            "avg_coapplicant": 60
        }
        
        return {
            "loan_data": {
                "amount": loan_amount,
                "rate": interest_rate,
                "tenure_months": tenure_months,
                "emi": round(emi, 2),
                "total_payable": round(total_payable, 2),
                "total_interest": round(total_interest, 2)
            },
            "credit_data": {
                "credit_score": credit_score,
                "risk_score": risk_score,
                "risk_tier": risk_tier,
                "shap_factors": shap_factors
            },
            "negotiation_summary": {
                "opening_rate": opening_rate,
                "final_rate": final_rate,
                "rounds_taken": rounds_taken,
                "total_savings": round(total_savings, 2)
            },
            "benchmark": benchmark
        }
        
    except Exception as e:
        logger.error(f"Analytics error for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get analytics: {str(e)}")


# ── PIPELINE START OVERRIDE ───────────────────────────────────────
# The master_router /pipeline/start expects {customer_name, initial_message}
# but the frontend sends a full loan payload. This override handles it.

@app.post("/pipeline/start")
async def pipeline_start_override(request: dict):
    """Accept frontend's full pipeline start payload and return session tracking info."""
    session_id = request.get("session_id") or f"LE-{__import__('uuid').uuid4().hex[:10].upper()}"
    from core.session import session_store as _ss
    _ss.get_or_create(session_id, {
        "stage": "INITIATED",
        "data": {
            "pan_number": request.get("pan_number"),
            "applicant_name": request.get("applicant_name"),
            "loan_amount": request.get("loan_amount"),
            "loan_term": request.get("loan_term"),
            "offered_rate": request.get("offered_rate"),
        }
    })
    return {
        "session_id": session_id,
        "status": "ACTIVE",
        "message": "Pipeline started",
        "pipeline_status": "ACTIVE",
        "agent_trace": [],
    }


@app.get("/pipeline/log/{session_id}")
async def pipeline_log(session_id: str):
    """Return pipeline execution log for a session."""
    from core.session import session_store as _ss
    session = _ss.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session_id,
        "pipeline_status": session.get("stage", "ACTIVE"),
        "agent_trace": session.get("agent_log", []),
    }


@app.get("/pipeline/global-logs")
async def get_global_logs(limit: int = 20):
    """Get the most recent system-wide agent activity"""
    return {
        "logs": session_store.get_global_activity(limit),
        "total_active_sessions": len(session_store._sessions),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ── CREDIT SCORE ALIAS ────────────────────────────────────────────
# Frontend calls GET /credit-score/{pan} — proxy to the underwriting agent logic

@app.get("/credit-score/{pan_number}")
async def get_credit_score_by_pan(pan_number: str):
    """
    GET /credit-score/{pan} — used by the frontend after KYC to fetch
    the simulated CIBIL score and risk tier for the applicant.
    """
    from services.credit_score import simulate_cibil_score, calculate_credit_score
    from agents.underwriting_agent.main import predict_credit_score

    pan = pan_number.strip().upper()
    try:
        cibil_score = simulate_cibil_score(pan)
        features = {"cibil_score": cibil_score}
        xgboost_score = predict_credit_score(features)
        result = calculate_credit_score(cibil_score, xgboost_score)

        credit_score = result["final_score"]
        risk_category = result.get("risk_category", "MEDIUM")

        # Map risk category to band label and color
        band_map = {
            "LOW":         {"label": "Low Risk",    "color": "green"},
            "MEDIUM":      {"label": "Medium Risk", "color": "yellow"},
            "MEDIUM-HIGH": {"label": "Medium-High Risk", "color": "orange"},
            "HIGH":        {"label": "High Risk",   "color": "red"},
        }
        band = band_map.get(risk_category, {"label": risk_category, "color": "yellow"})

        return {
            "pan_number": pan[:5] + "XXXXX",  # masked
            "credit_score": credit_score,
            "credit_score_out_of": 900,
            "credit_band": band["label"],
            "credit_band_color": band["color"],
            "eligible_for_loan": not result.get("hard_reject", False),
            "risk_category": risk_category,
            "message_en": (
                f"Your credit score is {credit_score}. "
                f"You are in the {band['label']} tier."
            ),
            "message_hi": (
                f"आपका credit score {credit_score} है। "
                f"आप {band['label']} tier में आते हैं।"
            ),
        }
    except Exception as e:
        logger.error(f"Credit score lookup failed for {pan}: {e}")
        raise HTTPException(status_code=500, detail=f"Credit score lookup failed: {str(e)}")
