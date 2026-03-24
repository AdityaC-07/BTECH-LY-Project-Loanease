from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AssessRequest(BaseModel):
    gender: str = Field(..., examples=["Male"])
    married: str = Field(..., examples=["Yes"])
    dependents: str = Field(..., examples=["1"])
    education: str = Field(..., examples=["Graduate"])
    self_employed: str = Field(..., examples=["No"])
    applicant_income: float = Field(..., ge=0)
    coapplicant_income: float = Field(..., ge=0)
    loan_amount: float = Field(..., ge=0)
    loan_amount_term: float = Field(..., ge=0)
    credit_history: float = Field(..., ge=0)
    property_area: str = Field(..., examples=["Urban"])


class AssessResponse(BaseModel):
    application_id: str
    decision: Literal["APPROVED", "APPROVED_WITH_CONDITIONS", "REJECTED"]
    approval_probability: float
    risk_tier: Literal["Low Risk", "Medium Risk", "High Risk"]
    risk_score: int
    shap_explanation: list[str]
    threshold_used: float


class ExplainResponse(BaseModel):
    application_id: str
    decision: str
    approval_probability: float
    risk_tier: str
    risk_score: int
    threshold_used: float
    raw_input: dict
    top_explanations: list[str]
    shap_waterfall: list[dict]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    model_version: str
    accuracy: float
    uptime_seconds: int
