"""
Verhoeff Algorithm for Aadhaar Number Validation

Mathematical Basis:
  The Verhoeff algorithm (Jacobus Verhoeff, 1969) uses the dihedral group D5
  of order 10. It employs three lookup tables:

  1. Multiplication table d[i][j]:
     Models multiplication in the dihedral group D5. Detects all single-digit
     errors.

  2. Permutation table p[pos][digit]:
     Applies a position-based permutation. The permutation (1 5 8 9 4 2 7 0)(3 6)
     is applied iteratively based on position from right. Detects all adjacent
     transpositions.

  3. Inverse table inv[digit]:
     Used to compute the check digit.

  Properties:
    - Detects ALL single-digit errors
    - Detects ALL adjacent transpositions
    - Detects most twin errors (99.9%)
    - Detects most other error types
    - Check digit is always a single digit

  UIDAI Application:
    Aadhaar numbers are 12 digits.
    Digits 1-11 are the unique identifier.
    Digit 12 is the Verhoeff check digit.
    First digit cannot be 0 or 1.

  Validation:
    Compute c = 0
    For each digit right-to-left (including check digit):
      c = d[c][p[i mod 8][digit]]
    Valid if final c == 0
"""

import logging
import re
from typing import Any, Optional

logger = logging.getLogger("aadhaar_verhoeff")

# ─── LOOKUP TABLES ──────────────────────

_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]

_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]

_INV = [0, 4, 3, 2, 1, 9, 8, 7, 6, 5]


# ─── CORE ALGORITHM ─────────────────────

def verhoeff_validate(number: str) -> bool:
    """
    Validate a number using the Verhoeff checksum algorithm.

    Args:
        number: Digit string to validate

    Returns:
        True if checksum is valid
    """
    digits = re.sub(r"\D", "", str(number))
    if not digits:
        return False

    c = 0
    for i, digit in enumerate(reversed(digits)):
        c = _D[c][_P[i % 8][int(digit)]]
    return c == 0


def verhoeff_generate(prefix: str) -> int:
    """
    Generate the Verhoeff check digit for an (n-1)-digit prefix.

    Args:
        prefix: Digit string without check digit

    Returns:
        Single check digit (0-9)
    """
    digits = re.sub(r"\D", "", str(prefix))
    if len(digits) != 11:
        raise ValueError("Prefix must be exactly 11 digits")

    c = 0
    for i, digit in enumerate(reversed(digits)):
        c = _D[c][_P[(i + 1) % 8][int(digit)]]

    for check_digit in range(10):
        if _D[c][_P[0][check_digit]] == 0:
            return check_digit

    raise ValueError("Could not compute Verhoeff check digit")


def verhoeff_get_check_digit(prefix: str) -> int:
    """Backward-compatible alias for verhoeff_generate."""
    return verhoeff_generate(prefix)


# ─── AADHAAR-SPECIFIC VALIDATION ────────

def _clean_aadhaar(raw: Any) -> Optional[str]:
    """
    Clean and normalize Aadhaar input.
    Accepts: "1234 5678 9012", "123456789012", "1234-5678-9012"
    Returns: "123456789012" or None
    """
    if raw is None:
        return None

    cleaned = re.sub(r"[\s\-\.]", "", str(raw).strip())
    if not re.match(r"^\d{12}$", cleaned):
        return None

    return cleaned


def validate_aadhaar_number(aadhaar_raw: Any) -> dict:
    """
    Complete Aadhaar number validation using the Verhoeff algorithm.

    Validates:
      1. Format: exactly 12 digits
      2. First digit: not 0 or 1 (UIDAI specification)
      3. Verhoeff checksum: last digit is mathematically derived from first 11

    Returns:
        dict with keys: valid, checked, reason, message, algorithm, and
        optional aadhaar_last4, masked, expected_check_digit, actual_check_digit
    """
    cleaned = _clean_aadhaar(aadhaar_raw)

    if cleaned is None:
        display = "" if aadhaar_raw is None else str(aadhaar_raw)
        return {
            "valid": False,
            "checked": True,
            "reason": "WRONG_FORMAT",
            "message": (
                f"Aadhaar number must be exactly 12 digits. Got: '{display}'"
            ),
            "algorithm": "Verhoeff (UIDAI)",
        }

    if cleaned[0] in ("0", "1"):
        return {
            "valid": False,
            "checked": True,
            "reason": "INVALID_FIRST_DIGIT",
            "message": (
                "Aadhaar numbers cannot start with 0 or 1. "
                "This number may be fictitious or incorrectly transcribed."
            ),
            "algorithm": "Verhoeff (UIDAI)",
        }

    checksum_valid = verhoeff_validate(cleaned)
    if not checksum_valid:
        expected = verhoeff_generate(cleaned[:11])
        actual = int(cleaned[11])
        return {
            "valid": False,
            "checked": True,
            "reason": "CHECKSUM_FAIL",
            "message": (
                "Aadhaar number fails Verhoeff checksum. "
                f"Last digit should be {expected}, got {actual}. "
                "This number is invalid, forged, or has a digit transcription error."
            ),
            "expected_check_digit": expected,
            "actual_check_digit": actual,
            "algorithm": "Verhoeff (UIDAI)",
        }

    return {
        "valid": True,
        "checked": True,
        "reason": "VALID",
        "message": (
            "Aadhaar number passes all validation checks. Format is correct "
            "and Verhoeff checksum is valid."
        ),
        "aadhaar_last4": cleaned[-4:],
        "last4": cleaned[-4:],
        "masked": "XXXX XXXX " + cleaned[-4:],
        "algorithm": "Verhoeff (UIDAI)",
    }


# ─── BATCH VALIDATION ───────────────────

def validate_multiple(numbers: list) -> list:
    """Validate multiple Aadhaar numbers. Returns list of result dicts."""
    return [{"input": n, **validate_aadhaar_number(n)} for n in numbers]


# ─── SELF-TEST ───────────────────────────

def run_verhoeff_tests() -> bool:
    """
    Self-test with known valid and invalid Aadhaar numbers.
    Run at application startup to verify implementation is correct.

    Returns True if all tests pass.
    """
    tests = [
        ("234123412346", True, "Valid Aadhaar format"),
        ("2341 2341 2346", True, "Valid with spaces"),
        ("2341-2341-2346", True, "Valid with hyphens"),
        ("12345678901", False, "11 digits"),
        ("1234567890123", False, "13 digits"),
        ("", False, "Empty string"),
        ("023456789012", False, "Starts with 0"),
        ("123456789012", False, "Starts with 1"),
        ("234123412341", False, "Wrong check digit (6→1)"),
        ("234123412345", False, "Wrong check digit (6→5)"),
        ("333333333333", True, "All 3s — coincidentally valid checksum"),
        ("555555555555", False, "All 5s — invalid checksum"),
    ]

    all_passed = True
    for aadhaar, expected, description in tests:
        result = validate_aadhaar_number(aadhaar)
        passed = result["valid"] == expected

        if not passed:
            logger.error(
                "Verhoeff TEST FAIL: '%s' (%s) expected=%s, got=%s",
                aadhaar,
                description,
                expected,
                result["valid"],
            )
            all_passed = False
        else:
            logger.debug("Verhoeff test OK: %s", description)

    if all_passed:
        logger.info("✅ Verhoeff self-test: all %s tests passed", len(tests))
    else:
        logger.error("❌ Verhoeff self-test FAILED")

    return all_passed
