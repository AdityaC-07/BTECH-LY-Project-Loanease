import logging
import os
import joblib
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.session import session_store
from services.credit_score import simulate_cibil_score, calculate_credit_score
from core.config import settings

logger = logging.getLogger("loanease.underwriting")

router = APIRouter()

# Global model cache
_model = None
_model_features = None

# Pydantic models
class AssessRequest(BaseModel):
    # Session-based fields (agents backend)
    session_id: Optional[str] = None
    loan_amount: Optional[float] = None
    tenure_years: Optional[int] = None
    # Frontend direct fields
    pan_number: Optional[str] = None
    gender: Optional[str] = None
    married: Optional[str] = None
    dependents: Optional[str] = None
    education: Optional[str] = None
    self_employed: Optional[str] = None
    applicant_income: Optional[float] = None
    coapplicant_income: Optional[float] = None
    loan_amount_term: Optional[float] = None
    credit_history: Optional[float] = None
    property_area: Optional[str] = None
    preferred_language: Optional[str] = "en"

class AssessResponse(BaseModel):
    application_id: str
    credit_score: int
    risk_category: str
    risk_score: int
    decision: str
    interest_rate: float
    max_loan_amount: float
    explanation: Dict[str, Any]
    # Aliases the frontend reads
    risk_tier: Optional[str] = None
    max_negotiation_rounds: Optional[int] = 3

    def model_post_init(self, __context: Any) -> None:
        if self.risk_tier is None:
            self.risk_tier = self.risk_category

class CreditScoreRequest(BaseModel):
    pan_number: str

class CreditScoreResponse(BaseModel):
    cibil_score: int
    credit_score: int
    risk_category: str
    risk_score: int

def load_model():
    """Load model and metadata into memory"""
    global _model, _model_features, _metadata
    try:
        # Try to load the model file
        model_path = "models/loan_model.pkl"
        meta_path = "models/model_metadata.json"
        
        if os.path.exists(model_path):
            _model = joblib.load(model_path)
            logger.info(f"Model loaded successfully: {type(_model).__name__}")
            
            if os.path.exists(meta_path):
                with open(meta_path, 'r') as f:
                    _metadata = json.load(f)
                    _model_features = _metadata.get("feature_names")
                    logger.info("Model metadata loaded")
            else:
                _metadata = None
        else:
            logger.warning("Model file not found, using fallback")
            _model = None
            _metadata = None
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        _model = None
        _metadata = None

# Initial load
import json
_metadata = None
load_model()

def model_loaded() -> bool:
    """Check if model is loaded"""
    return _model is not None

def predict_credit_score(features: Dict[str, Any]) -> float:
    """Predict credit score using XGBoost model"""
    global _model, _model_features
    
    if not _model:
        # Fallback: use rule-based scoring
        cibil_score = features.get("cibil_score", 750)
        age = features.get("age", 30)
        loan_amount = features.get("loan_amount", 500000)
        
        # Rule-based scoring
        base_score = cibil_score
        
        # Age adjustment
        if 25 <= age <= 40:
            age_adjustment = 50
        elif 41 <= age <= 55:
            age_adjustment = 30
        else:
            age_adjustment = -20
        
        # Loan amount adjustment (higher loan = slightly lower score)
        if loan_amount > 1000000:
            loan_adjustment = -30
        elif loan_amount > 500000:
            loan_adjustment = -10
        else:
            loan_adjustment = 10
        
        final_score = base_score + age_adjustment + loan_adjustment
        return max(300, min(900, final_score))
    
    try:
        # Convert features to DataFrame
        feature_df = pd.DataFrame([features])
        
        # Ensure required columns
        if _model_features:
            for col in _model_features:
                if col not in feature_df.columns:
                    feature_df[col] = 0
            feature_df = feature_df[_model_features]
        
        # Make prediction
        prediction = _model.predict(feature_df)[0]
        
        # Scale to 300-900 range
        score = 300 + (prediction * 600)
        score = max(300, min(900, score))
        
        return float(score)
        
    except Exception as e:
        logger.error(f"Prediction error: {e}")
        # Fallback
        import random
        return random.uniform(300, 900)

def generate_application_id() -> str:
    """Generate unique application ID"""
    import uuid
    return f"APP-{uuid.uuid4().hex[:12].upper()}"

