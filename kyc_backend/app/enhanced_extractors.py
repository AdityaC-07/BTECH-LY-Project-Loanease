from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple

from rapidfuzz import fuzz


# Enhanced patterns for better field recognition
PAN_PATTERN = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
AADHAAR_PATTERN = re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")
VID_PATTERN = re.compile(r"\b\d{16}\b")
PINCODE_PATTERN = re.compile(r"\b\d{6}\b")

# Enhanced keyword lists
PAN_KEYWORDS = [
    "INCOME TAX DEPARTMENT", "PERMANENT ACCOUNT NUMBER", "INCOME TAX",
    "GOVT. OF INDIA", "GOVERNMENT OF INDIA", "आयकर विभाग", "कर विभाग"
]

AADHAAR_KEYWORDS = [
    "UNIQUE IDENTIFICATION AUTHORITY", "UIDAI", "AADHAAR", "आधार",
    "GOVERNMENT OF INDIA", "भारत सरकार", "AADHAR", "भारत सरकार"
]

# Enhanced non-name hints
PAN_NON_NAME_HINTS = {
    "INCOME", "TAX", "DEPARTMENT", "PERMANENT", "ACCOUNT", "NUMBER",
    "GOVT", "GOVERNMENT", "INDIA", "SIGNATURE", "FATHER", "DOB",
    "DATE", "BIRTH", "PHOTO", "CARD", "FORM", "49AA", "आयकर", "कर"
}

AADHAAR_NON_NAME_HINTS = {
    "GOVERNMENT", "INDIA", "UNIQUE", "IDENTIFICATION", "AUTHORITY", "UIDAI",
    "AADHAAR", "ADDRESS", "DOB", "YEAR", "BIRTH", "MALE", "FEMALE", 
    "TRANSGENDER", "PHOTO", "CARD", "ENROLMENT", "VID", "आधार", "भारत", "सरकार"
}

# OCR digit mapping for better number recognition
OCR_DIGIT_MAP = str.maketrans({
    "O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "Z": "2", "S": "5",
    "B": "8", "०": "0", "१": "1", "२": "2", "३": "3", "४": "4", "५": "5",
    "६": "6", "७": "7", "८": "8", "९": "9", "o": "0", "l": "1", "i": "1"
})


def enhanced_clean_name(value: str) -> str:
    """Enhanced name cleaning with better pattern recognition"""
    # Remove non-alphabetic characters but keep spaces
    cleaned = re.sub(r"[^A-Za-z\s]", " ", value)
    # Normalize multiple spaces
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # Title case for better readability
    cleaned = cleaned.title()
    # Remove common OCR artifacts
    cleaned = re.sub(r"\b(?:And|Or|The|Of|In|On|At|To|For|With|By)\b", "", cleaned, flags=re.IGNORECASE)
    # Remove single characters
    cleaned = re.sub(r"\b[A-Za-z]\b", "", cleaned)
    # Final cleanup
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:50]


def enhanced_extract_name_from_context(lines: List[str], keywords: List[str], 
                                    non_name_hints: set) -> Optional[str]:
    """Enhanced name extraction with better context awareness"""
    for i, line in enumerate(lines):
        upper = line.upper()
        
        # Look for lines after name keywords
        if any(keyword in upper for keyword in keywords):
            # Check next few lines for name
            for j in range(i + 1, min(i + 4, len(lines))):
                candidate = lines[j].strip()
                if candidate and len(candidate) > 2:
                    # Validate as name
                    if is_valid_name_candidate(candidate, non_name_hints):
                        return enhanced_clean_name(candidate)
    
    # Fallback: look for name-like patterns anywhere
    for line in lines:
        if is_valid_name_candidate(line, non_name_hints):
            return enhanced_clean_name(line)
    
    return None


def is_valid_name_candidate(candidate: str, non_name_hints: set) -> bool:
    """Enhanced validation for name candidates"""
    upper = candidate.upper().strip()
    
    # Skip if too short or too long
    if len(upper) < 3 or len(upper) > 50:
        return False
    
    # Skip if contains numbers
    if re.search(r"\d", upper):
        return False
    
    # Skip if contains non-name hints
    if any(hint in upper for hint in non_name_hints):
        return False
    
    # Skip if all uppercase (likely not a name)
    if upper == candidate and len(upper.split()) < 2:
        return False
    
    # Skip if too few alphabetic characters
    alpha_ratio = len(re.sub(r"[^A-Za-z]", "", candidate)) / len(candidate)
    if alpha_ratio < 0.7:
        return False
    
    # Skip common OCR artifacts
    artifacts = ["SIGNATURE", "PHOTO", "CARD", "FORM", "DEPT", "GOVT", "INDIA"]
    if any(artifact in upper for artifact in artifacts):
        return False
    
    return True


