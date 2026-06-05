#!/usr/bin/env python3
"""Unit tests for services/aadhaar_verhoeff.py — FA2 Aadhaar checksum validation."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.aadhaar_verhoeff import (
    run_verhoeff_tests,
    validate_aadhaar_number,
    validate_multiple,
    verhoeff_generate,
    verhoeff_get_check_digit,
    verhoeff_validate,
)


class TestVerhoeffCore(unittest.TestCase):
    def test_generate_and_validate_roundtrip(self):
        for prefix in ("23412341234", "29998887776", "24567890123"):
            check = verhoeff_generate(prefix)
            full = prefix + str(check)
            self.assertTrue(verhoeff_validate(full), msg=full)
            self.assertEqual(check, verhoeff_get_check_digit(prefix))

    def test_generate_rejects_wrong_prefix_length(self):
        with self.assertRaises(ValueError):
            verhoeff_generate("12345")

    def test_validate_rejects_non_digits(self):
        self.assertFalse(verhoeff_validate("abcdefghijkl"))


class TestAadhaarValidation(unittest.TestCase):
    VALID = "234123412346"

    def test_valid_number(self):
        result = validate_aadhaar_number(self.VALID)
        self.assertTrue(result["valid"])
        self.assertEqual(result["reason"], "VALID")
        self.assertEqual(result["aadhaar_last4"], "2346")
        self.assertEqual(result["last4"], "2346")
        self.assertEqual(result["masked"], "XXXX XXXX 2346")
        self.assertTrue(result["checked"])

    def test_valid_with_formatting(self):
        for value in ("2341 2341 2346", "2341-2341-2346", "2341.2341.2346"):
            result = validate_aadhaar_number(value)
            self.assertTrue(result["valid"], msg=value)

    def test_wrong_length(self):
        for value in ("", "123", "12345678901", "1234567890123"):
            result = validate_aadhaar_number(value)
            self.assertFalse(result["valid"])
            self.assertEqual(result["reason"], "WRONG_FORMAT")

    def test_invalid_first_digit(self):
        for value in ("023456789012", "123456789012"):
            result = validate_aadhaar_number(value)
            self.assertFalse(result["valid"])
            self.assertEqual(result["reason"], "INVALID_FIRST_DIGIT")

    def test_checksum_fail_includes_expected_digit(self):
        result = validate_aadhaar_number("234123412341")
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "CHECKSUM_FAIL")
        self.assertEqual(result["expected_check_digit"], 6)
        self.assertEqual(result["actual_check_digit"], 1)

    def test_all_threes_valid_checksum(self):
        result = validate_aadhaar_number("333333333333")
        self.assertTrue(result["valid"])

    def test_all_fives_invalid_checksum(self):
        result = validate_aadhaar_number("555555555555")
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "CHECKSUM_FAIL")

    def test_none_input(self):
        result = validate_aadhaar_number(None)
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "WRONG_FORMAT")

    def test_numeric_input(self):
        result = validate_aadhaar_number(234123412346)
        self.assertTrue(result["valid"])

    def test_letters_mixed_in(self):
        result = validate_aadhaar_number("2341ABCD2346")
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "WRONG_FORMAT")

    def test_single_digit_error_detected(self):
        mutated = "334123412346"
        result = validate_aadhaar_number(mutated)
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "CHECKSUM_FAIL")

    def test_adjacent_transposition_detected(self):
        transposed = "243123412346"
        result = validate_aadhaar_number(transposed)
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "CHECKSUM_FAIL")


class TestBatchValidation(unittest.TestCase):
    def test_validate_multiple(self):
        results = validate_multiple(["234123412346", "123"])
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0]["valid"])
        self.assertFalse(results[1]["valid"])


class TestSelfTest(unittest.TestCase):
    def test_run_verhoeff_tests_passes(self):
        self.assertTrue(run_verhoeff_tests())


if __name__ == "__main__":
    unittest.main()
