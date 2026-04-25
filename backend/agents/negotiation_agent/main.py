import logging
import os
import joblib
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.session import session_store
from groq_client import groq_client
from services.emi import calculate_emi, calculate_negotiation_params
from core.config import settings

logger = logging.getLogger("loanease.negotiation")

router = APIRouter()

# Pydantic models
class NegotiationStartRequest(BaseModel):
    session_id: str
    desired_rate: Optional[float] = None
    customer_profile: str = "STANDARD"

class NegotiationStartResponse(BaseModel):
    negotiation_id: str
    current_rate: float
    min_rate: float
    max_concession: float
    total_steps: int
    customer_profile: str

class NegotiationCounterRequest(BaseModel):
    session_id: str
    negotiation_id: str
    proposed_rate: float

class NegotiationCounterResponse(BaseModel):
    negotiation_id: str
    current_rate: float
    proposed_rate: float
    counter_offer: float
    step: int
    total_steps: int
    accepted: bool
    negotiation_complete: bool
    message: str = ""

class NegotiationAcceptRequest(BaseModel):
    session_id: str
    negotiation_id: str
    final_rate: float

class NegotiationAcceptResponse(BaseModel):
    negotiation_id: str
    accepted_rate: float
    monthly_emi: float
    negotiation_complete: bool
    message: str

# Global negotiation store
_negotiations = {}

# Negotiation Analytics
_analytics = {
  "total_negotiations": 0,
  "acceptance_rate": "0%",
  "avg_rounds_to_acceptance": 0.0,
  "avg_concession_given": "0.0%",
  "escalation_rate": "0%",
  "decisions_by_engine": {
    "hard_rules": 0,
    "ml_model": 0
  },
  "most_common_accept_round": 0,
  "avg_savings_per_applicant": 0,
  "top_reason_for_escalation": "none",
  # internal counters
  "accepted_count": 0,
  "escalated_count": 0,
  "total_rounds": 0,
  "total_concession": 0.0,
  "accept_rounds_map": {},
  "total_savings": 0.0,
  "escalation_reasons": {}
}

# Load ML Model
MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "models", "negotiation_model.pkl")
negotiation_model = None

def get_negotiation_model():
    global negotiation_model
    if negotiation_model is None and os.path.exists(MODEL_PATH):
        try:
            negotiation_model = joblib.load(MODEL_PATH)
        except Exception as e:
            logger.error(f"Failed to load negotiation model: {e}")
    return negotiation_model

def get_top_features(features: dict) -> list:
    return ["counter_aggressiveness", "risk_score"]

def decide_concession(features: dict, session: dict) -> dict:
    global _analytics
    
    # HARD RULES (override ML always):
    # Rule 1: Never go below floor rate
    if features.get("rate_headroom", 0) < 0.1:
        _analytics["decisions_by_engine"]["hard_rules"] += 1
        return {
            "action": "HOLD_FIRM",
            "reason": "floor_rate_reached",
            "decided_by": "HARD_RULE"
        }
    
    # Rule 2: High risk gets no concession
    if features.get("risk_score", 100) < 50:
        _analytics["decisions_by_engine"]["hard_rules"] += 1
        return {
            "action": "HOLD_FIRM", 
            "reason": "high_risk_profile",
            "decided_by": "HARD_RULE"
        }
    
    # Rule 3: Max rounds exhausted
    if features.get("rounds_remaining", 1) <= 0:
        _analytics["decisions_by_engine"]["hard_rules"] += 1
        return {
            "action": "ESCALATE",
            "reason": "max_rounds_reached",
            "decided_by": "HARD_RULE"
        }
    
    # ML MODEL decides for everything else:
    model = get_negotiation_model()
    _analytics["decisions_by_engine"]["ml_model"] += 1
    
    if not model:
        return {
            "action": "HOLD_FIRM",
            "reason": "model_not_found",
            "decided_by": "HARD_RULE"
        }
        
    feature_list = [
        features.get("risk_score", 75),
        features.get("credit_score_norm", 0.75),
        features.get("loan_to_income_ratio", 0.4),
        features.get("employment_stability", 1),
        features.get("current_round", 1),
        features.get("rounds_remaining", 2),
        features.get("current_rate", 12.0),
        features.get("floor_rate", 11.0),
        features.get("ceiling_rate", 13.0),
        features.get("rate_headroom", 1.0),
        features.get("counter_aggressiveness", 0.5),
        features.get("response_speed_seconds", 30),
        features.get("rounds_without_acceptance", 0)
    ]
    
    try:
        ml_action = model.predict([feature_list])[0]
        ml_confidence = model.predict_proba([feature_list])[0].max()
    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        ml_action = 0
        ml_confidence = 0.0
    
    # If ML not confident enough, fall back to conservative rule:
    if ml_confidence < 0.65:
        ml_action = 0  # Hold firm
        
    action_map = {
        0: "HOLD_FIRM",
        1: "SMALL_CONCESSION",
        2: "LARGE_CONCESSION",
        3: "ESCALATE"
    }
    
    return {
        "action": action_map.get(ml_action, "HOLD_FIRM"),
        "ml_confidence": float(ml_confidence),
        "decided_by": "ML_MODEL",
        "model": "RandomForest",
        "feature_importances": get_top_features(features)
    }

