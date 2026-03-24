from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx

from app.constants import MAX_ROUNDS
from app.schemas import (
    AcceptRequest,
    AcceptResponse,
    CounterRequest,
    CounterResponse,
    EscalateRequest,
    EscalateResponse,
    HealthResponse,
    HistoryResponse,
    StartFromUnderwritingRequest,
    StartFromUnderwritingResponse,
    StartNegotiationRequest,
    StartNegotiationResponse,
)
from app.service import (
    append_history,
    build_escalation_reference,
    build_offer,
    build_sanction_reference,
    counter_session,
    extract_top_positive_factor,
    start_session,
)
from app.store import SessionStore

app = FastAPI(title="LoanEase Dynamic Negotiation API", version="1.0.0")

frontend_domain = os.getenv("FRONTEND_DOMAIN", "https://loanease.example.com")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:3000",
        frontend_domain,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

store = SessionStore()
boot_time = datetime.now(timezone.utc)


@app.post("/negotiate/start", response_model=StartNegotiationResponse)
def negotiate_start(payload: StartNegotiationRequest) -> StartNegotiationResponse:
    session = start_session(payload.model_dump())
    store.create(session)

    rounds_remaining = max(0, MAX_ROUNDS - session["rounds_completed"])

    return StartNegotiationResponse(
        session_id=session["session_id"],
        opening_offer=session["opening_offer"],
        reasoning=session["history"][0]["reasoning"],
        can_negotiate=session["can_negotiate"],
        rounds_remaining=rounds_remaining,
        negotiation_hint="You may request a rate reduction. Our system will evaluate your profile and respond.",
        detected_intent="START",
    )


@app.post("/negotiate/start-from-underwriting", response_model=StartFromUnderwritingResponse)
def negotiate_start_from_underwriting(payload: StartFromUnderwritingRequest) -> StartFromUnderwritingResponse:
    base_url = payload.underwriting_base_url.rstrip("/")
    assess_url = f"{base_url}/assess"

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(assess_url, json=payload.assess_payload.model_dump())
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Unable to reach underwriting service at {assess_url}") from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Underwriting service returned {response.status_code}: {response.text}",
        )

    assessment = response.json()
    risk_score = int(assessment.get("risk_score", 0))
    risk_tier = str(assessment.get("risk_tier", "Medium"))
    top_positive_factor = extract_top_positive_factor(assessment.get("shap_explanation"))

    session = start_session(
        {
            "applicant_name": payload.applicant_name,
            "risk_score": risk_score,
            "risk_tier": risk_tier,
            "loan_amount": payload.loan_amount,
            "tenure_months": payload.tenure_months,
            "top_positive_factor": top_positive_factor,
        }
    )
    store.create(session)
    rounds_remaining = max(0, MAX_ROUNDS - session["rounds_completed"])

    return StartFromUnderwritingResponse(
        session_id=session["session_id"],
        underwriting_assessment=assessment,
        opening_offer=session["opening_offer"],
        reasoning=session["history"][0]["reasoning"],
        can_negotiate=session["can_negotiate"],
        rounds_remaining=rounds_remaining,
        negotiation_hint="You may request a rate reduction. Our system will evaluate your profile and respond.",
        detected_intent="START",
    )


@app.post("/negotiate/counter", response_model=CounterResponse)
def negotiate_counter(payload: CounterRequest) -> CounterResponse:
    session = store.get(payload.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if store.mark_expired_if_needed(session):
        raise HTTPException(status_code=410, detail="Session expired")

    result = counter_session(session, payload.applicant_message, payload.requested_rate)
    append_history(session, "counter", result["reasoning"], result["intent"])
    store.update(payload.session_id, session)

    rounds_remaining = max(0, MAX_ROUNDS - session["rounds_completed"])

    return CounterResponse(
        session_id=payload.session_id,
        counter_offer=result["offer"],
        reasoning=result["reasoning"],
        rounds_remaining=rounds_remaining,
        can_negotiate_further=result["can_negotiate_further"],
        status=session["status"],
        detected_intent=result["intent"],
    )


@app.post("/negotiate/accept", response_model=AcceptResponse)
def negotiate_accept(payload: AcceptRequest) -> AcceptResponse:
    session = store.get(payload.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if store.mark_expired_if_needed(session):
        store.update(payload.session_id, session)
        expired_offer = build_offer(
            session["loan_amount"],
            session["tenure_months"],
            session["current_rate"],
            session["opening_offer"]["total_payable"],
        )
        return AcceptResponse(
            session_id=payload.session_id,
            final_offer=expired_offer,
            message="This negotiation session has expired after 48 hours. Please restart your negotiation.",
            sanction_reference="NA",
            status="expired",
            detected_intent="ACCEPTANCE",
        )

    final_offer = build_offer(
        session["loan_amount"],
        session["tenure_months"],
        session["current_rate"],
        session["opening_offer"]["total_payable"],
    )
    sanction_reference = build_sanction_reference()

    session["status"] = "completed"
    append_history(
        session,
        "accept",
        f"This concludes our negotiation. Your final approved rate is {session['current_rate']:.2f}% per annum. "
        "This offer is valid for 48 hours. Shall I generate your sanction letter?",
        "ACCEPTANCE",
    )
    store.update(payload.session_id, session)

    return AcceptResponse(
        session_id=payload.session_id,
        final_offer=final_offer,
        message=(
            f"Congratulations! Your loan at {session['current_rate']:.2f}% per annum has been accepted. "
            "Generating your digitally signed sanction letter now..."
        ),
        sanction_reference=sanction_reference,
        status="completed",
        detected_intent="ACCEPTANCE",
    )


@app.post("/negotiate/escalate", response_model=EscalateResponse)
def negotiate_escalate(payload: EscalateRequest) -> EscalateResponse:
    session = store.get(payload.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if store.mark_expired_if_needed(session):
        store.update(payload.session_id, session)
        return EscalateResponse(
            session_id=payload.session_id,
            message="Session expired before escalation could be processed. Please restart negotiation.",
            escalation_id="NA",
            status="expired",
            detected_intent="ESCALATION_REQUEST",
        )

    escalation_id = build_escalation_reference()
    sanction_reference = build_sanction_reference()
    session["status"] = "escalated"
    append_history(
        session,
        "escalate",
        "You have reached the minimum rate available for your risk tier. Further reduction is not possible within automated limits. "
        "Would you like me to escalate this to a human loan officer for a manual review?",
        "ESCALATION_REQUEST",
    )
    store.update(payload.session_id, session)

    return EscalateResponse(
        session_id=payload.session_id,
        message=(
            "Your case has been escalated to a senior loan officer. You will receive a call within 2 business hours. "
            f"Reference: {sanction_reference}."
        ),
        escalation_id=escalation_id,
        status="escalated",
        detected_intent="ESCALATION_REQUEST",
    )


@app.get("/negotiate/history/{session_id}", response_model=HistoryResponse)
def negotiate_history(session_id: str) -> HistoryResponse:
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if store.mark_expired_if_needed(session):
        store.update(session_id, session)

    return HistoryResponse(session_id=session_id, status=session["status"], session=session)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    uptime_seconds = int((datetime.now(timezone.utc) - boot_time).total_seconds())
    return HealthResponse(status="ok", uptime_seconds=uptime_seconds, active_sessions=store.count_active())
