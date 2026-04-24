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
    "INCOME",
    "TAX",
    "DEPARTMENT",
    "PERMANENT",
    "ACCOUNT",
    "NUMBER",
    "GOVT",
    "GOVERNMENT",
    "INDIA",
    "SIGNATURE",
    "FATHER",
    "DOB",
}

AADHAAR_NON_NAME_HINTS = {
    "GOVERNMENT",
    "INDIA",
    "UNIQUE",
    "IDENTIFICATION",
    "AUTHORITY",
    "UIDAI",
    "AADHAAR",
    "ADDRESS",
    "DOB",
    "YEAR",
    "BIRTH",
    "MALE",
    "FEMALE",
    "TRANSGENDER",
}

OCR_DIGIT_MAP = str.maketrans({
    "O": "0",
    "Q": "0",
    "D": "0",
    "I": "1",
    "L": "1",
    "Z": "2",
    "S": "5",
    "B": "8",
    "०": "0",
    "१": "1",
    "२": "2",
    "३": "3",
    "४": "4",
    "५": "5",
    "६": "6",
    "७": "7",
    "८": "8",
    "९": "9",
})


def _clean_caps_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z\s]", " ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().upper()
    return cleaned[:50]


def _clean_name_mixed(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z\s]", " ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().title()
    return cleaned[:50]


def _extract_next_line(lines: list[str], keywords: list[str]) -> str | None:
    for i, line in enumerate(lines):
        upper = line.upper()
        if any(k in upper for k in keywords):
            if i + 1 < len(lines):
                nxt = lines[i + 1].strip()
                if nxt:
                    return nxt
    return None


def _normalize_pan_candidate(candidate: str) -> str:
    token = re.sub(r"[^A-Z0-9]", "", candidate.upper())
    if len(token) != 10:
        return token

    chars = list(token)

    # PAN format positions: LLLLLDDDDL
    letter_map = {"0": "O", "1": "I", "2": "Z", "5": "S", "6": "G", "8": "B"}
    digit_map = {
        "I": "1",
        "L": "1",
        "O": "0",
        "Q": "0",
        "D": "0",
        "S": "5",
        "B": "8",
        "Z": "2",
    }

    for i in [0, 1, 2, 3, 4, 9]:
        chars[i] = letter_map.get(chars[i], chars[i])
    for i in [5, 6, 7, 8]:
        chars[i] = digit_map.get(chars[i], chars[i])

    return "".join(chars)


def _extract_pan_number(raw_text: str) -> str | None:
    upper = raw_text.upper()

    direct_match = PAN_PATTERN.search(upper)
    if direct_match:
        return direct_match.group(0)

    # OCR fallback: PANs often arrive with spaces, punctuation, or broken tokens.
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

    return None


def _fallback_pan_name(lines: list[str], pan_number: str | None) -> str | None:
    for line in lines:
        upper = line.upper().strip()
        if not upper:
            continue
        if any(hint in upper for hint in PAN_NON_NAME_HINTS):
            continue
        if re.search(r"\d", upper):
            continue
        if pan_number and pan_number in upper:
            continue
        if len(upper) < 3 or len(upper) > 50:
            continue
        if re.fullmatch(r"[A-Z\s]{3,50}", upper):
            return _clean_caps_name(upper)
    return None


def _extract_dob(raw_text: str) -> str | None:
    # Normalize common OCR confusions before date parsing.
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


def _extract_year_of_birth(raw_text: str) -> int | None:
    normalized = raw_text.upper().translate(OCR_DIGIT_MAP)
    match = re.search(r"(?:YEAR\s+OF\s+BIRTH|YOB)\s*[:\-]?\s*(\d{4})", normalized, flags=re.IGNORECASE)
    if not match:
        return None
    year = int(match.group(1))
    return year if 1900 <= year <= datetime.now(timezone.utc).year else None


def _calculate_age(dob_ddmmyyyy: str | None = None, year_of_birth: int | None = None) -> int | None:
    now = datetime.now(timezone.utc)
    if dob_ddmmyyyy:
        try:
            dob = datetime.strptime(dob_ddmmyyyy, "%d/%m/%Y")
            age = now.year - dob.year - ((now.month, now.day) < (dob.month, dob.day))
            return age
        except ValueError:
            return None

    if year_of_birth:
        return now.year - year_of_birth

    return None


def _age_eligible(age: int | None) -> bool:
    return age is not None and 21 <= age <= 65


def _validate_pan_format(pan: str | None) -> bool:
    if not pan or not PAN_PATTERN.fullmatch(pan):
        return False

    pan = pan.upper()
    if pan[3] not in {"P", "C", "H", "F"}:
        return False

    return True


def _confirm_document_type(raw_text_upper: str, keywords: list[str]) -> bool:
    return any(keyword in raw_text_upper for keyword in keywords)