async def generate_negotiation_message(action: str, features: dict, loan_context: dict, language: str) -> str:
    prompt = f"""
    You are a loan negotiation agent.
    Decision made: {action}
    Applicant risk score: {features.get('risk_score', 75)}
    Current rate: {loan_context.get('current_rate', 12.0)}%
    New rate (if concession): {loan_context.get('current_rate', 12.0) - 0.25}%
    Round: {features.get('current_round', 1)} of {loan_context.get('max_rounds', 3)}
    Language: {language}
    
    Write a 2-3 sentence negotiation response that explains this decision naturally.
    Sound like a senior relationship manager.
    Be specific about why this rate was chosen.
    If HOLD_FIRM: explain the boundary kindly.
    If SMALL_CONCESSION: make it feel earned.
    If ESCALATE: make escalation feel like VIP treatment.
    Max 70 words. Financial terms stay in English.
    """
    try:
        res = await groq_client.complete(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.4
        )
        return res.content
    except Exception as e:
        logger.error(f"Groq generation failed: {e}")
        if action == "HOLD_FIRM":
            return "I have reviewed your request. Unfortunately, we cannot offer a lower rate at this time."
        elif action == "ESCALATE":
            return "Let me escalate this to a senior manager who can better assist you with this rate."
        else:
            return "I have reviewed your profile and can offer you a small concession."

def generate_negotiation_id() -> str:
    """Generate unique negotiation ID"""
    import uuid
    return f"NEG-{uuid.uuid4().hex[:8].upper()}"

