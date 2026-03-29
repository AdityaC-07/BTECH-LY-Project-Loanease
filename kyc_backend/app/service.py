from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from app.extractors import (
    cross_validate_kyc,
    detect_document_type,
    extract_aadhaar,
    extract_pan,
)
from app.preprocess import preprocess_image, run_ocr


class KYCService:
    def __init__(self) -> None:
        self.boot_time = datetime.now(timezone.utc)
        self.processed_by_day: dict[str, int] = {}

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
