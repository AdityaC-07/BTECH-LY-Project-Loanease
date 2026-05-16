from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
import re
import logging
import numpy as np

from app.enhanced_extractors import (
    enhanced_extract_pan,
    enhanced_extract_aadhaar,
    enhanced_cross_validate_kyc,
    detect_document_type,
    score_field_confidence,
    basic_authenticity_check,
)
from app.enhanced_preprocess import (
    enhanced_preprocess_image, 
    run_enhanced_ocr,
    load_image_from_bytes,
    assess_image_quality,
)
from app.roboflow_mapper import extract_pan_hints_with_roboflow
from app.schemas import PanExtractedFields, AadhaarExtractedFields

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
    
    def extract_pan(self, file_bytes: bytes, filename: str) -> dict:
        """Enhanced PAN extraction with quality check, confidence and authenticity"""
        started = time.perf_counter()
        extension = Path(filename).suffix
        
        try:
            # 1. Load and assess quality
            pil_img = load_image_from_bytes(file_bytes, extension)
            img_np = np.array(pil_img)
            quality_data = assess_image_quality(img_np)
            
            # Rejection logic
            if not quality_data["proceed"]:
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                return {
                    "document_type": "PAN",
                    "extracted_fields": PanExtractedFields().dict(),
                    "validation": {
                        "overall_valid": False,
                        "issues": ["REJECTED: " + issue for issue in quality_data["issues"]],
                    },
                    "confidence_score": 0.0,
                    "processing_time_ms": elapsed_ms,
                    "image_quality": quality_data,
                }, ""
            
            # 2. Preprocess and OCR
            preprocessed = enhanced_preprocess_image(file_bytes, extension)
            ocr_text, confidence = run_enhanced_ocr(preprocessed)
            
            # 3. Extract and validate
            result = enhanced_extract_pan(ocr_text)
            
            # 4. Optional Roboflow enrichment
            hints = extract_pan_hints_with_roboflow(file_bytes, filename)
            if hints:
                result = self._merge_pan_hints(result, hints)
                confidence = max(confidence, float(hints.get("avg_confidence") or 0.0))
            
            # 5. Field Confidence Scoring
            fields = result.get("extracted_fields", {})
            field_conf = {
                "pan_number": score_field_confidence(ocr_text, fields.get("pan_number"), "pan"),
                "name": score_field_confidence(ocr_text, fields.get("name"), "name"),
                "date_of_birth": score_field_confidence(ocr_text, fields.get("date_of_birth"), "dob"),
                "fathers_name": score_field_confidence(ocr_text, fields.get("fathers_name"), "name"),
            }
            
            # Overall confidence update
            overall_conf = sum(field_conf.values()) / len(field_conf)
            
            # 6. Authenticity Check
            authenticity = basic_authenticity_check(result, "PAN")
            
            # Quality warning
            if 40 <= quality_data["quality_score"] < 65:
                result["validation"]["issues"].append(
                    "Image quality is low — some fields may not extract correctly. "
                    "We'll try, but a clearer photo works better."
                )
            
            # Critical field confidence check
            critical_fields = ["pan_number", "name", "date_of_birth"]
            low_conf_fields = [f for f in critical_fields if field_conf.get(f, 0) < 0.7]
            if low_conf_fields:
                result["validation"]["issues"].append(
                    f"Low confidence in fields: {', '.join(low_conf_fields)}. Please ensure they are clear."
                )
            
            # Auto-terminate on authenticity
            if authenticity["auto_terminate"]:
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                return {
                    "document_type": "PAN",
                    "extracted_fields": fields,
                    "validation": {
                        "overall_valid": False,
                        "issues": ["Only individual (personal) PAN cards are accepted for personal loan applications."],
                    },
                    "confidence_score": confidence,
                    "processing_time_ms": elapsed_ms,
                    "image_quality": quality_data,
                    "authenticity": authenticity,
                }, ocr_text
            
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self._register_processed_doc()
            
            final_result = {
                "document_type": "PAN",
                "extracted_fields": fields,
                "validation": result["validation"],
                "confidence_score": round(confidence, 2),
                "processing_time_ms": elapsed_ms,
                "image_quality": quality_data,
                "field_confidence": field_conf,
                "authenticity": authenticity,
            }
            return final_result, ocr_text
            
        except Exception as e:
            logger.error(f"PAN extraction failed: {e}")
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return {
                "document_type": "PAN",
                "extracted_fields": {
                    "pan_number": None, "name": None, "fathers_name": None,
                    "date_of_birth": None, "age": None, "age_eligible": False,
                },
                "validation": {
                    "overall_valid": False,
                    "issues": ["Extraction failed: " + str(e)],
                },
                "confidence_score": 0.0,
                "processing_time_ms": elapsed_ms,
            }, ""
    
    def extract_aadhaar(self, file_bytes: bytes, filename: str) -> dict:
        """Enhanced Aadhaar extraction with quality check and confidence"""
        started = time.perf_counter()
        extension = Path(filename).suffix
        
        try:
            # 1. Load and assess quality
            pil_img = load_image_from_bytes(file_bytes, extension)
            img_np = np.array(pil_img)
            quality_data = assess_image_quality(img_np)
            
            # Rejection logic
            if not quality_data["proceed"]:
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                return {
                    "document_type": "AADHAAR",
                    "extracted_fields": AadhaarExtractedFields().dict(),
                    "validation": {
                        "overall_valid": False,
                        "issues": ["REJECTED: " + issue for issue in quality_data["issues"]],
                    },
                    "confidence_score": 0.0,
                    "processing_time_ms": elapsed_ms,
                    "image_quality": quality_data,
                }, ""
                
            # 2. Preprocess and OCR
            preprocessed = enhanced_preprocess_image(file_bytes, extension)
            ocr_text, confidence = run_enhanced_ocr(preprocessed)
            
            # 3. Extract and validate
            result = enhanced_extract_aadhaar(ocr_text)
            
            # 4. Field Confidence Scoring
            fields = result.get("extracted_fields", {})
            field_conf = {
                "name": score_field_confidence(ocr_text, fields.get("name"), "name"),
                "date_of_birth": score_field_confidence(ocr_text, fields.get("date_of_birth"), "dob"),
            }
            
            # Quality warning
            if 40 <= quality_data["quality_score"] < 65:
                result["validation"]["issues"].append(
                    "Image quality is low — some fields may not extract correctly. "
                    "We'll try, but a clearer photo works better."
                )
            
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self._register_processed_doc()
            
            final_result = {
                "document_type": "AADHAAR",
                "extracted_fields": fields,
                "validation": result["validation"],
                "confidence_score": round(confidence, 2),
                "processing_time_ms": elapsed_ms,
                "image_quality": quality_data,
                "field_confidence": field_conf,
            }
            return final_result, ocr_text
            
        except Exception as e:
            logger.error(f"Aadhaar extraction failed: {e}")
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return {
                "document_type": "AADHAAR",
                "extracted_fields": {
                    "aadhaar_last4": None, "name": None, "date_of_birth": None,
                    "age": None, "gender": "Unknown", "address": None,
                    "vid": None, "age_eligible": False,
                },
                "validation": {
                    "overall_valid": False,
                    "issues": ["Extraction failed: " + str(e)],
                },
                "confidence_score": 0.0,
                "processing_time_ms": elapsed_ms,
            }, ""
    
    def extract_auto(self, file_bytes: bytes, filename: str) -> dict:
        """Enhanced auto-detection and extraction with new checks"""
        started = time.perf_counter()
        extension = Path(filename).suffix
        
        try:
            # 1. Quality check first
            pil_img = load_image_from_bytes(file_bytes, extension)
            img_np = np.array(pil_img)
            quality_data = assess_image_quality(img_np)
            
            if not quality_data["proceed"]:
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                return {
                    "detected_document_type": "UNKNOWN",
                    "message": "REJECTED: " + quality_data["issues"][0] if quality_data["issues"] else "Low quality",
                    "image_quality": quality_data
                }

            # 2. Proceed with extraction
            preprocessed = enhanced_preprocess_image(file_bytes, extension)
            ocr_text, confidence = run_enhanced_ocr(preprocessed)
            
            # Detect document type
            doc_type = detect_document_type(ocr_text)
            
            pan_result = None
            aadhaar_result = None
            
            if doc_type == "PAN":
                pan_result, _ = self.extract_pan(file_bytes, filename)
            elif doc_type == "AADHAAR":
                aadhaar_result, _ = self.extract_aadhaar(file_bytes, filename)
            
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self._register_processed_doc()
            
            return {
                "detected_document_type": doc_type,
                "pan_result": pan_result,
                "aadhaar_result": aadhaar_result,
                "message": f"{doc_type} document detected and extracted",
                "processing_time_ms": elapsed_ms,
            }
            
        except Exception as e:
            logger.error(f"Auto extraction failed: {e}")
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return {
                "detected_document_type": "UNKNOWN",
                "message": f"Auto extraction failed: {str(e)}",
                "processing_time_ms": elapsed_ms,
            }
    
    def verify(self, pan_file_bytes: bytes, pan_filename: str, 
              aadhaar_file_bytes: bytes, aadhaar_filename: str) -> dict:
        """Enhanced KYC verification with new checks"""
        try:
            # Extract PAN and Aadhaar data
            pan_full, _ = self.extract_pan(pan_file_bytes, pan_filename)
            aadhaar_full, _ = self.extract_aadhaar(aadhaar_file_bytes, aadhaar_filename)
            
            # Enhanced cross-validation
            cross = enhanced_cross_validate_kyc(pan_full, aadhaar_full)
            
            # Generate reference
            timestamp = datetime.now(timezone.utc)
            ref = f"KYC-{timestamp.year}-{self._today_processed():05d}"
            
            return {
                "kyc_status": cross["kyc_status"],
                "pan_data": pan_full["extracted_fields"],
                "aadhaar_data": aadhaar_full["extracted_fields"],
                "cross_validation": cross["cross_validation"],
                "overall_kyc_passed": cross["overall_kyc_passed"],
                "kyc_reference_id": ref,
                "timestamp": timestamp,
                "_metrics": {
                    "pan_confidence": pan_full["confidence_score"],
                    "aadhaar_confidence": aadhaar_full["confidence_score"],
                    "pan_ms": pan_full["processing_time_ms"],
                    "aadhaar_ms": aadhaar_full["processing_time_ms"],
                },
                "pan_quality": pan_full.get("image_quality"),
                "aadhaar_quality": aadhaar_full.get("image_quality"),
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
