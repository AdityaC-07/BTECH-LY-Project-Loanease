from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
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

# Import negotiation backend components
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "negotiation_backend"))
from app.constants import MAX_ROUNDS
from app.service import (
    append_history,
    build_escalation_reference,
    build_offer,
    build_sanction_reference,
    counter_session,
    extract_top_positive_factor,
    start_session,
)
from app.store import SessionStore
import app.schemas as negotiation_schemas

# Import translation backend components  
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "translation_backend"))
try:
    from app.translation_service import TranslationService
    from app.hinglish_intent import detect_hinglish_intent
    from app.groq_service import groq_service
    import app.schemas as translation_schemas
    TRANSLATION_AVAILABLE = True
except ImportError:
    TRANSLATION_AVAILABLE = False
    
# Import pipeline components
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import LoanPipeline

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("kyc.ocr")

BASE_DIR = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = BASE_DIR / "artifacts"
STORE_PATH = BASE_DIR / "data" / "applications.jsonl"

app = FastAPI(title="LoanEase Unified Backend API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

# Initialize pipeline
pipeline = LoanPipeline()
running_tasks: dict[str, asyncio.Task] = {}

# In-memory storage for sessions and escalations
sessions: dict[str, dict] = {}
escalations: dict[str, dict] = {}


@app.on_event("startup")
def startup_event() -> None:
    global service
    try:
        service = ModelService(ARTIFACTS_DIR)
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
    return HealthResponse(
        status="ok",
        model_version=service.model_version,
        accuracy=round(accuracy, 4),
        uptime_seconds=uptime_seconds,
    )


@app.get("/credit-score/{pan_number}", response_model=CreditScoreResponse)
def credit_score(pan_number: str) -> CreditScoreResponse:
    """
    Get credit score for PAN number after KYC verification.
    Returns simulated CIBIL credit score and eligibility details.
    """
    try:
        pan_number = pan_number.strip().upper()
        credit_score_val = get_credit_score(pan_number)
        credit_band = get_credit_band(credit_score_val)

        # Determine which band the score falls into
        band_names = {
            (700, 900): "low_risk",
            (301, 699): "medium_risk",
            (0, 300): "high_risk",
        }

        applicant_band = "medium_risk"
        for (min_score, max_score), band_label in band_names.items():
            if min_score <= credit_score_val <= max_score:
                applicant_band = band_label
                break

        message_en = (
            f"Your credit score is {credit_score_val}. You are in the {credit_band['label']} tier. "
            "You can continue your loan application. Interest pricing will be adjusted by risk tier."
        )
        message_hi = (
            f"आपका credit score {credit_score_val} है। आप {credit_band['label']} tier में आते हैं। "
            "आप loan application जारी रख सकते हैं। ब्याज दर risk tier के आधार पर तय होगी।"
        )

        return CreditScoreResponse(
            pan_number=mask_pan(pan_number),
            credit_score=credit_score_val,
            credit_score_out_of=900,
            credit_band=credit_band["label"],
            credit_band_color=credit_band["color"],
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
def assess(payload: AssessRequest) -> AssessResponse:
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

    # Build response with all fields from result
    return AssessResponse(
        application_id=application_id,
        **{
            k: result.get(k)
            for k in AssessResponse.model_fields
            if k != "application_id" and result.get(k) is not None
        },
    )


# Route alias for frontend compatibility
@app.post("/credit/assess", response_model=AssessResponse)
def credit_assess(payload: AssessRequest) -> AssessResponse:
    """Alias for /assess endpoint for frontend compatibility"""
    return assess(payload)


@app.post("/explain/{application_id}", response_model=ExplainResponse)
def explain(application_id: str) -> ExplainResponse:
    record = store.get(application_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Application not found")

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


@app.post("/escalation/callback-preference")
def save_escalation_preference(payload: EscalationPreferenceRequest):
    escalations[payload.session_id] = payload.model_dump()
    return {"status": "success", "message": "Callback preference saved"}


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
async def extract_pan_endpoint(document: UploadFile = File(...), language: str = Form("en")):
    language = "hi" if language == "hi" else "en"
    file_bytes = await document.read()
    
    logger.info(f"KYC PAN: Received file {document.filename}, type {document.content_type}, size {len(file_bytes)} bytes")
    
    _assert_upload_constraints(document, file_bytes)
    
    try:
        extension = (document.filename or "").lower().split(".")[-1]
        preprocessed = preprocess_image(file_bytes, extension)
        ocr_text, confidence = run_ocr(preprocessed)
        
        logger.info(f"KYC PAN: OCR completed, confidence {confidence:.2f}")
        logger.info(f"KYC PAN: Raw OCR text (first 200 chars): {ocr_text[:200] if ocr_text else 'EMPTY'}")
        
        result = extract_pan(ocr_text)
        logger.info(f"KYC PAN: Extracted fields - pan={result.get('extracted_fields', {}).get('pan_number')}, name={result.get('extracted_fields', {}).get('name')}")
        
        return {
            "document_type": "PAN",
            "extracted_fields": result["extracted_fields"],
            "validation": result["validation"],
            "confidence_score": confidence,
            "processing_time_ms": 0,
        }
    except UnsupportedDocumentError as exc:
        logger.error(f"KYC PAN: Document error - {str(exc)}")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"KYC PAN: Extraction failed - {str(exc)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"PAN extraction failed: {str(exc)}") from exc


@app.post("/kyc/extract/aadhaar")
async def extract_aadhaar_endpoint(document: UploadFile = File(...)):
    file_bytes = await document.read()
    
    logger.info(f"KYC Aadhaar: Received file {document.filename}, type {document.content_type}, size {len(file_bytes)} bytes")
    
    _assert_upload_constraints(document, file_bytes)
    
    try:
        extension = (document.filename or "").lower().split(".")[-1]
        preprocessed = preprocess_image(file_bytes, extension)
        ocr_text, confidence = run_ocr(preprocessed)
        
        logger.info(f"KYC Aadhaar: OCR completed, confidence {confidence:.2f}")
        logger.info(f"KYC Aadhaar: Raw OCR text (first 200 chars): {ocr_text[:200] if ocr_text else 'EMPTY'}")
        
        result = extract_aadhaar(ocr_text)
        logger.info(f"KYC Aadhaar: Extracted fields - aadhaar_last4={result.get('extracted_fields', {}).get('aadhaar_last4')}")
        
        return {
            "document_type": "AADHAAR",
            "extracted_fields": result["extracted_fields"],
            "validation": result["validation"],
            "confidence_score": confidence,
            "processing_time_ms": 0,
        }
    except UnsupportedDocumentError as exc:
        logger.error(f"KYC Aadhaar: Document error - {str(exc)}")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"KYC Aadhaar: Extraction failed - {str(exc)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Aadhaar extraction failed: {str(exc)}") from exc


@app.post("/kyc/verify")
async def verify_kyc(pan: UploadFile = File(...), aadhaar: UploadFile = File(...)):
    pan_bytes = await pan.read()
    aadhaar_bytes = await aadhaar.read()
    
    _assert_upload_constraints(pan, pan_bytes)
    _assert_upload_constraints(aadhaar, aadhaar_bytes)
    
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
        
        # Cross-validate
        validation = cross_validate_kyc(pan_result, aadhaar_result)
        
        return {
            "kyc_status": validation["kyc_status"],
            "pan_data": pan_result.get("extracted_fields"),
            "aadhaar_data": aadhaar_result.get("extracted_fields"),
            "cross_validation": validation["cross_validation"],
            "overall_kyc_passed": validation["overall_kyc_passed"],
            "kyc_reference_id": str(uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.error(f"KYC Verify: Failed - {str(exc)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"KYC verification failed: {str(exc)}") from exc


# =============================================================================
# NEGOTIATION ENDPOINTS (from negotiation_backend)
# =============================================================================

@app.post("/negotiate/start", response_model=negotiation_schemas.StartNegotiationResponse)
def negotiate_start(payload: negotiation_schemas.StartNegotiationRequest) -> negotiation_schemas.StartNegotiationResponse:
    session = start_session(payload.model_dump())
    negotiation_store.create(session)

    rounds_remaining = max(0, MAX_ROUNDS - session["rounds_completed"])

    return negotiation_schemas.StartNegotiationResponse(
        session_id=session["session_id"],
        opening_offer=session["opening_offer"],
        reasoning=session["history"][0]["reasoning"],
        can_negotiate=session["can_negotiate"],
        rounds_remaining=rounds_remaining,
        negotiation_hint="You may request a rate reduction. Our system will evaluate your profile and respond.",
        detected_intent="START",
    )


@app.post("/negotiate/start-from-underwriting", response_model=negotiation_schemas.StartFromUnderwritingResponse)
def negotiate_start_from_underwriting(payload: negotiation_schemas.StartFromUnderwritingRequest) -> negotiation_schemas.StartFromUnderwritingResponse:
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


@app.post("/negotiate/counter", response_model=negotiation_schemas.CounterResponse)
def negotiate_counter(payload: negotiation_schemas.CounterRequest) -> negotiation_schemas.CounterResponse:
    session = negotiation_store.get(payload.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if negotiation_store.mark_expired_if_needed(session):
        raise HTTPException(status_code=410, detail="Session expired")

    result = counter_session(session, payload.applicant_message, payload.requested_rate)
    append_history(session, "counter", result["reasoning"], result["intent"])
    negotiation_store.update(payload.session_id, session)

    rounds_remaining = max(0, MAX_ROUNDS - session["rounds_completed"])

    return negotiation_schemas.CounterResponse(
        session_id=payload.session_id,
        counter_offer=result["offer"],
        reasoning=result["reasoning"],
        rounds_remaining=rounds_remaining,
        can_negotiate_further=result["can_negotiate_further"],
        status=session["status"],
        detected_intent=result["intent"],
    )


@app.post("/negotiate/accept", response_model=negotiation_schemas.AcceptResponse)
def negotiate_accept(payload: negotiation_schemas.AcceptRequest) -> negotiation_schemas.AcceptResponse:
    session = negotiation_store.get(payload.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if negotiation_store.mark_expired_if_needed(session):
        negotiation_store.update(payload.session_id, session)
        expired_offer = build_offer(
            session["loan_amount"],
            session["tenure_months"],
            session["current_rate"],
            session["opening_offer"]["total_payable"],
        )
        return negotiation_schemas.AcceptResponse(
            session_id=payload.session_id,
            final_offer=expired_offer,
            message="This negotiation session has expired after 48 hours. Please restart your negotiation.",
            sanction_reference="NA",
            status="expired",
            detected_intent="ACCEPTANCE",
        )

    final_offer = build_offer(
        session["loan_amount"],
        session["tenure_months"],
        session["current_rate"],
        session["opening_offer"]["total_payable"],
    )
    sanction_reference = build_sanction_reference()

    session["status"] = "completed"
    append_history(
        session,
        "accept",
        f"This concludes our negotiation. Your final approved rate is {session['current_rate']:.2f}% per annum. "
        "This offer is valid for 48 hours. Shall I generate your sanction letter?",
        "ACCEPTANCE",
    )
    negotiation_store.update(payload.session_id, session)

    return negotiation_schemas.AcceptResponse(
        session_id=payload.session_id,
        final_offer=final_offer,
        message=(
            f"Congratulations! Your loan at {session['current_rate']:.2f}% per annum has been accepted. "
            "Generating your digitally signed sanction letter now..."
        ),
        sanction_reference=sanction_reference,
        status="completed",
        detected_intent="ACCEPTANCE",
    )


@app.post("/negotiate/escalate", response_model=negotiation_schemas.EscalateResponse)
def negotiate_escalate(payload: negotiation_schemas.EscalateRequest) -> negotiation_schemas.EscalateResponse:
    session = negotiation_store.get(payload.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if negotiation_store.mark_expired_if_needed(session):
        negotiation_store.update(payload.session_id, session)
        return negotiation_schemas.EscalateResponse(
            session_id=payload.session_id,
            message="Session expired before escalation could be processed. Please restart negotiation.",
            escalation_id="NA",
            status="expired",
            detected_intent="ESCALATION_REQUEST",
        )

    escalation_id = build_escalation_reference()
    sanction_reference = build_sanction_reference()
    session["status"] = "escalated"
    append_history(
        session,
        "escalate",
        "You have reached the minimum rate available for your risk tier. Further reduction is not possible within automated limits. "
        "Would you like me to escalate this to a human loan officer for a manual review?",
        "ESCALATION_REQUEST",
    )
    negotiation_store.update(payload.session_id, session)

    return negotiation_schemas.EscalateResponse(
        session_id=payload.session_id,
        message=(
            "Your case has been escalated to a senior loan officer. You will receive a call within 2 business hours. "
            f"Reference: {sanction_reference}."
        ),
        escalation_id=escalation_id,
        status="escalated",
        detected_intent="ESCALATION_REQUEST",
    )


@app.get("/negotiate/history/{session_id}", response_model=negotiation_schemas.HistoryResponse)
def negotiate_history(session_id: str) -> negotiation_schemas.HistoryResponse:
    session = negotiation_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if negotiation_store.mark_expired_if_needed(session):
        negotiation_store.update(session_id, session)

    return negotiation_schemas.HistoryResponse(session_id=session_id, status=session["status"], session=session)


# =============================================================================
# PIPELINE ENDPOINTS (from pipeline_app)
# =============================================================================

@app.post("/pipeline/start")
async def start_pipeline(request: dict) -> dict:
    """Start a complete loan processing pipeline"""
    session_id = request.get("session_id") or str(uuid4())
    request["session_id"] = session_id

    if session_id in running_tasks and not running_tasks[session_id].done():
        return {"session_id": session_id, "status": "ACTIVE", "message": "Pipeline already running"}

    running_tasks[session_id] = asyncio.create_task(pipeline.run_full_pipeline(request))
    return {"session_id": session_id, "status": "ACTIVE", "message": "Pipeline started"}


@app.get("/pipeline/log/{session_id}")
def get_pipeline_log(session_id: str) -> dict:
    """Get pipeline execution logs for a session"""
    log = pipeline.get_session_log(session_id)
    if not log.get("agent_trace"):
        raise HTTPException(status_code=404, detail="Session not found")
    return log


# =============================================================================
# TRANSLATION ENDPOINTS (from translation_backend)
# =============================================================================

if TRANSLATION_AVAILABLE:
    @app.post("/translate", response_model=translation_schemas.TranslateResponse)
    def translate(payload: translation_schemas.TranslateRequest) -> translation_schemas.TranslateResponse:
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
    async def chat(request: translation_schemas.ChatRequest) -> translation_schemas.ChatResponse:
        """Process chat message using Groq LLM"""
        return await groq_service.process_chat_request(request)

    @app.post("/chat/stream")
    async def chat_stream(request: translation_schemas.ChatRequest):
        """Stream chat response token by token"""
        async def generate():
            async for token in groq_service.stream_chat_response(request):
                yield token
        from fastapi.responses import StreamingResponse
        return StreamingResponse(generate(), media_type="text/plain")

    @app.post("/intent/classify", response_model=translation_schemas.IntentClassificationResponse)
    async def classify_intent(request: translation_schemas.IntentClassificationRequest) -> translation_schemas.IntentClassificationResponse:
        """Classify user intent using Groq"""
        return await groq_service.classify_intent(request)

    @app.post("/explain/credit")
    async def explain_credit(request: translation_schemas.CreditExplanationRequest):
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
    async def explain_negotiation(request: translation_schemas.NegotiationExplanationRequest):
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
    async def generate_rejection(request: translation_schemas.RejectionMessageRequest):
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


# =============================================================================
# AGENT ORCHESTRATION ROUTES
# =============================================================================

try:
    from app.agent_routes import router as agent_router
    app.include_router(agent_router)
except ImportError:
    pass  # Agent routes not available
