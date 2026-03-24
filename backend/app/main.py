from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.model_service import ModelService
from app.schemas import AssessRequest, AssessResponse, ExplainResponse, HealthResponse
from app.storage import ApplicationStore

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

    return AssessResponse(application_id=application_id, **{k: result[k] for k in AssessResponse.model_fields if k != "application_id"})


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