@router.post("/start", response_model=NegotiationStartResponse)
async def start_negotiation(request: NegotiationStartRequest):
    """Start rate negotiation"""
    try:
        # Get session
        session = session_store.get(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Get underwriting result
        underwriting_result = session["data"].get("underwriting_result", {})
        if not underwriting_result:
            raise HTTPException(status_code=400, detail="Complete underwriting first")
        
        current_rate = underwriting_result.get("interest_rate", 12.0)
        risk_category = underwriting_result.get("risk_category", "MEDIUM")
        
        # Calculate negotiation parameters
        neg_params = calculate_negotiation_params(
            current_rate, 
            risk_category, 
            request.customer_profile
        )
        
        # Generate negotiation ID
        negotiation_id = generate_negotiation_id()
        
        # Store negotiation state
        _negotiations[negotiation_id] = {
            "session_id": request.session_id,
            "current_rate": current_rate,
            "min_rate": neg_params["min_rate"],
            "original_rate": current_rate,
            "step": 0,
            "total_steps": neg_params["total_steps"],
            "negotiation_steps": neg_params["negotiation_steps"],
            "customer_profile": request.customer_profile,
            "risk_category": risk_category,
            "completed": False
        }
        
        # Update session
        session_store.update_stage(request.session_id, "NEGOTIATION_STARTED")
        session_store.log_agent(request.session_id, {
            "agent": "negotiation",
            "action": "start",
            "negotiation_id": negotiation_id,
            "initial_rate": current_rate,
            "min_rate": neg_params["min_rate"]
        })
        
        return NegotiationStartResponse(
            negotiation_id=negotiation_id,
            current_rate=current_rate,
            min_rate=neg_params["min_rate"],
            max_concession=neg_params["max_concession"],
            total_steps=neg_params["total_steps"],
            customer_profile=request.customer_profile
        )
        
    except Exception as e:
        logger.error(f"Negotiation start error: {e}")
        raise HTTPException(status_code=500, detail=f"Negotiation start failed: {str(e)}")

@router.post("/counter", response_model=NegotiationCounterResponse)
async def counter_offer(request: NegotiationCounterRequest):
    """Handle counter offer in negotiation"""
    try:
        # Get negotiation
        negotiation = _negotiations.get(request.negotiation_id)
        if not negotiation:
            raise HTTPException(status_code=404, detail="Negotiation not found")
        
        if negotiation["completed"]:
            raise HTTPException(status_code=400, detail="Negotiation already completed")
        
        current_rate = negotiation["current_rate"]
        min_rate = negotiation["min_rate"]
        step = negotiation["step"]
        total_steps = negotiation["total_steps"]
        
        # Validate proposed rate
        session = session_store.get(negotiation["session_id"])
        
        # Calculate features for ML
        rate_headroom = current_rate - min_rate
        if current_rate > min_rate:
            aggressiveness = (current_rate - request.proposed_rate) / (current_rate - min_rate)
        else:
            aggressiveness = 0
            
        features = {
            "risk_score": 75,
            "credit_score_norm": 0.75,
            "loan_to_income_ratio": 0.4,
            "employment_stability": 1,
            "current_round": step + 1,
            "rounds_remaining": total_steps - step - 1,
            "current_rate": current_rate,
            "floor_rate": min_rate,
            "ceiling_rate": current_rate + 0.5,
            "rate_headroom": rate_headroom,
            "counter_aggressiveness": max(0, min(1, aggressiveness)),
            "response_speed_seconds": 45,
            "rounds_without_acceptance": step
        }
        
        if session:
            uw_result = session.get("data", {}).get("underwriting_result", {})
            features["risk_score"] = uw_result.get("risk_score", 75)
            features["credit_score_norm"] = features["risk_score"] / 100.0

        decision = decide_concession(features, session or {})
        action = decision["action"]
        
        counter_offer = current_rate
        accepted = False
        negotiation_complete = False
        message = ""
        
        global _analytics
        _analytics["total_negotiations"] += 1
        
        if request.proposed_rate >= current_rate:
            # Accept customer offer
            counter_offer = request.proposed_rate
            negotiation["current_rate"] = request.proposed_rate
            negotiation["completed"] = True
            negotiation_complete = True
            accepted = True
            action = "ACCEPT"
            _analytics["accepted_count"] += 1
            _analytics["total_rounds"] += features["current_round"]
            _analytics["accept_rounds_map"][features["current_round"]] = _analytics["accept_rounds_map"].get(features["current_round"], 0) + 1
        else:
            # Apply decision
            if action == "HOLD_FIRM":
                counter_offer = current_rate
            elif action == "SMALL_CONCESSION":
                counter_offer = max(min_rate, current_rate - 0.25)
            elif action == "LARGE_CONCESSION":
                counter_offer = max(min_rate, current_rate - 0.50)
            elif action == "ESCALATE" or action == "ESCALATE_TO_HUMAN":
                counter_offer = current_rate
                negotiation["completed"] = True
                negotiation_complete = True
                _analytics["escalated_count"] += 1
                reason = decision.get("reason", "unknown")
                _analytics["escalation_reasons"][reason] = _analytics["escalation_reasons"].get(reason, 0) + 1
            
            if step + 1 >= total_steps and not negotiation_complete:
                negotiation["completed"] = True
                negotiation_complete = True
                
            negotiation["current_rate"] = counter_offer
            negotiation["step"] = step + 1
            
            # Record concession
            concession_given = current_rate - counter_offer
            if concession_given > 0:
                _analytics["total_concession"] += concession_given
                _analytics["total_savings"] += (concession_given / 100) * 1000000  # rough estimate
        
        # Generate message
        loan_context = {
            "current_rate": current_rate,
            "max_rounds": total_steps
        }
        language = "en"
        message = await generate_negotiation_message(action, features, loan_context, language)
        
        # Update session
        if session:
            session_store.log_agent(negotiation["session_id"], {
                "agent": "negotiation",
                "action": "counter",
                "negotiation_id": request.negotiation_id,
                "proposed_rate": request.proposed_rate,
                "counter_offer": counter_offer,
                "step": negotiation["step"],
                "decision": decision,
                "message": message
            })
        
        return NegotiationCounterResponse(
            negotiation_id=request.negotiation_id,
            current_rate=current_rate,
            proposed_rate=request.proposed_rate,
            counter_offer=counter_offer,
            step=negotiation["step"],
            total_steps=total_steps,
            accepted=accepted,
            negotiation_complete=negotiation_complete,
            message=message
        )
        
    except Exception as e:
        logger.error(f"Counter offer error: {e}")
        raise HTTPException(status_code=500, detail=f"Counter offer failed: {str(e)}")

@router.post("/accept", response_model=NegotiationAcceptResponse)
async def accept_negotiation(request: NegotiationAcceptRequest):
    """Accept final negotiated rate"""
    try:
        # Get negotiation
        negotiation = _negotiations.get(request.negotiation_id)
        if not negotiation:
            raise HTTPException(status_code=404, detail="Negotiation not found")
        
        if not negotiation["completed"]:
            raise HTTPException(status_code=400, detail="Negotiation not completed")
        
        # Get session and loan details
        session = session_store.get(negotiation["session_id"])
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        underwriting_result = session["data"].get("underwriting_result", {})
        loan_amount = underwriting_result.get("loan_amount", 500000)
        tenure_years = underwriting_result.get("tenure_years", 5)
        
        # Calculate EMI with accepted rate
        emi_result = calculate_emi(loan_amount, request.final_rate, tenure_years)
        
        # Update session
        session_store.update_stage(negotiation["session_id"], "NEGOTIATION_COMPLETE")
        session_store.update_data(negotiation["session_id"], "final_rate", request.final_rate)
        session_store.update_data(negotiation["session_id"], "emi_details", emi_result)
        session_store.log_agent(negotiation["session_id"], {
            "agent": "negotiation",
            "action": "accept",
            "negotiation_id": request.negotiation_id,
            "final_rate": request.final_rate,
            "monthly_emi": emi_result["monthly_emi"]
        })
        
        # Clean up negotiation
        del _negotiations[request.negotiation_id]
        
        return NegotiationAcceptResponse(
            negotiation_id=request.negotiation_id,
            accepted_rate=request.final_rate,
            monthly_emi=emi_result["monthly_emi"],
            negotiation_complete=True,
            message=f"Loan approved at {request.final_rate}% with EMI of ₹{emi_result['monthly_emi']:,.2f}"
        )
        
    except Exception as e:
        logger.error(f"Accept negotiation error: {e}")
        raise HTTPException(status_code=500, detail=f"Accept negotiation failed: {str(e)}")

@router.get("/health")
async def negotiation_health():
    """Negotiation service health check"""
    return {
        "status": "healthy",
        "active_negotiations": len(_negotiations),
        "rate_range": f"{settings.RATE_FLOOR}% - {settings.RATE_CEILING}%",
        "concession_step": settings.CONCESSION_STEP
    }

@router.get("/analytics")
async def get_analytics():
    """Get negotiation analytics"""
    global _analytics
    
    total = _analytics["total_negotiations"]
    if total > 0:
        _analytics["acceptance_rate"] = f"{(_analytics['accepted_count'] / total) * 100:.0f}%"
        _analytics["escalation_rate"] = f"{(_analytics['escalated_count'] / total) * 100:.0f}%"
    
    if _analytics["accepted_count"] > 0:
        _analytics["avg_rounds_to_acceptance"] = round(_analytics["total_rounds"] / _analytics["accepted_count"], 1)
        
    if total > 0:
        _analytics["avg_concession_given"] = f"{_analytics['total_concession'] / total:.2f}%"
        _analytics["avg_savings_per_applicant"] = int(_analytics["total_savings"] / total)
        
    if _analytics["accept_rounds_map"]:
        _analytics["most_common_accept_round"] = max(_analytics["accept_rounds_map"].items(), key=lambda x: x[1])[0]
        
    if _analytics["escalation_reasons"]:
        _analytics["top_reason_for_escalation"] = max(_analytics["escalation_reasons"].items(), key=lambda x: x[1])[0]
        
    return {
        "total_negotiations": total,
        "acceptance_rate": _analytics["acceptance_rate"],
        "avg_rounds_to_acceptance": _analytics["avg_rounds_to_acceptance"],
        "avg_concession_given": _analytics["avg_concession_given"],
        "escalation_rate": _analytics["escalation_rate"],
        "decisions_by_engine": _analytics["decisions_by_engine"],
        "most_common_accept_round": _analytics["most_common_accept_round"],
        "avg_savings_per_applicant": _analytics["avg_savings_per_applicant"],
        "top_reason_for_escalation": _analytics["top_reason_for_escalation"]
    }
