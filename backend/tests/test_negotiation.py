from __future__ import annotations

import pytest

from services.emi import calculate_negotiation_params


class TestNegotiationParams:
    @pytest.mark.parametrize("tier_key, tier_data", [
        ("TIER_4_GOOD", {"rate": 14.0, "risk": "LOW", "expected_min_rate": 12.5}),
        ("TIER_5_VERY_GOOD", {"rate": 12.0, "risk": "LOW", "expected_min_rate": 10.5}),
        ("TIER_3_BELOW_AVG", {"rate": 18.0, "risk": "MEDIUM", "expected_min_rate": 17.0}),
    ])
    def test_concession_calculation(self, tier_key, tier_data):
        result = calculate_negotiation_params(tier_data["rate"], tier_data["risk"])
        assert result["current_rate"] == tier_data["rate"]
        assert result["min_rate"] >= 10.5
        assert result["max_concession"] >= 0

    def test_high_risk_no_concession(self):
        result = calculate_negotiation_params(20.0, "HIGH")
        assert result["max_concession"] == 0.0
        assert result["min_rate"] == 20.0

    def test_medium_risk_limited_concession(self):
        result = calculate_negotiation_params(16.0, "MEDIUM")
        assert result["max_concession"] == 1.0
        assert result["total_steps"] >= 1

    def test_low_risk_max_concession(self):
        result = calculate_negotiation_params(14.0, "LOW")
        assert result["max_concession"] == 1.5
        assert result["total_steps"] >= 1

    def test_floor_rate_enforcement(self):
        result = calculate_negotiation_params(11.0, "LOW")
        assert result["min_rate"] >= 10.5

    def test_rate_never_below_floor(self):
        for risk in ["LOW", "MEDIUM", "MEDIUM-HIGH", "HIGH"]:
            result = calculate_negotiation_params(10.6, risk)
            assert result["min_rate"] >= 10.5

    def test_excellent_profile(self):
        result = calculate_negotiation_params(12.0, "LOW", customer_profile="EXCELLENT")
        assert result["max_concession"] >= 2.0

    def test_risky_profile(self):
        result = calculate_negotiation_params(15.0, "MEDIUM", customer_profile="RISKY")
        assert result["max_concession"] < 1.0

    def test_negotiation_steps_monotonic(self):
        result = calculate_negotiation_params(14.0, "LOW")
        steps = result["negotiation_steps"]
        for i in range(1, len(steps)):
            assert steps[i] < steps[i - 1], "Steps must be strictly decreasing"

    def test_negotiation_steps_within_bounds(self):
        result = calculate_negotiation_params(14.0, "LOW")
        steps = result["negotiation_steps"]
        for step in steps:
            assert result["min_rate"] <= step <= result["current_rate"]

    def test_medical_purpose_gets_extra_concession(self):
        result_medical = calculate_negotiation_params(14.0, "MEDIUM", purpose="medical")
        result_standard = calculate_negotiation_params(14.0, "MEDIUM")
        assert result_medical["max_concession"] > result_standard["max_concession"]

    def test_wedding_purpose(self):
        result = calculate_negotiation_params(14.0, "MEDIUM", purpose="wedding")
        assert result["max_concession"] > 0

    def test_debt_consolidation_purpose(self):
        result = calculate_negotiation_params(14.0, "MEDIUM", purpose="debt_consolidation")
        assert result["max_concession"] > 0


class TestCibilTierNegotiation:
    def test_tier_2_poor_no_negotiation(self):
        result = calculate_negotiation_params(20.0, "HIGH")
        assert result["max_concession"] == 0.0
        assert result["total_steps"] == 0

    def test_tier_3_below_avg_one_round(self):
        result = calculate_negotiation_params(18.0, "MEDIUM-HIGH")
        steps = result["negotiation_steps"]
        assert len(steps) <= 2

    def test_tier_4_good_one_round(self):
        result = calculate_negotiation_params(14.0, "MEDIUM")
        steps = result["negotiation_steps"]
        assert len(steps) >= 1

    def test_tier_5_very_good_two_rounds(self):
        result = calculate_negotiation_params(12.0, "LOW")
        steps = result["negotiation_steps"]
        assert len(steps) >= 2

    def test_tier_6_excellent_three_rounds(self):
        result = calculate_negotiation_params(10.5, "LOW", customer_profile="EXCELLENT")
        assert result["min_rate"] >= 10.5
        assert result["max_concession"] >= 2.0

    def test_concession_step_size(self):
        result = calculate_negotiation_params(14.0, "LOW")
        steps = result["negotiation_steps"]
        if len(steps) >= 2:
            diff = steps[0] - steps[1]
            assert diff == 0.25, "Each concession should be 0.25%"


class TestRateBandCompliance:
    def test_tier_4_rate_band(self):
        result = calculate_negotiation_params(14.0, "MEDIUM")
        assert result["min_rate"] >= 10.5
        assert result["current_rate"] <= 15.0

    def test_tier_5_rate_band(self):
        result = calculate_negotiation_params(12.0, "LOW")
        assert result["current_rate"] <= 12.5
        assert result["min_rate"] >= 10.5

    def test_tier_3_rate_band(self):
        result = calculate_negotiation_params(18.0, "MEDIUM-HIGH")
        assert result["current_rate"] >= 16.0
        assert result["current_rate"] <= 20.0

    def test_rate_reduction_consistency(self):
        result = calculate_negotiation_params(14.0, "LOW")
        steps = result["negotiation_steps"]
        if len(steps) >= 2:
            for i in range(1, len(steps)):
                assert steps[i - 1] - steps[i] == 0.25
