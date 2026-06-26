import logging
import time
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Body, File, Form, HTTPException, Query, Request, UploadFile
from PIL import UnidentifiedImageError
from pydantic import BaseModel

from core.config import settings
from core.limiter import limiter
from core.session import session_store
from services.aadhaar_verhoeff import validate_aadhaar_number
from services.otp_service import resend as resend_otp_via_twilio, send as send_otp_via_twilio, verify as verify_otp_via_twilio
from services.vlm_kyc import (
    cross_validate,
    extract_aadhaar,
    extract_pan,
    init_vlm,
    map_cross_validation_to_legacy,
    vlm_ready,
)

logger = logging.getLogger("loanease.kyc")

router = APIRouter()


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
    fa2_verhoeff: Dict[str, Any] | None = None
    verhoeff_validation: Dict[str, Any] | None = None


class OtpSendRequest(BaseModel):
    session_id: str


class OtpVerifyRequest(BaseModel):
    session_id: str
    otp: str


class OtpResponse(BaseModel):
    session_id: str
    mobile_last4: str
    expires_in_seconds: int
    resend_count: int | None = None
    sent: bool | None = None
    demo_otp: str | None = None


class OtpVerifyResponse(BaseModel):
    verified: bool
    terminated: bool
    attempts_remaining: int
    mobile_last4: str
    expires_in_seconds: int
    reason: str | None = None
    message: str | None = None
    method: str | None = None
    zero_knowledge: bool | None = None


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
    three_factor_status: Dict[str, Any] | None = None


class QuickEligibilityRequest(BaseModel):
    action: str
    customer_name: str
    monthly_income: float
    desired_loan_amount: float
    stage: str


class QuickEligibilityResponse(BaseModel):
    eligibility_status: str
    estimated_emi: float
    estimated_tenure_months: int
    dti_ratio: float
    safe_loan_cap: float
    reason: str
    next_action: str


def _get_aadhaar_mobile(session_id: str) -> str:
    session = session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    mobile_number = session.get("data", {}).get("aadhaar_mobile")
    if not mobile_number:
        aadhaar_data = session.get("data", {}).get("aadhaar_data", {})
        mobile_number = aadhaar_data.get("mobile_number")

    if not mobile_number:
        raise HTTPException(
            status_code=400,
            detail="Aadhaar mobile number not found. Please upload the full Aadhaar card with the mobile number visible.",
        )

    return mobile_number


def _assert_upload_constraints(file: UploadFile, file_bytes: bytes) -> None:
    if len(file_bytes) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {settings.MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit",
        )

    extension = file.filename.split(".")[-1].lower() if file.filename else ""
    if extension not in ["jpg", "jpeg", "png", "pdf", "bmp", "tiff"]:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Supported: JPG, PNG, PDF, BMP, TIFF",
        )


def _ensure_vlm_ready() -> None:
    if not vlm_ready():
        try:
            init_vlm()
        except Exception:
            pass  # Will fall back to RapidOCR below


def _use_vlm() -> bool:
    """Returns True only if VLM is actually available."""
    return vlm_ready()


async def _extract_pan_ocr_fallback(file_bytes: bytes, filename: str) -> dict:
    """Fall back to RapidOCR when VLM is unavailable."""
    from services.ocr import preprocess_image, run_ocr, extract_pan as ocr_extract_pan, ocr_ready, init_ocr
    if not ocr_ready():
        init_ocr()
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    preprocessed = preprocess_image(file_bytes, extension)
    ocr_text, confidence = run_ocr(preprocessed)
    pan_data = ocr_extract_pan(ocr_text)
    return {
        "extracted_fields": pan_data,
        "confidence_score": confidence,
        "engine": "rapidocr_fallback",
    }


async def _extract_aadhaar_ocr_fallback(file_bytes: bytes, filename: str) -> dict:
    """Fall back to RapidOCR when VLM is unavailable."""
    from services.ocr import preprocess_image, run_ocr, extract_aadhaar as ocr_extract_aadhaar, ocr_ready, init_ocr
    if not ocr_ready():
        init_ocr()
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    preprocessed = preprocess_image(file_bytes, extension)
    ocr_text, confidence = run_ocr(preprocessed)
    aadhaar_data = ocr_extract_aadhaar(ocr_text)
    return {
        "extracted_fields": aadhaar_data,
        "confidence_score": confidence,
        "engine": "rapidocr_fallback",
    }