def enhanced_extract_dob(raw_text: str) -> Optional[str]:
    """Enhanced DOB extraction with more patterns"""
    # Normalize common OCR confusions
    normalized = raw_text.upper()
    normalized = normalized.translate(OCR_DIGIT_MAP)
    
    # Enhanced date patterns
    patterns = [
        # Standard formats
        r"\b(\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{4})\b",
        r"\b(\d{1,2}\s*-\s*\d{1,2}\s*-\s*\d{4})\b",
        r"\b(\d{2}\s*/\s*\d{2}\s*/\s*\d{4})\b",
        r"\b(\d{2}\s*-\s*\d{2}\s*-\s*\d{4})\b",
        
        # Month name formats
        r"\b(\d{1,2}\s+(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+\d{4})\b",
        r"\b(\d{1,2}\s+(?:JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\s+\d{4})\b",
        
        # Hindi month patterns
        r"\b(\d{1,2}\s+(?:जनवरी|फरवरी|मार्च|अप्रैल|मई|जून|जुलाई|अगस्त|सितंबर|अक्टूबर|नवंबर|दिसंबर)\s+\d{4})\b",
        
        # Compact formats
        r"\b(\d{2})(\d{2})(\d{4})\b",
        r"\b(\d{8})\b",  # DDMMYYYY
    ]
    
    # Also look for DOB keywords
    dob_keywords = ["DOB", "DATE OF BIRTH", "BIRTH DATE", "BORN ON", "जन्म तिथि"]
    
    for pattern in patterns:
        matches = re.finditer(pattern, normalized, flags=re.IGNORECASE)
        for match in matches:
            if len(match.groups()) == 3:
                value = f"{match.group(1)}/{match.group(2)}/{match.group(3)}"
            elif len(match.groups()) == 2:
                value = f"{match.group(1)}/{match.group(2)}"
            else:
                value = match.group(1)
            
            # Parse and validate the date
            parsed_date = parse_flexible_date(value)
            if parsed_date:
                return parsed_date
    
    # Look for dates near DOB keywords
    for keyword in dob_keywords:
        if keyword in normalized:
            # Extract text around the keyword
            keyword_pos = normalized.find(keyword)
            context_start = max(0, keyword_pos - 20)
            context_end = min(len(normalized), keyword_pos + len(keyword) + 30)
            context = normalized[context_start:context_end]
            
            # Try to find date in context
            for pattern in patterns[:5]:  # Use first 5 patterns for context
                match = re.search(pattern, context)
                if match:
                    if len(match.groups()) >= 2:
                        value = f"{match.group(1)}/{match.group(2)}"
                        if len(match.groups()) == 3:
                            value += f"/{match.group(3)}"
                    
                    parsed_date = parse_flexible_date(value)
                    if parsed_date:
                        return parsed_date
    
    return None


def parse_flexible_date(date_str: str) -> Optional[str]:
    """Parse date in various formats and return DD/MM/YYYY"""
    formats = [
        "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y",
        "%d %b %y", "%d %B %y", "%d/%m/%y", "%d-%m-%y"
    ]
    
    # Clean the date string
    cleaned = re.sub(r"[^\d/\\-\sA-Za-z]", "", date_str)
    
    for fmt in formats:
        try:
            dt = datetime.strptime(cleaned, fmt)
            # Validate reasonable date range
            if 1900 <= dt.year <= 2026 and 1 <= dt.month <= 12 and 1 <= dt.day <= 31:
                return dt.strftime("%d/%m/%Y")
        except ValueError:
            continue
    
    return None


def enhanced_extract_pan_number(raw_text: str) -> Optional[str]:
    """Enhanced PAN number extraction with better OCR handling"""
    upper = raw_text.upper()
    
    # Direct pattern match
    direct_match = PAN_PATTERN.search(upper)
    if direct_match:
        return direct_match.group(0)
    
    # Enhanced OCR fallback
    compact_sources = [upper]
    compact_sources.extend(line.upper() for line in raw_text.splitlines() if line.strip())
    
    for source in compact_sources:
        # Clean the source
        compact = re.sub(r"[^A-Z0-9]", "", source)
        if len(compact) < 10:
            continue
        
        # Look for PAN-like patterns
        for start in range(0, len(compact) - 9):
            window = compact[start:start + 10]
            if is_valid_pan_candidate(window):
                return normalize_pan_candidate(window)
    
    return None


