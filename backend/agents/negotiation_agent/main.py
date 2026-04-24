import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.session import session_store
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
        if request.proposed_rate < min_rate:
            # Below minimum - offer minimum
            counter_offer = min_rate
            negotiation["current_rate"] = min_rate
            negotiation["completed"] = True
            negotiation_complete = True
            accepted = False
        elif request.proposed_rate >= current_rate:
            # Accept customer offer
            counter_offer = request.proposed_rate
            negotiation["current_rate"] = request.proposed_rate
            negotiation["completed"] = True
            negotiation_complete = True
            accepted = True
        else:
            # Make counter offer
            if step < total_steps - 1:
                # Move to next step
                next_step = step + 1
                negotiation_steps = negotiation["negotiation_steps"]
                counter_offer = negotiation_steps[next_step]
                negotiation["current_rate"] = counter_offer
                negotiation["step"] = next_step
                negotiation_complete = False
                accepted = False
            else:
                # Final step - accept if reasonable
                if request.proposed_rate >= min_rate:
                    counter_offer = request.proposed_rate
                    negotiation["current_rate"] = request.proposed_rate
                    negotiation["completed"] = True
                    negotiation_complete = True
                    accepted = True
                else:
                    counter_offer = min_rate
                    negotiation["current_rate"] = min_rate
                    negotiation["completed"] = True
                    negotiation_complete = True
                    accepted = False
        
        # Update session
        session = session_store.get(negotiation["session_id"])
        if session:
            session_store.log_agent(negotiation["session_id"], {
                "agent": "negotiation",
                "action": "counter",
                "negotiation_id": request.negotiation_id,
                "proposed_rate": request.proposed_rate,
                "counter_offer": counter_offer,
                "step": negotiation["step"]
            })
        
        return NegotiationCounterResponse(
            negotiation_id=request.negotiation_id,
            current_rate=current_rate,
            proposed_rate=request.proposed_rate,
            counter_offer=counter_offer,
            step=negotiation["step"],
            total_steps=total_steps,
            accepted=accepted,
            negotiation_complete=negotiation_complete
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
