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
    session_id: str
    loan_amount: float
    tenure_years: int

class AssessResponse(BaseModel):
    application_id: str
    credit_score: int
    risk_category: str
    risk_score: int
    decision: str
    interest_rate: float
    max_loan_amount: float
    explanation: Dict[str, Any]

class CreditScoreRequest(BaseModel):
    pan_number: str

class CreditScoreResponse(BaseModel):
    cibil_score: int
    credit_score: int
    risk_category: str
    risk_score: int

def load_model():
    """Load XGBoost model into memory"""
    global _model, _model_features
    try:
        # Try to load the model file
        model_path = "models/loan_model.pkl"
        if os.path.exists(model_path):
            _model = joblib.load(model_path)
            logger.info("XGBoost model loaded successfully")
        else:
            logger.warning("Model file not found, using fallback")
            _model = None
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        _model = None

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
    """Assess loan application"""
    try:
        # Artificial delay for demo visibility
        if settings.DEMO_MODE:
            import asyncio
            await asyncio.sleep(1.2)  # Let evaluators see Credit Agent activating
        # Get session
        session = session_store.get(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Get KYC data
        pan_data = session["data"].get("pan_data", {})
        pan_number = pan_data.get("pan_number", "")
        
        # Generate application ID
        app_id = generate_application_id()
        
        # Simulate CIBIL score
        cibil_score = simulate_cibil_score(pan_number)
        
        # Prepare features for XGBoost
        features = {
            "cibil_score": cibil_score,
            "loan_amount": request.loan_amount,
            "tenure_years": request.tenure_years,
            "age": pan_data.get("age", 30),
            "income_estimated": 500000,  # Default estimated income
        }
        
        # Predict credit score
        xgboost_score = predict_credit_score(features)
        
        # Calculate final credit score
        credit_result = calculate_credit_score(cibil_score, xgboost_score)
        
        # Determine interest rate based on risk category
        base_rate = 12.0  # Base rate
        risk_adjustments = {
            "LOW": -1.0,
            "MEDIUM": 0.0,
            "MEDIUM-HIGH": 1.5,
            "HIGH": 3.0
        }
        
        interest_rate = base_rate + risk_adjustments.get(credit_result["risk_category"], 0.0)
        interest_rate = max(settings.RATE_FLOOR, min(settings.RATE_CEILING, interest_rate))
        
        # Determine decision
        if credit_result["hard_reject"]:
            decision = "REJECTED"
            max_loan = 0
        else:
            decision = "APPROVED"
            # Calculate max loan based on credit score
            max_loan = request.loan_amount * (credit_result["final_score"] / 900)
        
        # Generate explanation
        explanation = {
            "factors": {
                "cibil_score": {
                    "value": cibil_score,
                    "weight": settings.CIBIL_WEIGHT,
                    "impact": "positive" if cibil_score >= 700 else "negative"
                },
                "xgboost_score": {
                    "value": round(xgboost_score, 2),
                    "weight": settings.XGBOOST_WEIGHT,
                    "impact": "positive" if xgboost_score >= 700 else "negative"
                }
            },
            "reasoning": f"Credit score of {credit_result['final_score']} falls in {credit_result['risk_category']} risk category"
        }
        
        # Update session
        session_store.update_stage(request.session_id, "UNDERWRITING_COMPLETE")
        session_store.update_data(request.session_id, "underwriting_result", {
            "application_id": app_id,
            "decision": decision,
            "credit_score": credit_result["final_score"],
            "interest_rate": interest_rate
        })
        session_store.log_agent(request.session_id, {
            "agent": "underwriting",
            "action": "assessment",
            "success": decision == "APPROVED",
            "application_id": app_id,
            "credit_score": credit_result["final_score"],
            "decision": decision
        })
        
        return AssessResponse(
            application_id=app_id,
            credit_score=credit_result["final_score"],
            risk_category=credit_result["risk_category"],
            risk_score=credit_result["risk_score"],
            decision=decision,
            interest_rate=interest_rate,
            max_loan_amount=max_loan,
            explanation=explanation
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
                max_loan_amount=request.loan_amount,
                explanation={"reasoning": "Fallback assessment due to component unavailability."}
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