def is_valid_pan_candidate(candidate: str) -> bool:
    """Validate PAN candidate format"""
    if len(candidate) != 10:
        return False
    
    # Check first 5 are letters, last 4 are digits, last is letter
    if not re.match(r"[A-Z]{5}\d{4}[A-Z]", candidate):
        return False
    
    # Check 4th character (account type)
    if candidate[3] not in {"P", "C", "H", "F", "A", "T", "B", "L", "J", "G"}:
        return False
    
    return True


def normalize_pan_candidate(candidate: str) -> str:
    """Normalize PAN candidate with OCR corrections"""
    # Common OCR corrections
    corrections = {
        "0": "O", "1": "I", "2": "Z", "5": "S", "6": "G", "8": "B",
        "I": "1", "L": "1", "O": "0", "Q": "0", "D": "0", "S": "5", "B": "8", "Z": "2"
    }
    
    chars = list(candidate)
    
    # Apply corrections for letter positions
    for i in [0, 1, 2, 3, 4, 9]:
        chars[i] = corrections.get(chars[i], chars[i])
    
    # Apply corrections for digit positions
    for i in [5, 6, 7, 8]:
        chars[i] = corrections.get(chars[i], chars[i])
    
    return "".join(chars)


def enhanced_extract_aadhaar_number(raw_text: str) -> Optional[str]:
    """Enhanced Aadhaar number extraction"""
    normalized = raw_text.upper().translate(OCR_DIGIT_MAP)
    
    # Look for grouped formats
    grouped_patterns = [
        r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b",
        r"\b\d{2}\s\d{2}\s\d{2}\s\d{2}\s\d{2}\s\d{2}\b"
    ]
    
    for pattern in grouped_patterns:
        match = re.search(pattern, normalized)
        if match:
            digits = re.sub(r"\D", "", match.group(0))
            if len(digits) == 12:
                # Validate Aadhaar format (not starting with 0 or 1)
                if digits[0] not in {"0", "1"}:
                    return digits
    
    # Fallback: any 12-digit sequence
    plain = re.search(r"\b\d{12}\b", normalized)
    if plain:
        digits = plain.group(0)
        if digits[0] not in {"0", "1"}:
            return digits
    
    return None


def enhanced_name_matching(pan_name: str, aadhaar_name: str) -> Tuple[int, str]:
    """Enhanced name matching with multiple algorithms"""
    if not pan_name or not aadhaar_name:
        return 0, "MISMATCH"
    
    # Normalize names
    pan_norm = normalize_name_for_matching(pan_name)
    aadhaar_norm = normalize_name_for_matching(aadhaar_name)
    
    # Multiple matching algorithms
    scores = []
    
    # Token sort ratio (handles word order differences)
    scores.append(fuzz.token_sort_ratio(pan_norm, aadhaar_norm))
    
    # Token set ratio (handles missing/extra words)
    scores.append(fuzz.token_set_ratio(pan_norm, aadhaar_norm))
    
    # Partial ratio (handles partial matches)
    scores.append(fuzz.partial_ratio(pan_norm, aadhaar_norm))
    
    # Simple ratio (direct comparison)
    scores.append(fuzz.ratio(pan_norm, aadhaar_norm))
    
    # Weighted average
    final_score = int(round(
        scores[0] * 0.3 +  # Token sort
        scores[1] * 0.3 +  # Token set
        scores[2] * 0.2 +  # Partial
        scores[3] * 0.2    # Simple
    ))
    
    # Determine status with more lenient thresholds
    if final_score >= 80:
        status = "MATCH"
    elif final_score >= 60:
        status = "PARTIAL"
    else:
        status = "MISMATCH"
    
    return final_score, status


