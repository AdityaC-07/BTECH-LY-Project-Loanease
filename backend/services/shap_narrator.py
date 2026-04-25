from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Tuple

import numpy as np
import pandas as pd


FEATURE_LABEL_MAP: dict[str, str] = {
    "cibil_score": "CIBIL credit score",
    "monthly_income": "monthly income",
    "annual_income": "annual income",
    "loan_amount": "requested loan amount",
    "loan_to_income": "loan amount relative to income",
    "foir": "existing EMI burden (FOIR)",
    "dti": "debt-to-income ratio",
    "tenure": "loan tenure (months)",
    "tenure_months": "loan tenure (months)",
    "interest_rate": "interest rate expectation",
    "delinquency_count": "missed payments in the past",
    "account_age_months": "length of credit history",
    "credit_history": "repayment history quality",
    "open_accounts": "number of active credit lines",
    "secured_loan_ratio": "share of secured loans",
    "credit_utilization": "credit card utilization",
    "recent_inquiries": "recent credit inquiries",
    "employment_years": "years in current employment",
    "emp_type_A": "employment type (self-employed)",
    "emp_type_B": "employment type (salaried)",
    "emp_type_C": "employment type (business owner)",
    "residence_stability_months": "residence stability",
    "savings_balance": "average savings balance",
    "emi_obligations": "current EMI obligations",
    "coapplicant_income": "co-applicant income",
    "property_area_Urban": "property area (urban)",
    "property_area_Semiurban": "property area (semi-urban)",
    "property_area_Rural": "property area (rural)",
    "self_employed_Yes": "self-employed status",
    "education_Graduate": "education level (graduate)",
}

ACTIONABLE_FEATURES: list[str] = [
    "cibil_score",
    "monthly_income",
    "foir",
    "loan_amount",
    "tenure",
]

_ACTIONABLE_BOUNDS: dict[str, Tuple[float, float]] = {
    "cibil_score": (300.0, 900.0),
    "monthly_income": (5000.0, 2_000_000.0),
    "foir": (0.0, 100.0),
    "loan_amount": (10_000.0, 100_000_000.0),
    "tenure": (6.0, 480.0),
}

_ACTIONABLE_STEPS: dict[str, Iterable[float]] = {
    "cibil_score": [10, 20, 30, 40, 50, 70, 100],
    "monthly_income": [5000, 10000, 20000, 30000, 50000, 75000, 100000],
    "foir": [2, 4, 6, 8, 10, 12, 15],
    "loan_amount": [25000, 50000, 100000, 200000, 300000, 500000, 750000],
    "tenure": [6, 12, 18, 24, 36, 48, 60],
}


@dataclass
class _CandidateChange:
    feature: str
    original: float
    updated: float
    delta: float
    score_after: float


def _human_label(feature_name: str) -> str:
    return FEATURE_LABEL_MAP.get(feature_name, feature_name.replace("_", " "))


def format_shap_for_prompt(shap_values: dict[str, float], top_n: int = 5) -> str:
    """Format top-N SHAP contributors into a prompt-ready numbered list."""
    if not shap_values:
        return "1. Feature: data unavailable, Direction: neutral, Magnitude: 0.00"

    ranked = sorted(
        shap_values.items(),
        key=lambda kv: abs(float(kv[1])),
        reverse=True,
    )[: max(1, top_n)]

    lines: list[str] = []
    for idx, (feature, raw_value) in enumerate(ranked, start=1):
        value = float(raw_value)
        direction = "positive" if value >= 0 else "negative"
        lines.append(
            f"{idx}. Feature: {_human_label(feature)}, Direction: {direction}, Magnitude: {abs(value):.2f}"
        )
    return "\n".join(lines)


def _score_profile(model: Any, profile: dict[str, Any]) -> float:
    """
    Compute approval probability for a single profile.

    Supports models with either `predict_proba` or `predict`.
    """
    frame = pd.DataFrame([profile])
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(frame)
        # Binary classifier assumed; use probability of positive class.
        return float(proba[0][1]) if np.ndim(proba) > 1 else float(proba[0])

    pred = model.predict(frame)
    return float(pred[0])


