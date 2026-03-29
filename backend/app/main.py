from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.model_service import ModelService
from app.schemas import (
    AssessRequest,
    AssessResponse,
    CreditScoreResponse,
    ExplainResponse,
    HealthResponse,
)
from app.storage import ApplicationStore
from app.credit_score import get_credit_score, get_credit_band, mask_pan

BASE_DIR = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = BASE_DIR / "artifacts"
STORE_PATH = BASE_DIR / "data" / "applications.jsonl"

app = FastAPI(title="LoanEase Underwriting API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

service: ModelService | None = None
store = ApplicationStore(STORE_PATH)
boot_time = datetime.now(timezone.utc)


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
            (750, 900): "excellent",
            (700, 749): "good",
            (550, 699): "fair",
            (300, 549): "poor",
            (0, 299): "ineligible",
        }
        
        applicant_band = "ineligible"
        for (min_score, max_score), band_label in band_names.items():
            if min_score <= credit_score_val <= max_score:
                applicant_band = band_label
                break

        # Friendly messages
        if credit_band["eligible"]:
            message_en = f"Great news! Your credit score of {credit_score_val} qualifies you for our loan products. "
            message_en += f"You fall in the {applicant_band} category."
            message_hi = f"बहुत बढ़िया! आपका credit score {credit_score_val} है जो हमारे loan products के लिए योग्य है। "
            message_hi += f"आप {applicant_band} category में आते हैं।"
        else:
            shortfall = 300 - credit_score_val
            message_en = (
                f"Your credit score of {credit_score_val} is below our minimum requirement of 300. "
                f"You are short by {shortfall} points. Come back after improving your score."
            )
            message_hi = (
                f"आपका credit score {credit_score_val} है जो हमारी न्यूनतम आवश्यकता 300 से कम है। "
                f"आप {shortfall} points से कम हैं। अपना score सुधारने के बाद वापस आएं।"
            )

        improvement_tips = None
        earliest_reapply = None
        shortfall = None

        if not credit_band["eligible"]:
            shortfall = 300 - credit_score_val
            improvement_tips = [
                "Pay all existing EMIs on time",
                "Clear any outstanding credit card dues",
                "Avoid multiple loan applications in a short period",
                "Maintain credit utilization below 30%",
                "Wait 6 months before reapplying",
            ]
            earliest_reapply = "6 months from today"

        return CreditScoreResponse(
            pan_number=mask_pan(pan_number),
            credit_score=credit_score_val,
            credit_score_out_of=900,
            credit_band=credit_band["label"],
            credit_band_color=credit_band["color"],
            eligible_for_loan=credit_band["eligible"],
            applicant_score_falls_in=applicant_band,
            message_en=message_en,
            message_hi=message_hi,
            shortfall=shortfall,
            improvement_tips=improvement_tips,
            earliest_reapply=earliest_reapply,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