def normalize_name_for_matching(name: str) -> str:
    """Normalize name for fuzzy matching"""
    # Remove non-alphabetic characters
    cleaned = re.sub(r"[^A-Za-z\s]", " ", name.upper())
    # Normalize spaces
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # Remove common titles
    titles = ["MR", "MRS", "MS", "DR", "SHRI", "SMT", "KUMAR", "KUMARI"]
    for title in titles:
        cleaned = re.sub(rf"\b{title}\b", "", cleaned)
    # Final cleanup
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def enhanced_extract_pan(raw_text: str) -> dict:
    """Enhanced PAN extraction"""
    text_upper = raw_text.upper()
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    
    # Extract fields with enhanced methods
    pan_number = enhanced_extract_pan_number(raw_text)
    name = enhanced_extract_name_from_context(lines, ["NAME"], PAN_NON_NAME_HINTS)
    fathers_name = enhanced_extract_name_from_context(lines, ["FATHER", "FATHER'S NAME"], PAN_NON_NAME_HINTS)
    dob = enhanced_extract_dob(raw_text)
    
    # Calculate age
    age = calculate_age(dob)
    age_ok = is_age_eligible(age)
    
    # Validation
    issues = []
    pan_ok = is_valid_pan_candidate(pan_number) if pan_number else False
    if not pan_ok:
        issues.append("PAN format invalid or not found")
    if not name:
        issues.append("Name not detected")
    if not dob:
        issues.append("Date of birth not detected")
    if age is not None and not age_ok:
        issues.append("Age must be between 21 and 65")
    
    doc_ok = any(keyword in text_upper for keyword in PAN_KEYWORDS)
    if not doc_ok:
        issues.append("PAN document keywords not confidently detected")
    
    return {
        "document_type": "PAN",
        "extracted_fields": {
            "pan_number": pan_number,
            "name": name,
            "fathers_name": fathers_name,
            "date_of_birth": dob,
            "age": age,
            "age_eligible": age_ok,
        },
        "validation": {
            "pan_format_valid": pan_ok,
            "age_check_passed": age_ok,
            "name_found": bool(name),
            "dob_found": bool(dob),
            "overall_valid": pan_ok and bool(name) and bool(dob) and age_ok and doc_ok,
            "issues": issues,
        },
    }


def enhanced_extract_aadhaar(raw_text: str) -> dict:
    """Enhanced Aadhaar extraction"""
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    text_upper = raw_text.upper()
    
    # Extract fields with enhanced methods
    aadhaar_number = enhanced_extract_aadhaar_number(raw_text)
    aadhaar_last4 = aadhaar_number[-4:] if aadhaar_number else None
    name = enhanced_extract_name_from_context(lines, [], AADHAAR_NON_NAME_HINTS)
    dob = enhanced_extract_dob(raw_text)
    yob = extract_year_of_birth(raw_text)
    
    # Calculate age
    age = calculate_age(dob, yob)
    age_ok = is_age_eligible(age)
    
    # Extract other fields
    gender = extract_gender(raw_text)
    address = extract_address(lines)
    vid = extract_vid(raw_text)
    
    # Validation
    issues = []
    aadhaar_ok = bool(aadhaar_number and len(aadhaar_number) == 12 and aadhaar_number[0] not in {"0", "1"})
    if not aadhaar_ok:
        issues.append("Aadhaar number invalid or not found")
    if age is not None and not age_ok:
        issues.append("Age must be between 21 and 65")
    
    doc_ok = any(keyword in text_upper for keyword in AADHAAR_KEYWORDS)
    if not doc_ok:
        issues.append("Aadhaar document keywords not confidently detected")
    
    return {
        "document_type": "AADHAAR",
        "extracted_fields": {
            "aadhaar_last4": aadhaar_last4,
            "name": name,
            "date_of_birth": dob if dob else (str(yob) if yob else None),
            "age": age,
            "gender": gender,
            "address": address,
            "vid": vid,
            "age_eligible": age_ok,
        },
        "validation": {
            "aadhaar_format_valid": aadhaar_ok,
            "age_check_passed": age_ok,
            "overall_valid": aadhaar_ok and age_ok and doc_ok,
            "issues": issues,
        },
    }


