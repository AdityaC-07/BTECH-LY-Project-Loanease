from __future__ import annotations

import re
from datetime import datetime, timezone

from rapidfuzz import fuzz


PAN_PATTERN = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
AADHAAR_PATTERN = re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")
VID_PATTERN = re.compile(r"\b\d{16}\b")
PINCODE_PATTERN = re.compile(r"\b\d{6}\b")

PAN_KEYWORDS = ["INCOME TAX DEPARTMENT", "PERMANENT ACCOUNT NUMBER", "INCOME TAX"]
AADHAAR_KEYWORDS = ["UNIQUE IDENTIFICATION AUTHORITY", "UIDAI", "AADHAAR", "आधार"]

PAN_NON_NAME_HINTS = {
    "INCOME", "TAX", "DEPARTMENT", "PERMANENT", "ACCOUNT", "NUMBER", "GOVT", "GOVERNMENT", "INDIA", "SIGNATURE", "FATHER", "DOB",
}

AADHAAR_NON_NAME_HINTS = {
    "GOVERNMENT", "INDIA", "UNIQUE", "IDENTIFICATION", "AUTHORITY", "UIDAI", "AADHAAR", "ADDRESS", "DOB", "YEAR", "BIRTH", "MALE", "FEMALE", "TRANSGENDER",
}

OCR_DIGIT_MAP = str.maketrans({
    "O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "Z": "2", "S": "5", "B": "8",
    "०": "0", "१": "1", "२": "2", "३": "3", "४": "4", "५": "5", "६": "6", "७": "7", "८": "8", "९": "9",
})


def _normalize_pan_candidate(candidate: str) -> str:
    token = re.sub(r"[^A-Z0-9]", "", candidate.upper())
    if len(token) != 10:
        return token
    chars = list(token)
    letter_map = {"0": "O", "1": "I", "2": "Z", "5": "S", "6": "G", "8": "B"}
    digit_map = {"I": "1", "L": "1", "O": "0", "Q": "0", "D": "0", "S": "5", "B": "8", "Z": "2"}
    for i in [0, 1, 2, 3, 4, 9]:
        chars[i] = letter_map.get(chars[i], chars[i])
    for i in [5, 6, 7, 8]:
        chars[i] = digit_map.get(chars[i], chars[i])
    return "".join(chars)


def _validate_pan_format(pan: str | None) -> bool:
    if not pan or not PAN_PATTERN.fullmatch(pan):
        return False
    pan = pan.upper()
    if pan[3] not in {"P", "C", "H", "F"}:
        return False
    return True


def _extract_pan_number(raw_text: str) -> str | None:
    upper = raw_text.upper()
    direct_match = PAN_PATTERN.search(upper)
    if direct_match:
        return direct_match.group(0)
    
    compact_sources = [upper]
    compact_sources.extend(line.upper() for line in raw_text.splitlines() if line.strip())
    
    for source in compact_sources:
        compact = re.sub(r"[^A-Z0-9]", "", source)
        if len(compact) < 10:
            continue
        
        for start in range(0, len(compact) - 9):
            window = compact[start : start + 10]
            normalized = _normalize_pan_candidate(window)
            if _validate_pan_format(normalized):
                return normalized
        
        # Spaced PAN patterns (e.g., "ABCDE 1234 F")
        spaced_match = re.search(r'([A-Z]{5})\s?([0-9]{4})\s?([A-Z])', source)
        if spaced_match:
            candidate = spaced_match.group(1) + spaced_match.group(2) + spaced_match.group(3)
            if _validate_pan_format(candidate):
                return candidate
    
    return None


