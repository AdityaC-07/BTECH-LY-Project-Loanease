from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ValidationBlock(BaseModel):
    overall_valid: bool
    issues: list[str] = Field(default_factory=list)


class PanExtractedFields(BaseModel):
    pan_number: str | None = None
    name: str | None = None
    fathers_name: str | None = None
    date_of_birth: str | None = None
    age: int | None = None
    age_eligible: bool = False


class PanValidation(ValidationBlock):
    pan_format_valid: bool = False
    age_check_passed: bool = False
    name_found: bool = False
    dob_found: bool = False


class PanExtractResponse(BaseModel):
    document_type: Literal["PAN"]
    extracted_fields: PanExtractedFields
    validation: PanValidation
    confidence_score: float
    processing_time_ms: int


class AadhaarAddress(BaseModel):
    full: str | None = None
    house_no: str | None = None
    street: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None


class AadhaarExtractedFields(BaseModel):
    aadhaar_last4: str | None = None
    name: str | None = None
    date_of_birth: str | None = None
    age: int | None = None
    gender: Literal["Male", "Female", "Other", "Unknown"] = "Unknown"
    address: AadhaarAddress = Field(default_factory=AadhaarAddress)
    vid: str | None = None
    age_eligible: bool = False


class AadhaarValidation(ValidationBlock):
    aadhaar_format_valid: bool = False
    age_check_passed: bool = False


class AadhaarExtractResponse(BaseModel):
    document_type: Literal["AADHAAR"]
    extracted_fields: AadhaarExtractedFields
    validation: AadhaarValidation
    confidence_score: float
    processing_time_ms: int


class CrossValidationResult(BaseModel):
    name_match_score: int
    name_match_status: Literal["MATCH", "PARTIAL", "MISMATCH"]
    pan_name: str | None = None
    aadhaar_name: str | None = None
    dob_match: bool
    age_eligible: bool


class VerifyResponse(BaseModel):
    kyc_status: Literal["VERIFIED", "PARTIAL", "FAILED"]
    pan_data: PanExtractedFields
    aadhaar_data: AadhaarExtractedFields
    cross_validation: CrossValidationResult
    overall_kyc_passed: bool
    kyc_reference_id: str
    timestamp: datetime


class AutoExtractResponse(BaseModel):
    detected_document_type: Literal["PAN", "AADHAAR", "UNKNOWN"]
    pan_result: PanExtractResponse | None = None
    aadhaar_result: AadhaarExtractResponse | None = None
    message: str


class HealthResponse(BaseModel):
    status: Literal["ok"]
    uptime_seconds: int
    tesseract_version: str
    installed_language_packs: list[str]
    total_docs_processed_today: int
    server_time: datetime