@router.get("/health")
async def kyc_health():
    ready = vlm_ready()
    return {
        "status": "healthy" if ready else "degraded",
        "ocr_ready": ready,
        "engine": "Amazon Bedrock" if settings.VLM_PROVIDER == "bedrock" else "Google Gemini VLM",
        "model": settings.VLM_PRIMARY,
        "fallback": settings.VLM_FALLBACK,
        "max_upload_mb": settings.MAX_UPLOAD_BYTES // (1024 * 1024),
        "capabilities": [
            "PAN card extraction",
            "Aadhaar extraction",
            "Cross-document validation",
            "Aadhaar Verhoeff checksum validation",
            "Hindi + English",
            "PDF + Image support",
            "Mobile number extraction",
        ],
    }


@router.get("/audit-trail/{session_id}")
async def get_kyc_audit_trail(session_id: str):
    """Return the full KYC audit trail with summary for a session."""
    trail = session_store.get_kyc_audit_trail(session_id)
    if trail is None:
        session = session_store.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        trail = []

    return {
        "session_id": session_id,
        "kyc_audit_trail": trail,
        "summary": session_store.build_kyc_audit_summary(session_id, trail),
    }


@router.get("/validate-aadhaar/{number}")
@limiter.limit("30/minute")
async def validate_aadhaar_endpoint(request: Request, number: str):
    """
    Real-time Verhoeff validation for Aadhaar numbers.
    Pure mathematical check — no session or authentication required.
    """
    result = validate_aadhaar_number(number)
    return {
        "input": number,
        "valid": result["valid"],
        "message": result["message"],
        "masked": result.get("masked"),
        "last4": result.get("aadhaar_last4") or result.get("last4"),
        "reason": result.get("reason"),
    }


def _build_three_factor_status(session_id: str) -> dict:
    session = session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    data = session.get("data", {})
    fa1 = bool(data.get("kyc_pan_done")) and bool(data.get("kyc_aadhaar_done")) and bool(data.get("kyc_cross_validated"))
    fa2 = bool(data.get("fa2_verhoeff_passed", False))
    fa3 = bool(data.get("mobile_verified"))
    all_passed = fa1 and fa2 and fa3

    if all_passed and session.get("stage") != "KYC_VERIFIED":
        session_store.update_stage(session_id, "KYC_VERIFIED")

    return {
        "session_id": session_id,
        "fa1_document_verification": {
            "passed": fa1,
            "description": "VLM field extraction + name/DOB cross-validation",
            "pan_done": data.get("kyc_pan_done"),
            "aadhaar_done": data.get("kyc_aadhaar_done"),
            "cross_validated": data.get("kyc_cross_validated"),
        },
        "fa2_verhoeff_validation": {
            "passed": fa2,
            "description": "Verhoeff algorithm checksum on 12-digit Aadhaar number — mathematical validity proof per UIDAI standard",
            "algorithm": "Verhoeff D5",
            "aadhaar_last4": data.get("aadhaar_data", {}).get("aadhaar_last4"),
            "result": data.get("fa2_verhoeff_result", {}),
        },
        "fa3_otp_verification": {
            "passed": fa3,
            "description": "Twilio Verify SMS OTP on registered Aadhaar mobile number",
            "mobile_verified": data.get("mobile_verified"),
            "verification_method": data.get("verification_method"),
        },
        "overall_kyc_passed": all_passed,
        "factors_passed": sum([fa1, fa2, fa3]),
        "kyc_reference": data.get("kyc_reference"),
    }


@router.get("/kyc-status/{session_id}")
async def get_kyc_status(session_id: str):
    """Returns complete 3FA KYC status."""
    session = session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    data = session.get("data", {})
    
    fa1 = (
        bool(data.get("kyc_pan_done")) and
        bool(data.get("kyc_aadhaar_done")) and
        bool(data.get("kyc_cross_validated"))
    )
    
    fa2 = bool(data.get("fa2_verhoeff_passed", False))
    
    fa3 = bool(data.get("mobile_verified", False))
    
    all_passed = fa1 and fa2 and fa3
    
    if all_passed:
        session_store.update_stage(session_id, "KYC_VERIFIED")
        if not data.get("kyc_reference"):
            session_store.update_data(
                session_id,
                "kyc_reference",
                f"KYC-{session_id[:6].upper()}"
            )
    
    return {
        "session_id": session_id,
        "fa1_document_verification": {
            "passed": fa1,
            "description": (
                "VLM document extraction + "
                "PAN-Aadhaar name and DOB "
                "cross-validation"
            ),
            "components": {
                "pan_extracted": data.get("kyc_pan_done", False),
                "aadhaar_extracted": data.get("kyc_aadhaar_done", False),
                "cross_validated": data.get("kyc_cross_validated", False),
            }
        },
        "fa2_verhoeff_validation": {
            "passed": fa2,
            "description": (
                "Verhoeff algorithm checksum "
                "on 12-digit Aadhaar number "
                "— mathematical validity "
                "proof per UIDAI standard"
            ),
            "algorithm": "Verhoeff D5",
            "aadhaar_last4": data.get("aadhaar_data", {}).get("aadhaar_last4"),
            "result": data.get("fa2_verhoeff_result", {}),
        },
        "fa3_otp_verification": {
            "passed": fa3,
            "description": (
                "Twilio Verify SMS OTP to "
                "Aadhaar-registered mobile"
            ),
            "mobile_on_file": bool(data.get("aadhaar_mobile")),
            "verified": fa3,
            "method": data.get("verification_method", "TWILIO_OTP"),
        },
        "summary": {
            "factors_passed": sum([fa1, fa2, fa3]),
            "total_factors": 3,
            "overall_passed": all_passed,
            "kyc_reference": data.get("kyc_reference"),
            "percentage": f"{sum([fa1, fa2, fa3])*33}%",
        }
    }


