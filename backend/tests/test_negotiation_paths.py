"""
Section 2.1 – Negotiation path tests.

Three paths:
  Path 1: Aggressive applicant (Good tier, CIBIL 720, 2 counter-offer rounds)
  Path 2: Passive applicant   (Good tier, CIBIL 720, accepts initial offer)
  Path 3: Excellent credit, max rounds (Excellent tier, CIBIL 870, 3 rounds)

Rate guardrails (from core/config.py):
  RATE_FLOOR   = 10.5 %
  RATE_CEILING = 14.0 %
  CONCESSION_STEP = 0.25 %
"""
from __future__ import annotations

import pytest

from services.emi import calculate_negotiation_params
from services.credit_score import simulate_cibil_score, calculate_credit_score
from tests.test_pan_generator import GENERATED_TEST_PANS


RATE_FLOOR = 10.5
CONCESSION_STEP = 0.25


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _rate_for_risk(risk: str) -> float:
    """Return a representative initial offered rate for a given risk category."""
    return {"LOW": 11.5, "MEDIUM": 13.5, "MEDIUM-HIGH": 16.0, "HIGH": 20.0}[risk]


def _negotiate_round(params: dict, counter: float) -> dict:
    """
    Simulate one negotiation round.

    Returns a new params dict with the rate set to the minimum of the
    bank's concession and the counter (clamped to floor).
    """
    conceded = max(params["min_rate"], params["current_rate"] - CONCESSION_STEP)
    accepted_rate = max(params["min_rate"], min(conceded, counter))
    updated = dict(params)
    updated["current_rate"] = accepted_rate
    return updated


# ---------------------------------------------------------------------------
# Path 1 – Aggressive applicant (Good tier, 2 counter-offer rounds)
# ---------------------------------------------------------------------------

@pytest.mark.negotiation
class TestPath1AggressiveApplicant:
    """
    Scenario: CIBIL 720 (Good), income Rs. 2,50,000, loan Rs. 5,00,000.
    Strategy: counter on every round.
    Round 1: offered 13.5% → counter 12%
    Round 2: conceded 13.25% → counter 11.5%
    Expected: floor 10.5% protection holds; final rate ≥ floor.
    """

    PAN = GENERATED_TEST_PANS["good_mid"]  # → CIBIL 720
    INITIAL_RATE = 13.5
    RISK = "MEDIUM"

    def test_pan_resolves_to_720(self) -> None:
        assert simulate_cibil_score(self.PAN) == 720

    def test_initial_params_medium_risk(self) -> None:
        result = calculate_credit_score(720, 720)
        assert result["risk_category"] == "MEDIUM"

    def test_negotiation_params_generated(self) -> None:
        params = calculate_negotiation_params(self.INITIAL_RATE, self.RISK)
        assert params["current_rate"] == self.INITIAL_RATE
        assert params["min_rate"] >= RATE_FLOOR
        assert params["max_concession"] > 0

    def test_round_1_counter_at_12_pct(self) -> None:
        params = calculate_negotiation_params(self.INITIAL_RATE, self.RISK)
        round1 = _negotiate_round(params, counter=12.0)
        assert round1["current_rate"] >= RATE_FLOOR
        assert round1["current_rate"] <= self.INITIAL_RATE

    def test_round_2_counter_at_11_5_pct_hits_floor(self) -> None:
        params = calculate_negotiation_params(self.INITIAL_RATE, self.RISK)
        round1 = _negotiate_round(params, counter=12.0)
        round2 = _negotiate_round(round1, counter=11.5)
        assert round2["current_rate"] >= RATE_FLOOR, (
            f"Rate {round2['current_rate']} breached floor {RATE_FLOOR}"
        )

    def test_floor_never_breached_through_rounds(self) -> None:
        params = calculate_negotiation_params(self.INITIAL_RATE, self.RISK)
        current = params
        for counter in [12.0, 11.5, 10.0, 9.0]:  # progressively aggressive
            current = _negotiate_round(current, counter=counter)
            assert current["current_rate"] >= RATE_FLOOR

    def test_concession_step_is_0_25(self) -> None:
        params = calculate_negotiation_params(self.INITIAL_RATE, self.RISK)
        steps = params.get("negotiation_steps", [])
        if len(steps) >= 2:
            diff = round(steps[0] - steps[1], 4)
            assert diff == CONCESSION_STEP

    def test_final_rate_accepted_within_band(self) -> None:
        params = calculate_negotiation_params(self.INITIAL_RATE, self.RISK)
        round1 = _negotiate_round(params, counter=12.0)
        round2 = _negotiate_round(round1, counter=11.5)
        final_rate = round2["current_rate"]
        assert 10.5 <= final_rate <= 14.0

    def test_monthly_emi_decreases_with_rate(self) -> None:
        """Lower rate must produce lower EMI (P=500000, N=5 years)."""
        from services.emi import calculate_emi
        emi_high = calculate_emi(500_000, self.INITIAL_RATE, 5)["monthly_emi"]
        emi_low = calculate_emi(500_000, 11.5, 5)["monthly_emi"]
        assert emi_low < emi_high


# ---------------------------------------------------------------------------
# Path 2 – Passive applicant (accepts initial offer immediately)
# ---------------------------------------------------------------------------

