import logging
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional, Dict, Any
import io
from PIL import Image

from core.session import session_store
from services.ocr import preprocess_image, run_ocr, extract_pan, extract_aadhaar, cross_validate_kyc, ocr_ready
from core.config import settings

logger = logging.getLogger("loanease.kyc")

router = APIRouter()

# Pydantic models
class PanExtractResponse(BaseModel):
    document_type: str = "PAN"
    extracted_fields: Dict[str, Any]
    validation: Dict[str, Any]
    confidence_score: float
    processing_time_ms: int

class AadhaarExtractResponse(BaseModel):
    document_type: str = "AADHAAR"
    extracted_fields: Dict[str, Any]
    validation: Dict[str, Any]
    confidence_score: float
    processing_time_ms: int

class VerifyRequest(BaseModel):
    session_id: str

class VerifyResponse(BaseModel):
    kyc_status: str
    pan_data: Dict[str, Any]
    aadhaar_data: Dict[str, Any]
    cross_validation: Dict[str, Any]
    overall_kyc_passed: bool
    kyc_reference_id: str
    timestamp: str

def _assert_upload_constraints(file: UploadFile, file_bytes: bytes):
    """Validate file upload constraints"""
    if file.size > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413, 
            detail=f"File exceeds {settings.MAX_UPLOAD_BYTES // (1024*1024)}MB limit"
        )
    
    extension = file.filename.split('.')[-1].lower() if file.filename else ""
    if extension not in ['jpg', 'jpeg', 'png', 'pdf', 'bmp', 'tiff']:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Supported: JPG, PNG, PDF, BMP, TIFF"
        )

@router.post("/extract/pan", response_model=PanExtractResponse)
async def extract_pan_endpoint(
    document: UploadFile = File(...),
    session_id: str = Form(...),
    language: str = Form("en")
):
    """Extract information from PAN card"""
    import time
    start_time = time.time()
    
    try:
        # Read file
        file_bytes = await document.read()
        _assert_upload_constraints(document, file_bytes)
        
        # Get session
        session = session_store.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Process document
        extension = document.filename.split('.')[-1].lower()
        preprocessed = preprocess_image(file_bytes, extension)
        ocr_text, confidence = run_ocr(preprocessed)
        
        # Extract PAN information
        pan_data = extract_pan(ocr_text)
        
        # Validation
        issues = []
        pan_valid = bool(pan_data.get("pan_number"))
        if not pan_valid:
            issues.append("PAN number not detected")
        
        if not pan_data.get("name"):
            issues.append("Name not detected")
        
        if not pan_data.get("date_of_birth"):
            issues.append("Date of birth not detected")
        
        age = pan_data.get("age")
        age_ok = age is not None and 21 <= age <= 65
        if not age_ok:
            issues.append("Age must be between 21 and 65")
        
        processing_time = int((time.time() - start_time) * 1000)
        
        # Update session
        session_store.update_data(session_id, "pan_data", pan_data)
        session_store.log_agent(session_id, {
            "agent": "kyc",
            "action": "pan_extraction",
            "success": pan_valid,
            "confidence": confidence,
            "processing_time_ms": processing_time
        })
        
        return PanExtractResponse(
            extracted_fields=pan_data,
            validation={
                "pan_format_valid": pan_valid,
                "age_check_passed": age_ok,
                "name_found": bool(pan_data.get("name")),
                "dob_found": bool(pan_data.get("date_of_birth")),
                "overall_valid": pan_valid and age_ok,
                "issues": issues
            },
            confidence_score=confidence,
            processing_time_ms=processing_time
        )
        
    except Exception as e:
        logger.error(f"PAN extraction error: {e}")
        raise HTTPException(status_code=500, detail=f"PAN extraction failed: {str(e)}")