@router.post("/extract/pan", response_model=PanExtractResponse)
@limiter.limit("10/minute")
async def extract_pan_endpoint(
    request: Request,
    document: UploadFile = File(...),
    session_id: str = Form(...),
    language: str = Form("en"),
):
    start_time = time.time()

    try:
        file_bytes = await document.read()
        _assert_upload_constraints(document, file_bytes)
        session_store.get_or_create(session_id)

        filename_lower = (document.filename or "").lower()
        if settings.DEMO_MODE and any(kw in filename_lower for kw in ("demo", "test", "sample")):
            await asyncio.sleep(1.5)
            demo_pan_data = {
                "pan_number": "DEMO00000D",
                "name": "RAHUL SHARMA",
                "date_of_birth": "15/08/1995",
                "age": 29,
                "age_eligible": True,
            }
            processing_time = int((time.time() - start_time) * 1000)
            session_store.update_data(session_id, "pan_data", demo_pan_data)
            session_store.log_agent(
                session_id,
                {
                    "agent": "kyc",
                    "action": "pan_extraction",
                    "success": True,
                    "confidence": 0.99,
                    "processing_time_ms": processing_time,
                    "source": "DEMO_MODE",
                },
            )
            session_store.record_kyc_event(
                session_id,
                "FA1",
                "PAN_EXTRACTED",
                "success",
                {"pan_last4": demo_pan_data["pan_number"][-4:], "confidence": 0.99, "source": "DEMO_MODE"},
            )
            return PanExtractResponse(
                extracted_fields=demo_pan_data,
                validation={
                    "pan_format_valid": True,
                    "age_check_passed": True,
                    "name_found": True,
                    "dob_found": True,
                    "overall_valid": True,
                    "issues": [],
                },
                confidence_score=0.99,
                processing_time_ms=processing_time,
            )

        _ensure_vlm_ready()
        if _use_vlm():
            vlm_result = await extract_pan(file_bytes, document.filename or "pan.jpg")
        else:
            logger.warning("VLM unavailable — using RapidOCR fallback for PAN extraction")
            vlm_result = await _extract_pan_ocr_fallback(file_bytes, document.filename or "pan.jpg")
        pan_data = vlm_result.get("extracted_fields") or {}
        confidence = float(vlm_result.get("confidence_score") or 0.0)

        issues = []
        pan_valid = bool(pan_data.get("pan_number"))
        if not pan_valid:
            issues.append("PAN number not detected")
        if not pan_data.get("name") and confidence < 0.3:
            issues.append("Name not detected")
        if not pan_data.get("date_of_birth") and confidence < 0.2:
            issues.append("Date of birth not detected")

        age = pan_data.get("age")
        age_ok = age is not None and 18 <= age <= 75
        if not age_ok and age is not None:
            issues.append("Age must be between 18 and 75")

        processing_time = int((time.time() - start_time) * 1000)
        session_store.update_data(session_id, "pan_data", pan_data)
        session_store.update_data(session_id, "kyc_pan_done", pan_valid)
        session_store.log_agent(
            session_id,
            {
                "agent": "kyc",
                "action": "pan_extraction",
                "success": pan_valid,
                "confidence": confidence,
                "processing_time_ms": processing_time,
            },
        )
        pan_number = pan_data.get("pan_number") or ""
        session_store.record_kyc_event(
            session_id,
            "FA1",
            "PAN_EXTRACTED",
            "success" if pan_valid else "failed",
            {
                "pan_last4": pan_number[-4:] if len(pan_number) >= 4 else None,
                "confidence": round(confidence, 2),
            },
        )

        overall_valid = pan_valid and (confidence >= 0.15 or bool(pan_data.get("name")))
        return PanExtractResponse(
            extracted_fields=pan_data,
            validation={
                "pan_format_valid": pan_valid,
                "age_check_passed": age_ok,
                "name_found": bool(pan_data.get("name")),
                "dob_found": bool(pan_data.get("date_of_birth")),
                "overall_valid": overall_valid,
                "issues": issues,
            },
            confidence_score=confidence,
            processing_time_ms=processing_time,
        )

    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        logger.warning("PAN extraction upload validation failed: %s", exc)
        error_msg = str(exc).lower()
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
        raise HTTPException(status_code=400, detail=detail) from exc
    except Exception as exc:
        logger.error("PAN extraction error: %s", exc)
        raise HTTPException(status_code=500, detail=f"PAN extraction failed: {exc}") from exc


