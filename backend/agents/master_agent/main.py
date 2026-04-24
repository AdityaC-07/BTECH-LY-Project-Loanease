import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime, timezone

from core.session import session_store
from core.config import settings

logger = logging.getLogger("loanease.master")

router = APIRouter()

# Pydantic models
class PipelineStartRequest(BaseModel):
    customer_name: str
    initial_message: str = "I want to apply for a personal loan"
    language: str = "en"

class PipelineStartResponse(BaseModel):
    session_id: str
    stage: str
    message: str
    next_steps: list[str]

class PipelineStatusRequest(BaseModel):
    session_id: str

class PipelineStatusResponse(BaseModel):
    session_id: str
    stage: str
    progress: Dict[str, Any]
    agent_log: list[Dict[str, Any]]
    next_actions: list[str]

class PipelineProcessRequest(BaseModel):
    session_id: str
    action: str
    data: Optional[Dict[str, Any]] = None

class PipelineProcessResponse(BaseModel):
    session_id: str
    stage: str
    action_result: Dict[str, Any]
    next_stage: Optional[str]
    message: str

def create_session(customer_name: str, initial_data: Dict[str, Any]) -> str:
    """Create new session"""
    session_data = {
        "customer_name": customer_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        **initial_data
    }
    return session_store.create(session_data)

def get_session_stage_actions(stage: str) -> list[str]:
    """Get available actions for current stage"""
    stage_actions = {
        "INITIATED": ["upload_pan", "start_chat"],
        "PAN_UPLOADED": ["upload_aadhaar", "extract_pan"],
        "AADHAAR_UPLOADED": ["verify_kyc"],
        "KYC_VERIFIED": ["assess_credit"],
        "UNDERWRITING_COMPLETE": ["start_negotiation"],
        "NEGOTIATION_STARTED": ["negotiate_rate", "accept_offer"],
        "NEGOTIATION_COMPLETE": ["generate_sanction"],
        "BLOCKCHAIN_VERIFIED": ["complete"],
        "COMPLETED": []
    }
    return stage_actions.get(stage, [])

def get_stage_progress(stage: str) -> Dict[str, Any]:
    """Get progress information for stage"""
    progress_stages = [
        "INITIATED",
        "PAN_UPLOADED", 
        "AADHAAR_UPLOADED",
        "KYC_VERIFIED",
        "UNDERWRITING_COMPLETE",
        "NEGOTIATION_COMPLETE",
        "BLOCKCHAIN_VERIFIED",
        "COMPLETED"
    ]
    
    current_index = progress_stages.index(stage) if stage in progress_stages else 0
    total_stages = len(progress_stages)
    
    return {
        "current_stage": stage,
        "current_index": current_index,
        "total_stages": total_stages,
        "progress_percentage": (current_index / (total_stages - 1)) * 100 if total_stages > 1 else 0,
        "completed_stages": progress_stages[:current_index],
        "remaining_stages": progress_stages[current_index + 1:]
    }

@router.post("/start", response_model=PipelineStartResponse)
async def start_pipeline(request: PipelineStartRequest):
    """Start loan application pipeline"""
    try:
        # Create session
        session_id = create_session(request.customer_name, {
            "initial_message": request.initial_message,
            "language": request.language
        })
        
        # Get next actions
        next_actions = get_session_stage_actions("INITIATED")
        
        # Update session
        session_store.update_stage(session_id, "INITIATED")
        session_store.log_agent(session_id, {
            "agent": "master",
            "action": "pipeline_start",
            "customer_name": request.customer_name,
            "language": request.language
        })
        
        return PipelineStartResponse(
            session_id=session_id,
            stage="INITIATED",
            message=f"Welcome {request.customer_name}! Your loan application has been initiated.",
            next_steps=next_actions
        )
        
    except Exception as e:
        logger.error(f"Pipeline start error: {e}")
        raise HTTPException(status_code=500, detail=f"Pipeline start failed: {str(e)}")

