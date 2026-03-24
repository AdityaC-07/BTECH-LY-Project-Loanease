from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class StartNegotiationRequest(BaseModel):
    applicant_name: str
    risk_score: int = Field(..., ge=0, le=100)
    risk_tier: str
    loan_amount: int = Field(..., gt=0)
    tenure_months: int = Field(..., gt=0)
    top_positive_factor: str = "credit history"


class UnderwritingAssessPayload(BaseModel):
    gender: str
    married: str
    dependents: str
    education: str
    self_employed: str
    applicant_income: float
    coapplicant_income: float
    loan_amount: float
    loan_amount_term: float
    credit_history: float
    property_area: str


class StartFromUnderwritingRequest(BaseModel):
    applicant_name: str
    loan_amount: int = Field(..., gt=0)
    tenure_months: int = Field(..., gt=0)
    underwriting_base_url: str = "http://localhost:8000"
    assess_payload: UnderwritingAssessPayload


class StartFromUnderwritingResponse(BaseModel):
    session_id: str
    underwriting_assessment: dict
    opening_offer: OfferPayload
    reasoning: str
    can_negotiate: bool
    rounds_remaining: int
    negotiation_hint: str
    detected_intent: Literal["START"]


class OfferPayload(BaseModel):
    rate: float
    tenure_months: int
    loan_amount: int
    loan_amount_formatted: str
    emi: int
    emi_formatted: str
    total_payable: int
    total_payable_formatted: str
    total_interest: int
    total_interest_formatted: str
    savings_vs_opening: int | None = None
    savings_vs_opening_formatted: str | None = None


class StartNegotiationResponse(BaseModel):
    session_id: str
    opening_offer: OfferPayload
    reasoning: str
    can_negotiate: bool
    rounds_remaining: int
    negotiation_hint: str
    detected_intent: Literal["START"]


class CounterRequest(BaseModel):
    session_id: str
    applicant_message: str
    requested_rate: float | None = None


class CounterResponse(BaseModel):
    session_id: str
    counter_offer: OfferPayload
    reasoning: str
    rounds_remaining: int
    can_negotiate_further: bool
    status: str
    detected_intent: str


class AcceptRequest(BaseModel):
    session_id: str


class AcceptResponse(BaseModel):
    session_id: str
    final_offer: OfferPayload
    message: str
    sanction_reference: str
    status: Literal["completed", "expired"]
    detected_intent: Literal["ACCEPTANCE"]


class EscalateRequest(BaseModel):
    session_id: str
    reason: str = "applicant_requested"


class EscalateResponse(BaseModel):
    session_id: str
    message: str
    escalation_id: str
    status: Literal["escalated", "expired"]
    detected_intent: Literal["ESCALATION_REQUEST"]


class HistoryResponse(BaseModel):
    session_id: str
    status: str
    session: dict


class HealthResponse(BaseModel):
    status: Literal["ok"]
    uptime_seconds: int
    active_sessions: int
