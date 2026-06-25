from __future__ import annotations

import pytest

from services.conversation_context import (
    validate_income,
    validate_loan_amount,
    calculate_emi,
    determine_eligibility_status,
    extract_applicant_name,
    extract_loan_amount,
    extract_loan_purpose,
)


class TestValidateIncome:
    def test_valid_income(self):
        result = validate_income(50000)
        assert result["valid"] is True
        assert result["field"] == "income"

    def test_income_below_minimum(self):
        result = validate_income(5000)
        assert result["valid"] is False
        assert "10,000" in result["error"]

    def test_income_at_minimum(self):
        result = validate_income(10000)
        assert result["valid"] is True

    def test_income_at_maximum(self):
        result = validate_income(2000000)
        assert result["valid"] is True

    def test_income_above_maximum(self):
        result = validate_income(2500000)
        assert result["valid"] is False
        assert "2,000,000" in result["error"]

    def test_zero_income(self):
        result = validate_income(0)
        assert result["valid"] is False

    def test_negative_income(self):
        result = validate_income(-5000)
        assert result["valid"] is False

    def test_none_income(self):
        result = validate_income(None)  # type: ignore
        assert result["valid"] is False


class TestValidateLoanAmount:
    def test_valid_loan_amount(self):
        result = validate_loan_amount(500000, 50000)
        assert result["valid"] is True
        assert result["max_eligible"] == 750000

    def test_loan_below_minimum(self):
        result = validate_loan_amount(25000, 50000)
        assert result["valid"] is False
        assert "50,000" in result["error"]

    def test_loan_at_minimum(self):
        result = validate_loan_amount(50000, 50000)
        assert result["valid"] is True

    def test_loan_exceeds_income_cap(self):
        result = validate_loan_amount(1000000, 50000)
        assert result["valid"] is False
        assert "15x" in result["error"]

    def test_loan_at_income_cap(self):
        result = validate_loan_amount(750000, 50000)
        assert result["valid"] is True

    def test_loan_without_income(self):
        result = validate_loan_amount(500000)
        assert result["valid"] is True
        assert result["max_eligible"] == 2500000

    def test_loan_exceeds_absolute_max(self):
        result = validate_loan_amount(3000000, 500000)
        assert result["valid"] is False

    def test_high_income_large_loan(self):
        result = validate_loan_amount(2000000, 200000)
        assert result["valid"] is True

    def test_zero_loan(self):
        result = validate_loan_amount(0, 50000)
        assert result["valid"] is False

    def test_none_loan(self):
        result = validate_loan_amount(None, 50000)  # type: ignore
        assert result["valid"] is False


class TestCalculateEmiHelper:
    def test_standard_calculation(self):
        emi = calculate_emi(500000, 13.0, 60)
        assert abs(emi - 11376.54) < 1

    def test_zero_rate(self):
        emi = calculate_emi(100000, 0.0, 60)
        assert round(emi, 2) == 1666.67

    def test_short_tenure(self):
        emi = calculate_emi(100000, 12.0, 12)
        assert emi > 0

    def test_small_amount(self):
        emi = calculate_emi(1000, 10.0, 12)
        assert emi > 0

    def test_large_amount(self):
        emi = calculate_emi(10000000, 15.0, 240)
        assert emi > 0
        assert emi < 1000000


class TestDetermineEligibilityStatus:
    def test_strong_eligibility(self):
        status = determine_eligibility_status(11250, 50000, 500000)
        assert status["status"] == "STRONG"

    def test_moderate_eligibility(self):
        status = determine_eligibility_status(27500, 50000, 600000)
        assert status["status"] == "MODERATE"

    def test_weak_eligibility(self):
        status = determine_eligibility_status(40000, 50000, 1000000)
        assert status["status"] == "WEAK"

    def test_zero_income(self):
        status = determine_eligibility_status(0, 0, 0)
        assert status["status"] == "WEAK"

    def test_low_emi_ratio_strong(self):
        status = determine_eligibility_status(5000, 100000, 500000)
        assert status["status"] == "STRONG"

    def test_boundary_50_percent(self):
        status = determine_eligibility_status(25000, 50000, 750000)
        assert status["status"] == "STRONG"

    def test_boundary_60_percent(self):
        status = determine_eligibility_status(30000, 50000, 600000)
        assert status["status"] == "MODERATE"


class TestExtractApplicantName:
    def test_extract_my_name_is(self):
        name = extract_applicant_name("my name is John Doe")
        assert name == "John Doe"

    def test_extract_i_am(self):
        name = extract_applicant_name("I am Jane Smith")
        assert name == "Jane Smith"

    def test_extract_i_am_contraction(self):
        name = extract_applicant_name("I'm Bob Wilson")
        assert name == "Bob Wilson"

    def test_extract_hindi(self):
        name = extract_applicant_name("mera naam Rahul Kumar")
        assert name == "Rahul Kumar"

    def test_existing_name_returned(self):
        name = extract_applicant_name("some message", existing_name="Existing Name")
        assert name == "Existing Name"

    def test_no_name_in_message(self):
        name = extract_applicant_name("I want a loan")
        assert name is None

    def test_empty_message(self):
        name = extract_applicant_name("")
        assert name is None

    def test_name_with_loan_context(self):
        name = extract_applicant_name("my name is Priya Sharma and I want a loan")
        assert name == "Priya Sharma And I"


class TestExtractLoanAmount:
    def test_simple_number(self):
        amount = extract_loan_amount("I need 500000")
        assert amount == 500000

    def test_with_rupee_symbol(self):
        amount = extract_loan_amount("I need ₹500000")
        assert amount == 500000

    def test_in_lakhs(self):
        amount = extract_loan_amount("I need 5 lakhs")
        assert amount == 500000

    def test_in_crores(self):
        amount = extract_loan_amount("need 2 crore")
        assert amount == 20000000

    def test_in_thousands(self):
        amount = extract_loan_amount("need 50 thousand")
        assert amount == 50000

    def test_with_commas(self):
        amount = extract_loan_amount("need 5,00,000")
        assert amount == 500000

    def test_no_amount(self):
        amount = extract_loan_amount("I want a loan")
        assert amount is None

    def test_empty_message(self):
        amount = extract_loan_amount("")
        assert amount is None


class TestExtractLoanPurpose:
    def test_medical(self):
        purpose = extract_loan_purpose("need for medical treatment")
        assert purpose == "medical"

    def test_wedding(self):
        purpose = extract_loan_purpose("loan for my wedding")
        assert purpose == "wedding"

    def test_education(self):
        purpose = extract_loan_purpose("college fees payment")
        assert purpose == "education"

    def test_business(self):
        purpose = extract_loan_purpose("expand my business")
        assert purpose == "business"

    def test_home_renovation(self):
        purpose = extract_loan_purpose("home renovation")
        assert purpose == "home_renovation"

    def test_debt_consolidation(self):
        purpose = extract_loan_purpose("consolidate my debt")
        assert purpose == "debt_consolidation"

    def test_travel(self):
        purpose = extract_loan_purpose("travel vacation trip")
        assert purpose == "travel"

    def test_unknown_purpose(self):
        purpose = extract_loan_purpose("I want some money")
        assert purpose is None
