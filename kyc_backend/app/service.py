from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
import re

from app.extractors import (
    cross_validate_kyc,
    detect_document_type,
    extract_aadhaar,
    extract_pan,
)
from app.preprocess import preprocess_image, run_ocr
from app.roboflow_mapper import extract_pan_hints_with_roboflow


class KYCService:
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
        if not hints:
            return pan_result

        fields = pan_result.get("extracted_fields", {})
        validation = pan_result.get("validation", {})

        normalized_pan = self._normalize_pan_text(hints.get("pan_number"))
        if not fields.get("pan_number") and normalized_pan:
            fields["pan_number"] = normalized_pan
            validation["pan_format_valid"] = True

        if not fields.get("name") and hints.get("name"):
            fields["name"] = re.sub(r"\s+", " ", str(hints.get("name")).strip()).upper()[:50]
            validation["name_found"] = True

        if not fields.get("fathers_name") and hints.get("fathers_name"):
            fields["fathers_name"] = re.sub(r"\s+", " ", str(hints.get("fathers_name")).strip()).upper()[:50]

        normalized_dob = self._normalize_date_text(hints.get("date_of_birth"))
        if not fields.get("date_of_birth") and normalized_dob:
            fields["date_of_birth"] = normalized_dob
            validation["dob_found"] = True

        if fields.get("age") is None and fields.get("date_of_birth"):
            age = self._calc_age_from_dob(fields.get("date_of_birth"))
            fields["age"] = age
            fields["age_eligible"] = bool(age is not None and 21 <= age <= 65)
            validation["age_check_passed"] = fields["age_eligible"]

        # Recompute overall validity after enrichment.
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
        started = time.perf_counter()
        extension = Path(filename).suffix
        preprocessed = preprocess_image(file_bytes, extension)
        ocr_text, confidence = run_ocr(preprocessed)
        result = extract_pan(ocr_text)

        # Optional Roboflow mapping enrichment (if API key/workflow env vars are configured).
        hints = extract_pan_hints_with_roboflow(file_bytes, filename)
        if hints:
            result = self._merge_pan_hints(result, hints)
            confidence = max(confidence, float(hints.get("avg_confidence") or 0.0))

        elapsed_ms = int((time.perf_counter() - started) * 1000)

        self._register_processed_doc()
        return result, confidence, elapsed_ms, ocr_text

    def extract_aadhaar(self, file_bytes: bytes, filename: str) -> tuple[dict, float, int, str]:
        started = time.perf_counter()
        extension = Path(filename).suffix
        preprocessed = preprocess_image(file_bytes, extension)
        ocr_text, confidence = run_ocr(preprocessed)
        result = extract_aadhaar(ocr_text)
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        self._register_processed_doc()
        return result, confidence, elapsed_ms, ocr_text

    def extract_auto(self, file_bytes: bytes, filename: str) -> tuple[str, dict | None, dict | None, float, int]:
        started = time.perf_counter()
        extension = Path(filename).suffix
        preprocessed = preprocess_image(file_bytes, extension)
        ocr_text, confidence = run_ocr(preprocessed)
        doc_type = detect_document_type(ocr_text)

        pan_result = None
        aadhaar_result = None

        if doc_type == "PAN":
            pan_result = extract_pan(ocr_text)
        elif doc_type == "AADHAAR":
            aadhaar_result = extract_aadhaar(ocr_text)

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        self._register_processed_doc()

        return doc_type, pan_result, aadhaar_result, confidence, elapsed_ms

    def verify(self, pan_file_bytes: bytes, pan_filename: str, aadhaar_file_bytes: bytes, aadhaar_filename: str) -> dict:
        pan_result, pan_conf, pan_ms, _ = self.extract_pan(pan_file_bytes, pan_filename)
        aadhaar_result, aadhaar_conf, aadhaar_ms, _ = self.extract_aadhaar(aadhaar_file_bytes, aadhaar_filename)

        cross = cross_validate_kyc(pan_result, aadhaar_result)

        timestamp = datetime.now(timezone.utc)
        ref = f"KYC-{timestamp.year}-{self._today_processed():05d}"

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
