from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AssessRequest(BaseModel):
    pan_number: str = Field(..., description="PAN number (ABCDE1234F)", examples=["ABCDE1234F"])
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
    preferred_language: Literal["en", "hi"] = Field(default="en", description="Preferred language for messages")


class AssessResponse(BaseModel):
    application_id: str
    decision: Literal["APPROVED", "APPROVED_WITH_CONDITIONS", "REJECTED"]
    credit_score: int
    credit_score_out_of: int = 900
    credit_band: str
    credit_band_color: Literal["green", "yellow", "orange", "red"]
    risk_score: int
    risk_score_out_of: int = 100
    approval_probability: float
    risk_tier: Literal["Low Risk", "Medium Risk", "High Risk"]
    offered_rate: float = Field(..., description="Interest rate offered based on credit band")
    rate_range: dict = Field(..., description="Min/max rates for credit band")
    negotiation_allowed: bool
    max_negotiation_rounds: int
    xgboost_probability: float
    xgboost_ran: bool
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


class CreditScoreResponse(BaseModel):
    pan_number: str = Field(..., description="Masked PAN (first 5 + last 1 char)")
    credit_score: int
    credit_score_out_of: int = 900
    credit_band: str
    credit_band_color: Literal["green", "yellow", "orange", "red"]
    eligible_for_loan: bool
    score_breakdown: dict = Field(
        default={
            "excellent": "750-900",
            "good": "700-749",
            "fair": "550-699",
            "poor": "300-549",
            "ineligible": "Below 300",
        }
    )
    applicant_score_falls_in: str
    message_en: str
    message_hi: str
    minimum_required_score: int = 300
    shortfall: int | None = None
    improvement_tips: list[str] | None = None
    earliest_reapply: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    model_version: str
    accuracy: float
    uptime_seconds: int