@router.post("/status", response_model=PipelineStatusResponse)
async def get_pipeline_status(request: PipelineStatusRequest):
    """Get current pipeline status"""
    try:
        # Get session
        session = session_store.get(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Get progress
        progress = get_stage_progress(session["stage"])
        
        # Get next actions
        next_actions = get_session_stage_actions(session["stage"])
        
        return PipelineStatusResponse(
            session_id=request.session_id,
            stage=session["stage"],
            progress=progress,
            agent_log=session["agent_log"],
            next_actions=next_actions
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pipeline status error: {e}")
        raise HTTPException(status_code=500, detail=f"Pipeline status failed: {str(e)}")

@router.post("/process", response_model=PipelineProcessResponse)
async def process_pipeline_action(request: PipelineProcessRequest):
    """Process pipeline action"""
    try:
        # Get session
        session = session_store.get(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        current_stage = session["stage"]
        action_result = {}
        next_stage = None
        message = ""
        
        # Process action based on current stage
        if request.action == "upload_pan":
            if request.data and "pan_data" in request.data:
                session_store.update_data(request.session_id, "pan_data", request.data["pan_data"])
                session_store.update_stage(request.session_id, "PAN_UPLOADED")
                next_stage = "PAN_UPLOADED"
                message = "PAN card uploaded successfully"
                action_result = {"status": "success", "data": request.data["pan_data"]}
            else:
                message = "PAN data required"
                action_result = {"status": "error", "message": "PAN data required"}
        
        elif request.action == "upload_aadhaar":
            if request.data and "aadhaar_data" in request.data:
                session_store.update_data(request.session_id, "aadhaar_data", request.data["aadhaar_data"])
                session_store.update_stage(request.session_id, "AADHAAR_UPLOADED")
                next_stage = "AADHAAR_UPLOADED"
                message = "Aadhaar card uploaded successfully"
                action_result = {"status": "success", "data": request.data["aadhaar_data"]}
            else:
                message = "Aadhaar data required"
                action_result = {"status": "error", "message": "Aadhaar data required"}
        
        elif request.action == "verify_kyc":
            # KYC verification would be handled by KYC agent
            if request.data and "kyc_result" in request.data:
                kyc_result = request.data["kyc_result"]
                if kyc_result.get("overall_kyc_passed"):
                    session_store.update_stage(request.session_id, "KYC_VERIFIED")
                    next_stage = "KYC_VERIFIED"
                    message = "KYC verification completed successfully"
                else:
                    message = "KYC verification failed"
                action_result = {"status": "success", "data": kyc_result}
            else:
                message = "KYC verification result required"
                action_result = {"status": "error", "message": "KYC result required"}
        
        elif request.action == "assess_credit":
            # Credit assessment would be handled by underwriting agent
            if request.data and "underwriting_result" in request.data:
                underwriting_result = request.data["underwriting_result"]
                if underwriting_result.get("decision") == "APPROVED":
                    session_store.update_stage(request.session_id, "UNDERWRITING_COMPLETE")
                    next_stage = "UNDERWRITING_COMPLETE"
                    message = "Credit assessment completed - Loan approved"
                else:
                    message = "Credit assessment completed - Loan rejected"
                action_result = {"status": "success", "data": underwriting_result}
            else:
                message = "Underwriting result required"
                action_result = {"status": "error", "message": "Underwriting result required"}
        
        elif request.action == "start_negotiation":
            if request.data and "negotiation_data" in request.data:
                session_store.update_stage(request.session_id, "NEGOTIATION_STARTED")
                next_stage = "NEGOTIATION_STARTED"
                message = "Rate negotiation started"
                action_result = {"status": "success", "data": request.data["negotiation_data"]}
            else:
                message = "Negotiation data required"
                action_result = {"status": "error", "message": "Negotiation data required"}
        
        elif request.action == "complete_negotiation":
            if request.data and "final_rate" in request.data:
                session_store.update_stage(request.session_id, "NEGOTIATION_COMPLETE")
                next_stage = "NEGOTIATION_COMPLETE"
                message = f"Negotiation completed at {request.data['final_rate']}% interest rate"
                action_result = {"status": "success", "data": request.data}
            else:
                message = "Final rate required"
                action_result = {"status": "error", "message": "Final rate required"}
        
        elif request.action == "generate_sanction":
            if request.data and "blockchain_data" in request.data:
                session_store.update_stage(request.session_id, "BLOCKCHAIN_VERIFIED")
                next_stage = "BLOCKCHAIN_VERIFIED"
                message = "Sanction letter generated and verified on blockchain"
                action_result = {"status": "success", "data": request.data["blockchain_data"]}
            else:
                message = "Blockchain data required"
                action_result = {"status": "error", "message": "Blockchain data required"}
        
        elif request.action == "complete":
            session_store.update_stage(request.session_id, "COMPLETED")
            next_stage = "COMPLETED"
            message = "Loan application process completed successfully!"
            action_result = {"status": "success"}
        
        else:
            message = f"Unknown action: {request.action}"
            action_result = {"status": "error", "message": message}
        
        # Log action
        session_store.log_agent(request.session_id, {
            "agent": "master",
            "action": request.action,
            "result": action_result,
            "next_stage": next_stage
        })
        
        return PipelineProcessResponse(
            session_id=request.session_id,
            stage=session["stage"],
            action_result=action_result,
            next_stage=next_stage,
            message=message
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pipeline process error: {e}")
        raise HTTPException(status_code=500, detail=f"Pipeline process failed: {str(e)}")

@router.get("/health")
async def pipeline_health():
    """Pipeline service health check"""
    return {
        "status": "healthy",
        "active_sessions": len(session_store._sessions),
        "session_ttl_hours": settings.SESSION_TTL_HOURS
    }