def extract_pan(raw_text: str) -> dict:
    text_upper = raw_text.upper()
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

    pan_number = _extract_pan_number(raw_text)

    name_line = _extract_next_line(lines, ["NAME"]) or ""
    father_line = _extract_next_line(lines, ["FATHER", "FATHER'S NAME"]) or ""

    name = _clean_caps_name(name_line) if name_line else _fallback_pan_name(lines, pan_number)
    fathers_name = _clean_caps_name(father_line) if father_line else None

    dob = _extract_dob(raw_text)
    age = _calculate_age(dob_ddmmyyyy=dob)
    age_ok = _age_eligible(age)

    issues: list[str] = []
    pan_ok = _validate_pan_format(pan_number)
    if not pan_ok:
        issues.append("PAN format invalid or not found")
    if not name:
        issues.append("Name not detected")
    if not dob:
        issues.append("Date of birth not detected")
    if age is not None and not age_ok:
        issues.append("Age must be between 21 and 65")

    doc_ok = _confirm_document_type(text_upper, PAN_KEYWORDS)
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


def _extract_aadhaar_name(lines: list[str]) -> str | None:
    header_idx = -1
    for i, line in enumerate(lines):
        upper = line.upper()
        if "GOVERNMENT OF INDIA" in upper or "भारत सरकार" in upper:
            header_idx = i
            break

    if header_idx == -1:
        candidates = lines[:6]
    else:
        candidates = lines[header_idx + 1 : header_idx + 7]

    for line in candidates:
        upper = line.upper().strip()
        if not upper:
            continue
        if any(h in upper for h in AADHAAR_NON_NAME_HINTS):
            continue
        if re.search(r"\d", upper):
            continue
        if re.fullmatch(r"[A-Za-z\s]{3,50}", line.strip()):
            return _clean_name_mixed(line)

    # Fallback scan across full document for best name-like line.
    for line in lines:
        upper = line.upper().strip()
        if not upper:
            continue
        if any(h in upper for h in AADHAAR_NON_NAME_HINTS):
            continue
        if re.search(r"\d", upper):
            continue
        if 3 <= len(upper) <= 50 and re.fullmatch(r"[A-Za-z\s]{3,50}", line.strip()):
            return _clean_name_mixed(line)

    return None


def _extract_gender(raw_text: str) -> str:
    upper = raw_text.upper()
    if any(token in upper for token in ["FEMALE", "FEM ALE", "FEMA1E"]) or "महिला" in raw_text:
        return "Female"
    if any(token in upper for token in ["MALE", "M ALE", "MA1E"]) or "पुरुष" in raw_text:
        return "Male"
    if "TRANSGENDER" in upper or "ट्रांसजेंडर" in raw_text:
        return "Other"
    return "Unknown"


