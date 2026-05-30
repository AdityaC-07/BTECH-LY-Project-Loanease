"""
Verhoeff algorithm for Aadhaar 12-digit number validation.

Mathematical basis:
  - Dihedral group D5 multiplication table
  - Permutation table (position-based)
  - Inverse table for check digit

Last digit of Aadhaar is a Verhoeff check digit.
This catches:
  - Single digit errors (9/10 errors caught)
  - Adjacent transpositions (all caught)
  - Most twin errors and other patterns
"""

import re

# Verhoeff multiplication table
# Based on dihedral group D5
D = [
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

# Permutation table
# p(i, n) — position-based permutation
P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]

# Inverse table
INV = [0, 4, 3, 2, 1, 9, 8, 7, 6, 5]


def verhoeff_validate(number: str) -> bool:
    """
    Validate an Aadhaar number using the Verhoeff checksum algorithm.

    Returns True if number is valid.
    """
    digits = re.sub(r"\D", "", number)

    if len(digits) != 12:
        return False

    # Aadhaar cannot start with 0 or 1
    if digits[0] in ("0", "1"):
        return False

    c = 0
    for i, digit in enumerate(reversed(digits)):
        c = D[c][P[i % 8][int(digit)]]

    return c == 0


def verhoeff_get_check_digit(number: str) -> int:
    """
    Calculate the Verhoeff check digit for an 11-digit prefix.
    """
    digits = re.sub(r"\D", "", number)

    if len(digits) != 11:
        raise ValueError("Prefix must be 11 digits")

    c = 0
    for i, digit in enumerate(reversed(digits)):
        c = D[c][P[(i + 1) % 8][int(digit)]]

    return INV[c]


def validate_aadhaar_number(aadhaar: str) -> dict:
    """Complete Aadhaar number validation with detailed result output."""
    clean = re.sub(r"\D", "", aadhaar)

    if not clean:
        return {
            "valid": False,
            "reason": "EMPTY",
            "message": "No digits found",
        }

    if len(clean) != 12:
        return {
            "valid": False,
            "reason": "WRONG_LENGTH",
            "message": f"Expected 12 digits, got {len(clean)}",
            "digits_found": len(clean),
        }

    if clean[0] in ("0", "1"):
        return {
            "valid": False,
            "reason": "INVALID_START",
            "message": "Aadhaar cannot start with 0 or 1",
            "first_digit": clean[0],
        }

    checksum_valid = verhoeff_validate(clean)
    if not checksum_valid:
        return {
            "valid": False,
            "reason": "CHECKSUM_FAIL",
            "message": (
                "Verhoeff checksum validation failed. This number may be forged "
                "or have a transcription error."
            ),
            "algorithm": "Verhoeff (UIDAI)",
        }

    return {
        "valid": True,
        "reason": "VALID",
        "message": "Aadhaar number passes Verhoeff checksum validation",
        "algorithm": "Verhoeff (UIDAI)",
        "last4": clean[-4:],
        "masked": "XXXX XXXX " + clean[-4:],
    }
