from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.test_data import VALID_AADHAAR, VALID_AADHAAR_2, TEST_PANS


@pytest.fixture
def valid_aadhaar() -> str:
    return VALID_AADHAAR


@pytest.fixture
def valid_aadhaar_2() -> str:
    return VALID_AADHAAR_2


@pytest.fixture
def test_pans() -> list[str]:
    return TEST_PANS


@pytest.fixture
def sample_sanction_transaction() -> dict:
    return {
        "transaction_type": "SANCTION",
        "applicant_name": "Test Applicant",
        "pan_number": "ABCDE1234F",
        "loan_amount": 500000,
        "interest_rate": 11.5,
        "tenure_years": 5,
        "reference": "SANCTION-TEST-001",
    }


@pytest.fixture
def sample_loan_offer() -> dict:
    return {
        "loan_amount": 500000,
        "interest_rate": 13.0,
        "tenure_months": 60,
        "monthly_emi": 11376.54,
        "total_payable": 682592.40,
        "total_interest": 182592.40,
    }
