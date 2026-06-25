from __future__ import annotations

import pytest

from services.aadhaar_verhoeff import (
    run_verhoeff_tests,
    validate_aadhaar_number,
    validate_multiple,
    verhoeff_generate,
    verhoeff_get_check_digit,
    verhoeff_validate,
)


class TestVerhoeffCore:
    def test_generate_and_validate_roundtrip(self):
        prefixes = ["23412341234", "29998887776", "24567890123"]
        for prefix in prefixes:
            check = verhoeff_generate(prefix)
            full = prefix + str(check)
            assert verhoeff_validate(full), f"Failed for prefix {prefix}"
            assert check == verhoeff_get_check_digit(prefix)

    def test_generate_rejects_wrong_length(self):
        with pytest.raises(ValueError):
            verhoeff_generate("12345")
        with pytest.raises(ValueError):
            verhoeff_generate("")
        with pytest.raises(ValueError):
            verhoeff_generate("123456789012")

    def test_validate_rejects_non_digits(self):
        assert not verhoeff_validate("abcdefghijkl")
        assert not verhoeff_validate("")
        assert not verhoeff_validate("   ")

    def test_validate_single_number(self):
        assert verhoeff_validate("0")
        assert not verhoeff_validate("1")

    def test_validate_large_number(self):
        assert verhoeff_validate("12345678901234567895")


class TestAadhaarValidation:
    VALID = "234123412346"

    def test_valid_number(self):
        result = validate_aadhaar_number(self.VALID)
        assert result["valid"]
        assert result["reason"] == "VALID"
        assert result["aadhaar_last4"] == "2346"
        assert result["masked"] == "XXXX XXXX 2346"

    def test_valid_with_formatting(self):
        formatted = ["2341 2341 2346", "2341-2341-2346", "2341.2341.2346"]
        for value in formatted:
            result = validate_aadhaar_number(value)
            assert result["valid"], f"Failed for {value}"

    def test_wrong_length(self):
        cases = ["", "123", "12345678901", "1234567890123"]
        for value in cases:
            result = validate_aadhaar_number(value)
            assert not result["valid"]
            assert result["reason"] == "WRONG_FORMAT"

    def test_invalid_first_digit(self):
        cases = ["023456789012", "123456789012"]
        for value in cases:
            result = validate_aadhaar_number(value)
            assert not result["valid"]
            assert result["reason"] == "INVALID_FIRST_DIGIT"

    def test_checksum_fail_includes_expected_digit(self):
        result = validate_aadhaar_number("234123412341")
        assert not result["valid"]
        assert result["reason"] == "CHECKSUM_FAIL"
        assert result["expected_check_digit"] == 6
        assert result["actual_check_digit"] == 1

    def test_checksum_fail_message(self):
        result = validate_aadhaar_number("234123412341")
        assert "Verhoeff" in result["message"]
        assert "6" in result["message"]
        assert "1" in result["message"]

    def test_all_threes_valid_checksum(self):
        result = validate_aadhaar_number("333333333333")
        assert result["valid"]

    def test_all_fives_invalid_checksum(self):
        result = validate_aadhaar_number("555555555555")
        assert not result["valid"]
        assert result["reason"] == "CHECKSUM_FAIL"

    def test_none_input(self):
        result = validate_aadhaar_number(None)
        assert not result["valid"]
        assert result["reason"] == "WRONG_FORMAT"

    def test_numeric_input(self):
        result = validate_aadhaar_number(234123412346)
        assert result["valid"]

    def test_letters_mixed_in(self):
        result = validate_aadhaar_number("2341ABCD2346")
        assert not result["valid"]
        assert result["reason"] == "WRONG_FORMAT"

    def test_single_digit_error_detected(self):
        mutated = "334123412346"
        result = validate_aadhaar_number(mutated)
        assert not result["valid"]
        assert result["reason"] == "CHECKSUM_FAIL"

    def test_adjacent_transposition_detected(self):
        transposed = "243123412346"
        result = validate_aadhaar_number(transposed)
        assert not result["valid"]
        assert result["reason"] == "CHECKSUM_FAIL"


class TestValidateMultiple:
    def test_multiple_valid(self):
        results = validate_multiple(["234123412346", "333333333333"])
        assert len(results) == 2
        assert all(r["valid"] for r in results)

    def test_mixed_validity(self):
        results = validate_multiple(["234123412346", "123"])
        assert len(results) == 2
        assert results[0]["valid"]
        assert not results[1]["valid"]

    def test_empty_list(self):
        results = validate_multiple([])
        assert results == []

    def test_invalid_inputs(self):
        results = validate_multiple(["", None, "abc", "023456789012"])
        assert all(not r["valid"] for r in results)


class TestSelfTest:
    def test_run_verhoeff_tests_passes(self):
        assert run_verhoeff_tests()