def _preferred_direction(feature: str, favor_approval: bool) -> int:
    """
    Direction for actionable movement.
    +1 means increase, -1 means decrease.
    """
    if feature in {"cibil_score", "monthly_income", "tenure"}:
        return 1 if favor_approval else -1
    if feature in {"foir", "loan_amount"}:
        return -1 if favor_approval else 1
    return 1


def _bounded(value: float, feature: str) -> float:
    low, high = _ACTIONABLE_BOUNDS[feature]
    return float(min(max(value, low), high))


def generate_counterfactual(shap_values: dict, profile: dict, model: Any) -> str:
    """
    Find the smallest actionable feature change likely to flip the model decision.
    """
    if not profile or model is None:
        return "Counterfactual unavailable: profile or model is missing."

    score_now = _score_profile(model, profile)
    current_label = 1 if score_now >= 0.5 else 0

    # Primary use-case is helping a rejected applicant qualify.
    if current_label == 1:
        return (
            "Applicant is already likely approved. To improve terms further, reduce FOIR or request a slightly lower loan amount."
        )

    best: _CandidateChange | None = None
    target_label = 1

    for feature in ACTIONABLE_FEATURES:
        if feature not in profile:
            continue
        try:
            base = float(profile[feature])
        except (TypeError, ValueError):
            continue

        direction = _preferred_direction(feature, favor_approval=True)
        for step in _ACTIONABLE_STEPS[feature]:
            candidate_value = _bounded(base + (direction * float(step)), feature)
            if candidate_value == base:
                continue

            candidate_profile = dict(profile)
            candidate_profile[feature] = candidate_value
            score_after = _score_profile(model, candidate_profile)
            label_after = 1 if score_after >= 0.5 else 0

            if label_after != target_label:
                continue

            delta = abs(candidate_value - base)
            if best is None or delta < best.delta:
                best = _CandidateChange(
                    feature=feature,
                    original=base,
                    updated=candidate_value,
                    delta=delta,
                    score_after=score_after,
                )

    if best is None:
        return (
            "No single actionable change was sufficient to flip the decision. A combined improvement in CIBIL score and FOIR is recommended."
        )

    feature_label = _human_label(best.feature)
    if best.feature == "loan_amount":
        return (
            f"If your {feature_label} were {int(best.updated):,} instead of {int(best.original):,}, "
            "the model indicates your approval chances would likely cross the threshold."
        )
    if best.feature == "monthly_income":
        return (
            f"If your {feature_label} were {int(best.updated):,} instead of {int(best.original):,}, "
            "you would likely qualify for a stronger approval outcome."
        )
    return (
        f"If your {feature_label} were {best.updated:.0f} instead of {best.original:.0f}, "
        "the decision would likely flip to approved."
    )


def _profile_summary(profile: dict[str, Any]) -> str:
    if not profile:
        return "No applicant profile details available."
    keys_of_interest = [
        "cibil_score",
        "monthly_income",
        "loan_amount",
        "foir",
        "tenure",
        "employment_type",
    ]
    parts: list[str] = []
    for key in keys_of_interest:
        if key in profile:
            parts.append(f"{_human_label(key)}: {profile[key]}")
    if not parts:
        for key, value in list(profile.items())[:6]:
            parts.append(f"{_human_label(key)}: {value}")
    return "; ".join(parts)


def build_shap_context_for_prompt(
    shap_values: dict,
    decision: str,
    profile: dict,
    model: Any,
) -> dict:
    """Build prompt context block for UNDERWRITING_SYSTEM_PROMPT injection."""
    credit_score = profile.get("cibil_score") or profile.get("credit_score")
    return {
        "shap_summary": format_shap_for_prompt(shap_values, top_n=5),
        "counterfactual": generate_counterfactual(shap_values, profile, model),
        "decision": decision,
        "credit_score": credit_score,
        "profile_summary": _profile_summary(profile),
    }