@router.post("/extract/aadhaar", response_model=AadhaarExtractResponse)
@limiter.limit("10/minute")
async def extract_aadhaar_endpoint(
    request: Request,
    document: UploadFile = File(...),
    session_id: str = Form(...),
    language: str = Form("en"),
):
    start_time = time.time()

    try:
        file_bytes = await document.read()
        _assert_upload_constraints(document, file_bytes)
        session_store.get_or_create(session_id)

        filename_lower = (document.filename or "").lower()
        if settings.DEMO_MODE and any(kw in filename_lower for kw in ("demo", "test", "sample")):
            await asyncio.sleep(1.2)
            demo_aadhaar_data = {
                "aadhaar_number": "XXXX XXXX 1234",
                "aadhaar_last4": "1234",
                "name": "RAHUL SHARMA",
                "date_of_birth": "15/08/1995",
                "age": 29,
                "gender": "Male",
                "age_eligible": True,
            }
            processing_time = int((time.time() - start_time) * 1000)
            session_store.update_data(session_id, "aadhaar_data", demo_aadhaar_data)
            session_store.log_agent(
                session_id,
                {
                    "agent": "kyc",
                    "action": "aadhaar_extraction",
                    "success": True,
                    "confidence": 0.99,
                    "processing_time_ms": processing_time,
                    "source": "DEMO_MODE",
                },
            )
            session_store.record_kyc_event(
                session_id,
                "FA1",
                "AADHAAR_EXTRACTED",
                "success",
                {"aadhaar_last4": demo_aadhaar_data["aadhaar_last4"], "confidence": 0.99, "source": "DEMO_MODE"},
            )
            return AadhaarExtractResponse(
                extracted_fields=demo_aadhaar_data,
                validation={
                    "aadhaar_format_valid": True,
                    "age_check_passed": True,
                    "overall_valid": True,
                    "issues": [],
                },
                confidence_score=0.99,
                processing_time_ms=processing_time,
            )

        _ensure_vlm_ready()
        if _use_vlm():
            vlm_result = await extract_aadhaar(file_bytes, document.filename or "aadhaar.jpg")
        else:
            logger.warning("VLM unavailable — using RapidOCR fallback for Aadhaar extraction")
            vlm_result = await _extract_aadhaar_ocr_fallback(file_bytes, document.filename or "aadhaar.jpg")
        aadhaar_data = vlm_result.get("extracted_fields") or {}
        confidence = float(vlm_result.get("confidence_score") or 0.0)

        # FA2: Verhoeff validation - Run immediately on extracted number
        aadhaar_raw = aadhaar_data.get("aadhaar_number")
        verhoeff_result = {
            "checked": False,
            "valid": None,
            "reason": "Aadhaar number not found"
        }
        
        if aadhaar_raw:
            verhoeff_result = validate_aadhaar_number(aadhaar_raw)
            
            if verhoeff_result["valid"]:
                logger.info(f"FA2 Verhoeff PASS: XXXX XXXX {aadhaar_raw[-4:]}")
            else:
                logger.warning(f"FA2 Verhoeff FAIL: {verhoeff_result['reason']} — {aadhaar_raw}")
        
        # Attach Verhoeff result to response
        vlm_result["fa2_verhoeff"] = verhoeff_result
        vlm_result["fa2_passed"] = verhoeff_result.get("valid", False)

        mobile_number = aadhaar_data.get("mobile_number")
        if session_id and mobile_number:
            session_store.update_data(session_id, "aadhaar_mobile", mobile_number)
            session_store.update_data(session_id, "aadhaar_mobile_last4", mobile_number[-4:])

        issues = []
        aadhaar_valid = bool(aadhaar_data.get("aadhaar_number")) or bool(aadhaar_data.get("aadhaar_last4"))
        if not aadhaar_valid and confidence < 0.1:
            issues.append("Aadhaar number not detected")

        age = aadhaar_data.get("age")
        age_ok = age is not None and 18 <= age <= 75
        if not age_ok and age is not None:
            issues.append("Age must be between 18 and 75")

        processing_time = int((time.time() - start_time) * 1000)
        session_store.update_data(session_id, "aadhaar_data", aadhaar_data)
        session_store.update_data(session_id, "fa2_verhoeff_passed", verhoeff_result.get("valid", False))
        session_store.update_data(session_id, "fa2_verhoeff_result", verhoeff_result)
        session_store.update_data(session_id, "kyc_aadhaar_done", aadhaar_valid)
        session_store.log_agent(
            session_id,
            {
                "agent": "KYCAgent",
                "action": "AADHAAR_EXTRACTED",
                "fa1_vlm": "complete",
                "fa2_verhoeff": "PASS" if verhoeff_result.get("valid") else "FAIL",
                "fa3_otp": "pending",
            },
        )

        aadhaar_last4 = (
            aadhaar_data.get("aadhaar_last4")
            or (aadhaar_raw[-4:] if aadhaar_raw and len(str(aadhaar_raw)) >= 4 else None)
        )
        session_store.record_kyc_event(
            session_id,
            "FA1",
            "AADHAAR_EXTRACTED",
            "success" if aadhaar_valid else "failed",
            {"aadhaar_last4": aadhaar_last4, "confidence": round(confidence, 2)},
        )
        if aadhaar_raw or aadhaar_last4:
            verhoeff_valid = bool(verhoeff_result.get("valid"))
            session_store.record_kyc_event(
                session_id,
                "FA2",
                "PASSED" if verhoeff_valid else "FAILED",
                verhoeff_result.get("message", ""),
                {
                    "algorithm": "Verhoeff D5",
                    "aadhaar_last4": aadhaar_last4,
                    "reason": verhoeff_result.get("reason"),
                },
            )
        if verhoeff_result.get("valid") is False:
            issues.append(
                f"Aadhaar number failed Verhoeff checksum: {verhoeff_result.get('reason')}"
            )

        return AadhaarExtractResponse(
            extracted_fields={
                **aadhaar_data,
                "mobile_number": None,
                "mobile_last4": aadhaar_data.get("mobile_last4"),
            },
            validation={
                "aadhaar_format_valid": aadhaar_valid,
                "age_check_passed": age_ok,
                "overall_valid": aadhaar_valid and age_ok,
                "issues": issues,
            },
            confidence_score=confidence,
            processing_time_ms=processing_time,
            fa2_verhoeff=verhoeff_result,
            verhoeff_validation=verhoeff_result,
        )

    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        logger.warning("Aadhaar extraction upload validation failed: %s", exc)
        raise HTTPException(
            status_code=400,
            detail="Unable to read uploaded Aadhaar document. Please upload a clear JPG/PNG/JPEG/BMP/TIFF image.",
        ) from exc
    except Exception as exc:
        logger.error("Aadhaar extraction error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Aadhaar extraction failed: {exc}") from exc


