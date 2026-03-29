from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.preprocess import MAX_UPLOAD_BYTES, UnsupportedDocumentError, get_tesseract_info
from app.schemas import (
    AadhaarExtractResponse,
    AutoExtractResponse,
    HealthResponse,
    PanExtractResponse,
    VerifyResponse,
)
from app.service import KYCService

app = FastAPI(title="LoanEase KYC Verification API", version="1.0.0")

frontend_domain = os.getenv("FRONTEND_DOMAIN", "https://loanease.example.com")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:8081",
        "http://127.0.0.1:8081",
        "http://localhost:8082",
        "http://127.0.0.1:8082",
        "http://localhost:3000",
        frontend_domain,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

service = KYCService()


HI_MESSAGES = {
    "low_confidence": "दस्तावेज़ स्पष्ट नहीं है। कृपया अच्छी रोशनी में स्पष्ट फोटो अपलोड करें।",
    "name_mismatch": "PAN और Aadhaar पर नाम पर्याप्त रूप से मेल नहीं खा रहे हैं। कृपया दस्तावेज़ जांचें।",
    "age_ineligible": "आवेदन करने के लिए आयु 21 से 65 वर्ष के बीच होनी चाहिए।",
}

EN_MESSAGES = {
    "low_confidence": "The document image is unclear. Please upload a better quality photo in good lighting.",
    "name_mismatch": "The names on your PAN and Aadhaar do not match closely enough. Please check your documents.",
    "age_ineligible": "Applicants must be between 21 and 65 years old to apply.",
}


def _assert_upload_constraints(file: UploadFile, file_bytes: bytes) -> None:
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large. Max 5MB allowed")

    ext = (file.filename or "").lower().split(".")[-1]
    if ext not in {"jpg", "jpeg", "png", "pdf"}:
        raise HTTPException(status_code=400, detail="Only JPG, PNG or PDF files are supported")


def _confidence_issues(conf: float, language: str) -> list[str]:
    issues: list[str] = []
    if conf < 0.70:
        issues.append(HI_MESSAGES["low_confidence"] if language == "hi" else EN_MESSAGES["low_confidence"])
    return issues


@app.post("/kyc/extract/pan", response_model=PanExtractResponse)
async def extract_pan(
    document: UploadFile = File(...),
    language: str = Form("en"),
) -> PanExtractResponse:
    language = "hi" if language == "hi" else "en"
    file_bytes = await document.read()
    _assert_upload_constraints(document, file_bytes)

    try:
        result, conf, elapsed, _ = service.extract_pan(file_bytes, document.filename or "upload.jpg")
    except UnsupportedDocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PAN extraction failed: {str(exc)}") from exc

    result["validation"]["issues"].extend(_confidence_issues(conf, language))
    if result["extracted_fields"].get("age_eligible") is False:
        result["validation"]["issues"].append(
            HI_MESSAGES["age_ineligible"] if language == "hi" else EN_MESSAGES["age_ineligible"]
        )

    result["validation"]["overall_valid"] = (
        result["validation"]["overall_valid"] and conf >= 0.70
    )

    return PanExtractResponse(
        document_type="PAN",
        extracted_fields=result["extracted_fields"],
        validation=result["validation"],
        confidence_score=conf,
        processing_time_ms=elapsed,
    )


@app.post("/kyc/extract/aadhaar", response_model=AadhaarExtractResponse)
async def extract_aadhaar(document: UploadFile = File(...)) -> AadhaarExtractResponse:
    file_bytes = await document.read()
    _assert_upload_constraints(document, file_bytes)

    try:
        result, conf, elapsed, _ = service.extract_aadhaar(file_bytes, document.filename or "upload.jpg")
    except UnsupportedDocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Aadhaar extraction failed: {str(exc)}") from exc

    result["validation"]["issues"].extend(_confidence_issues(conf, "en"))
    if result["extracted_fields"].get("age_eligible") is False:
        result["validation"]["issues"].append(EN_MESSAGES["age_ineligible"])

    result["validation"]["overall_valid"] = (
        result["validation"]["overall_valid"] and conf >= 0.70
    )

    return AadhaarExtractResponse(
        document_type="AADHAAR",
        extracted_fields=result["extracted_fields"],
        validation=result["validation"],
        confidence_score=conf,
        processing_time_ms=elapsed,
    )


@app.post("/kyc/verify", response_model=VerifyResponse)
async def verify_kyc(
    pan: UploadFile = File(...),
    aadhaar: UploadFile = File(...),
) -> VerifyResponse:
    pan_bytes = await pan.read()
    aadhaar_bytes = await aadhaar.read()

    _assert_upload_constraints(pan, pan_bytes)
    _assert_upload_constraints(aadhaar, aadhaar_bytes)

    try:
        result = service.verify(pan_bytes, pan.filename or "pan.jpg", aadhaar_bytes, aadhaar.filename or "aadhaar.jpg")
    except UnsupportedDocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"KYC verification failed: {str(exc)}") from exc

    if result["cross_validation"]["name_match_score"] < 70:
        result["overall_kyc_passed"] = False

    if not result["cross_validation"]["age_eligible"]:
        result["overall_kyc_passed"] = False

    return VerifyResponse(
        kyc_status=result["kyc_status"],
        pan_data=result["pan_data"],
        aadhaar_data=result["aadhaar_data"],
        cross_validation=result["cross_validation"],
        overall_kyc_passed=result["overall_kyc_passed"],
        kyc_reference_id=result["kyc_reference_id"],
        timestamp=result["timestamp"],
    )


@app.post("/kyc/extract/auto", response_model=AutoExtractResponse)
async def extract_auto(document: UploadFile = File(...)) -> AutoExtractResponse:
    file_bytes = await document.read()
    _assert_upload_constraints(document, file_bytes)

    try:
        doc_type, pan_result, aadhaar_result, conf, elapsed = service.extract_auto(
            file_bytes,
            document.filename or "upload.jpg",
        )
    except UnsupportedDocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Auto extraction failed: {str(exc)}") from exc

    if doc_type == "PAN" and pan_result is not None:
        return AutoExtractResponse(
            detected_document_type="PAN",
            pan_result=PanExtractResponse(
                document_type="PAN",
                extracted_fields=pan_result["extracted_fields"],
                validation=pan_result["validation"],
                confidence_score=conf,
                processing_time_ms=elapsed,
            ),
            message="PAN document detected and extracted",
        )

    if doc_type == "AADHAAR" and aadhaar_result is not None:
        return AutoExtractResponse(
            detected_document_type="AADHAAR",
            aadhaar_result=AadhaarExtractResponse(
                document_type="AADHAAR",
                extracted_fields=aadhaar_result["extracted_fields"],
                validation=aadhaar_result["validation"],
                confidence_score=conf,
                processing_time_ms=elapsed,
            ),
            message="Aadhaar document detected and extracted",
        )

    return AutoExtractResponse(
        detected_document_type="UNKNOWN",
        message="Unable to detect document type confidently",
    )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    version, langs = get_tesseract_info()

    return HealthResponse(
        status="ok",
        uptime_seconds=service.uptime_seconds(),
        tesseract_version=version,
        installed_language_packs=langs,
        total_docs_processed_today=service._today_processed(),
        server_time=datetime.now(timezone.utc),
    )