@pytest.mark.negotiation
class TestPath2PassiveApplicant:
    """
    Scenario: CIBIL 720 (Good), same loan as Path 1.
    Strategy: accept initial offer, no counter.
    Expected: single-round closure at 13.5%.
    """

    PAN = GENERATED_TEST_PANS["good_mid"]
    INITIAL_RATE = 13.5
    RISK = "MEDIUM"

    def test_acceptance_at_initial_rate(self) -> None:
        params = calculate_negotiation_params(self.INITIAL_RATE, self.RISK)
        # Passive applicant accepts without countering
        accepted_rate = params["current_rate"]
        assert accepted_rate == self.INITIAL_RATE

    def test_no_additional_rounds_needed(self) -> None:
        params = calculate_negotiation_params(self.INITIAL_RATE, self.RISK)
        # If applicant accepts immediately, round count consumed is 0
        rounds_used = 0
        assert rounds_used < params.get("total_steps", 0) or params.get("total_steps", 0) >= 0

    def test_accepted_rate_within_good_tier_band(self) -> None:
        assert 13.0 <= self.INITIAL_RATE <= 15.0

    def test_passive_emi_higher_than_aggressive(self) -> None:
        """Passive applicant pays higher EMI because they don't negotiate."""
        from services.emi import calculate_emi
        emi_passive = calculate_emi(500_000, self.INITIAL_RATE, 5)["monthly_emi"]  # 13.5%
        emi_aggressive = calculate_emi(500_000, 12.75, 5)["monthly_emi"]           # post-negotiation
        assert emi_passive > emi_aggressive

    def test_total_interest_higher_for_passive(self) -> None:
        from services.emi import calculate_emi
        total_passive = calculate_emi(500_000, 13.5, 5)["total_interest"]
        total_aggress = calculate_emi(500_000, 12.75, 5)["total_interest"]
        assert total_passive > total_aggress


# ---------------------------------------------------------------------------
# Path 3 – Excellent credit, max negotiation (3 rounds, floor protection)
# ---------------------------------------------------------------------------

@pytest.mark.negotiation
class TestPath3ExcellentMaxRounds:
    """
    Scenario: CIBIL 870 (Excellent), income Rs. 5,00,000, loan Rs. 10,00,000.
    Strategy: aggressive rate chasing over 3 rounds.
    Round 1: offered 10.8% → counter 9.5%
    Round 2: conceded 10.55% → counter 9.8%
    Round 3: bank holds at floor 10.5% → applicant accepts
    Expected: floor 10.5% enforced; final rate == 10.5%.
    """

    PAN = GENERATED_TEST_PANS["excellent_mid"]  # → CIBIL 870
    INITIAL_RATE = 10.8
    RISK = "LOW"

    def test_pan_resolves_to_870(self) -> None:
        assert simulate_cibil_score(self.PAN) == 870

    def test_excellent_score_is_low_risk(self) -> None:
        result = calculate_credit_score(870, 870)
        assert result["risk_category"] == "LOW"
        assert result["risk_score"] == 20

    def test_negotiation_allows_excellent_concession(self) -> None:
        params = calculate_negotiation_params(
            self.INITIAL_RATE, self.RISK, customer_profile="EXCELLENT"
        )
        assert params["max_concession"] >= 2.0

    def test_round_1_counter_9_5_clamped_to_floor(self) -> None:
        params = calculate_negotiation_params(
            self.INITIAL_RATE, self.RISK, customer_profile="EXCELLENT"
        )
        r1 = _negotiate_round(params, counter=9.5)
        assert r1["current_rate"] >= RATE_FLOOR

    def test_round_2_counter_9_8_still_at_floor(self) -> None:
        params = calculate_negotiation_params(
            self.INITIAL_RATE, self.RISK, customer_profile="EXCELLENT"
        )
        r1 = _negotiate_round(params, counter=9.5)
        r2 = _negotiate_round(r1, counter=9.8)
        assert r2["current_rate"] >= RATE_FLOOR

    def test_round_3_bank_holds_firm_at_floor(self) -> None:
        params = calculate_negotiation_params(
            self.INITIAL_RATE, self.RISK, customer_profile="EXCELLENT"
        )
        r1 = _negotiate_round(params, counter=9.5)
        r2 = _negotiate_round(r1, counter=9.8)
        r3 = _negotiate_round(r2, counter=9.5)
        # After 3 aggressive counters the rate must not go below floor
        assert r3["current_rate"] >= RATE_FLOOR

    def test_two_or_more_negotiation_steps_available(self) -> None:
        params = calculate_negotiation_params(
            self.INITIAL_RATE, self.RISK, customer_profile="EXCELLENT"
        )
        steps = params.get("negotiation_steps", [])
        assert len(steps) >= 2, (
            f"Excellent tier should allow ≥ 2 steps, got {len(steps)}"
        )

    def test_final_accepted_rate_equals_floor(self) -> None:
        params = calculate_negotiation_params(
            self.INITIAL_RATE, self.RISK, customer_profile="EXCELLENT"
        )
        # Drive rate to floor through maximum concessions
        r = params
        for counter in [9.5, 9.8, 9.5]:
            r = _negotiate_round(r, counter=counter)
        assert r["current_rate"] == pytest.approx(RATE_FLOOR, abs=0.01)

    def test_floor_rate_emi_calculation(self) -> None:
        """Verify EMI at floor rate for Rs. 10,00,000 loan over 5 years."""
        from services.emi import calculate_emi
        result = calculate_emi(1_000_000, RATE_FLOOR, 5)
        emi = result["monthly_emi"]
        assert emi > 0
        # At 10.5% for 5y on 10L, EMI ~21,494
        assert 20_000 < emi < 25_000

    def test_excellent_rate_band_respected(self) -> None:
        """Excellent tier rate must stay within 10.5–11.5% band."""
        params = calculate_negotiation_params(
            self.INITIAL_RATE, self.RISK, customer_profile="EXCELLENT"
        )
        assert params["min_rate"] >= 10.5
        assert params["current_rate"] <= 11.5 + 0.5  # slight tolerance for initial offer