@router.post("/extract/auto")
@limiter.limit("10/minute")
async def extract_auto(
    request: Request,
    document: UploadFile = File(...),
    session_id: str | None = Form(None),
    language: str = Form("en"),
):
    """Auto-detect PAN vs Aadhaar and route to the appropriate VLM extractor."""
    file_bytes = await document.read()
    filename = document.filename or "document.jpg"
    filename_lower = filename.lower()

    if session_id:
        session_store.get_or_create(session_id)

    _ensure_vlm_ready()

    if "pan" in filename_lower:
        detected = "PAN"
        vlm_result = await extract_pan(file_bytes, filename)
    elif any(keyword in filename_lower for keyword in ("aad", "adh", "uid")):
        detected = "AADHAAR"
        vlm_result = await extract_aadhaar(file_bytes, filename)
    else:
        pan_result = await extract_pan(file_bytes, filename)
        pan_fields = pan_result.get("extracted_fields") or {}
        if pan_fields.get("pan_number"):
            vlm_result = pan_result
            detected = "PAN"
        else:
            vlm_result = await extract_aadhaar(file_bytes, filename)
            detected = "AADHAAR"

    fields = vlm_result.get("extracted_fields") or {}
    if session_id:
        if detected == "PAN":
            session_store.update_data(session_id, "pan_data", fields)
            session_store.update_data(session_id, "kyc_pan_done", bool(fields.get("pan_number")))
        else:
            session_store.update_data(session_id, "aadhaar_data", fields)
            mobile = fields.get("mobile_number")
            if mobile:
                session_store.update_data(session_id, "aadhaar_mobile", mobile)
            session_store.update_data(session_id, "kyc_aadhaar_done", bool(fields.get("aadhaar_number") or fields.get("aadhaar_last4")))

    return {**vlm_result, "auto_detected": detected}


