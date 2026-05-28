import logging
import time
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Body, File, Form, HTTPException, Request, UploadFile
from PIL import UnidentifiedImageError
from pydantic import BaseModel

from core.config import settings
from core.limiter import limiter
from core.session import session_store
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
    qr_verification: Dict[str, Any] | None = None


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
        init_vlm()
    if not vlm_ready():
        raise HTTPException(
            status_code=503,
            detail="OCR service is initializing. Please retry in a few seconds.",
        )


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
            "Hindi + English",
            "PDF + Image support",
            "Mobile number extraction",
        ],
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
        vlm_result = await extract_pan(file_bytes, document.filename or "pan.jpg")
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
        vlm_result = await extract_aadhaar(file_bytes, document.filename or "aadhaar.jpg")
        qr_data = vlm_result.pop("_qr_data_for_session", None)
        if qr_data and session_id:
            session_store.update_data(session_id, "aadhaar_qr_data", qr_data)
        aadhaar_data = vlm_result.get("extracted_fields") or {}
        confidence = float(vlm_result.get("confidence_score") or 0.0)

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
        session_store.log_agent(
            session_id,
            {
                "agent": "kyc",
                "action": "aadhaar_extraction",
                "success": aadhaar_valid,
                "confidence": confidence,
                "processing_time_ms": processing_time,
            },
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
            qr_verification=vlm_result.get("qr_verification"),
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
        else:
            session_store.update_data(session_id, "aadhaar_data", fields)
            mobile = fields.get("mobile_number")
            if mobile:
                session_store.update_data(session_id, "aadhaar_mobile", mobile)

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

            pan_bytes = await pan.read()
            aadhaar_bytes = await aadhaar.read()
            _assert_upload_constraints(pan, pan_bytes)
            _assert_upload_constraints(aadhaar, aadhaar_bytes)

            pan_vlm = await extract_pan(pan_bytes, pan.filename or "pan.jpg")
            pan_data = pan_vlm.get("extracted_fields") or {}

            aadhaar_vlm = await extract_aadhaar(aadhaar_bytes, aadhaar.filename or "aadhaar.jpg")
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

        vlm_cross = await cross_validate(pan_data, aadhaar_data)
        cross_validation = map_cross_validation_to_legacy(vlm_cross, pan_data, aadhaar_data)

        timestamp = datetime.now(timezone.utc)
        log_count = 0
        if resolved_session_id:
            session_for_ref = session_store.get(resolved_session_id)
            if session_for_ref:
                log_count = len(session_for_ref.get("agent_log", []))
        ref = f"KYC-{timestamp.year}-{log_count + 1:05d}"

        if resolved_session_id:
            session_store.update_stage(resolved_session_id, "KYC_OTP_PENDING")
            session_store.log_agent(
                resolved_session_id,
                {
                    "agent": "kyc",
                    "action": "verification",
                    "success": cross_validation["overall_kyc_passed"],
                    "kyc_status": cross_validation["kyc_status"],
                    "reference_id": ref,
                },
            )

        return VerifyResponse(
            kyc_status=cross_validation["kyc_status"],
            pan_data=pan_data,
            aadhaar_data={**aadhaar_data, "mobile_number": None},
            cross_validation=cross_validation,
            overall_kyc_passed=cross_validation["overall_kyc_passed"],
            kyc_reference_id=ref,
            timestamp=timestamp.isoformat(),
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("KYC verification error: %s", exc)
        raise HTTPException(status_code=500, detail=f"KYC verification failed: {exc}") from exc


@router.post("/send-otp", response_model=OtpResponse)
@limiter.limit("3/minute")
async def send_otp_endpoint(request: Request, payload: OtpSendRequest):
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

    if not result["sent"] and not result.get("fallback_active") and not settings.DEMO_MODE:
        raise HTTPException(status_code=502, detail="Unable to send OTP right now. Please try again.")

    return OtpResponse(**result)


@router.post("/resend-otp", response_model=OtpResponse)
@limiter.limit("3/minute")
async def resend_otp_endpoint(request: Request, payload: OtpSendRequest):
    mobile_number = _get_aadhaar_mobile(payload.session_id)
    result = await resend_otp_via_twilio(payload.session_id, mobile_number)

    return OtpResponse(**result)


@router.post("/verify-otp", response_model=OtpVerifyResponse)
@limiter.limit("10/minute")
async def verify_otp_endpoint(request: Request, payload: OtpVerifyRequest):
    mobile_number = _get_aadhaar_mobile(payload.session_id)
    session = session_store.get(payload.session_id)
    data = (session or {}).get("data", {})
    qr_data = data.get("aadhaar_qr_data")
    aadhaar_last4 = data.get("aadhaar_data", {}).get("aadhaar_last4", "")

    if qr_data and qr_data.get("mobile_hash") and mobile_number:
        from services.aadhaar_qr import verify_mobile_against_qr

        qr_verify = verify_mobile_against_qr(mobile_number, qr_data, aadhaar_last4)
        if qr_verify.get("verified"):
            session_store.update_stage(payload.session_id, "KYC_VERIFIED")
            session_store.update_data(payload.session_id, "aadhaar_otp_verified", True)
            session_store.update_data(payload.session_id, "mobile_verified", True)
            session_store.update_data(payload.session_id, "verification_method", "AADHAAR_QR_HASH")

            return OtpVerifyResponse(
                verified=True,
                terminated=False,
                attempts_remaining=3,
                mobile_last4=mobile_number[-4:],
                expires_in_seconds=600,
                reason=None,
                message="Identity verified via Aadhaar cryptographic seal - no OTP required.",
                method="QR_HASH",
                zero_knowledge=True,
            )

    result = await verify_otp_via_twilio(payload.session_id, payload.otp, mobile_number)

    if result["verified"]:
        session_store.update_stage(payload.session_id, "KYC_VERIFIED")
        session_store.update_data(payload.session_id, "aadhaar_otp_verified", True)
        session_store.update_data(payload.session_id, "mobile_verified", True)
        session_store.update_data(payload.session_id, "verification_method", "OTP_SMS")
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