def enhanced_cross_validate_kyc(pan_data: dict, aadhaar_data: dict) -> dict:
    """Enhanced KYC cross-validation"""
    pan_name = (pan_data.get("extracted_fields", {}).get("name") or "").strip()
    aadhaar_name = (aadhaar_data.get("extracted_fields", {}).get("name") or "").strip()
    
    # Enhanced name matching
    name_score, name_status = enhanced_name_matching(pan_name, aadhaar_name)
    
    # DOB matching
    pan_dob = (pan_data.get("extracted_fields", {}).get("date_of_birth") or "").strip()
    aadhaar_dob = (aadhaar_data.get("extracted_fields", {}).get("date_of_birth") or "").strip()
    
    dob_match = False
    if pan_dob and aadhaar_dob:
        if re.fullmatch(r"\d{2}/\d{2}/\d{4}", aadhaar_dob):
            dob_match = pan_dob == aadhaar_dob
        elif re.fullmatch(r"\d{4}", aadhaar_dob):
            dob_match = pan_dob.endswith(aadhaar_dob)
    
    # Age eligibility
    age_eligible = bool(
        pan_data.get("extracted_fields", {}).get("age_eligible")
        and aadhaar_data.get("extracted_fields", {}).get("age_eligible")
    )
    
    # Enhanced KYC status determination
    if name_score >= 80 and dob_match:
        kyc_status = "VERIFIED"
    elif name_score >= 60 and dob_match:
        kyc_status = "PARTIAL"
    elif name_score >= 70:
        kyc_status = "PARTIAL"  # Accept partial name match even without DOB
    else:
        kyc_status = "FAILED"
    
    return {
        "kyc_status": kyc_status,
        "cross_validation": {
            "name_match_score": name_score,
            "name_match_status": name_status,
            "pan_name": pan_name or None,
            "aadhaar_name": aadhaar_name or None,
            "dob_match": dob_match,
            "age_eligible": age_eligible,
        },
        "overall_kyc_passed": kyc_status in {"VERIFIED", "PARTIAL"} and age_eligible,
    }


# Helper functions (keeping existing ones)
def calculate_age(dob: Optional[str] = None, yob: Optional[int] = None) -> Optional[int]:
    now = datetime.now(timezone.utc)
    if dob:
        try:
            dob_dt = datetime.strptime(dob, "%d/%m/%Y")
            age = now.year - dob_dt.year - ((now.month, now.day) < (dob_dt.month, dob_dt.day))
            return age
        except ValueError:
            return None
    if yob:
        return now.year - yob
    return None


def is_age_eligible(age: Optional[int]) -> bool:
    return age is not None and 21 <= age <= 65


def extract_gender(raw_text: str) -> str:
    upper = raw_text.upper()
    if any(token in upper for token in ["FEMALE", "FEM ALE", "FEMA1E"]) or "महिला" in raw_text:
        return "Female"
    if any(token in upper for token in ["MALE", "M ALE", "MA1E"]) or "पुरुष" in raw_text:
        return "Male"
    if "TRANSGENDER" in upper or "ट्रांसजेंडर" in raw_text:
        return "Other"
    return "Unknown"


def extract_address(lines: List[str]) -> dict:
    # Simplified address extraction
    start = -1
    for i, line in enumerate(lines):
        if "ADDRESS" in line.upper() or "पता" in line:
            start = i
            break
    
    if start == -1:
        return {"full": None, "house_no": None, "street": None, "city": None, "state": None, "pincode": None}
    
    block = []
    for line in lines[start + 1:start + 10]:
        block.append(line)
        if PINCODE_PATTERN.search(line):
            break
    
    full = re.sub(r"\s+", " ", ", ".join(block)).strip(" ,")
    pincode_match = PINCODE_PATTERN.search(full)
    pincode = pincode_match.group(0) if pincode_match else None
    
    parts = [p.strip() for p in full.split(",") if p.strip()]
    
    return {
        "full": full or None,
        "house_no": parts[0] if len(parts) > 0 else None,
        "street": parts[1] if len(parts) > 1 else None,
        "city": parts[-2] if len(parts) >= 2 else None,
        "state": parts[-1] if len(parts) >= 1 else None,
        "pincode": pincode,
    }


def extract_year_of_birth(raw_text: str) -> Optional[int]:
    normalized = raw_text.upper().translate(OCR_DIGIT_MAP)
    match = re.search(r"(?:YEAR\s+OF\s+BIRTH|YOB|जन्म\s+वर्ष)\s*[:\-]?\s*(\d{4})", normalized, flags=re.IGNORECASE)
    if match:
        year = int(match.group(1))
        return year if 1900 <= year <= datetime.now(timezone.utc).year else None
    return None


def extract_vid(raw_text: str) -> Optional[str]:
    vid_match = VID_PATTERN.search(raw_text)
    return vid_match.group(0) if vid_match else None


def detect_document_type(raw_text: str) -> str:
    upper = raw_text.upper()
    
    has_pan = any(keyword in upper for keyword in PAN_KEYWORDS) or bool(PAN_PATTERN.search(upper))
    has_aadhaar = any(keyword in upper for keyword in AADHAAR_KEYWORDS) or bool(AADHAAR_PATTERN.search(raw_text))
    
    if has_pan and not has_aadhaar:
        return "PAN"
    if has_aadhaar and not has_pan:
        return "AADHAAR"
    if has_pan:
        return "PAN"
    if has_aadhaar:
        return "AADHAAR"
    
    return "UNKNOWN"
