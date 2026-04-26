import logging
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Body
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional, Dict, Any
import io
from PIL import UnidentifiedImageError

from core.session import session_store
from services.ocr import preprocess_image, run_ocr, extract_pan, extract_aadhaar, cross_validate_kyc, ocr_ready, init_ocr
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
    if len(file_bytes) > settings.MAX_UPLOAD_BYTES:
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
        # Lazy-init OCR for resilience in reload/startup race conditions.
        if not ocr_ready():
            init_ocr()
        if not ocr_ready():
            raise HTTPException(status_code=503, detail="OCR service is initializing. Please retry in a few seconds.")

        # Read file
        file_bytes = await document.read()
        _assert_upload_constraints(document, file_bytes)
        
        # Get or initialize session
        session_store.get_or_create(session_id)
        
        # Process document
        extension = document.filename.split('.')[-1].lower()
        preprocessed = preprocess_image(file_bytes, extension)
        ocr_text, confidence = run_ocr(preprocessed)
        
        # Extract PAN information
        pan_data = extract_pan(ocr_text)
        
        # Relaxed Validation
        issues = []
        pan_valid = bool(pan_data.get("pan_number"))
        if not pan_valid:
            issues.append("PAN number not detected")
        
        # Name is optional now - more forgiving
        if not pan_data.get("name") and confidence < 0.3:
            issues.append("Name not detected")
        
        # DOB is optional now - more forgiving
        if not pan_data.get("date_of_birth") and confidence < 0.2:
            issues.append("Date of birth not detected")
        
        age = pan_data.get("age")
        age_ok = age is not None and 18 <= age <= 75  # Wider age range
        if not age_ok and age is not None:
            issues.append("Age must be between 18 and 75")
        
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
        
        # More lenient overall validation - PAN number is the key requirement
        overall_valid = pan_valid and (confidence >= 0.15 or bool(pan_data.get("name")))
        
        return PanExtractResponse(
            extracted_fields=pan_data,
            validation={
                "pan_format_valid": pan_valid,
                "age_check_passed": age_ok,
                "name_found": bool(pan_data.get("name")),
                "dob_found": bool(pan_data.get("date_of_birth")),
                "overall_valid": overall_valid,
                "issues": issues
            },
            confidence_score=confidence,
            processing_time_ms=processing_time
        )
        
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as e:
        logger.warning(f"PAN extraction upload validation failed: {e}")
        error_msg = str(e).lower()
        if "cannot identify" in error_msg or "not a valid image" in error_msg:
            detail = "This doesn't appear to be a valid image file. Please upload a JPG, PNG, or PDF PAN card."
        elif "truncated" in error_msg or "corrupt" in error_msg:
            detail = "The image file appears to be corrupted. Please try uploading a different PAN card image."
        elif "allocation" in error_msg or "memory" in error_msg:
            detail = "The image is too large. Please upload a smaller PAN card image under 5MB."
        elif "pdf" in error_msg and ("not available" in error_msg or "processing" in error_msg):
            detail = "PDF processing is not available. Please upload a JPG or PNG image of your PAN card."
        elif "pdf" in error_msg and ("invalid" in error_msg or "corrupt" in error_msg):
            detail = "The PDF file appears to be corrupted. Please try uploading a different PAN card PDF or image."
        elif "no valid images found in pdf" in error_msg:
            detail = "No readable content found in the PDF. Please ensure it contains a clear PAN card image."
        else:
            detail = "Please upload a clear PAN card image or PDF. The system couldn't process this file."
        
        raise HTTPException(
            status_code=400,
            detail=detail,
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
        # Lazy-init OCR for resilience in reload/startup race conditions.
        if not ocr_ready():
            init_ocr()
        if not ocr_ready():
            raise HTTPException(status_code=503, detail="OCR service is initializing. Please retry in a few seconds.")

        # Read file
        file_bytes = await document.read()
        _assert_upload_constraints(document, file_bytes)
        
        # Get or initialize session
        session_store.get_or_create(session_id)
        
        # Process document
        extension = document.filename.split('.')[-1].lower()
        preprocessed = preprocess_image(file_bytes, extension)
        ocr_text, confidence = run_ocr(preprocessed)
        
        # Extract Aadhaar information
        aadhaar_data = extract_aadhaar(ocr_text)
        
        # Relaxed Validation
        issues = []
        aadhaar_valid = bool(aadhaar_data.get("aadhaar_number")) or bool(aadhaar_data.get("aadhaar_last4"))
        if not aadhaar_valid and confidence < 0.1:
            issues.append("Aadhaar number not detected")
        
        age = aadhaar_data.get("age")
        age_ok = age is not None and 18 <= age <= 75  # Wider age range
        if not age_ok and age is not None:
            issues.append("Age must be between 18 and 75")
        
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
        
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as e:
        logger.warning(f"Aadhaar extraction upload validation failed: {e}")
        raise HTTPException(
            status_code=400,
            detail="Unable to read uploaded Aadhaar document. Please upload a clear JPG/PNG/JPEG/BMP/TIFF image.",
        )
    except Exception as e:
        logger.error(f"Aadhaar extraction error: {e}")
        raise HTTPException(status_code=500, detail=f"Aadhaar extraction failed: {str(e)}")

@router.post("/verify", response_model=VerifyResponse)
async def verify_kyc(
    request: VerifyRequest | None = Body(default=None),
    session_id: str | None = Form(default=None),
    pan: UploadFile | None = File(default=None),
    aadhaar: UploadFile | None = File(default=None),
):
    """Verify KYC by cross-validating PAN and Aadhaar data"""
    from datetime import datetime, timezone
    
    try:
        resolved_session_id = request.session_id if request is not None else session_id

        # Path 1: verify directly from uploaded PAN + Aadhaar documents.
        if pan is not None and aadhaar is not None:
            if not ocr_ready():
                init_ocr()
            if not ocr_ready():
                raise HTTPException(status_code=503, detail="OCR service is initializing. Please retry in a few seconds.")

            pan_bytes = await pan.read()
            aadhaar_bytes = await aadhaar.read()
            _assert_upload_constraints(pan, pan_bytes)
            _assert_upload_constraints(aadhaar, aadhaar_bytes)

            pan_ext = pan.filename.split('.')[-1].lower() if pan.filename else ""
            aadhaar_ext = aadhaar.filename.split('.')[-1].lower() if aadhaar.filename else ""

            pan_preprocessed = preprocess_image(pan_bytes, pan_ext)
            pan_ocr_text, _ = run_ocr(pan_preprocessed)
            pan_data = extract_pan(pan_ocr_text)

            aadhaar_preprocessed = preprocess_image(aadhaar_bytes, aadhaar_ext)
            aadhaar_ocr_text, _ = run_ocr(aadhaar_preprocessed)
            aadhaar_data = extract_aadhaar(aadhaar_ocr_text)

            if resolved_session_id:
                session_store.get_or_create(resolved_session_id)
                session_store.update_data(resolved_session_id, "pan_data", pan_data)
                session_store.update_data(resolved_session_id, "aadhaar_data", aadhaar_data)

        # Path 2: verify from previously extracted session data.
        else:
            if not resolved_session_id:
                raise HTTPException(status_code=400, detail="session_id is required")

            session = session_store.get(resolved_session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")

            pan_data = session["data"].get("pan_data", {})
            aadhaar_data = session["data"].get("aadhaar_data", {})

            if not pan_data or not aadhaar_data:
                raise HTTPException(status_code=400, detail="Both PAN and Aadhaar data required")
        
        # Cross-validate
        cross_validation = cross_validate_kyc(pan_data, aadhaar_data)
        
        # Generate reference ID
        timestamp = datetime.now(timezone.utc)
        log_count = 0
        if resolved_session_id:
            session_for_ref = session_store.get(resolved_session_id)
            if session_for_ref:
                log_count = len(session_for_ref.get("agent_log", []))
        ref = f"KYC-{timestamp.year}-{log_count + 1:05d}"
        
        # Update session
        if resolved_session_id:
            session_store.update_stage(resolved_session_id, "KYC_VERIFIED")
            session_store.log_agent(resolved_session_id, {
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
        
    except HTTPException:
        raise
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
