from __future__ import annotations

import pytest

from services.emi import calculate_emi, calculate_affordability


class TestCalculateEmi:
    def test_standard_emi_calculation(self):
        result = calculate_emi(500000, 13.0, 5)
        assert result["principal"] == 500000
        assert result["annual_rate"] == 13.0
        assert result["tenure_years"] == 5
        assert result["monthly_emi"] == 11376.54
        assert abs(result["total_payment"] - 682592.40) < 1
        assert abs(result["total_interest"] - 182592.40) < 1

    def test_zero_interest_rate(self):
        result = calculate_emi(100000, 0.0, 5)
        assert result["monthly_emi"] == 1666.67

    def test_small_loan(self):
        result = calculate_emi(50000, 10.5, 3)
        assert result["monthly_emi"] > 0
        assert result["total_interest"] > 0
        assert result["principal"] == 50000

    def test_large_loan(self):
        result = calculate_emi(2500000, 14.0, 7)
        assert result["monthly_emi"] > 0
        assert result["total_payment"] > result["principal"]
        assert result["tenure_years"] == 7

    def test_short_tenure(self):
        result = calculate_emi(100000, 12.0, 1)
        assert result["tenure_years"] == 1
        assert result["monthly_emi"] > 0

    def test_long_tenure(self):
        result = calculate_emi(500000, 11.5, 20)
        assert result["tenure_years"] == 20
        assert result["monthly_emi"] > 0
        assert result["total_interest"] > result["principal"]

    def test_high_interest_rate(self):
        result = calculate_emi(100000, 24.0, 5)
        assert result["monthly_emi"] > 0
        assert result["interest_rate_percentage"] > 0

    def test_integer_principal(self):
        result = calculate_emi(100000, 10.0, 5)
        assert isinstance(result["monthly_emi"], float)

    def test_rounding_accuracy(self):
        result = calculate_emi(1000000, 12.0, 5)
        monthly = result["monthly_emi"]
        total_payable = monthly * 60
        assert abs(total_payable - result["total_payment"]) < 0.5


class TestCalculateAffordability:
    def test_standard_affordability(self):
        result = calculate_affordability(100000)
        assert result["max_loan_amount"] > 0
        assert result["max_emi"] > 0
        assert result["affordable"] is True
        assert result["assumed_rate"] == 12.0
        assert result["assumed_tenure"] == 5

    def test_with_existing_emi(self):
        result = calculate_affordability(100000, existing_emi=20000)
        assert result["max_loan_amount"] > 0
        assert result["max_emi"] == 30000

    def test_low_income_not_affordable(self):
        result = calculate_affordability(5000)
        assert result["max_emi"] == 2500.0
        assert result["max_loan_amount"] > 0
        assert result["affordable"] is True

    def test_existing_emi_exceeds_threshold(self):
        result = calculate_affordability(50000, existing_emi=40000)
        assert result["affordable"] is False

    def test_high_income(self):
        result = calculate_affordability(500000)
        assert result["max_loan_amount"] > 1000000
        assert result["affordable"] is True

    def test_zero_income(self):
        result = calculate_affordability(0)
        assert result["max_loan_amount"] == 0

    def test_custom_dti_ratio(self):
        result = calculate_affordability(100000, max_dti_ratio=0.3)
        assert result["max_emi"] == 30000

    def test_max_dti_ratio_zero(self):
        result = calculate_affordability(100000, max_dti_ratio=0.0)
        assert result["max_loan_amount"] == 0
