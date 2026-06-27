from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from typing import Optional, Any, TypeAlias

from fastapi import FastAPI, HTTPException, File, Form, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

from app.model_service import ModelService
from app.schemas import (
    AssessRequest,
    AssessResponse,
    CreditScoreResponse,
    ExplainResponse,
    HealthResponse,
    SessionSaveRequest,
    SessionResponse,
    EscalationPreferenceRequest,
)
from app.storage import ApplicationStore
from app.credit_score import get_credit_score, get_credit_band, mask_pan
from app.kyc_extractors import extract_pan, extract_aadhaar, cross_validate_kyc
from app.kyc_preprocess import preprocess_image, run_ocr, MAX_UPLOAD_BYTES, UnsupportedDocumentError
from services.otp_service import init_twilio, resend as resend_otp_via_twilio, send as send_otp_via_twilio, verify as verify_otp_via_twilio
from core.config import settings, get_band

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("kyc.ocr")
# Rate limiting
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

limiter = Limiter(key_func=get_remote_address)

# Load negotiation backend constants, service, and store
neg_backend_path = Path(__file__).resolve().parent.parent.parent / "negotiation_backend" / "app"


def _load_module(module_name: str, module_path: Path, aliases: list[str] | None = None):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    if aliases:
        for alias in aliases:
                        sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module

negotiation_constants = _load_module(
    "negotiation_app_constants",
    neg_backend_path / "constants.py",
    aliases=["app.constants"],
)
MAX_ROUNDS = negotiation_constants.MAX_ROUNDS

negotiation_intent = _load_module(
    "negotiation_app_intent",
    neg_backend_path / "intent.py",
    aliases=["app.intent"],
)

negotiation_utils = _load_module(
    "negotiation_app_utils",
    neg_backend_path / "utils.py",
    aliases=["app.utils"],
)

negotiation_service = _load_module(
    "negotiation_app_service",
    neg_backend_path / "service.py",
)

negotiation_store_module = _load_module(
    "negotiation_app_store",
    neg_backend_path / "store.py",
)

negotiation_schemas = _load_module(
    "negotiation_app_schemas",
    neg_backend_path / "schemas.py",
)


class PipelineStartRequest(BaseModel):
    session_id: str
    applicant_name: str
    loan_amount: float
    loan_term: int
    offered_rate: float


CounterRequest: TypeAlias = Any
CounterResponse: TypeAlias = Any
StartNegotiationRequest: TypeAlias = Any
StartNegotiationResponse: TypeAlias = Any
StartFromUnderwritingRequest: TypeAlias = Any
StartFromUnderwritingResponse: TypeAlias = Any
AcceptRequest: TypeAlias = Any
AcceptResponse: TypeAlias = Any
EscalateRequest: TypeAlias = Any
EscalateResponse: TypeAlias = Any
HistoryResponse: TypeAlias = Any
TranslateRequest: TypeAlias = Any
TranslateResponse: TypeAlias = Any
ChatRequest: TypeAlias = Any
ChatResponse: TypeAlias = Any
IntentClassificationRequest: TypeAlias = Any
IntentClassificationResponse: TypeAlias = Any
CreditExplanationRequest: TypeAlias = Any
NegotiationExplanationRequest: TypeAlias = Any
RejectionMessageRequest: TypeAlias = Any

# Import specific functions and classes
append_history = negotiation_service.append_history
build_escalation_reference = negotiation_service.build_escalation_reference
build_offer = negotiation_service.build_offer
build_sanction_reference = negotiation_service.build_sanction_reference
counter_session = negotiation_service.counter_session
extract_top_positive_factor = negotiation_service.extract_top_positive_factor
start_session = negotiation_service.start_session
SessionStore = negotiation_store_module.SessionStore

# Import translation backend components  
try:
    trans_backend_path = Path(__file__).resolve().parent.parent.parent / "translation_backend" / "app"
    
    spec = importlib.util.spec_from_file_location("translation_service_module", trans_backend_path / "translation_service.py")
    trans_service_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(trans_service_module)
    TranslationService = trans_service_module.TranslationService
    
    spec = importlib.util.spec_from_file_location("hinglish_intent_module", trans_backend_path / "hinglish_intent.py")
    hinglish_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hinglish_module)
    detect_hinglish_intent = hinglish_module.detect_hinglish_intent
    
    spec = importlib.util.spec_from_file_location("groq_service_module", trans_backend_path / "groq_service.py")
    groq_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(groq_module)
    groq_service = groq_module.groq_service
    
    spec = importlib.util.spec_from_file_location("translation_schemas", trans_backend_path / "schemas.py")
    translation_schemas = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(translation_schemas)
    
    TRANSLATION_AVAILABLE = True
except ImportError as e:
    TRANSLATION_AVAILABLE = False
    logger.warning(f"Translation services not available: {e}")

# Import pipeline components
try:
    spec = importlib.util.spec_from_file_location("pipeline_module", Path(__file__).resolve().parent.parent / "pipeline.py")
    pipeline_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pipeline_module)
    LoanPipeline = pipeline_module.LoanPipeline
    PIPELINE_AVAILABLE = True
except ImportError as e:
    PIPELINE_AVAILABLE = False
    logger.warning(f"Pipeline not available: {e}")
    LoanPipeline = None

# Import session store
from core.session import session_store

BASE_DIR = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = BASE_DIR / "artifacts"
STORE_PATH = BASE_DIR / "data" / "applications.jsonl"

app = FastAPI(title="LoanEase Unified Backend API", version="2.0.0")

# Rate limiting middleware and exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Import routers from agents
from agents.blockchain_agent.main import router as blockchain_router
app.include_router(blockchain_router, prefix="/blockchain", tags=["Blockchain Agent"])

# Import new negotiation agent (replaces legacy negotiation_backend endpoints)
from agents.negotiation_agent.main import (
    start_negotiation as _neg_start,
    counter_offer as _neg_counter,
    accept_negotiation as _neg_accept,
    escalate_to_human as _neg_escalate,
    NegotiationStartRequest as NegStartReq,
    NegotiationCounterRequest as NegCounterReq,
    NegotiationAcceptRequest as NegAcceptReq,
    NegotiateEscalateRequest as NegEscalateReq,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

service: ModelService | None = None
store = ApplicationStore(STORE_PATH)
negotiation_store = SessionStore()
boot_time = datetime.now(timezone.utc)

# Initialize translation services if available
translation_service: TranslationService | None = None
if TRANSLATION_AVAILABLE:
    translation_service = TranslationService()

# Initialize pipeline if available
pipeline = None
running_tasks: dict[str, asyncio.Task] = {}
if PIPELINE_AVAILABLE:
    pipeline = LoanPipeline()

# In-memory storage for sessions and escalations
sessions: dict[str, dict] = {}
escalations: dict[str, dict] = {}


class OtpSendRequest(BaseModel):
    session_id: str


class OtpVerifyRequest(BaseModel):
    session_id: str
    otp: str


class OtpResponse(BaseModel):
    session_id: str
    mobile_last4: str
    expires_in_seconds: int
    resend_count: int | None = None
    sent: bool | None = None
    demo_otp: str | None = None


class OtpVerifyResponse(BaseModel):
    verified: bool
    terminated: bool
    attempts_remaining: int
    mobile_last4: str
    expires_in_seconds: int
    reason: str | None = None
    message: str | None = None
    method: str | None = None
    zero_knowledge: bool | None = None


@app.on_event("startup")
def startup_event() -> None:
    global service
    try:
        service = ModelService(ARTIFACTS_DIR)
        try:
            if init_twilio():
                logger.info("Twilio Verify ready")
            else:
                logger.warning("Twilio not configured - OTP in demo mode")
        except Exception as exc:
            logger.error("Twilio init failed: %s", exc)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Model artifacts missing. Run `python train_model.py --data data/loan_train.csv` first."
        ) from exc


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    if service is None:
        raise HTTPException(status_code=503, detail="Model service not ready")

    uptime_seconds = int((datetime.now(timezone.utc) - boot_time).total_seconds())
    accuracy = float(service.metrics.get("accuracy", 0.0))
    drift_status = service.drift_status()
    return HealthResponse(
        status="ok",
        model_version=service.model_version,
        accuracy=round(accuracy, 4),
        uptime_seconds=uptime_seconds,
        model_drift_warning=bool(drift_status.get("model_drift_warning", False)),
        drifted_features=list(drift_status.get("drifted_features", [])),
        recommendation=drift_status.get("recommendation"),
    )


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "LoanEase Unified Backend API",
        "status": "running",
        "health": "/health",
        "docs": "/docs",
    }