def _extract_dob(raw_text: str) -> str | None:
    normalized = raw_text.upper()
    normalized = normalized.replace("O", "0").replace("I", "1").replace("L", "1")
    
    patterns = [
        r"\b(\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{4})\b",
        r"\b(\d{1,2}\s*-\s*\d{1,2}\s*-\s*\d{4})\b",
        r"\b(\d{2}\s*/\s*\d{2}\s*/\s*\d{4})\b",
        r"\b(\d{2}\s*-\s*\d{2}\s*-\s*\d{4})\b",
        r"\b(\d{2}\s+[A-Z]{3,9}\s+\d{4})\b",
        r"\b(\d{2})(\d{2})(\d{4})\b",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if not match:
            continue
        
        if len(match.groups()) == 3:
            value = f"{match.group(1)}/{match.group(2)}/{match.group(3)}"
        else:
            value = re.sub(r"\s+", "", match.group(1).strip())
            if "/" in value:
                parts = value.split("/")
                if len(parts) == 3:
                    value = f"{parts[0].zfill(2)}/{parts[1].zfill(2)}/{parts[2]}"
            elif "-" in value:
                parts = value.split("-")
                if len(parts) == 3:
                    value = f"{parts[0].zfill(2)}-{parts[1].zfill(2)}-{parts[2]}"
        
        fmts = ["%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y"]
        for fmt in fmts:
            try:
                dt = datetime.strptime(value, fmt)
                return dt.strftime("%d/%m/%Y")
            except ValueError:
                continue
    return None


def _calculate_age(dob_ddmmyyyy: str | None = None) -> int | None:
    now = datetime.now(timezone.utc)
    if dob_ddmmyyyy:
        try:
            dob = datetime.strptime(dob_ddmmyyyy, "%d/%m/%Y")
            age = now.year - dob.year - ((now.month, now.day) < (dob.month, dob.day))
            return age
        except ValueError:
            return None
    return None


def extract_pan(raw_text: str) -> dict:
    text_upper = raw_text.upper()
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    
    pan_number = _extract_pan_number(raw_text)
    
    # Extract name
    name = None
    for line in lines:
        if any(hint in line.upper() for hint in ["NAME"]):
            idx = lines.index(line)
            if idx + 1 < len(lines):
                name = lines[idx + 1]
                break
    
    name = (re.sub(r"[^A-Za-z\s]", " ", name or "").strip().upper() if name else None)
    
    dob = _extract_dob(raw_text)
    age = _calculate_age(dob_ddmmyyyy=dob)
    age_ok = age is not None and 21 <= age <= 65
    
    pan_ok = _validate_pan_format(pan_number)
    doc_ok = any(keyword in text_upper for keyword in PAN_KEYWORDS)
    
    return {
        "document_type": "PAN",
        "extracted_fields": {
            "pan_number": pan_number,
            "name": name,
            "date_of_birth": dob,
            "age": age,
            "age_eligible": age_ok,
        },
        "validation": {
            "pan_format_valid": pan_ok,
            "name_found": bool(name),
            "dob_found": bool(dob),
            "overall_valid": pan_ok and bool(name) and bool(dob) and age_ok,
        },
    }


def extract_aadhaar(raw_text: str) -> dict:
    text_upper = raw_text.upper()
    
    # Extract Aadhaar (last 4 digits)
    aadhaar_match = re.search(r'\d{4}[\s\-]?\d{4}[\s\-]?(\d{4})', raw_text)
    aadhaar_last4 = aadhaar_match.group(1) if aadhaar_match else None
    
    aadhaar_ok = bool(aadhaar_last4)
    
    dob = _extract_dob(raw_text)
    age = _calculate_age(dob_ddmmyyyy=dob)
    age_ok = age is not None and 21 <= age <= 65
    
    gender = "Male" if "MALE" in text_upper else ("Female" if "FEMALE" in text_upper else "Other")
    doc_ok = any(keyword in text_upper for keyword in AADHAAR_KEYWORDS)
    
    return {
        "document_type": "AADHAAR",
        "extracted_fields": {
            "aadhaar_last4": aadhaar_last4,
            "date_of_birth": dob,
            "age": age,
            "gender": gender,
            "age_eligible": age_ok,
        },
        "validation": {
            "aadhaar_format_valid": aadhaar_ok,
            "overall_valid": aadhaar_ok and age_ok,
        },
    }


def cross_validate_kyc(pan_data: dict, aadhaar_data: dict) -> dict:
    pan_name = (pan_data.get("extracted_fields", {}).get("name") or "").strip()
    aadhaar_name = ""  # Simplified for unified backend
    
    name_score = fuzz.token_sort_ratio(pan_name, aadhaar_name) if pan_name else 0
    name_status = "MATCH" if name_score >= 85 else ("PARTIAL" if name_score >= 70 else "MISMATCH")
    
    pan_dob = (pan_data.get("extracted_fields", {}).get("date_of_birth") or "").strip()
    aadhaar_dob = (aadhaar_data.get("extracted_fields", {}).get("date_of_birth") or "").strip()
    dob_match = pan_dob == aadhaar_dob if pan_dob and aadhaar_dob else False
    
    age_eligible = bool(
        pan_data.get("extracted_fields", {}).get("age_eligible")
        and aadhaar_data.get("extracted_fields", {}).get("age_eligible")
    )
    
    kyc_status = "VERIFIED" if name_score >= 85 and dob_match else ("PARTIAL" if name_score >= 70 else "FAILED")
    
    return {
        "kyc_status": kyc_status,
        "cross_validation": {
            "name_match_score": name_score,
            "dob_match": dob_match,
            "age_eligible": age_eligible,
        },
        "overall_kyc_passed": kyc_status in {"VERIFIED", "PARTIAL"} and age_eligible,
    }