@router.post("/verify", response_model=VerifyResponse)
@limiter.limit("20/minute")
async def verify_kyc(
    request: Request,
    payload: VerifyRequest | None = Body(default=None),
    session_id: str | None = Form(default=None),
    pan: UploadFile | None = File(default=None),
    aadhaar: UploadFile | None = File(default=None),
):
    try:
        resolved_session_id = payload.session_id if payload is not None else session_id

        if pan is not None and aadhaar is not None:
            _ensure_vlm_ready()

            if resolved_session_id:
                session_store.get_or_create(resolved_session_id)

            pan_bytes = await pan.read()
            aadhaar_bytes = await aadhaar.read()
            _assert_upload_constraints(pan, pan_bytes)
            _assert_upload_constraints(aadhaar, aadhaar_bytes)

            if _use_vlm():
                pan_vlm = await extract_pan(pan_bytes, pan.filename or "pan.jpg")
                pan_data = pan_vlm.get("extracted_fields") or {}
                aadhaar_vlm = await extract_aadhaar(aadhaar_bytes, aadhaar.filename or "aadhaar.jpg")
                aadhaar_data = aadhaar_vlm.get("extracted_fields") or {}
            else:
                logger.warning("VLM unavailable — using RapidOCR fallback for KYC verify")
                pan_vlm = await _extract_pan_ocr_fallback(pan_bytes, pan.filename or "pan.jpg")
                pan_data = pan_vlm.get("extracted_fields") or {}
                aadhaar_vlm = await _extract_aadhaar_ocr_fallback(aadhaar_bytes, aadhaar.filename or "aadhaar.jpg")
                aadhaar_data = aadhaar_vlm.get("extracted_fields") or {}

            mobile_number = aadhaar_data.get("mobile_number")
            if resolved_session_id and mobile_number:
                session_store.update_data(resolved_session_id, "aadhaar_mobile", mobile_number)
                session_store.update_data(resolved_session_id, "aadhaar_mobile_last4", mobile_number[-4:])

            if resolved_session_id:
                session_store.get_or_create(resolved_session_id)
                session_store.update_data(resolved_session_id, "pan_data", pan_data)
                session_store.update_data(resolved_session_id, "aadhaar_data", aadhaar_data)
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

        if _use_vlm():
            vlm_cross = await cross_validate(pan_data, aadhaar_data)
            cross_validation = map_cross_validation_to_legacy(vlm_cross, pan_data, aadhaar_data)
        else:
            from services.ocr import cross_validate_kyc as ocr_cross_validate
            cross_validation = ocr_cross_validate(pan_data, aadhaar_data)
        fa1_passed = bool(cross_validation.get("overall_kyc_passed"))

        timestamp = datetime.now(timezone.utc)
        log_count = 0
        if resolved_session_id:
            session_for_ref = session_store.get(resolved_session_id)
            if session_for_ref:
                log_count = len(session_for_ref.get("agent_log", []))
        ref = f"KYC-{timestamp.year}-{log_count + 1:05d}"

        if resolved_session_id:
            session_store.update_data(resolved_session_id, "pan_data", pan_data)
            session_store.update_data(resolved_session_id, "aadhaar_data", aadhaar_data)
            session_store.update_data(resolved_session_id, "kyc_pan_done", bool(pan_data.get("pan_number")))
            session_store.update_data(resolved_session_id, "kyc_aadhaar_done", bool(aadhaar_data.get("aadhaar_number") or aadhaar_data.get("aadhaar_last4")))
            session_store.update_data(resolved_session_id, "kyc_cross_validated", fa1_passed)
            session_store.update_data(resolved_session_id, "fa1_document_passed", fa1_passed)
            session_store.update_data(resolved_session_id, "kyc_reference", ref)
            session_store.update_stage(resolved_session_id, "KYC_OTP_PENDING" if fa1_passed else "KYC_PENDING")
            session_store.log_agent(
                resolved_session_id,
                {
                    "agent": "kyc",
                    "action": "verification",
                    "success": fa1_passed,
                    "kyc_status": cross_validation["kyc_status"],
                    "reference_id": ref,
                },
            )
            session_store.record_kyc_event(
                resolved_session_id,
                "FA1",
                "CROSS_VALIDATED",
                "passed" if fa1_passed else "failed",
                {
                    "name_similarity": cross_validation.get("name_similarity"),
                    "dob_match": cross_validation.get("dob_match"),
                    "name_match": cross_validation.get("name_match"),
                    "kyc_reference": ref,
                },
            )

        # Get session data for FA2/FA3 status
        data = session_store.get(resolved_session_id).get("data", {}) if resolved_session_id else {}
        
        # FA2: Verhoeff result (already computed during upload)
        verhoeff_passed = data.get("fa2_verhoeff_passed", False) if resolved_session_id else False
        verhoeff_result = data.get("fa2_verhoeff_result", {}) if resolved_session_id else {}
        
        # FA3: OTP status
        mobile_verified = data.get("mobile_verified", False) if resolved_session_id else False
        
        # Determine if ready for FA3 - FA2 must pass before FA3 prompt
        fa2_blocks_progress = (
            aadhaar_data.get("aadhaar_number") is not None and 
            not verhoeff_passed
        )

        return VerifyResponse(
            kyc_status=cross_validation["kyc_status"],
            pan_data=pan_data,
            aadhaar_data={**aadhaar_data, "mobile_number": None},
            cross_validation=cross_validation,
            overall_kyc_passed=fa1_passed and verhoeff_passed and mobile_verified,
            kyc_reference_id=ref,
            timestamp=timestamp.isoformat(),
            three_factor_status={
                "fa1_cross_validation": {
                    "passed": fa1_passed,
                    "name_match": cross_validation.get("name_match"),
                    "name_similarity": cross_validation.get("name_similarity"),
                    "dob_match": cross_validation.get("dob_match"),
                    "pan_name": cross_validation.get("pan_name"),
                    "aadhaar_name": cross_validation.get("aadhaar_name"),
                },
                "fa2_verhoeff": {
                    "passed": verhoeff_passed,
                    "algorithm": "Verhoeff (UIDAI)",
                    "aadhaar_last4": aadhaar_data.get("aadhaar_last4"),
                    "reason": verhoeff_result.get("reason"),
                    "message": (
                        "Aadhaar number is mathematically valid"
                        if verhoeff_passed
                        else verhoeff_result.get("message", "Aadhaar checksum failed")
                    ),
                },
                "fa3_otp": {
                    "passed": mobile_verified,
                    "mobile_found": bool(data.get("aadhaar_mobile")) if resolved_session_id else False,
                    "status": "verified" if mobile_verified else "pending",
                },
                "overall_kyc_passed": fa1_passed and verhoeff_passed and mobile_verified,
                "blocks_on_fa2": fa2_blocks_progress,
                "next_step": (
                    "OTP_VERIFICATION" 
                    if fa1_passed and verhoeff_passed and not mobile_verified
                    else "COMPLETE" 
                    if fa1_passed and verhoeff_passed and mobile_verified
                    else "FAILED"
                ),
                "kyc_reference": ref,
            } if resolved_session_id else None,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("KYC verification error: %s", exc)
        raise HTTPException(status_code=500, detail=f"KYC verification failed: {exc}") from exc


@router.post("/send-otp", response_model=OtpResponse)
@limiter.limit("3/minute")
async def send_otp_endpoint(request: Request, payload: OtpSendRequest):
    session = session_store.get(payload.session_id)
    if not session or not session.get("data", {}).get("fa2_verhoeff_passed", False):
        raise HTTPException(status_code=409, detail="Complete Aadhaar verification (Verhoeff checksum must pass) before OTP verification.")

    mobile_number = _get_aadhaar_mobile(payload.session_id)

    result = await send_otp_via_twilio(payload.session_id, mobile_number)
    session_store.update_stage(payload.session_id, "KYC_OTP_PENDING")
    session_store.update_data(payload.session_id, "aadhaar_mobile", mobile_number)
    session_store.update_data(payload.session_id, "aadhaar_otp_pending", True)
    session_store.log_agent(
        payload.session_id,
        {
            "agent": "KYCVerificationAgent",
            "action": "OTP_SENT",
            "reasoning": f"Sending verification OTP to Aadhaar-linked mobile ending in {mobile_number[-4:]}",
            "status": "SUCCESS" if result["sent"] else "FAILED",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    session_store.record_kyc_event(
        payload.session_id,
        "FA3",
        "OTP_SENT",
        "pending" if result["sent"] else "failed",
        {"mobile_last4": mobile_number[-4:], "method": "TWILIO_VERIFY"},
    )

    if not result["sent"] and not result.get("fallback_active") and not settings.DEMO_MODE:
        raise HTTPException(status_code=502, detail="Unable to send OTP right now. Please try again.")

    return OtpResponse(**result)


@router.post("/resend-otp", response_model=OtpResponse)
@limiter.limit("3/minute")
async def resend_otp_endpoint(request: Request, payload: OtpSendRequest):
    session = session_store.get(payload.session_id)
    if not session or not session.get("data", {}).get("fa2_verhoeff_passed", False):
        raise HTTPException(status_code=409, detail="Complete Aadhaar verification (Verhoeff checksum must pass) before OTP verification.")

    mobile_number = _get_aadhaar_mobile(payload.session_id)
    result = await resend_otp_via_twilio(payload.session_id, mobile_number)

    return OtpResponse(**result)


@router.post("/verify-otp", response_model=OtpVerifyResponse)
@limiter.limit("10/minute")
async def verify_otp_endpoint(request: Request, payload: OtpVerifyRequest):
    session = session_store.get(payload.session_id)
    if not session or not session.get("data", {}).get("fa2_verhoeff_passed", False):
        raise HTTPException(status_code=409, detail="Complete Aadhaar verification (Verhoeff checksum must pass) before OTP verification.")

    mobile_number = _get_aadhaar_mobile(payload.session_id)
    data = (session or {}).get("data", {})

    result = await verify_otp_via_twilio(payload.session_id, payload.otp, mobile_number)

    if result["verified"]:
        session_store.update_stage(payload.session_id, "KYC_VERIFIED")
        session_store.update_data(payload.session_id, "aadhaar_otp_verified", True)
        session_store.update_data(payload.session_id, "mobile_verified", True)
        session_store.update_data(payload.session_id, "verification_method", "OTP_SMS")
        session_store.update_data(payload.session_id, "fa3_otp_passed", True)
        session_store.log_agent(
            payload.session_id,
            {
                "agent": "KYCVerificationAgent",
                "action": "OTP_VERIFIED",
                "reasoning": "Aadhaar-linked mobile OTP verified successfully.",
                "status": "SUCCESS",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        session_store.record_kyc_event(
            payload.session_id,
            "FA3",
            "OTP_VERIFIED",
            "success",
            {
                "method": data.get("verification_method", "TWILIO_VERIFY"),
                "mobile_last4": mobile_number[-4:],
            },
        )
    elif result["terminated"]:
        session_store.update_stage(payload.session_id, "KYC_TERMINATED")
        session_store.update_data(payload.session_id, "aadhaar_otp_failed", True)
        session_store.log_agent(
            payload.session_id,
            {
                "agent": "KYCVerificationAgent",
                "action": "OTP_FAILED",
                "reasoning": result.get("reason") or "OTP verification failed too many times.",
                "status": "FAILED",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    return OtpVerifyResponse(**result)


@router.post("/quick-eligibility", response_model=QuickEligibilityResponse)
@limiter.limit("10/minute")
async def quick_eligibility_endpoint(request: Request, payload: QuickEligibilityRequest):
    """
    Quick eligibility check based on income and loan amount.
    Calculates DTI ratio and provides preliminary eligibility assessment.
    """
    try:
        # Constants for EMI calculation
        INTEREST_RATE = 0.12  # 12% per annum
        TENURE_MONTHS = 60
        
        # Calculate EMI using standard formula: EMI = P * r * (1+r)^n / ((1+r)^n - 1)
        # where P = principal, r = monthly interest rate, n = tenure in months
        monthly_rate = INTEREST_RATE / 12
        emi = payload.desired_loan_amount * monthly_rate * (1 + monthly_rate) ** TENURE_MONTHS / ((1 + monthly_rate) ** TENURE_MONTHS - 1)
        
        # Calculate DTI ratio (EMI / Monthly Income)
        dti_ratio = emi / payload.monthly_income
        
        # Calculate safe loan cap (50% DTI constraint)
        safe_loan_cap = (TENURE_MONTHS * payload.monthly_income) / 2
        
        # Determine eligibility status based on DTI and loan amount
        if dti_ratio <= 0.50 and payload.desired_loan_amount <= payload.monthly_income * 15:
            eligibility_status = "STRONG"
            reason = "You meet our lending criteria with strong repayment capacity."
            next_action = "PROCEED_TO_KYC"
        elif dti_ratio <= 0.60 and payload.desired_loan_amount <= payload.monthly_income * 12:
            eligibility_status = "MODERATE"
            reason = "Subject to credit verification. Your profile shows moderate eligibility."
            next_action = "PROCEED_TO_KYC"
        elif dti_ratio <= 0.70:
            eligibility_status = "CONDITIONAL"
            reason = "May require additional documentation or co-applicant for approval."
            next_action = "PROCEED_TO_KYC"
        else:
            eligibility_status = "INELIGIBLE"
            reason = "Debt-to-income ratio exceeds our lending threshold. Consider reducing loan amount."
            next_action = "ADJUST_AMOUNT"
        
        logger.info(
            f"Quick eligibility check for {payload.customer_name}: "
            f"Income={payload.monthly_income}, Loan={payload.desired_loan_amount}, "
            f"DTI={dti_ratio:.2%}, Status={eligibility_status}"
        )
        
        return QuickEligibilityResponse(
            eligibility_status=eligibility_status,
            estimated_emi=round(emi, 2),
            estimated_tenure_months=TENURE_MONTHS,
            dti_ratio=round(dti_ratio, 4),
            safe_loan_cap=round(safe_loan_cap, 2),
            reason=reason,
            next_action=next_action
        )
        
    except Exception as e:
        logger.error(f"Error in quick eligibility check: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to process eligibility check")
