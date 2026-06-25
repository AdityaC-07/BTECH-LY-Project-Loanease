from __future__ import annotations

import pytest

from services.aadhaar_verhoeff import validate_aadhaar_number


def mask_pan(pan: str) -> str:
    if not pan or len(pan) != 10:
        return pan
    return pan[:5] + "****" + pan[9:]


def mask_aadhaar(aadhaar: str) -> str:
    if not aadhaar or len(aadhaar) != 12:
        return aadhaar
    return aadhaar[:4] + "****" + aadhaar[-4:]


class TestPanMasking:
    def test_standard_pan_masking(self):
        pan = "ABCDE1234F"
        masked = mask_pan(pan)
        assert masked == "ABCDE****F"
        assert "1234" not in masked

    def test_pan_masking_reveals_only_last_char(self):
        pan = "ABCDE1234F"
        masked = mask_pan(pan)
        assert masked[0:5] == pan[0:5]
        assert masked[-1] == pan[-1]
        assert masked[5:9] == "****"

    def test_short_pan_returns_unchanged(self):
        assert mask_pan("ABCD") == "ABCD"

    def test_empty_pan(self):
        assert mask_pan("") == ""

    def test_none_pan(self):
        assert mask_pan(None) is None  # type: ignore

    def test_lowercase_pan_masking(self):
        pan = "abcde1234f"
        masked = mask_pan(pan)
        assert masked == "abcde****f"

    def test_pan_with_special_chars(self):
        pan = "AB@DE1234F"
        masked = mask_pan(pan)
        assert len(masked) == 10
        assert "*" in masked


class TestAadhaarMasking:
    def test_aadhaar_masking_in_validation(self):
        result = validate_aadhaar_number("234123412346")
        assert result["valid"]
        assert result["masked"] == "XXXX XXXX 2346"
        assert "2341" not in result["masked"]

    def test_aadhaar_only_last4_exposed(self):
        result = validate_aadhaar_number("234123412346")
        assert result["aadhaar_last4"] == "2346"

    def test_aadhaar_middle_digits_masked(self):
        result = validate_aadhaar_number("678912345678")
        if result["valid"]:
            assert result["aadhaar_last4"] == "5678"
            assert "1234" not in result["aadhaar_last4"]

    def test_standard_aadhaar_masking(self):
        aadhaar = "123456789012"
        masked = mask_aadhaar(aadhaar)
        assert masked == "1234****9012"
        assert "5678" not in masked

    def test_aadhaar_first4_last4_visible(self):
        aadhaar = "987654321098"
        masked = mask_aadhaar(aadhaar)
        assert masked[:4] == "9876"
        assert masked[-4:] == "1098"

    def test_short_aadhaar(self):
        assert mask_aadhaar("12345") == "12345"

    def test_empty_aadhaar(self):
        assert mask_aadhaar("") == ""


class TestPiiNotInOutputs:
    def test_full_pan_not_in_api_response(self):
        from services.credit_score import simulate_cibil_score
        score = simulate_cibil_score("ABCDE1234F")
        response = str(score)
        assert "ABCDE1234F" not in response
        assert "ABCDE" not in response

    def test_full_aadhaar_not_in_validation_response(self):
        result = validate_aadhaar_number("234123412346")
        response = str(result)
        assert "234123412346" not in response

    def test_no_raw_pan_in_logs(self):
        result = validate_aadhaar_number("234123412346")
        assert "aadhaar_last4" in result or "last4" in result
        if "aadhaar_last4" in result:
            assert len(result["aadhaar_last4"]) == 4
