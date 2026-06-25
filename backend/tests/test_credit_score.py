from __future__ import annotations

import hashlib

import pytest

from services.credit_score import simulate_cibil_score, calculate_credit_score
from tests.test_data import CIBIL_TIERS, CIBIL_BOUNDARY_CASES, TEST_PANS


class TestSimulateCibilScore:
    def test_deterministic_same_pan(self):
        score_1 = simulate_cibil_score("ABCDE1234F")
        score_2 = simulate_cibil_score("ABCDE1234F")
        assert score_1 == score_2, "CIBIL score must be deterministic for same PAN"

    def test_different_pans_different_scores(self):
        scores = {simulate_cibil_score(pan) for pan in TEST_PANS}
        assert len(scores) >= 2, "Different PANs should produce different scores"

    def test_score_in_range(self):
        for pan in TEST_PANS:
            score = simulate_cibil_score(pan)
            assert 300 <= score <= 900, f"Score {score} for {pan} out of range [300, 900]"

    def test_empty_pan_returns_random(self):
        score = simulate_cibil_score("")
        assert 300 <= score <= 900

    def test_none_pan_returns_random(self):
        score = simulate_cibil_score(None)  # type: ignore
        assert 300 <= score <= 900

    def test_score_formula_correctness(self):
        pan = "ABCDE1234F"
        pan_hash = hashlib.md5(pan.encode()).hexdigest()
        hash_num = int(pan_hash[:8], 16)
        expected_score = 300 + (hash_num % 601)
        actual_score = simulate_cibil_score(pan)
        assert actual_score == expected_score, f"Expected {expected_score}, got {actual_score}"

    def test_lowercase_pan_produces_same_score(self):
        upper_score = simulate_cibil_score("ABCDE1234F")
        lower_score = simulate_cibil_score("abcde1234f")
        assert upper_score == lower_score, "Score should be case-insensitive"


class TestCalculateCreditScore:
    def test_high_score_low_risk(self):
        result = calculate_credit_score(800, 750)
        assert result["risk_category"] == "LOW"
        assert result["risk_score"] == 20
        assert not result["hard_reject"]
        assert 300 <= result["final_score"] <= 900

    def test_medium_score_medium_risk(self):
        result = calculate_credit_score(720, 680)
        assert result["risk_category"] == "MEDIUM"
        assert result["risk_score"] == 40

    def test_medium_high_score(self):
        result = calculate_credit_score(670, 630)
        assert result["risk_category"] == "MEDIUM-HIGH"
        assert result["risk_score"] == 60

    def test_low_score_high_risk(self):
        result = calculate_credit_score(400, 350)
        assert result["risk_category"] == "HIGH"
        assert result["risk_score"] == 80

    def test_hard_reject_threshold(self):
        result = calculate_credit_score(250, 250)
        assert result["final_score"] == 300
        assert result["risk_category"] == "HIGH"
        assert result["hard_reject"] is False

    def test_boundary_750_low_risk(self):
        result = calculate_credit_score(750, 750)
        assert result["risk_category"] == "LOW"

    def test_boundary_700_medium_risk(self):
        result = calculate_credit_score(700, 700)
        assert result["risk_category"] == "MEDIUM"

    def test_boundary_650_medium_high_risk(self):
        result = calculate_credit_score(650, 650)
        assert result["risk_category"] == "MEDIUM-HIGH"

    def test_boundary_649_high_risk(self):
        result = calculate_credit_score(649, 649)
        assert result["risk_category"] == "HIGH"

    def test_final_score_clamped(self):
        result = calculate_credit_score(100, 100)
        assert result["final_score"] >= 300

    def test_final_score_clamped_upper(self):
        result = calculate_credit_score(950, 950)
        assert result["final_score"] <= 900

    def test_xgboost_weight_applied(self):
        result = calculate_credit_score(500, 500)
        expected = int(500 * 0.60 + 500 * 0.40)
        assert result["final_score"] == expected

    def test_zero_cibil_score(self):
        result = calculate_credit_score(0, 500)
        assert result["final_score"] >= 300


class TestCibilTierClassification:
    @pytest.mark.parametrize("tier_key, tier_data", list(CIBIL_TIERS.items()))
    def test_tier_decision_mapping(self, tier_key, tier_data):
        score = tier_data["score"]
        if score < 0:
            pytest.skip("NH/NA tier requires special handling")
        result = calculate_credit_score(score, score)
        if score >= 750:
            assert not result["hard_reject"]
        elif score >= 650:
            assert not result["hard_reject"]
        elif score >= 550:
            assert not result["hard_reject"]
        else:
            assert result["hard_reject"] or result["risk_category"] == "HIGH"

    @pytest.mark.parametrize("score, expected_decision, expected_rounds, tier_name", CIBIL_BOUNDARY_CASES)
    def test_boundary_values(self, score, expected_decision, expected_rounds, tier_name):
        result = calculate_credit_score(score, score)
        if expected_decision == "REJECTED":
            assert result["risk_category"] == "HIGH"
        else:
            assert result["hard_reject"] is False

        final = result["final_score"]
        if final < 650:
            assert result["risk_category"] == "HIGH"
        elif final < 700:
            assert result["risk_category"] == "MEDIUM-HIGH"
        elif final < 750:
            assert result["risk_category"] == "MEDIUM"
        else:
            assert result["risk_category"] == "LOW"
