from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
import re
import logging

from app.enhanced_extractors import (
    enhanced_extract_pan,
    enhanced_extract_aadhaar,
    enhanced_cross_validate_kyc,
    detect_document_type,
)
from app.enhanced_preprocess import enhanced_preprocess_image, run_enhanced_ocr
from app.roboflow_mapper import extract_pan_hints_with_roboflow

logger = logging.getLogger(__name__)


class EnhancedKYCService:
    """Enhanced KYC service with improved OCR and field extraction"""
    
    def __init__(self) -> None:
        self.boot_time = datetime.now(timezone.utc)
        self.processed_by_day: dict[str, int] = {}
    
    @staticmethod
    def _normalize_pan_text(value: str | None) -> str | None:
        if not value:
            return None
        cleaned = re.sub(r"[^A-Z0-9]", "", value.upper())
        if len(cleaned) != 10:
            return None
        return cleaned
    
    @staticmethod
    def _normalize_date_text(value: str | None) -> str | None:
        if not value:
            return None
        compact = re.sub(r"\s+", "", value)
        m = re.search(r"(\d{2})[/-]?(\d{2})[/-]?(\d{4})", compact)
        if not m:
            return None
        return f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
    
    @staticmethod
    def _calc_age_from_dob(dob: str | None) -> int | None:
        if not dob:
            return None
        try:
            dt = datetime.strptime(dob, "%d/%m/%Y")
            now = datetime.now(timezone.utc)
            return now.year - dt.year - ((now.month, now.day) < (dt.month, dt.day))
        except Exception:
            return None
    
    def _merge_pan_hints(self, pan_result: dict, hints: dict | None) -> dict:
        """Merge Roboflow hints with enhanced extraction"""
        if not hints:
            return pan_result
        
        fields = pan_result.get("extracted_fields", {})
        validation = pan_result.get("validation", {})
        
        # Merge PAN number
        normalized_pan = self._normalize_pan_text(hints.get("pan_number"))
        if not fields.get("pan_number") and normalized_pan:
            fields["pan_number"] = normalized_pan
            validation["pan_format_valid"] = True
        
        # Merge name with enhanced cleaning
        if not fields.get("name") and hints.get("name"):
            from app.enhanced_extractors import enhanced_clean_name
            fields["name"] = enhanced_clean_name(str(hints.get("name")))
            validation["name_found"] = True
        
        # Merge father's name
        if not fields.get("fathers_name") and hints.get("fathers_name"):
            from app.enhanced_extractors import enhanced_clean_name
            fields["fathers_name"] = enhanced_clean_name(str(hints.get("fathers_name")))
        
        # Merge DOB
        normalized_dob = self._normalize_date_text(hints.get("date_of_birth"))
        if not fields.get("date_of_birth") and normalized_dob:
            fields["date_of_birth"] = normalized_dob
            validation["dob_found"] = True
        
        # Recalculate age
        if fields.get("age") is None and fields.get("date_of_birth"):
            age = self._calc_age_from_dob(fields.get("date_of_birth"))
            fields["age"] = age
            fields["age_eligible"] = bool(age is not None and 21 <= age <= 65)
            validation["age_check_passed"] = fields["age_eligible"]
        
        # Recompute overall validity
        validation["overall_valid"] = bool(
            validation.get("pan_format_valid")
            and validation.get("name_found")
            and validation.get("dob_found")
            and validation.get("age_check_passed")
        )
        
        pan_result["extracted_fields"] = fields
        pan_result["validation"] = validation
        return pan_result
    
    def _register_processed_doc(self) -> None:
        key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.processed_by_day[key] = self.processed_by_day.get(key, 0) + 1
    
    def _today_processed(self) -> int:
        key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self.processed_by_day.get(key, 0)
    
    def uptime_seconds(self) -> int:
        return int((datetime.now(timezone.utc) - self.boot_time).total_seconds())
    
    def extract_pan(self, file_bytes: bytes, filename: str) -> tuple[dict, float, int, str]:
        """Enhanced PAN extraction with better OCR"""
        started = time.perf_counter()
        extension = Path(filename).suffix
        
        try:
            # Use enhanced preprocessing
            preprocessed = enhanced_preprocess_image(file_bytes, extension)
            ocr_text, confidence = run_enhanced_ocr(preprocessed)
            
            # Use enhanced extraction
            result = enhanced_extract_pan(ocr_text)
            
            # Optional Roboflow enrichment
            hints = extract_pan_hints_with_roboflow(file_bytes, filename)
            if hints:
                result = self._merge_pan_hints(result, hints)
                confidence = max(confidence, float(hints.get("avg_confidence") or 0.0))
            
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            
            self._register_processed_doc()
            
            logger.info(f"PAN extraction completed in {elapsed_ms}ms with confidence {confidence}")
            return result, confidence, elapsed_ms, ocr_text
            
        except Exception as e:
            logger.error(f"PAN extraction failed: {e}")
            # Return empty result on failure
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return {
                "document_type": "PAN",
                "extracted_fields": {
                    "pan_number": None,
                    "name": None,
                    "fathers_name": None,
                    "date_of_birth": None,
                    "age": None,
                    "age_eligible": False,
                },
                "validation": {
                    "pan_format_valid": False,
                    "age_check_passed": False,
                    "name_found": False,
                    "dob_found": False,
                    "overall_valid": False,
                    "issues": ["Extraction failed: " + str(e)],
                },
            }, 0.0, elapsed_ms, ""
    
    def extract_aadhaar(self, file_bytes: bytes, filename: str) -> tuple[dict, float, int, str]:
        """Enhanced Aadhaar extraction with better OCR"""
        started = time.perf_counter()
        extension = Path(filename).suffix
        
        try:
            # Use enhanced preprocessing
            preprocessed = enhanced_preprocess_image(file_bytes, extension)
            ocr_text, confidence = run_enhanced_ocr(preprocessed)
            
            # Use enhanced extraction
            result = enhanced_extract_aadhaar(ocr_text)
            
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            
            self._register_processed_doc()
            
            logger.info(f"Aadhaar extraction completed in {elapsed_ms}ms with confidence {confidence}")
            return result, confidence, elapsed_ms, ocr_text
            
        except Exception as e:
            logger.error(f"Aadhaar extraction failed: {e}")
            # Return empty result on failure
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return {
                "document_type": "AADHAAR",
                "extracted_fields": {
                    "aadhaar_last4": None,
                    "name": None,
                    "date_of_birth": None,
                    "age": None,
                    "gender": "Unknown",
                    "address": None,
                    "vid": None,
                    "age_eligible": False,
                },
                "validation": {
                    "aadhaar_format_valid": False,
                    "age_check_passed": False,
                    "overall_valid": False,
                    "issues": ["Extraction failed: " + str(e)],
                },
            }, 0.0, elapsed_ms, ""
    
    def extract_auto(self, file_bytes: bytes, filename: str) -> tuple[str, dict | None, dict | None, float, int]:
        """Enhanced auto-detection and extraction"""
        started = time.perf_counter()
        extension = Path(filename).suffix
        
        try:
            # Use enhanced preprocessing
            preprocessed = enhanced_preprocess_image(file_bytes, extension)
            ocr_text, confidence = run_enhanced_ocr(preprocessed)
            
            # Detect document type
            doc_type = detect_document_type(ocr_text)
            
            pan_result = None
            aadhaar_result = None
            
            if doc_type == "PAN":
                pan_result = enhanced_extract_pan(ocr_text)
            elif doc_type == "AADHAAR":
                aadhaar_result = enhanced_extract_aadhaar(ocr_text)
            
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            
            self._register_processed_doc()
            
            logger.info(f"Auto extraction completed: {doc_type} in {elapsed_ms}ms")
            return doc_type, pan_result, aadhaar_result, confidence, elapsed_ms
            
        except Exception as e:
            logger.error(f"Auto extraction failed: {e}")
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return "UNKNOWN", None, None, 0.0, elapsed_ms
    
    def verify(self, pan_file_bytes: bytes, pan_filename: str, 
              aadhaar_file_bytes: bytes, aadhaar_filename: str) -> dict:
        """Enhanced KYC verification with better matching"""
        try:
            # Extract PAN and Aadhaar data
            pan_result, pan_conf, pan_ms, _ = self.extract_pan(pan_file_bytes, pan_filename)
            aadhaar_result, aadhaar_conf, aadhaar_ms, _ = self.extract_aadhaar(aadhaar_file_bytes, aadhaar_filename)
            
            # Enhanced cross-validation
            cross = enhanced_cross_validate_kyc(pan_result, aadhaar_result)
            
            # Generate reference
            timestamp = datetime.now(timezone.utc)
            ref = f"KYC-{timestamp.year}-{self._today_processed():05d}"
            
            # Log verification results
            logger.info(f"KYC verification completed: {cross['kyc_status']} "
                        f"(Name score: {cross['cross_validation']['name_match_score']})")
            
            return {
                "kyc_status": cross["kyc_status"],
                "pan_data": pan_result["extracted_fields"],
                "aadhaar_data": aadhaar_result["extracted_fields"],
                "cross_validation": cross["cross_validation"],
                "overall_kyc_passed": cross["overall_kyc_passed"],
                "kyc_reference_id": ref,
                "timestamp": timestamp,
                "_metrics": {
                    "pan_confidence": pan_conf,
                    "aadhaar_confidence": aadhaar_conf,
                    "pan_ms": pan_ms,
                    "aadhaar_ms": aadhaar_ms,
                },
            }
            
        except Exception as e:
            logger.error(f"KYC verification failed: {e}")
            # Return failed result
            timestamp = datetime.now(timezone.utc)
            ref = f"KYC-{timestamp.year}-{self._today_processed():05d}"
            
            return {
                "kyc_status": "FAILED",
                "pan_data": {},
                "aadhaar_data": {},
                "cross_validation": {
                    "name_match_score": 0,
                    "name_match_status": "MISMATCH",
                    "pan_name": None,
                    "aadhaar_name": None,
                    "dob_match": False,
                    "age_eligible": False,
                },
                "overall_kyc_passed": False,
                "kyc_reference_id": ref,
                "timestamp": timestamp,
                "_metrics": {
                    "pan_confidence": 0.0,
                    "aadhaar_confidence": 0.0,
                    "pan_ms": 0,
                    "aadhaar_ms": 0,
                },
            }
