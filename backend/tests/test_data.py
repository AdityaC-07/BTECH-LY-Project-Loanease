from __future__ import annotations

from typing import Any, Dict

CIBIL_TIERS: Dict[str, Dict[str, Any]] = {
    "TIER_1_NH_NA": {
        "score": -1,
        "category": "New to Credit",
        "expected_decision": "CONDITIONAL_APPROVAL",
        "expected_rounds": 1,
        "min_rate": 14.0,
        "max_rate": 16.0,
    },
    "TIER_2_POOR": {
        "score": 450,
        "category": "Poor",
        "expected_decision": "REJECTED",
        "expected_rounds": 0,
        "min_rate": None,
        "max_rate": None,
    },
    "TIER_3_BELOW_AVG": {
        "score": 600,
        "category": "Below Average",
        "expected_decision": "CONDITIONAL_APPROVAL",
        "expected_rounds": 1,
        "min_rate": 16.0,
        "max_rate": 20.0,
    },
    "TIER_4_GOOD": {
        "score": 700,
        "category": "Good",
        "expected_decision": "APPROVED",
        "expected_rounds": 1,
        "min_rate": 13.0,
        "max_rate": 15.0,
    },
    "TIER_5_VERY_GOOD": {
        "score": 775,
        "category": "Very Good",
        "expected_decision": "APPROVED",
        "expected_rounds": 2,
        "min_rate": 11.5,
        "max_rate": 12.5,
    },
    "TIER_6_EXCELLENT": {
        "score": 850,
        "category": "Excellent",
        "expected_decision": "APPROVED",
        "expected_rounds": 3,
        "min_rate": 10.5,
        "max_rate": 11.5,
    },
}

CIBIL_BOUNDARY_CASES = [
    (549, "REJECTED", 0, "TIER_2_POOR"),
    (550, "CONDITIONAL_APPROVAL", 1, "TIER_3_BELOW_AVG"),
    (649, "CONDITIONAL_APPROVAL", 1, "TIER_3_BELOW_AVG"),
    (650, "APPROVED", 1, "TIER_4_GOOD"),
    (749, "APPROVED", 1, "TIER_4_GOOD"),
    (750, "APPROVED", 2, "TIER_5_VERY_GOOD"),
    (799, "APPROVED", 2, "TIER_5_VERY_GOOD"),
    (800, "APPROVED", 3, "TIER_6_EXCELLENT"),
    (900, "APPROVED", 3, "TIER_6_EXCELLENT"),
]

VALID_AADHAAR = "234123412346"
VALID_AADHAAR_2 = "333333333333"

TEST_PANS = ["ABCDE1234F", "AAAAA0000A", "DEMO00000D", "DEMO11111E", "DEMO22222F"]