@router.post("/assess", response_model=AssessResponse)
async def assess_loan(request: AssessRequest):
    """Assess loan application — accepts both session-based and direct payloads"""
    import time
    try:
        if settings.DEMO_MODE:
            import asyncio
            await asyncio.sleep(1.2)

        # Resolve loan_amount and tenure from either payload shape
        loan_amount = request.loan_amount
        tenure_years = request.tenure_years

        # Frontend sends loan_amount_term (months) and loan_amount (rupees / lakhs)
        if loan_amount is None and request.loan_amount_term is not None:
            # loan_amount_term is tenure in months from frontend
            tenure_years = max(1, int((request.loan_amount_term or 12) / 12))

        # Frontend may send loan_amount already in rupees (e.g. 500000)
        # or in lakhs (e.g. 5.0). Normalise: if < 1000, treat as lakhs
        if loan_amount is not None and loan_amount < 1000:
            loan_amount = loan_amount * 100000  # convert lakhs → rupees

        if loan_amount is None:
            loan_amount = 500000  # sensible default
        if tenure_years is None:
            tenure_years = 5

        # Resolve PAN — from session or direct field
        pan_number = request.pan_number or ""
        session = None
        if request.session_id:
            session = session_store.get(request.session_id)
            if session:
                pan_data = session["data"].get("pan_data", {})
                pan_number = pan_number or pan_data.get("pan_number", "")

        # If no session exists yet, create one
        if not session and request.session_id:
            session_store.get_or_create(request.session_id)
            session = session_store.get(request.session_id)

        app_id = generate_application_id()
        cibil_score = simulate_cibil_score(pan_number)

        age = 30
        if session:
            pan_data = session["data"].get("pan_data", {})
            age = pan_data.get("age") or 30

        features = {
            "cibil_score": cibil_score,
            "loan_amount": loan_amount,
            "tenure_years": tenure_years,
            "age": age,
            "income_estimated": (request.applicant_income or 50000) * 12,
        }

        xgboost_score = predict_credit_score(features)
        credit_result = calculate_credit_score(cibil_score, xgboost_score)

        base_rate = 12.0
        risk_adjustments = {"LOW": -1.0, "MEDIUM": 0.0, "MEDIUM-HIGH": 1.5, "HIGH": 3.0}
        interest_rate = base_rate + risk_adjustments.get(credit_result["risk_category"], 0.0)
        interest_rate = max(settings.RATE_FLOOR, min(settings.RATE_CEILING, interest_rate))

        if credit_result["hard_reject"]:
            decision = "REJECTED"
            max_loan = 0
        else:
            decision = "APPROVED"
            max_loan = loan_amount * (credit_result["final_score"] / 900)

        explanation = {
            "factors": {
                "cibil_score": {"value": cibil_score, "weight": settings.CIBIL_WEIGHT,
                                "impact": "positive" if cibil_score >= 700 else "negative"},
                "xgboost_score": {"value": round(xgboost_score, 2), "weight": settings.XGBOOST_WEIGHT,
                                  "impact": "positive" if xgboost_score >= 700 else "negative"},
            },
            "reasoning": f"Credit score {credit_result['final_score']} → {credit_result['risk_category']} risk",
        }

        if request.session_id:
            session_store.update_stage(request.session_id, "UNDERWRITING_COMPLETE")
            session_store.update_data(request.session_id, "underwriting_result", {
                "application_id": app_id,
                "decision": decision,
                "credit_score": credit_result["final_score"],
                "interest_rate": interest_rate,
                "risk_category": credit_result["risk_category"],
                "risk_score": credit_result["risk_score"],
                "loan_amount": loan_amount,
                "tenure_years": tenure_years,
            })
            session_store.log_agent(request.session_id, {
                "agent": "underwriting", "action": "assessment",
                "success": decision == "APPROVED",
                "application_id": app_id,
                "credit_score": credit_result["final_score"],
                "decision": decision,
            })

        return AssessResponse(
            application_id=app_id,
            credit_score=credit_result["final_score"],
            risk_category=credit_result["risk_category"],
            risk_score=credit_result["risk_score"],
            decision=decision,
            interest_rate=interest_rate,
            max_loan_amount=max_loan,
            explanation=explanation,
        )

    except Exception as e:
        if settings.DEMO_MODE:
            from core.fallback_map import get_fallback
            logger.error(f"Loan assessment failed, using demo fallback: {e}")
            fb = get_fallback("xgboost")
            return AssessResponse(
                application_id=f"APP-FB-{int(time.time())}",
                credit_score=fb["credit_score"],
                risk_category="MEDIUM",
                risk_score=75,
                decision="APPROVED",
                interest_rate=10.5,
                max_loan_amount=request.loan_amount or 500000,
                explanation={"reasoning": "Fallback assessment."},
            )
        logger.error(f"Loan assessment error: {e}")
        raise HTTPException(status_code=500, detail=f"Loan assessment failed: {str(e)}")

@router.post("/credit-score", response_model=CreditScoreResponse)
async def get_credit_score(request: CreditScoreRequest):
    """Get credit score for PAN number"""
    try:
        # Simulate CIBIL score
        cibil_score = simulate_cibil_score(request.pan_number)
        
        # Predict XGBoost score
        features = {"cibil_score": cibil_score}
        xgboost_score = predict_credit_score(features)
        
        # Calculate final score
        credit_result = calculate_credit_score(cibil_score, xgboost_score)
        
        return CreditScoreResponse(
            cibil_score=cibil_score,
            credit_score=credit_result["final_score"],
            risk_category=credit_result["risk_category"],
            risk_score=credit_result["risk_score"]
        )
        
    except Exception as e:
        logger.error(f"Credit score error: {e}")
        raise HTTPException(status_code=500, detail=f"Credit score calculation failed: {str(e)}")

@router.get("/health")
async def underwriting_health():
    """Underwriting service health check"""
    return {
        "status": "healthy" if model_loaded() else "degraded",
        "model_loaded": model_loaded(),
        "score_range": f"{settings.CREDIT_SCORE_MIN}-{settings.CREDIT_SCORE_MAX}",
        "hard_reject_threshold": settings.HARD_REJECT_THRESHOLD
    }

@router.get("/model-info")
async def get_model_info():
    """Returns model metadata and training details"""
    global _metadata
    if not _metadata:
        # Try to reload if missing
        load_model()
        
    if not _metadata:
        return {
            "error": "Model metadata not found",
            "status": "degraded",
            "message": "Model is running in rule-based fallback mode"
        }
    
    return _metadata