@router.post("/extract/aadhaar", response_model=AadhaarExtractResponse)
async def extract_aadhaar_endpoint(
    document: UploadFile = File(...),
    session_id: str = Form(...),
    language: str = Form("en")
):
    """Extract information from Aadhaar card"""
    import time
    start_time = time.time()
    
    try:
        # Read file
        file_bytes = await document.read()
        _assert_upload_constraints(document, file_bytes)
        
        # Get session
        session = session_store.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Process document
        extension = document.filename.split('.')[-1].lower()
        preprocessed = preprocess_image(file_bytes, extension)
        ocr_text, confidence = run_ocr(preprocessed)
        
        # Extract Aadhaar information
        aadhaar_data = extract_aadhaar(ocr_text)
        
        # Validation (more lenient for testing)
        issues = []
        aadhaar_valid = bool(aadhaar_data.get("aadhaar_number")) or bool(aadhaar_data.get("aadhaar_last4"))
        if not aadhaar_valid:
            issues.append("Aadhaar number not detected")
        
        age = aadhaar_data.get("age")
        age_ok = age is not None and 21 <= age <= 65
        if not age_ok:
            issues.append("Age must be between 21 and 65")
        
        processing_time = int((time.time() - start_time) * 1000)
        
        # Update session
        session_store.update_data(session_id, "aadhaar_data", aadhaar_data)
        session_store.log_agent(session_id, {
            "agent": "kyc",
            "action": "aadhaar_extraction",
            "success": aadhaar_valid,
            "confidence": confidence,
            "processing_time_ms": processing_time
        })
        
        return AadhaarExtractResponse(
            extracted_fields=aadhaar_data,
            validation={
                "aadhaar_format_valid": aadhaar_valid,
                "age_check_passed": age_ok,
                "overall_valid": aadhaar_valid and age_ok,
                "issues": issues
            },
            confidence_score=confidence,
            processing_time_ms=processing_time
        )
        
    except Exception as e:
        logger.error(f"Aadhaar extraction error: {e}")
        raise HTTPException(status_code=500, detail=f"Aadhaar extraction failed: {str(e)}")

@router.post("/verify", response_model=VerifyResponse)
async def verify_kyc(request: VerifyRequest):
    """Verify KYC by cross-validating PAN and Aadhaar data"""
    from datetime import datetime, timezone
    
    try:
        # Get session
        session = session_store.get(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Get PAN and Aadhaar data
        pan_data = session["data"].get("pan_data", {})
        aadhaar_data = session["data"].get("aadhaar_data", {})
        
        if not pan_data or not aadhaar_data:
            raise HTTPException(status_code=400, detail="Both PAN and Aadhaar data required")
        
        # Cross-validate
        cross_validation = cross_validate_kyc(pan_data, aadhaar_data)
        
        # Generate reference ID
        timestamp = datetime.now(timezone.utc)
        ref = f"KYC-{timestamp.year}-{len(session['agent_log']) + 1:05d}"
        
        # Update session
        session_store.update_stage(request.session_id, "KYC_VERIFIED")
        session_store.log_agent(request.session_id, {
            "agent": "kyc",
            "action": "verification",
            "success": cross_validation["overall_kyc_passed"],
            "kyc_status": cross_validation["kyc_status"],
            "reference_id": ref
        })
        
        return VerifyResponse(
            kyc_status=cross_validation["kyc_status"],
            pan_data=pan_data,
            aadhaar_data=aadhaar_data,
            cross_validation=cross_validation,
            overall_kyc_passed=cross_validation["overall_kyc_passed"],
            kyc_reference_id=ref,
            timestamp=timestamp.isoformat()
        )
        
    except Exception as e:
        logger.error(f"KYC verification error: {e}")
        raise HTTPException(status_code=500, detail=f"KYC verification failed: {str(e)}")

@router.get("/health")
async def kyc_health():
    """KYC service health check"""
    return {
        "status": "healthy" if ocr_ready() else "degraded",
        "ocr_ready": ocr_ready(),
        "max_upload_mb": settings.MAX_UPLOAD_BYTES // (1024 * 1024)
    }