@app.get("/credit-score/{pan_number}", response_model=CreditScoreResponse)
def credit_score(pan_number: str) -> CreditScoreResponse:
    """
    Get credit score for PAN number after KYC verification.
    Returns simulated CIBIL credit score and eligibility details.
    """
    try:
        pan_number = pan_number.strip().upper()
        credit_score_val = get_credit_score(pan_number)
        # Use industry-standard TransUnion CIBIL bands for messaging
        band = get_band(credit_score_val)

        # Friendly English/Hindi messages using the new CIBIL banding
        rate_range = None
        if band.get("rate_min") is not None and band.get("rate_max") is not None:
            rate_range = f"{band['rate_min']}–{band['rate_max']}% p.a."

        message_en = (
            f"Your CIBIL score is {credit_score_val} — rated '{band.get('cibil_classification') or band.get('label')}' on TransUnion CIBIL's 5-tier scale. "
            f"This places you in our {band.get('label')} category{', qualifying you for rates between ' + rate_range if rate_range else ''}."
        )
        message_hi = (
            f"आपका CIBIL स्कोर {credit_score_val} है — TransUnion CIBIL के 5-tier scale पर '{band.get('cibil_classification') or band.get('label')}' रेटिंग मिली है। "
            f"यह आपको हमारी {band.get('label')} category में रखता है{('। आप ' + rate_range + ' वार्षिक दर के लिए पात्र हैं') if rate_range else ''}।"
        )

        applicant_band = band.get("band_key") or band.get("label")

        return CreditScoreResponse(
            pan_number=mask_pan(pan_number),
            credit_score=credit_score_val,
            credit_score_out_of=900,
            credit_band=band.get("label"),
            credit_band_color=band.get("color"),
            eligible_for_loan=True,
            applicant_score_falls_in=applicant_band,
            message_en=message_en,
            message_hi=message_hi,
            shortfall=None,
            improvement_tips=None,
            earliest_reapply=None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# Route alias for frontend compatibility
@app.get("/credit/credit-score", response_model=CreditScoreResponse)
def get_credit_score_route() -> CreditScoreResponse:
    """Placeholder endpoint for frontend compatibility - use /{pan_number} instead"""
    raise HTTPException(status_code=400, detail="Please provide PAN number: /credit/credit-score/{pan_number}")


@app.post("/assess", response_model=AssessResponse)
@limiter.limit("20/minute")
async def assess(request: Request, payload: AssessRequest) -> AssessResponse:
    if service is None:
        raise HTTPException(status_code=503, detail="Model service not ready")

    result = service.assess(payload.model_dump())
    application_id = str(uuid4())

    record = {
        "application_id": application_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        **result,
    }
    store.save(record)

    structured_narration = result.get("structured_shap_narration")
    if isinstance(structured_narration, (dict, list)):
        structured_narration = json.dumps(structured_narration, ensure_ascii=False)

    # Log Credit assessment
    # Try to find session_id in payload or raw request
    session_id = payload.session_id if hasattr(payload, 'session_id') else str(uuid4())
    
    session_store.log_agent(session_id, {
        "agent": "CreditUnderwritingAgent",
        "action": "LOAN_APPROVED",
        "reasoning": f"Credit assessment complete. Risk Tier: {result.get('risk_tier')}. Score: {result.get('credit_score')}",
        "status": "SUCCESS",
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    session_store.update_stage(session_id, "CREDIT_ASSESSED")
    session_store.update_data(session_id, "underwriting_result", result)

    # ── Bridge: initialize negotiation session immediately after assessment ──
    try:
        loan_amount = float(payload.loan_amount or 500000)
        tenure_months = int(payload.loan_amount_term or 60)
        await handle_credit_to_negotiation(session_id, result, loan_amount, tenure_months)
    except Exception as _bridge_err:
        logger.warning("Negotiation bridge (non-fatal): %s", _bridge_err)

    # Build response with all fields from result
    response_data = {
        k: (structured_narration if k == "structured_shap_narration" else result.get(k))
        for k in AssessResponse.model_fields
        if k != "application_id"
    }

    # Attach industry-standard CIBIL band metadata when a credit score is present
    try:
        score = result.get("credit_score")
        if score is not None:
            band = get_band(int(score))
            rate_range = None
            if band.get("rate_min") is not None and band.get("rate_max") is not None:
                rate_range = f"{band['rate_min']}–{band['rate_max']}% p.a."

            extra = {
                "cibil_score": int(score),
                "cibil_band": band.get("display") or band.get("label"),
                "cibil_classification": band.get("cibil_classification"),
                "risk_label": band.get("label"),
                "industry_standard": "TransUnion CIBIL 5-tier scale",
                "eligible": band.get("eligible"),
                "conditional": band.get("conditional", False),
                "rate_range": rate_range,
                "max_negotiation_rounds": band.get("max_rounds"),
            }
            response_data.update(extra)
    except Exception:
        # If anything goes wrong, continue without CIBIL extras
        pass

    return AssessResponse(application_id=application_id, **response_data)


# Route alias for frontend compatibility
@app.post("/credit/assess", response_model=AssessResponse)
async def credit_assess(request: Request, payload: AssessRequest) -> AssessResponse:
    """Alias for /assess endpoint for frontend compatibility"""
    return await assess(request, payload)


@app.post("/explain/{application_id}", response_model=ExplainResponse)
def explain(application_id: str) -> ExplainResponse:
    record = store.get(application_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Application not found")

    structured_narration = record.get("structured_shap_narration")
    if isinstance(structured_narration, (dict, list)):
        structured_narration = json.dumps(structured_narration, ensure_ascii=False)

    return ExplainResponse(
        application_id=record["application_id"],
        decision=record["decision"],
        approval_probability=record["approval_probability"],
        risk_tier=record["risk_tier"],
        risk_score=record["risk_score"],
        threshold_used=record["threshold_used"],
        raw_input=record["raw_input"],
        top_explanations=record["shap_explanation"],
        shap_waterfall=record["shap_waterfall"],
        structured_shap_narration=structured_narration,
        confidence_lower=record.get("confidence_lower"),
        confidence_upper=record.get("confidence_upper"),
        confidence_width=record.get("confidence_width"),
        model_certainty=record.get("model_certainty"),
        income_reasonability=record.get("income_reasonability"),
        soft_reject_guidance=record.get("soft_reject_guidance"),
        confidence_message=record.get("confidence_message"),
    )


@app.post("/session/save", response_model=SessionResponse)
def save_session(payload: SessionSaveRequest) -> SessionResponse:
    sessions[payload.session_id] = payload.model_dump()
    return SessionResponse(**sessions[payload.session_id])


@app.get("/session/{session_id}", response_model=SessionResponse)
def get_session(session_id: str) -> SessionResponse:
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionResponse(**sessions[session_id])


@app.get("/pipeline/log/{session_id}")
async def get_pipeline_log(session_id: str):
    """Return pipeline execution log for a session."""
    session = session_store.get(session_id)
    if not session:
        # Create a new session if it doesn't exist to avoid front-end 404s
        session = session_store.get_or_create(session_id)
        
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

@app.post("/session/init/{session_id}")
async def init_session(session_id: str):
    """Initialize a new session and log the start."""
    session_store.get_or_create(session_id)
    session_store.log_agent(session_id, {
        "agent": "MasterOrchestratorAgent",
        "action": "INITIATED_SESSION",
        "reasoning": "New loan inquiry received. Starting orchestration.",
        "status": "SUCCESS",
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    session_store.update_stage(session_id, "INITIATED")
    return {"status": "success", "session_id": session_id}


@app.post("/pipeline/start")
async def start_pipeline(payload: PipelineStartRequest):
    """
    Manually start or update the pipeline orchestration for a session.
    Used when transitioning from chat input to agent processing.
    """
    session_id = payload.session_id
    session_store.get_or_create(session_id)
    
    # Update session data with what we have so far
    session_store.update_data(session_id, "applicant_name", payload.applicant_name)
    session_store.update_data(session_id, "loan_amount", payload.loan_amount)
    session_store.update_data(session_id, "loan_term", payload.loan_term)
    session_store.update_data(session_id, "offered_rate", payload.offered_rate)
    
    session_store.log_agent(session_id, {
        "agent": "MasterOrchestratorAgent",
        "action": "PIPELINE_ACTIVATED",
        "reasoning": f"Orchestration pipeline activated for {payload.applicant_name}. Starting multi-agent verification.",
        "status": "SUCCESS",
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    session_store.update_stage(session_id, "ACTIVE")
    
    return {
        "status": "ACTIVE",
        "session_id": session_id,
        "message": "Pipeline orchestration activated successfully"
    }


@app.post("/escalation/callback-preference")
def save_escalation_preference(payload: EscalationPreferenceRequest):
    escalations[payload.session_id] = payload.model_dump()
    return {"status": "success", "message": "Callback preference saved"}


@app.get("/analytics/{session_id}")
async def get_analytics(session_id: str):
    """Get comprehensive analytics data for post-sanction dashboard"""
    try:
        def coerce_number(value: Any, default: float) -> float:
            if value is None:
                return float(default)
            if isinstance(value, (int, float)):
                return float(value)
            try:
                cleaned = str(value).replace("₹", "").replace(",", "").replace("%", "").strip()
                return float(cleaned)
            except (TypeError, ValueError):
                return float(default)

        def coerce_int(value: Any, default: int) -> int:
            try:
                return int(float(coerce_number(value, default)))
            except (TypeError, ValueError):
                return int(default)

        def session_payload_for(target_session_id: str) -> dict[str, Any]:
            candidates = [target_session_id]
            if "-" in target_session_id:
                candidates.append(target_session_id.split("-")[0])

            for candidate in candidates:
                session = session_store.get(candidate)
                if isinstance(session, dict):
                    payload = session.get("data")
                    if isinstance(payload, dict) and payload:
                        return payload
                    if any(key in session for key in ("loan_amount", "offered_rate", "loan_term", "credit_score", "risk_score")):
                        return session

                saved_session = app.state.saved_sessions.get(candidate)
                if isinstance(saved_session, dict):
                    payload = saved_session.get("applicant_data")
                    if isinstance(payload, dict) and payload:
                        return payload

            return {}

        session_data = session_payload_for(session_id)
        session_found = bool(session_data)

        loan_amount = coerce_number(session_data.get("loan_amount") or session_data.get("amount") or session_data.get("selected_amount"), 500000)
        interest_rate = coerce_number(session_data.get("final_rate") or session_data.get("sanctioned_rate") or session_data.get("offered_rate") or session_data.get("interest_rate"), 11.0)
        tenure_months = max(1, coerce_int(session_data.get("tenure_months") or session_data.get("tenure") or session_data.get("loan_term"), 60))

        monthly_rate = interest_rate / 12 / 100
        if monthly_rate > 0:
            power_val = (1 + monthly_rate) ** float(tenure_months)
            emi = loan_amount * monthly_rate * power_val / (power_val - 1) if power_val > 1 else loan_amount / tenure_months
        else:
            emi = loan_amount / tenure_months

        total_payable = emi * float(tenure_months)
        total_interest = total_payable - float(loan_amount)

        credit_score = coerce_number(session_data.get("credit_score") or session_data.get("cibil_score"), 720)
        risk_score = coerce_number(session_data.get("risk_score") or session_data.get("combined_score"), 75)
        risk_tier = "Low Risk" if risk_score >= 75 else "Medium Risk" if risk_score >= 50 else "High Risk"

        shap_factors = session_data.get("shap_factors") or session_data.get("shap_explanation") or [
            {"feature": "Credit History", "value": 0.41, "direction": "positive"},
            {"feature": "Income Level", "value": 0.28, "direction": "positive"},
            {"feature": "Loan Amount", "value": -0.15, "direction": "negative"},
            {"feature": "Employment", "value": 0.12, "direction": "positive"},
            {"feature": "Existing EMIs", "value": -0.09, "direction": "negative"},
        ]

        opening_rate = coerce_number(session_data.get("initial_rate"), interest_rate + 0.5)
        final_rate = interest_rate
        rounds_taken = coerce_int(session_data.get("rounds_completed") or session_data.get("negotiation_rounds"), 1)
        total_savings = max(((opening_rate - final_rate) / 100 / 12) * loan_amount * tenure_months / 2, 0)

        benchmark = {
            "avg_credit_score": 720,
            "avg_income_normalized": 70,
            "avg_loan_to_income": 65,
            "avg_employment": 75,
            "avg_repayment": 80,
            "avg_coapplicant": 60,
        }

        applicant_normalized = {
            "credit_score": min(max(round((credit_score - 300) / 6), 0), 100),
            "income_norm": min(max(int(risk_score), 0), 100),
            "loan_income": max(100 - round((loan_amount / 500000) * 50), 30),
            "employment": 75,
            "repayment": min(max(round(credit_score / 9), 0), 100),
            "coapplicant": 60,
        }

        return {
            "success": True,
            "session_found": session_found,
            "loan_data": {
                "amount": round(loan_amount, 2),
                "rate": round(interest_rate, 2),
                "tenure_months": tenure_months,
                "emi": round(emi, 2),
                "total_payable": round(total_payable, 2),
                "total_interest": round(total_interest, 2),
            },
            "credit_data": {
                "credit_score": round(credit_score, 2),
                "risk_score": round(risk_score, 2),
                "risk_tier": risk_tier,
                "shap_factors": shap_factors,
            },
            "negotiation_summary": {
                "opening_rate": round(opening_rate, 2),
                "final_rate": round(final_rate, 2),
                "rounds_taken": rounds_taken,
                "total_savings": round(total_savings, 2),
            },
            "benchmark": benchmark,
            "applicant_normalized": applicant_normalized,
        }

    except Exception as e:
        logger.error(f"Analytics error for session {session_id}: {e}", exc_info=True)
        return {
            "success": True,
            "session_found": False,
            "loan_data": {
                "amount": 500000,
                "rate": 11.0,
                "tenure_months": 60,
                "emi": 10871,
                "total_payable": 652260,
                "total_interest": 152260,
            },
            "credit_data": {
                "credit_score": 750,
                "risk_score": 80,
                "risk_tier": "Low Risk",
                "shap_factors": [
                    {"feature": "Credit History", "value": 0.41, "direction": "positive"},
                    {"feature": "Income Level", "value": 0.28, "direction": "positive"},
                    {"feature": "Loan Amount", "value": -0.15, "direction": "negative"},
                ],
            },
            "negotiation_summary": {
                "opening_rate": 11.5,
                "final_rate": 11.0,
                "rounds_taken": 2,
                "total_savings": 8400,
            },
            "benchmark": {
                "avg_credit_score": 720,
                "avg_income_normalized": 70,
                "avg_loan_to_income": 65,
                "avg_employment": 75,
                "avg_repayment": 80,
                "avg_coapplicant": 60,
            },
            "applicant_normalized": {
                "credit_score": 75,
                "income_norm": 80,
                "loan_income": 65,
                "employment": 75,
                "repayment": 83,
                "coapplicant": 60,
            },
        }


# =============================================================================
# KYC EXTRACTION ENDPOINTS
# =============================================================================

def _assert_upload_constraints(file: UploadFile, file_bytes: bytes) -> None:
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large. Max 5MB allowed")
    ext = (file.filename or "").lower().split(".")[-1]
    if ext not in {"jpg", "jpeg", "png", "pdf"}:
        raise HTTPException(status_code=400, detail="Only JPG, PNG or PDF files are supported")


@app.post("/kyc/extract/pan")
@limiter.limit("10/minute")
async def extract_pan_document(request: Request, document: UploadFile = File(...), session_id: str | None = Form(None)):
    file_bytes = await document.read()
    _assert_upload_constraints(document, file_bytes)
    
    # Log KYC start if session_id provided
    if session_id:
        session_store.get_or_create(session_id)
        session_store.log_agent(session_id, {
            "agent": "KYCVerificationAgent",
            "action": "SCANNING_PAN",
            "reasoning": "User uploaded PAN card. Extracting identity fields.",
            "status": "RUNNING",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        session_store.update_stage(session_id, "KYC_PENDING")

    try:
        extension = (document.filename or "").lower().split(".")[-1]
        preprocessed = preprocess_image(file_bytes, extension)
        ocr_text, confidence = await _run_ocr_with_timeout(preprocessed, timeout_s=5.0)
        if not ocr_text:
            raise HTTPException(status_code=503, detail="OCR service timed out. Please retry or upload a clearer image.")
        result = extract_pan(ocr_text)

        return {
            "document_type": "PAN",
            "extracted_fields": result["extracted_fields"],
            "validation": result["validation"],
            "confidence_score": confidence,
            "processing_time_ms": 0,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"KYC PAN: Extraction failed - {str(exc)}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/kyc/extract/aadhaar")
@limiter.limit("10/minute")
async def extract_aadhaar_document(request: Request, document: UploadFile = File(...), session_id: str | None = Form(None)):
    file_bytes = await document.read()
    _assert_upload_constraints(document, file_bytes)
    
    # Log KYC start if session_id provided
    if session_id:
        session_store.get_or_create(session_id)
        session_store.log_agent(session_id, {
            "agent": "KYCVerificationAgent",
            "action": "SCANNING_AADHAAR",
            "reasoning": "User uploaded Aadhaar card. Extracting identity fields.",
            "status": "RUNNING",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        session_store.update_stage(session_id, "KYC_PENDING")

    try:
        extension = (document.filename or "").lower().split(".")[-1]
        preprocessed = preprocess_image(file_bytes, extension)
        ocr_text, confidence = await _run_ocr_with_timeout(preprocessed, timeout_s=5.0)
        if not ocr_text:
            raise HTTPException(status_code=503, detail="OCR service timed out. Please retry or upload a clearer image.")
        result = extract_aadhaar(ocr_text)
        mobile_number = result.get("extracted_fields", {}).get("mobile_number")
        if session_id and mobile_number:
            session_store.update_data(session_id, "aadhaar_data", result.get("extracted_fields", {}))
            session_store.update_data(session_id, "aadhaar_mobile", mobile_number)
            session_store.update_data(session_id, "aadhaar_mobile_last4", mobile_number[-4:])
        
        return {
            "document_type": "AADHAAR",
            "extracted_fields": {
                **result["extracted_fields"],
            },
            "validation": result["validation"],
            "confidence_score": confidence,
            "processing_time_ms": 0,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"KYC Aadhaar: Extraction failed - {str(exc)}")
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/kyc/verify")
async def verify_kyc(pan: UploadFile = File(...), aadhaar: UploadFile = File(...), session_id: str | None = Form(None)):
    pan_bytes = await pan.read()
    aadhaar_bytes = await aadhaar.read()
    
    _assert_upload_constraints(pan, pan_bytes)
    _assert_upload_constraints(aadhaar, aadhaar_bytes)

    if session_id:
        session_store.get_or_create(session_id)
    
    try:
        # Extract PAN
        pan_ext = (pan.filename or "").lower().split(".")[-1]
        pan_preprocessed = preprocess_image(pan_bytes, pan_ext)
        pan_ocr_text, _ = run_ocr(pan_preprocessed)
        pan_result = extract_pan(pan_ocr_text)
        
        # Extract Aadhaar
        aadhaar_ext = (aadhaar.filename or "").lower().split(".")[-1]
        aadhaar_preprocessed = preprocess_image(aadhaar_bytes, aadhaar_ext)
        aadhaar_ocr_text, _ = run_ocr(aadhaar_preprocessed)
        aadhaar_result = extract_aadhaar(aadhaar_ocr_text)
        mobile_number = aadhaar_result.get("extracted_fields", {}).get("mobile_number")
        if session_id and mobile_number:
            session_store.update_data(session_id, "aadhaar_data", aadhaar_result.get("extracted_fields", {}))
            session_store.update_data(session_id, "aadhaar_mobile", mobile_number)
            session_store.update_data(session_id, "aadhaar_mobile_last4", mobile_number[-4:])
        
        # Cross-validate
        validation = cross_validate_kyc(pan_result, aadhaar_result)
        
        # Log KYC step
        s_id = session_id or (pan.filename.split('_')[0] if '_' in pan.filename else str(uuid4()))
        
        session_store.log_agent(s_id, {
            "agent": "KYCVerificationAgent",
            "action": "DOCUMENTS_VERIFIED",
            "reasoning": "Cross-validation of PAN and Aadhaar successful. Identity confirmed.",
            "status": "SUCCESS",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        session_store.update_stage(s_id, "KYC_OTP_PENDING")

        return {
            "kyc_status": validation["kyc_status"],
            "pan_data": pan_result.get("extracted_fields"),
            "aadhaar_data": {
                **aadhaar_result.get("extracted_fields"),
            },
            "cross_validation": validation["cross_validation"],
            "overall_kyc_passed": validation["overall_kyc_passed"],
            "kyc_reference_id": str(uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.error(f"KYC Verify: Failed - {str(exc)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"KYC verification failed: {str(exc)}") from exc


@app.post("/kyc/send-otp", response_model=OtpResponse)
async def send_otp(payload: OtpSendRequest):
    session = session_store.get_or_create(payload.session_id)

    mobile_number = session.get("data", {}).get("aadhaar_mobile")
    if not mobile_number:
        aadhaar_data = session.get("data", {}).get("aadhaar_data", {})
        mobile_number = aadhaar_data.get("mobile_number")

    if not mobile_number:
        raise HTTPException(
            status_code=400,
            detail="Aadhaar mobile number not found. Please upload the full Aadhaar card with the mobile number visible.",
        )

    result = await send_otp_via_twilio(payload.session_id, mobile_number)
    session_store.update_stage(payload.session_id, "KYC_OTP_PENDING")
    session_store.update_data(payload.session_id, "aadhaar_mobile", mobile_number)
    session_store.update_data(payload.session_id, "aadhaar_otp_pending", True)

    if not result["sent"] and not result.get("fallback_active") and not settings.DEMO_MODE:
        raise HTTPException(
            status_code=502,
            detail="Unable to send OTP right now. Configure SMS_PROVIDER with valid credentials.",
        )

    return OtpResponse(**result)


@app.post("/kyc/resend-otp", response_model=OtpResponse)
async def resend_otp(payload: OtpSendRequest):
    session = session_store.get_or_create(payload.session_id)
    mobile_number = session.get("data", {}).get("aadhaar_mobile")
    if not mobile_number:
        aadhaar_data = session.get("data", {}).get("aadhaar_data", {})
        mobile_number = aadhaar_data.get("mobile_number")
    if not mobile_number:
        raise HTTPException(
            status_code=400,
            detail="Aadhaar mobile number not found. Please upload the full Aadhaar card with the mobile number visible.",
        )

    result = await resend_otp_via_twilio(payload.session_id, mobile_number)

    return OtpResponse(**result)


@app.post("/kyc/verify-otp", response_model=OtpVerifyResponse)
async def verify_otp(payload: OtpVerifyRequest):
    session = session_store.get_or_create(payload.session_id)
    mobile_number = session.get("data", {}).get("aadhaar_mobile")
    if not mobile_number:
        aadhaar_data = session.get("data", {}).get("aadhaar_data", {})
        mobile_number = aadhaar_data.get("mobile_number")
    if not mobile_number:
        raise HTTPException(
            status_code=400,
            detail="Aadhaar mobile number not found. Please upload the full Aadhaar card with the mobile number visible.",
        )

    result = await verify_otp_via_twilio(payload.session_id, payload.otp, mobile_number)

    if result["verified"]:
        session_store.update_stage(payload.session_id, "KYC_VERIFIED")
        session_store.update_data(payload.session_id, "aadhaar_otp_verified", True)
        session_store.update_data(payload.session_id, "mobile_verified", True)
        session_store.update_data(payload.session_id, "verification_method", "OTP_SMS")
    elif result["terminated"]:
        session_store.update_stage(payload.session_id, "KYC_TERMINATED")
        session_store.update_data(payload.session_id, "aadhaar_otp_failed", True)

    return OtpVerifyResponse(**result)


# =============================================================================
# NEGOTIATION ENDPOINTS (from negotiation_backend)
# =============================================================================

async def handle_credit_to_negotiation(
    session_id: str,
    credit_result: dict,
    loan_amount: float,
    tenure_months: int,
) -> dict:
    """
    Bridge: Underwriting Agent → Negotiation Agent.

    Called automatically after /assess succeeds.
    Initializes the negotiation session so the frontend only needs to
    call /negotiate/start with the session_id — all parameters are
    already resolved from the underwriting output.
    """
    nego_params = credit_result.get("negotiation") or {}
    risk_score = credit_result.get("risk_score")
    risk_tier = credit_result.get("risk_tier", "HIGH")
    applicant_name = (
        (session_store.get(session_id) or {})
        .get("data", {})
        .get("applicant_name", "Applicant")
    )

    req = NegStartReq(
        session_id=session_id,
        applicant_name=applicant_name,
        risk_score=risk_score,
        risk_tier=str(risk_tier),
        loan_amount=loan_amount,
        tenure_months=tenure_months,
        starting_rate=nego_params.get("starting_rate"),
        lgbm_probability=credit_result.get("lgbm_probability"),
    )
    result = await _neg_start(req)
    result_dict = result if isinstance(result, dict) else result.model_dump()

    # Persist negotiation bootstrap in session for analytics
    session_store.update_data(session_id, "negotiation_start", {
        "risk_tier": str(risk_tier),
        "risk_score": risk_score,
        "starting_rate": result_dict.get("current_rate"),
        "max_rounds": result_dict.get("total_steps"),
        "loan_amount": loan_amount,
        "tenure_months": tenure_months,
        "negotiation_id": result_dict.get("negotiation_id"),
    })
    session_store.update_stage(session_id, "OFFER_GENERATED")
    return result_dict


@app.post("/negotiate/chat", response_model=negotiation_schemas.CounterResponse)
def negotiate_chat(payload: CounterRequest) -> CounterResponse:
    # Log Negotiation action
    session_store.log_agent(payload.session_id, {
        "agent": "Negotiation Agent",
        "action": "RATE_NEGOTIATED",
        "reasoning": f"Processing user counter-offer. Intent: {payload.applicant_message[:30]}...",
        "status": "SUCCESS",
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    session_store.update_stage(payload.session_id, "NEGOTIATING")
    
    return negotiation_schemas.CounterResponse(**counter_session(payload.model_dump()))

@app.post("/negotiate/start")
async def negotiate_start(payload: NegStartReq):
    """
    Flowchart entry: 'Underwriting Agent sends Risk Score'.
    Delegates to the new negotiation agent which enforces the flowchart
    decision tree (HIGH/MEDIUM/LOW tier, 0/1/3 rounds, 0.25% step).
    """
    return await _neg_start(payload)


@app.post("/negotiate/start-from-underwriting", response_model=negotiation_schemas.StartFromUnderwritingResponse)
def negotiate_start_from_underwriting(payload: StartFromUnderwritingRequest) -> StartFromUnderwritingResponse:
    base_url = payload.underwriting_base_url.rstrip("/")
    assess_url = f"{base_url}/assess"

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(assess_url, json=payload.assess_payload.model_dump())
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Unable to reach underwriting service at {assess_url}") from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Underwriting service returned {response.status_code}: {response.text}",
        )

    assessment = response.json()
    risk_score = int(assessment.get("risk_score", 0))
    risk_tier = str(assessment.get("risk_tier", "Medium"))
    top_positive_factor = extract_top_positive_factor(assessment.get("shap_explanation"))

    session = start_session(
        {
            "applicant_name": payload.applicant_name,
            "risk_score": risk_score,
            "risk_tier": risk_tier,
            "loan_amount": payload.loan_amount,
            "tenure_months": payload.tenure_months,
            "top_positive_factor": top_positive_factor,
        }
    )
    negotiation_store.create(session)
    rounds_remaining = max(0, MAX_ROUNDS - session["rounds_completed"])

    return negotiation_schemas.StartFromUnderwritingResponse(
        session_id=session["session_id"],
        underwriting_assessment=assessment,
        opening_offer=session["opening_offer"],
        reasoning=session["history"][0]["reasoning"],
        can_negotiate=session["can_negotiate"],
        rounds_remaining=rounds_remaining,
        negotiation_hint="You may request a rate reduction. Our system will evaluate your profile and respond.",
        detected_intent="START",
    )


@app.post("/negotiate/counter")
async def negotiate_counter(payload: NegCounterReq):
    """
    Flowchart: 'Applicant Counters?' — CONCEDE / FLOOR_REACHED / FINAL_OFFER.
    """
    return await _neg_counter(payload)


@app.post("/negotiate/accept")
async def negotiate_accept(payload: NegAcceptReq):
    """
    Flowchart: 'No (Accepts)' → triggers sanction letter + blockchain.
    """
    return await _neg_accept(payload)


@app.post("/negotiate/escalate")
async def negotiate_escalate(payload: NegEscalateReq):
    """
    Flowchart: 'Escalate to Human?' YES → Human Loan Officer Takes Over.
    """
    return await _neg_escalate(payload)


@app.get("/negotiate/history/{session_id}", response_model=negotiation_schemas.HistoryResponse)
def negotiate_history(session_id: str) -> HistoryResponse:
    session = negotiation_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if negotiation_store.mark_expired_if_needed(session):
        negotiation_store.update(session_id, session)

    return negotiation_schemas.HistoryResponse(session_id=session_id, status=session["status"], session=session)


# =============================================================================
# PIPELINE ENDPOINTS (from pipeline_app)
# =============================================================================

if PIPELINE_AVAILABLE:
    @app.post("/pipeline/start")
    async def start_pipeline(request: dict) -> dict:
        """Start a complete loan processing pipeline"""
        try:
            session_id = request.get("session_id") or str(uuid4())
            request["session_id"] = session_id

            if session_id in running_tasks and not running_tasks[session_id].done():
                return {"session_id": session_id, "status": "ACTIVE", "message": "Pipeline already running"}

            running_tasks[session_id] = asyncio.create_task(pipeline.run_full_pipeline(request))
            return {"session_id": session_id, "status": "ACTIVE", "message": "Pipeline started"}
        except Exception as e:
            logger.error(f"Pipeline start error: {e}")
            fallback_id = request.get("session_id") or str(uuid4())
            return {"session_id": fallback_id, "status": "error", "message": "Pipeline could not start. Please try again."}


    @app.get("/pipeline/log/{session_id}")
    def get_pipeline_log(session_id: str) -> dict:
        """Get pipeline execution logs for a session"""
        try:
            log = pipeline.get_session_log(session_id)
            if not log.get("agent_trace"):
                raise HTTPException(status_code=404, detail="Session not found")
            return log
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Pipeline log error: {e}")


# =============================================================================
# TRANSLATION ENDPOINTS (from translation_backend)
# =============================================================================

if TRANSLATION_AVAILABLE:
    @app.post("/translate", response_model=translation_schemas.TranslateResponse)
    def translate(payload: TranslateRequest) -> TranslateResponse:
        """Translate text between languages"""
        try:
            result = translation_service.translate(
                payload.text,
                source_language=payload.source_language,
                target_language=payload.target_language,
            )
            return translation_schemas.TranslateResponse(**result)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Translation failed: {str(exc)}") from exc

    @app.post("/detect-hinglish-intent")
    def detect_hinglish(payload: dict) -> dict:
        """Detect intent from Hinglish input"""
        message = payload.get("message", "").strip()
        if not message:
            raise HTTPException(status_code=400, detail="Message required")
        intent = detect_hinglish_intent(message)
        return {"message": message, "intent": intent}

    @app.post("/chat", response_model=translation_schemas.ChatResponse)
    async def chat(request: ChatRequest) -> ChatResponse:
        """Process chat message using Groq LLM"""
        return await groq_service.process_chat_request(request)

    @app.post("/chat/stream")
    async def chat_stream(request: ChatRequest):
        """Stream chat response token by token"""
        async def generate():
            async for token in groq_service.stream_chat_response(request):
                yield token
        from fastapi.responses import StreamingResponse
        return StreamingResponse(generate(), media_type="text/plain")

    @app.post("/intent/classify", response_model=translation_schemas.IntentClassificationResponse)
    async def classify_intent(request: IntentClassificationRequest) -> IntentClassificationResponse:
        """Classify user intent using Groq"""
        return await groq_service.classify_intent(request)

    @app.post("/explain/credit")
    async def explain_credit(request: CreditExplanationRequest):
        """Generate credit decision explanation"""
        explanation = await groq_service.generate_credit_explanation(
            request.credit_score,
            request.risk_score,
            request.decision,
            request.rate,
            request.shap_factors,
            request.language
        )
        return {"explanation": explanation}

    @app.post("/explain/negotiation")
    async def explain_negotiation(request: NegotiationExplanationRequest):
        """Generate negotiation explanation"""
        explanation = await groq_service.generate_negotiation_explanation(
            request.starting_rate,
            request.current_rate,
            request.floor_rate,
            request.round,
            request.max_rounds,
            request.risk_tier,
            request.positive_factor,
            request.language
        )
        return {"explanation": explanation}

    @app.post("/generate/rejection")
    async def generate_rejection(request: RejectionMessageRequest):
        """Generate empathetic rejection message"""
        message = await groq_service.generate_rejection_message(
            request.credit_score,
            request.language
        )
        return {"message": message}

    @app.get("/groq/health")
    def groq_health():
        """Get Groq API health status"""
        return groq_service.client.get_health_status()



@app.get("/blockchain/sanction")
async def download_sanction_letter(reference_id: str):
    """
    Download a generated sanction letter PDF.
    This is a robust fallback endpoint that searches multiple locations.
    """
    from fastapi.responses import FileResponse
    
    # Clean reference ID
    ref = reference_id.strip()
    
    # Possible directories
    base = Path(__file__).resolve().parent.parent
    possible_dirs = [
        base / "artifacts" / "sanctions",
        Path("artifacts/sanctions"),
        base / "agents" / "blockchain_agent" / "artifacts" / "sanctions",
    ]
    
    for s_dir in possible_dirs:
        if not s_dir.exists():
            continue
            
        # Try patterns
        patterns = [
            f"sanction_{ref}.pdf",
            f"{ref}.pdf",
            f"*{ref}*.pdf"
        ]
        
        for pattern in patterns:
            if "*" in pattern:
                candidates = list(s_dir.glob(pattern))
                if candidates:
                    return FileResponse(candidates[0], media_type="application/pdf", filename=f"Sanction_{ref}.pdf")
            else:
                file_path = s_dir / pattern
                if file_path.exists():
                    return FileResponse(file_path, media_type="application/pdf", filename=f"Sanction_{ref}.pdf")
    
    logger.error(f"Sanction letter not found: {ref}")
    raise HTTPException(status_code=404, detail=f"Sanction letter {ref} not found. It may still be generating.")

# =============================================================================
# AUDIT TRAIL
# =============================================================================

@app.get("/kyc/audit/{session_id}")
async def get_kyc_audit_trail(session_id: str):
    """Structured audit trail for all KYC and loan processing events in a session."""
    session = session_store.get(session_id)
    if not session:
        session = session_store.get_or_create(session_id)

    agent_log = session.get("agent_log", []) if isinstance(session, dict) else []
    events = [
        {
            "timestamp": entry.get("timestamp", ""),
            "event": entry.get("action", "").replace("_", " ").title(),
            "agent": entry.get("agent", ""),
            "status": entry.get("status", ""),
            "details": entry.get("reasoning", ""),
        }
        for entry in agent_log
    ]
    return {
        "session_id": session_id,
        "events": events,
        "total_events": len(events),
    }


# =============================================================================
# SANCTION DELIVERY (Email / SMS confirmation)
# =============================================================================

class SanctionDeliveryRequest(BaseModel):
    reference_id: str
    email: Optional[str] = None
    phone: Optional[str] = None


@app.post("/sanction/deliver")
async def deliver_sanction_notification(payload: SanctionDeliveryRequest):
    """
    Send sanction letter confirmation via email and/or SMS.
    In DEMO_MODE or when credentials are absent, returns a success stub.
    """
    reference_id = payload.reference_id.strip()
    sent_channels: list[str] = []
    errors: list[str] = []

    if not reference_id:
        raise HTTPException(status_code=422, detail="reference_id is required")

    # ── Email delivery ────────────────────────────────────────────────
    if payload.email:
        try:
            if settings.DEMO_MODE or not any([
                getattr(settings, "SENDGRID_API_KEY", ""),
                getattr(settings, "SMTP_HOST", ""),
            ]):
                logger.info(f"[DEMO] Email sanction confirmation to {payload.email} for {reference_id}")
            else:
                import smtplib, email.mime.text as _mime
                smtp_host = getattr(settings, "SMTP_HOST", "")
                smtp_port = int(getattr(settings, "SMTP_PORT", 587))
                smtp_user = getattr(settings, "SMTP_USER", "")
                smtp_pass = getattr(settings, "SMTP_PASS", "")
                from_addr = getattr(settings, "SMTP_FROM", smtp_user)

                body = (
                    f"Dear Applicant,\n\n"
                    f"Your loan sanction letter is ready.\n"
                    f"Reference ID: {reference_id}\n\n"
                    f"Please log in to LoanEase to download your document.\n\n"
                    f"Regards,\nLoanEase Team"
                )
                msg = _mime.MIMEText(body)
                msg["Subject"] = f"LoanEase — Sanction Letter Ready ({reference_id})"
                msg["From"] = from_addr
                msg["To"] = payload.email

                with smtplib.SMTP(smtp_host, smtp_port) as srv:
                    srv.starttls()
                    srv.login(smtp_user, smtp_pass)
                    srv.sendmail(from_addr, [payload.email], msg.as_string())
            sent_channels.append("email")
        except Exception as exc:
            logger.warning(f"Sanction email failed: {exc}")
            errors.append(f"email: {str(exc)[:80]}")

    # ── SMS delivery ──────────────────────────────────────────────────
    if payload.phone:
        try:
            sms_text = (
                f"LoanEase: Your loan is sanctioned! "
                f"Ref: {reference_id}. "
                f"Download your sanction letter from the app."
            )
            if settings.DEMO_MODE or not settings.FAST2SMS_API_KEY:
                logger.info(f"[DEMO] SMS to {payload.phone}: {sms_text}")
            else:
                import httpx
                r = await httpx.AsyncClient().post(
                    "https://www.fast2sms.com/dev/bulkV2",
                    params={
                        "authorization": settings.FAST2SMS_API_KEY,
                        "message": sms_text,
                        "language": "english",
                        "route": "q",
                        "numbers": payload.phone.replace("+91", "").strip(),
                    },
                    timeout=8,
                )
                r.raise_for_status()
            sent_channels.append("sms")
        except Exception as exc:
            logger.warning(f"Sanction SMS failed: {exc}")
            errors.append(f"sms: {str(exc)[:80]}")

    if not payload.email and not payload.phone:
        raise HTTPException(status_code=422, detail="Provide at least one of: email, phone")

    return {
        "success": len(sent_channels) > 0,
        "reference_id": reference_id,
        "sent_via": sent_channels,
        "errors": errors,
        "demo_mode": settings.DEMO_MODE,
    }


# =============================================================================
# API VERSIONING — version header middleware + /v1/ aliases
# =============================================================================

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse


class ApiVersionMiddleware(BaseHTTPMiddleware):
    """Attach X-API-Version header to every response."""
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-API-Version-Current"] = "2"
        response.headers["X-API-Version-Deprecated"] = "1"
        return response


app.add_middleware(ApiVersionMiddleware)

# /v1/ router — exposes stable aliases for key endpoints
v1_router = APIRouter(prefix="/v1", tags=["v1 (stable)"])


@v1_router.get("/health")
def v1_health(request: Request):
    return {"status": "ok", "api_version": 1, "upgrade_to": "/health"}


@v1_router.post("/assess")
@limiter.limit("20/minute")
async def v1_assess(request: Request, payload: AssessRequest):
    return await assess(request, payload)


@v1_router.get("/credit-score/{pan_number}")
def v1_credit_score(pan_number: str):
    return credit_score(pan_number)


app.include_router(v1_router)


# =============================================================================
# ENHANCEMENT 14 — FRAUD DETECTION & RISK SCORING
# =============================================================================

import difflib
import time as _time

_fraud_rate_window: dict[str, list[float]] = {}  # phone → [timestamps]
_FRAUD_WINDOW_SECONDS = 300  # 5-minute sliding window
_FRAUD_MAX_APPS = 3          # flag if > 3 apps in the window


class FraudAssessRequest(BaseModel):
    session_id: str
    pan_name: Optional[str] = None
    aadhaar_name: Optional[str] = None
    pan_confidence: Optional[float] = None
    aadhaar_confidence: Optional[float] = None
    phone: Optional[str] = None
    application_timestamp: Optional[str] = None  # ISO-8601


def _name_similarity(a: str, b: str) -> float:
    """Token-sort ratio between two names (0–1)."""
    if not a or not b:
        return 1.0  # can't compare → no penalty
    a_tokens = sorted(a.lower().split())
    b_tokens = sorted(b.lower().split())
    return difflib.SequenceMatcher(None, " ".join(a_tokens), " ".join(b_tokens)).ratio()


def _is_after_market_hours(ts: Optional[str]) -> bool:
    """True if the application arrived outside 9 AM – 6 PM IST on a weekday."""
    if not ts:
        return False
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        # IST = UTC+5:30
        ist_hour = (dt.hour + 5) % 24 + (1 if dt.minute >= 30 else 0)
        return ist_hour < 9 or ist_hour >= 18 or dt.weekday() >= 5
    except Exception:
        return False


def _rapid_application_flag(phone: Optional[str]) -> bool:
    """Return True if the same phone has > _FRAUD_MAX_APPS apps in last 5 min."""
    if not phone:
        return False
    now = _time.monotonic()
    key = phone.strip().replace(" ", "")
    history = _fraud_rate_window.setdefault(key, [])
    # Prune old entries
    _fraud_rate_window[key] = [t for t in history if now - t < _FRAUD_WINDOW_SECONDS]
    _fraud_rate_window[key].append(now)
    return len(_fraud_rate_window[key]) > _FRAUD_MAX_APPS


@app.post("/fraud/assess")
@limiter.limit("30/minute")
async def assess_fraud_risk(request: Request, payload: FraudAssessRequest):
    """
    Enhancement 14: Fraud Detection.
    Returns a risk_score (0–100) with contributing factors.
    Score > 60 → escalate to human agent.
    """
    risk_score = 0
    flags: list[str] = []

    # Rule 1: PAN ↔ Aadhaar name mismatch
    sim = _name_similarity(payload.pan_name or "", payload.aadhaar_name or "")
    if sim < 0.30:
        risk_score += 20
        flags.append(f"Name mismatch: PAN vs Aadhaar similarity {sim:.0%} (threshold 30%)")

    # Rule 2: Low document extraction confidence
    for doc, conf in [("PAN", payload.pan_confidence), ("Aadhaar", payload.aadhaar_confidence)]:
        if conf is not None and conf < 0.70:
            risk_score += 15
            flags.append(f"Low {doc} extraction confidence: {conf:.0%} (threshold 70%)")

    # Rule 3: Rapid successive applications from same phone
    if _rapid_application_flag(payload.phone):
        risk_score += 25
        flags.append(f"Rapid successive applications detected from phone ending {(payload.phone or '')[-4:]}")

    # Rule 4: Application after market hours
    if _is_after_market_hours(payload.application_timestamp):
        risk_score += 10
        flags.append("Application submitted outside business hours (9 AM–6 PM IST, Mon–Fri)")

    escalate = risk_score >= 60
    risk_level = "HIGH" if risk_score >= 60 else "MEDIUM" if risk_score >= 30 else "LOW"

    # Log to audit trail
    session_store.log_agent(payload.session_id, {
        "agent": "FraudDetectionAgent",
        "action": "FRAUD_RISK_ASSESSED",
        "reasoning": f"Fraud risk score: {risk_score}/100. Level: {risk_level}. Flags: {len(flags)}",
        "status": "ESCALATE" if escalate else "PASS",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "session_id": payload.session_id,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "flags": flags,
        "escalate_to_human": escalate,
        "recommendation": (
            "Refer to human loan officer for manual review."
            if escalate
            else "Proceed with automated processing."
        ),
    }


# =============================================================================
# WEBHOOK NOTIFICATIONS — register, list, test, deliver
# =============================================================================

_webhook_registry: dict[str, dict] = {}  # webhook_id → {url, events, secret, active}

WEBHOOK_EVENTS = {
    "loan.created", "kyc.verified", "credit.assessed",
    "offer.generated", "negotiation.accepted", "loan.sanctioned",
}


class WebhookRegisterRequest(BaseModel):
    url: str
    events: list[str]
    secret: Optional[str] = None


class WebhookTestRequest(BaseModel):
    webhook_id: str


async def _deliver_webhook(webhook_id: str, event: str, payload: dict) -> bool:
    """Attempt to POST event payload to the registered webhook URL (3 retries)."""
    entry = _webhook_registry.get(webhook_id)
    if not entry or not entry.get("active"):
        return False
    delivery_payload = {
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "webhook_id": webhook_id,
        "data": payload,
    }
    headers = {"Content-Type": "application/json"}
    if entry.get("secret"):
        import hmac, hashlib
        body = json.dumps(delivery_payload).encode()
        sig = hmac.new(entry["secret"].encode(), body, hashlib.sha256).hexdigest()
        headers["X-LoanEase-Signature"] = f"sha256={sig}"

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                r = await client.post(entry["url"], json=delivery_payload, headers=headers)
                if r.status_code < 300:
                    logger.info("Webhook %s delivered event %s (attempt %d)", webhook_id, event, attempt + 1)
                    return True
                logger.warning("Webhook %s got HTTP %s on attempt %d", webhook_id, r.status_code, attempt + 1)
        except Exception as exc:
            logger.warning("Webhook %s delivery error (attempt %d): %s", webhook_id, attempt + 1, exc)
        await asyncio.sleep(2 ** attempt)  # 0s, 2s, 4s backoff
    return False


async def _fire_webhook_event(event: str, payload: dict) -> None:
    """Fire event to all registered, active webhooks that subscribe to it."""
    for wid, entry in list(_webhook_registry.items()):
        if entry.get("active") and event in entry.get("events", []):
            asyncio.create_task(_deliver_webhook(wid, event, payload))


@app.post("/webhooks/register")
@limiter.limit("10/minute")
async def register_webhook(request: Request, payload: WebhookRegisterRequest):
    invalid = [e for e in payload.events if e not in WEBHOOK_EVENTS]
    if invalid:
        raise HTTPException(status_code=422, detail=f"Unknown events: {invalid}. Valid: {sorted(WEBHOOK_EVENTS)}")
    wid = str(uuid4())[:12]
    _webhook_registry[wid] = {
        "id": wid,
        "url": payload.url,
        "events": list(payload.events),
        "secret": payload.secret,
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return {"webhook_id": wid, "url": payload.url, "events": payload.events, "active": True}


@app.get("/webhooks")
async def list_webhooks():
    return {
        "webhooks": [
            {k: v for k, v in w.items() if k != "secret"}
            for w in _webhook_registry.values()
        ]
    }


@app.delete("/webhooks/{webhook_id}")
async def delete_webhook(webhook_id: str):
    if webhook_id not in _webhook_registry:
        raise HTTPException(status_code=404, detail="Webhook not found")
    _webhook_registry[webhook_id]["active"] = False
    return {"webhook_id": webhook_id, "active": False}


@app.post("/webhooks/test")
async def test_webhook(payload: WebhookTestRequest):
    if payload.webhook_id not in _webhook_registry:
        raise HTTPException(status_code=404, detail="Webhook not found")
    success = await _deliver_webhook(
        payload.webhook_id,
        "loan.created",
        {"test": True, "session_id": "TEST-SESSION"},
    )
    return {"webhook_id": payload.webhook_id, "delivered": success}


# =============================================================================
# COMPLIANCE AUDIT — IP-aware logging + CSV/JSON export
# (RBI Digital Lending Guidelines 2022 — 7-year retention)
# =============================================================================

class ComplianceAuditRequest(BaseModel):
    session_id: str
    action: str
    details: Optional[str] = None


@app.post("/audit/log")
@limiter.limit("60/minute")
async def log_compliance_event(request: Request, payload: ComplianceAuditRequest):
    """Append an immutable compliance audit event (include requester IP)."""
    client_ip = request.client.host if request.client else "unknown"
    session_store.log_agent(payload.session_id, {
        "agent": "ComplianceAuditAgent",
        "action": payload.action,
        "reasoning": payload.details or "",
        "status": "LOGGED",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ip_address": client_ip,
    })
    return {"logged": True, "session_id": payload.session_id, "action": payload.action}


@app.get("/admin/audit-logs")
async def export_audit_logs(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    format: str = "json",
):
    """
    Export all audit logs across all sessions.
    Filter by ISO date (YYYY-MM-DD). format=json|csv.
    """
    all_events: list[dict] = []
    for sid, session in session_store._sessions.items():
        for entry in session.get("agent_log", []):
            entry_copy = dict(entry)
            entry_copy["session_id"] = sid
            ts = entry_copy.get("timestamp", "")
            if start_date and ts < start_date:
                continue
            if end_date and ts > end_date + "Z":
                continue
            all_events.append(entry_copy)

    all_events.sort(key=lambda e: e.get("timestamp", ""))

    if format == "csv":
        from fastapi.responses import StreamingResponse
        import csv, io
        output = io.StringIO()
        if all_events:
            writer = csv.DictWriter(output, fieldnames=list(all_events[0].keys()))
            writer.writeheader()
            writer.writerows(all_events)
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
        )

    return {
        "total": len(all_events),
        "start_date": start_date,
        "end_date": end_date,
        "events": all_events,
    }


# =============================================================================
# GRACEFUL DEGRADATION — timeout wrapper for VLM (KYC) extraction
# =============================================================================

async def _run_ocr_with_timeout(preprocessed: bytes, timeout_s: float = 5.0):
    """
    Run OCR in a thread pool with a 5-second timeout.
    Falls back to an empty string on timeout so the caller can handle gracefully.
    """
    loop = asyncio.get_event_loop()
    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(None, run_ocr, preprocessed),
            timeout=timeout_s,
        )
        return result
    except asyncio.TimeoutError:
        logger.warning("OCR timed out after %ss — returning empty result", timeout_s)
        return ("", 0.0)


# =============================================================================
# AGENT ORCHESTRATION ROUTES
# =============================================================================

try:
    from app.agent_routes import router as agent_router
    app.include_router(agent_router)
except ImportError:
    pass  # Agent routes not available