def _extract_aadhaar_number(raw_text: str) -> str | None:
    normalized = raw_text.upper().translate(OCR_DIGIT_MAP)

    # Prefer grouped formats first.
    grouped = re.search(r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b", normalized)
    if grouped:
        digits = re.sub(r"\D", "", grouped.group(0))
        if len(digits) == 12:
            return digits

    # Fallback: any 12-digit run.
    plain = re.search(r"\b\d{12}\b", normalized)
    if plain:
        return plain.group(0)

    return None


def _extract_address(lines: list[str]) -> dict:
    start = -1
    for i, line in enumerate(lines):
        if "ADDRESS" in line.upper() or "पता" in line:
            start = i
            break

    if start == -1:
        # Fallback: collect contiguous tail lines that end at pincode.
        fallback_block: list[str] = []
        for line in lines[-8:]:
            fallback_block.append(line)
            if PINCODE_PATTERN.search(line):
                break
        full = re.sub(r"\s+", " ", ", ".join(fallback_block)).strip(" ,")
        pincode_match = PINCODE_PATTERN.search(full)
        pincode = pincode_match.group(0) if pincode_match else None
        if not pincode:
            return {
                "full": None,
                "house_no": None,
                "street": None,
                "city": None,
                "state": None,
                "pincode": None,
            }

        parts = [p.strip() for p in full.split(",") if p.strip()]
        return {
            "full": full or None,
            "house_no": parts[0] if len(parts) > 0 else None,
            "street": parts[1] if len(parts) > 1 else None,
            "city": parts[-2] if len(parts) >= 2 else None,
            "state": parts[-1] if len(parts) >= 1 else None,
            "pincode": pincode,
        }

    block: list[str] = []
    for line in lines[start + 1 : start + 10]:
        block.append(line)
        if PINCODE_PATTERN.search(line):
            break

    full = re.sub(r"\s+", " ", ", ".join(block)).strip(" ,")
    pincode_match = PINCODE_PATTERN.search(full)
    pincode = pincode_match.group(0) if pincode_match else None

    parts = [p.strip() for p in full.split(",") if p.strip()]
    house_no = parts[0] if len(parts) > 0 else None
    street = parts[1] if len(parts) > 1 else None
    city = parts[-2] if len(parts) >= 2 else None
    state = parts[-1] if len(parts) >= 1 else None

    return {
        "full": full or None,
        "house_no": house_no,
        "street": street,
        "city": city,
        "state": state,
        "pincode": pincode,
    }


def extract_aadhaar(raw_text: str) -> dict:
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    text_upper = raw_text.upper()

    digits = _extract_aadhaar_number(raw_text)

    aadhaar_ok = bool(digits and len(digits) == 12 and digits[0] not in {"0", "1"})
    aadhaar_last4 = digits[-4:] if digits else None

    full_dob = _extract_dob(raw_text)
    yob = _extract_year_of_birth(raw_text)
    age = _calculate_age(dob_ddmmyyyy=full_dob, year_of_birth=yob)
    age_ok = _age_eligible(age)

    name = _extract_aadhaar_name(lines)
    gender = _extract_gender(raw_text)
    address = _extract_address(lines)

    vid_match = VID_PATTERN.search(raw_text)
    vid = vid_match.group(0) if vid_match else None

    doc_ok = _confirm_document_type(
        text_upper,
        AADHAAR_KEYWORDS + ["GOVERNMENT OF INDIA", "भारत सरकार", "AADHAR"],
    )

    issues: list[str] = []
    if not aadhaar_ok:
        issues.append("Aadhaar number invalid or not found")
    if age is not None and not age_ok:
        issues.append("Age must be between 21 and 65")
    if not doc_ok:
        issues.append("Aadhaar document keywords not confidently detected")

    return {
        "document_type": "AADHAAR",
        "extracted_fields": {
            "aadhaar_last4": aadhaar_last4,
            "name": name,
            "date_of_birth": full_dob if full_dob else (str(yob) if yob else None),
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


def detect_document_type(raw_text: str) -> str:
    upper = raw_text.upper()

    has_pan = _confirm_document_type(upper, PAN_KEYWORDS) or bool(PAN_PATTERN.search(upper))
    has_aadhaar = _confirm_document_type(upper, AADHAAR_KEYWORDS) or bool(AADHAAR_PATTERN.search(raw_text))

    if has_pan and not has_aadhaar:
        return "PAN"
    if has_aadhaar and not has_pan:
        return "AADHAAR"
    if has_pan:
        return "PAN"
    if has_aadhaar:
        return "AADHAAR"

    return "UNKNOWN"


def cross_validate_kyc(pan_data: dict, aadhaar_data: dict) -> dict:
    pan_name = (pan_data.get("extracted_fields", {}).get("name") or "").strip()
    aadhaar_name = (aadhaar_data.get("extracted_fields", {}).get("name") or "").strip()

    def _normalize_name(value: str) -> str:
        cleaned = re.sub(r"[^A-Z\s]", " ", value.upper())
        return re.sub(r"\s+", " ", cleaned).strip()

    pan_norm = _normalize_name(pan_name)
    aadhaar_norm = _normalize_name(aadhaar_name)

    if pan_norm and aadhaar_norm:
        score_sort = fuzz.token_sort_ratio(pan_norm, aadhaar_norm)
        score_set = fuzz.token_set_ratio(pan_norm, aadhaar_norm)
        score_partial = fuzz.partial_ratio(pan_norm, aadhaar_norm)
        name_score = int(round(max(score_sort, score_set, score_partial)))
    else:
        name_score = 0

    if name_score >= 85:
        name_status = "MATCH"
    elif name_score >= 70:
        name_status = "PARTIAL"
    else:
        name_status = "MISMATCH"

    pan_dob = (pan_data.get("extracted_fields", {}).get("date_of_birth") or "").strip()
    aadhaar_dob = (aadhaar_data.get("extracted_fields", {}).get("date_of_birth") or "").strip()

    dob_match = False
    if pan_dob and aadhaar_dob:
        if re.fullmatch(r"\d{2}/\d{2}/\d{4}", aadhaar_dob):
            dob_match = pan_dob == aadhaar_dob
        elif re.fullmatch(r"\d{4}", aadhaar_dob):
            dob_match = pan_dob.endswith(aadhaar_dob)

    age_eligible = bool(
        pan_data.get("extracted_fields", {}).get("age_eligible")
        and aadhaar_data.get("extracted_fields", {}).get("age_eligible")
    )

    if name_score >= 85 and dob_match:
        kyc_status = "VERIFIED"
    elif name_score >= 70 and dob_match:
        kyc_status = "PARTIAL"
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
