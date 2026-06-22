import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.config import settings
from core.session import session_store
from groq_client import groq_client

router = APIRouter()
logger = logging.getLogger("loanease.negotiation")

# ─── CONSTANTS ───────────────────────────────────────────────────────────────

FLOOR_RATE = settings.RATE_FLOOR          # 10.5 — absolute minimum
CONCESSION_STEP = settings.CONCESSION_STEP  # 0.25 — per round

# ─── TIER CONFIG ─────────────────────────────────────────────────────────────
# Single source of truth for all three risk paths.
# Cutoffs (0/50/75) match the negotiation flowchart exactly.

TIER_CONFIG: Dict[str, Dict[str, Any]] = {
    "HIGH": {
        "rate_min": 13.5,
        "rate_max": 14.0,
        "default_starting": 13.75,
        "max_rounds": 0,
        "negotiation_permitted": False,
        "floor_rate": 13.5,  # HIGH tier floor is its own band minimum
    },
    "MEDIUM": {
        "rate_min": 12.0,
        "rate_max": 13.0,
        "default_starting": 12.5,
        "max_rounds": 1,
        "negotiation_permitted": True,
        "floor_rate": FLOOR_RATE,
    },
    "LOW": {
        "rate_min": 10.5,
        "rate_max": 11.5,
        "default_starting": 11.0,
        "max_rounds": 3,
        "negotiation_permitted": True,
        "floor_rate": FLOOR_RATE,
    },
}

# ─── SESSION STORE ────────────────────────────────────────────────────────────
# Keyed by negotiation_id (kept for backward compat with frontend).
# Each record also carries the pipeline session_id for session_store sync.

_sessions: Dict[str, dict] = {}

# ─── ANALYTICS ───────────────────────────────────────────────────────────────

_analytics: Dict[str, Any] = {
    "total_negotiations": 0,
    "accepted_count": 0,
    "escalated_count": 0,
    "total_rounds": 0,
    "total_concession": 0.0,
    "total_savings": 0.0,
    "accept_rounds_map": {},
    "escalation_reasons": {},
    "purpose_distribution": {},
}

# ─── SCHEMAS ─────────────────────────────────────────────────────────────────

class NegotiationStartRequest(BaseModel):
    session_id: Optional[str] = None
    applicant_name: Optional[str] = None
    risk_score: Optional[int] = None        # 0-100 combined score
    risk_tier: Optional[str] = None         # HIGH / MEDIUM / LOW (or verbose label)
    loan_amount: Optional[float] = None
    tenure_months: Optional[int] = None
    starting_rate: Optional[float] = None   # from underwriting agent
    lgbm_probability: Optional[float] = None
    # Legacy fields kept for backward compat
    desired_rate: Optional[float] = None
    customer_profile: str = "STANDARD"
    max_negotiation_rounds: Optional[int] = None
    top_positive_factor: Optional[str] = None
    purpose: Optional[str] = None


class NegotiationCounterRequest(BaseModel):
    session_id: Optional[str] = None       # legacy: was negotiation_id
    negotiation_id: Optional[str] = None
    applicant_message: Optional[str] = None
    proposed_rate: Optional[float] = None  # legacy numeric counter


class NegotiationAcceptRequest(BaseModel):
    session_id: Optional[str] = None
    negotiation_id: Optional[str] = None
    final_rate: Optional[float] = None
    holiday_months: Optional[int] = None


class NegotiateEscalateRequest(BaseModel):
    session_id: Optional[str] = None
    negotiation_id: Optional[str] = None
    reason: Optional[str] = "applicant_requested"


# ─── EMI / OFFER HELPERS ─────────────────────────────────────────────────────

def _calculate_emi(principal: float, annual_rate: float, tenure_months: int) -> float:
    """Standard reducing-balance EMI formula."""
    tenure = max(1, int(tenure_months))
    if annual_rate == 0:
        return round(principal / tenure, 2)
    r = annual_rate / 12 / 100
    factor = (1 + r) ** tenure
    return round(principal * r * factor / (factor - 1), 2)


def build_offer(
    loan_amount: float,
    rate: float,
    tenure_months: int,
    previous_emi: Optional[float] = None,
) -> dict:
    """Build a complete offer object with EMI, total payable, and savings."""
    emi = _calculate_emi(loan_amount, rate, tenure_months)
    total_payable = round(emi * tenure_months, 2)
    total_interest = round(total_payable - loan_amount, 2)

    savings = None
    if previous_emi is not None:
        monthly_savings = round(previous_emi - emi, 2)
        savings = {
            "per_month": monthly_savings,
            "total": round(monthly_savings * tenure_months, 2),
        }

    return {
        "rate": rate,
        "interest_rate": rate,          # backward compat alias
        "loan_amount": loan_amount,
        "tenure_months": tenure_months,
        "emi": emi,
        "monthly_emi": emi,             # backward compat alias
        "total_payable": total_payable,
        "total_interest": total_interest,
        "savings_vs_opening": savings,
    }


def with_emi_holiday(
    principal: float, rate: float, tenure_months: int, holiday_months: int
) -> dict:
    """EMI holiday preview — interest accrues during holiday period."""
    holiday = max(0, int(holiday_months))
    tenure = max(1, int(tenure_months))
    monthly_rate = rate / 12 / 100
    adjusted_principal = (
        principal * ((1 + monthly_rate) ** holiday) if monthly_rate > 0 else principal
    )
    emi = _calculate_emi(adjusted_principal, rate, tenure)
    original_emi = _calculate_emi(principal, rate, tenure)
    return {
        "holiday_months": holiday,
        "adjusted_principal": round(adjusted_principal, 2),
        "emi": emi,
        "original_emi": original_emi,
        "extra_cost": round(max(0.0, emi * tenure - original_emi * tenure), 2),
        "first_emi_after_month": holiday + 1,
    }


# ─── FLOWCHART DECISION HELPERS ──────────────────────────────────────────────

def _resolve_negotiation_id(req_session_id: Optional[str], req_neg_id: Optional[str]) -> Optional[str]:
    """
    Resolve which key to use for _sessions lookup.
    Frontend may send either session_id or negotiation_id; both are stored as
    the same key (negotiation_id) in _sessions.
    """
    if req_neg_id and req_neg_id in _sessions:
        return req_neg_id
    if req_session_id and req_session_id in _sessions:
        return req_session_id
    return req_neg_id or req_session_id


def _normalize_tier(raw: Optional[str]) -> str:
    """Convert any tier string variant to HIGH / MEDIUM / LOW."""
    if not raw:
        return "MEDIUM"
    up = raw.upper()
    if "HIGH" in up:
        return "HIGH"
    if "LOW" in up:
        return "LOW"
    return "MEDIUM"


def _tier_from_score(risk_score: int) -> str:
    """Flowchart cutoffs: <50 → HIGH, 50-74 → MEDIUM, ≥75 → LOW."""
    if risk_score < 50:
        return "HIGH"
    if risk_score < 75:
        return "MEDIUM"
    return "LOW"


def _is_floor_reached(current_rate: float, tier: str) -> bool:
    """True when current rate is at or below the tier floor (±0.01 tolerance)."""
    return current_rate <= TIER_CONFIG[tier]["floor_rate"] + 0.01


def _rounds_exhausted(session: dict) -> bool:
    return session["rounds_completed"] >= session["max_rounds"]


def _can_concede(session: dict) -> bool:
    """Both conditions must hold: rounds remaining AND floor not yet hit."""
    if _rounds_exhausted(session):
        return False
    if _is_floor_reached(session["current_rate"], session["risk_tier"]):
        return False
    return True


# ─── GROQ REASONING ──────────────────────────────────────────────────────────

async def _generate_reasoning(action: str, session: dict, new_rate: float, offer: dict) -> str:
    """Natural-language explanation via Groq; falls back to template."""
    try:
        prev_rate = new_rate + CONCESSION_STEP if action == "CONCEDE" else new_rate
        savings = offer.get("savings_vs_opening") or {}
        monthly_savings = savings.get("per_month", 0)

        prompt = (
            f"You are a loan relationship manager explaining a negotiation decision.\n"
            f"Action: {action}\n"
            f"Previous rate: {prev_rate}%\n"
            f"New rate: {new_rate}%\n"
            f"Round: {session['rounds_completed']} of {session['max_rounds']}\n"
            f"Risk tier: {session['risk_tier']}\n"
            f"Monthly EMI savings: INR {monthly_savings}\n\n"
            f"Write 1-2 sentences. Sound professional and specific about why this rate. "
            f"Keep financial terms in English. Max 70 words."
        )
        res = await groq_client.complete(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=120,
            temperature=0.3,
        )
        return res.content if hasattr(res, "content") else str(res)
    except Exception as exc:
        logger.debug(f"Groq reasoning failed ({exc}), using template")
        if action == "CONCEDE":
            monthly = (offer.get("savings_vs_opening") or {}).get("per_month", 0)
            return (
                f"Based on your {session['risk_tier'].lower()} risk profile, "
                f"we can reduce the rate to {new_rate}% p.a."
                + (f" This saves you INR {monthly:,.0f}/month." if monthly > 0 else "")
            )
        if action in ("FLOOR_REACHED", "ESCALATE"):
            return (
                f"We have reached the minimum rate of {new_rate}% for your profile. "
                f"Would you like to escalate to a senior loan officer?"
            )
        if action == "FINAL_OFFER":
            return (
                f"All negotiation rounds have been used. "
                f"This is our final offer at {new_rate}% p.a."
            )
        return f"Your current rate stands at {new_rate}% p.a."


# ─── ENDPOINTS ────────────────────────────────────────────────────────────────

@router.post("/start")
async def start_negotiation(request: NegotiationStartRequest):
    """
    FLOWCHART ENTRY: 'Underwriting Agent sends Risk Score'

    HIGH RISK  → Rate fixed, no negotiation, returns FINAL_OFFER immediately.
    MEDIUM/LOW → Sets starting rate and max rounds, returns ACTIVE session.
    """
    if settings.DEMO_MODE:
        import asyncio
        await asyncio.sleep(1.5)

    # ── Resolve inputs from request or pipeline session store ────────────────
    pipeline_session = None
    if request.session_id:
        pipeline_session = session_store.get(request.session_id)
        if not pipeline_session:
            session_store.get_or_create(request.session_id)
            pipeline_session = session_store.get(request.session_id)

    uw_result: dict = {}
    if pipeline_session:
        uw_result = pipeline_session["data"].get("underwriting_result", {})

    # Risk score — numeric wins over string label
    risk_score_val: Optional[int] = request.risk_score or uw_result.get("risk_score")
    if risk_score_val is not None:
        tier = _tier_from_score(int(risk_score_val))
    else:
        tier = _normalize_tier(request.risk_tier or uw_result.get("risk_tier", "MEDIUM"))

    config = TIER_CONFIG[tier]

    # Starting rate — use underwriting's fine-tuned value when available
    raw_starting = (
        request.starting_rate
        or request.desired_rate
        or uw_result.get("interest_rate")
        or uw_result.get("offered_rate")
        or config["default_starting"]
    )
    starting_rate = round(
        max(config["rate_min"], min(config["rate_max"], float(raw_starting))) * 4
    ) / 4

    loan_amount = float(request.loan_amount or uw_result.get("loan_amount", 500000))
    tenure_months = int(request.tenure_months or uw_result.get("tenure_months", 60))
    applicant_name = request.applicant_name or uw_result.get("applicant_name", "Applicant")
    purpose = request.purpose or (
        pipeline_session["data"].get("conversation_context", {}).get("loan_purpose")
        if pipeline_session else None
    )

    negotiation_id = f"NEG-{uuid.uuid4().hex[:8].upper()}"
    opening_offer = build_offer(loan_amount, starting_rate, tenure_months)

    # ── HIGH RISK PATH ────────────────────────────────────────────────────────
    # Flowchart: "Rate Fixed, No Negotiation" → terminal state immediately.
    if not config["negotiation_permitted"]:
        logger.info(
            "HIGH RISK session=%s rate=%.2f%% negotiation=blocked",
            request.session_id, starting_rate,
        )
        _sessions[negotiation_id] = {
            "negotiation_id": negotiation_id,
            "pipeline_session_id": request.session_id,
            "applicant_name": applicant_name,
            "risk_score": risk_score_val,
            "risk_tier": tier,
            "loan_amount": loan_amount,
            "tenure_months": tenure_months,
            "current_rate": starting_rate,
            "starting_rate": starting_rate,
            "floor_rate": config["floor_rate"],
            "max_rounds": 0,
            "rounds_completed": 0,
            "concessions_given": 0,
            "status": "FINAL_OFFER",
            "history": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        if request.session_id:
            session_store.update_stage(request.session_id, "NEGOTIATION_STARTED")
            session_store.log_agent(request.session_id, {
                "agent": "negotiation", "action": "start_high_risk",
                "negotiation_id": negotiation_id, "rate": starting_rate,
            })

        _analytics["total_negotiations"] += 1
        if purpose:
            _analytics["purpose_distribution"][purpose] = (
                _analytics["purpose_distribution"].get(purpose, 0) + 1
            )

        return {
            "negotiation_id": negotiation_id,
            "session_id": negotiation_id,       # frontend reads this field
            "risk_tier": tier,
            "negotiation_permitted": False,
            "can_negotiate": False,
            # Flat backward-compat fields
            "current_rate": starting_rate,
            "min_rate": config["rate_min"],
            "max_concession": 0.0,
            "total_steps": 0,
            "rounds_remaining": 0,
            "customer_profile": request.customer_profile,
            # Full offer object
            "offer": opening_offer,
            "opening_offer": opening_offer,
            "status": "FINAL_OFFER",
            "message": (
                f"Based on your risk profile (score: {risk_score_val}/100), "
                f"the interest rate is fixed at {starting_rate}% p.a. "
                f"This offer cannot be negotiated."
            ),
            "actions": ["ACCEPT", "DECLINE"],
            "detected_intent": "START",
        }

    # ── MEDIUM / LOW RISK PATH ────────────────────────────────────────────────
    max_rounds = config["max_rounds"]
    logger.info(
        "%s RISK session=%s rate=%.2f%% max_rounds=%d",
        tier, request.session_id, starting_rate, max_rounds,
    )

    # EMI holiday option for Medium/Low applicants
    emi_holiday_option = None
    if tier in {"LOW", "MEDIUM"}:
        preview = with_emi_holiday(loan_amount, starting_rate, tenure_months, 2)
        emi_holiday_option = {
            **preview,
            "message": (
                "Would you like a 2-month EMI holiday? "
                "Interest accrues during the holiday period."
            ),
            "recommended": tier == "LOW",
        }

    _sessions[negotiation_id] = {
        "negotiation_id": negotiation_id,
        "pipeline_session_id": request.session_id,
        "applicant_name": applicant_name,
        "risk_score": risk_score_val,
        "risk_tier": tier,
        "loan_amount": loan_amount,
        "tenure_months": tenure_months,
        "current_rate": starting_rate,
        "starting_rate": starting_rate,
        "floor_rate": config["floor_rate"],
        "max_rounds": max_rounds,
        "rounds_completed": 0,
        "concessions_given": 0,
        "status": "ACTIVE",
        "history": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    if request.session_id:
        session_store.update_stage(request.session_id, "NEGOTIATION_STARTED")
        session_store.log_agent(request.session_id, {
            "agent": "negotiation", "action": "start",
            "negotiation_id": negotiation_id,
            "initial_rate": starting_rate,
            "min_rate": config["floor_rate"],
            "max_rounds": max_rounds,
        })

    _analytics["total_negotiations"] += 1
    if purpose:
        _analytics["purpose_distribution"][purpose] = (
            _analytics["purpose_distribution"].get(purpose, 0) + 1
        )

    rounds_label = (
        f"up to {max_rounds} time{'s' if max_rounds > 1 else ''}"
    )

    return {
        "negotiation_id": negotiation_id,
        "session_id": negotiation_id,
        "risk_tier": tier,
        "negotiation_permitted": True,
        "can_negotiate": True,
        # Flat backward-compat fields
        "current_rate": starting_rate,
        "min_rate": config["floor_rate"],
        "max_concession": round(starting_rate - config["floor_rate"], 2),
        "total_steps": max_rounds,
        "rounds_remaining": max_rounds,
        "customer_profile": request.customer_profile,
        # Full offer objects
        "offer": opening_offer,
        "opening_offer": opening_offer,
        "emi_holiday_option": emi_holiday_option,
        "status": "ACTIVE",
        "message": (
            f"Based on your {tier.lower()} risk profile, your opening rate is "
            f"{starting_rate}% p.a. You may negotiate {rounds_label} for a better rate."
        ),
        "actions": ["ACCEPT", "COUNTER"],
        "detected_intent": "START",
        "reasoning": f"Opening offer at {starting_rate}% for {tier} risk profile.",
    }


@router.post("/counter")
async def counter_offer(request: NegotiationCounterRequest):
    """
    FLOWCHART: 'Applicant Counters?'

    Decision tree (in order):
      1. Tier not permitted         → reject with current offer
      2. _can_concede() == True     → reduce rate by 0.25%, return ACTIVE
      3. Floor reached              → FLOOR_REACHED, offer ESCALATE_TO_HUMAN
      4. Rounds exhausted           → FINAL_OFFER, no more counters
    """
    if settings.DEMO_MODE:
        import asyncio
        await asyncio.sleep(1.2)

    neg_id = _resolve_negotiation_id(request.session_id, request.negotiation_id)
    session = _sessions.get(neg_id) if neg_id else None
    if not session:
        raise HTTPException(status_code=404, detail="Negotiation session not found")

    if session["status"] in ("ACCEPTED", "ESCALATED", "DECLINED"):
        raise HTTPException(
            status_code=400,
            detail=f"Session already {session['status']}",
        )

    tier = session["risk_tier"]
    config = TIER_CONFIG[tier]

    # ── Blocked tier ──────────────────────────────────────────────────────────
    if not config["negotiation_permitted"]:
        offer = build_offer(session["loan_amount"], session["current_rate"], session["tenure_months"])
        return {
            "negotiation_id": neg_id,
            "session_id": neg_id,
            "status": "FINAL_OFFER",
            "action_taken": "BLOCKED",
            "current_rate": session["current_rate"],
            "counter_offer": session["current_rate"],
            "proposed_rate": request.proposed_rate,
            "step": session["rounds_completed"],
            "total_steps": session["max_rounds"],
            "accepted": False,
            "negotiation_complete": True,
            "offer": offer,
            "message": "Your risk profile does not qualify for rate negotiation. The offered rate is final.",
            "actions": ["ACCEPT", "DECLINE"],
        }

    prev_rate = session["current_rate"]
    prev_emi = _calculate_emi(session["loan_amount"], prev_rate, session["tenure_months"])

    # Increment round counter before branching
    session["rounds_completed"] += 1

    # ── FLOWCHART: "Concessions Remaining?" ───────────────────────────────────
    if _can_concede(session):
        # YES branch — reduce by CONCESSION_STEP (0.25%)
        new_rate = round(
            max(session["floor_rate"], prev_rate - CONCESSION_STEP) * 4
        ) / 4
        session["current_rate"] = new_rate
        session["concessions_given"] += 1

        rounds_remaining = session["max_rounds"] - session["rounds_completed"]
        floor_hit_after = _is_floor_reached(new_rate, tier)
        can_go_further = rounds_remaining > 0 and not floor_hit_after

        new_offer = build_offer(
            session["loan_amount"], new_rate, session["tenure_months"],
            previous_emi=prev_emi,
        )
        session["history"].append({
            "round": session["rounds_completed"],
            "applicant_message": request.applicant_message,
            "proposed_rate": request.proposed_rate,
            "prev_rate": prev_rate,
            "new_rate": new_rate,
            "action": "CONCEDE",
        })

        _analytics["total_concession"] += round(prev_rate - new_rate, 4)
        _analytics["total_savings"] += round(
            (prev_rate - new_rate) / 100 * session["loan_amount"], 2
        )

        reasoning = await _generate_reasoning("CONCEDE", session, new_rate, new_offer)

        logger.info(
            "CONCEDE session=%s %s%%→%s%% round=%d/%d",
            neg_id, prev_rate, new_rate,
            session["rounds_completed"], session["max_rounds"],
        )

        _sync_pipeline_session(session, "NEGOTIATION_COUNTER", {
            "action": "CONCEDE", "prev_rate": prev_rate, "new_rate": new_rate,
            "round": session["rounds_completed"],
        })

        return {
            "negotiation_id": neg_id,
            "session_id": neg_id,
            "status": "ACTIVE",
            "action_taken": "CONCEDE",
            # Flat backward-compat
            "current_rate": prev_rate,
            "counter_offer": new_rate,
            "proposed_rate": request.proposed_rate,
            "step": session["rounds_completed"],
            "total_steps": session["max_rounds"],
            "accepted": False,
            "negotiation_complete": False,
            # Rich fields
            "offer": new_offer,
            "rounds_remaining": rounds_remaining,
            "can_negotiate_further": can_go_further,
            "reasoning": reasoning,
            "message": reasoning,
            "actions": ["ACCEPT", "COUNTER"] if can_go_further else ["ACCEPT"],
        }

    # ── NO branch — determine which terminal we hit ───────────────────────────
    floor_reached = _is_floor_reached(session["current_rate"], tier)
    rounds_done = _rounds_exhausted(session)

    if floor_reached:
        # FLOWCHART: "Floor Rate Reached" → "Escalate to Human?"
        session["history"].append({
            "round": session["rounds_completed"],
            "applicant_message": request.applicant_message,
            "action": "FLOOR_REACHED",
        })
        offer = build_offer(session["loan_amount"], session["current_rate"], session["tenure_months"])
        reasoning = await _generate_reasoning("FLOOR_REACHED", session, session["current_rate"], offer)

        logger.info("FLOOR_REACHED session=%s rate=%s%%", neg_id, session["current_rate"])
        _sync_pipeline_session(session, "NEGOTIATION_FLOOR", {"rate": session["current_rate"]})

        return {
            "negotiation_id": neg_id,
            "session_id": neg_id,
            "status": "FLOOR_REACHED",
            "action_taken": "FLOOR_REACHED",
            "current_rate": session["current_rate"],
            "counter_offer": session["current_rate"],
            "proposed_rate": request.proposed_rate,
            "step": session["rounds_completed"],
            "total_steps": session["max_rounds"],
            "accepted": False,
            "negotiation_complete": False,
            "offer": offer,
            "floor_rate": session["floor_rate"],
            "escalation_available": True,
            "reasoning": reasoning,
            "message": (
                f"We have reached the minimum rate available for your profile "
                f"({session['current_rate']}% p.a.). "
                f"Would you like to escalate to a human loan officer for further review?"
            ),
            "actions": ["ACCEPT", "ESCALATE_TO_HUMAN"],
        }

    if rounds_done:
        # FLOWCHART: "Final Offer Issued"
        session["status"] = "FINAL_OFFER"
        session["history"].append({
            "round": session["rounds_completed"],
            "applicant_message": request.applicant_message,
            "action": "FINAL_OFFER",
        })
        offer = build_offer(session["loan_amount"], session["current_rate"], session["tenure_months"])
        reasoning = await _generate_reasoning("FINAL_OFFER", session, session["current_rate"], offer)

        logger.info("FINAL_OFFER session=%s rate=%s%%", neg_id, session["current_rate"])
        _sync_pipeline_session(session, "NEGOTIATION_FINAL", {"rate": session["current_rate"]})

        return {
            "negotiation_id": neg_id,
            "session_id": neg_id,
            "status": "FINAL_OFFER",
            "action_taken": "FINAL_OFFER",
            "current_rate": session["current_rate"],
            "counter_offer": session["current_rate"],
            "proposed_rate": request.proposed_rate,
            "step": session["rounds_completed"],
            "total_steps": session["max_rounds"],
            "accepted": False,
            "negotiation_complete": True,
            "offer": offer,
            "reasoning": reasoning,
            "message": (
                f"This is our final offer: {session['current_rate']}% p.a. "
                f"All negotiation rounds have been used."
            ),
            "actions": ["ACCEPT", "DECLINE"],
        }

    # Fallback — should never reach here with correct logic
    offer = build_offer(session["loan_amount"], session["current_rate"], session["tenure_months"])
    return {
        "negotiation_id": neg_id,
        "session_id": neg_id,
        "status": "FINAL_OFFER",
        "action_taken": "FINAL_OFFER",
        "current_rate": session["current_rate"],
        "counter_offer": session["current_rate"],
        "proposed_rate": request.proposed_rate,
        "step": session["rounds_completed"],
        "total_steps": session["max_rounds"],
        "accepted": False,
        "negotiation_complete": True,
        "offer": offer,
        "message": f"Final offer at {session['current_rate']}% p.a.",
        "actions": ["ACCEPT", "DECLINE"],
    }


@router.post("/accept")
async def accept_negotiation(request: NegotiationAcceptRequest):
    """
    FLOWCHART: 'No (Accepts)' path
    → Triggers sanction letter + blockchain registration.
    """
    neg_id = _resolve_negotiation_id(request.session_id, request.negotiation_id)
    session = _sessions.get(neg_id) if neg_id else None

    # Graceful fallback — accept from pipeline session directly
    if not session:
        final_rate = request.final_rate or 11.5
        loan_amount = 500000
        tenure_months = 60

        if request.session_id:
            pipeline_session = session_store.get(request.session_id)
            if pipeline_session:
                uw = pipeline_session["data"].get("underwriting_result", {})
                final_rate = request.final_rate or uw.get("interest_rate", 11.5)
                loan_amount = float(uw.get("loan_amount", 500000))
                tenure_months = int(uw.get("tenure_months", 60))
            session_store.update_stage(request.session_id, "NEGOTIATION_COMPLETE")
            session_store.update_data(request.session_id, "final_rate", final_rate)

        emi = _calculate_emi(loan_amount, final_rate, tenure_months)
        return {
            "negotiation_id": neg_id or "NEG-DIRECT",
            "session_id": neg_id or request.session_id,
            "status": "ACCEPTED",
            "accepted_rate": final_rate,
            "monthly_emi": emi,
            "negotiation_complete": True,
            "message": f"Loan approved at {final_rate}% with EMI of INR {emi:,.2f}.",
            "next_action": "GENERATE_SANCTION",
        }

    final_rate = request.final_rate or session["current_rate"]
    loan_amount = session["loan_amount"]
    tenure_months = session["tenure_months"]

    # Optional EMI holiday
    holiday_months = max(0, int(request.holiday_months or 0))
    if holiday_months > 0:
        holiday_details = with_emi_holiday(loan_amount, final_rate, tenure_months, holiday_months)
        monthly_emi = float(holiday_details["emi"])
    else:
        monthly_emi = _calculate_emi(loan_amount, final_rate, tenure_months)

    session["status"] = "ACCEPTED"
    session["accepted_at"] = datetime.now(timezone.utc).isoformat()

    opening_emi = _calculate_emi(loan_amount, session["starting_rate"], tenure_months)
    total_savings = round(max(0.0, (opening_emi - monthly_emi) * tenure_months), 2)

    logger.info(
        "ACCEPTED session=%s final_rate=%.2f%% rounds=%d",
        neg_id, final_rate, session["rounds_completed"],
    )

    _analytics["accepted_count"] += 1
    _analytics["total_rounds"] += session["rounds_completed"]
    r = session["rounds_completed"]
    _analytics["accept_rounds_map"][r] = _analytics["accept_rounds_map"].get(r, 0) + 1

    pid = session.get("pipeline_session_id")
    if pid:
        session_store.update_stage(pid, "NEGOTIATION_COMPLETE")
        session_store.update_data(pid, "final_rate", final_rate)
        session_store.update_data(pid, "emi_details", {
            "monthly_emi": monthly_emi, "holiday_months": holiday_months,
        })
        session_store.log_agent(pid, {
            "agent": "negotiation", "action": "accept",
            "negotiation_id": neg_id, "final_rate": final_rate, "monthly_emi": monthly_emi,
        })

    return {
        "negotiation_id": neg_id,
        "session_id": neg_id,
        "status": "ACCEPTED",
        "accepted_rate": final_rate,
        "monthly_emi": monthly_emi,
        "negotiation_complete": True,
        "final_offer": build_offer(loan_amount, final_rate, tenure_months),
        "summary": {
            "opening_rate": session["starting_rate"],
            "final_rate": final_rate,
            "rate_reduction": round(session["starting_rate"] - final_rate, 2),
            "rounds_taken": session["rounds_completed"],
            "total_interest_savings": total_savings,
        },
        "message": (
            f"Congratulations! Your loan at {final_rate}% p.a. has been accepted. "
            f"Generating your blockchain-secured sanction letter..."
            + (f" (includes {holiday_months}-month EMI holiday)" if holiday_months > 0 else "")
        ),
        "next_action": "GENERATE_SANCTION",
    }


@router.post("/escalate")
async def escalate_to_human(request: NegotiateEscalateRequest):
    """
    FLOWCHART: 'Escalate to Human?' → YES → 'Human Loan Officer Takes Over'

    Triggered when:
      - Floor rate reached and applicant chooses to escalate
      - Applicant explicitly requests human review
    """
    neg_id = _resolve_negotiation_id(request.session_id, request.negotiation_id)
    session = _sessions.get(neg_id) if neg_id else None

    if not session:
        raise HTTPException(status_code=404, detail="Negotiation session not found")

    session["status"] = "ESCALATED"
    session["escalated_at"] = datetime.now(timezone.utc).isoformat()
    session["escalation_reason"] = request.reason

    escalation_id = f"ESC-{uuid.uuid4().hex[:8].upper()}"
    session["escalation_id"] = escalation_id

    _analytics["escalated_count"] += 1
    reason = request.reason or "applicant_requested"
    _analytics["escalation_reasons"][reason] = (
        _analytics["escalation_reasons"].get(reason, 0) + 1
    )

    logger.info(
        "ESCALATED session=%s reason=%s id=%s", neg_id, reason, escalation_id
    )

    pid = session.get("pipeline_session_id")
    if pid:
        session_store.update_stage(pid, "ESCALATED_TO_HUMAN")
        session_store.log_agent(pid, {
            "agent": "negotiation", "action": "escalate",
            "escalation_id": escalation_id, "reason": reason,
        })

    return {
        "negotiation_id": neg_id,
        "session_id": neg_id,
        "status": "ESCALATED",
        "escalation_id": escalation_id,
        "current_offer": build_offer(
            session["loan_amount"], session["current_rate"], session["tenure_months"]
        ),
        "message": (
            f"Your case has been escalated to a senior loan officer. "
            f"You will receive a call within 2 business hours. "
            f"Reference: {escalation_id}"
        ),
    }


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    """Return full negotiation session state (supports both negotiation_id and pipeline session_id)."""
    neg_id = _resolve_negotiation_id(session_id, session_id)
    session = _sessions.get(neg_id) if neg_id else None
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/health")
async def negotiation_health():
    return {
        "status": "healthy",
        "active_sessions": len(_sessions),
        "floor_rate": FLOOR_RATE,
        "concession_step": CONCESSION_STEP,
        "tier_config": {
            t: {
                "max_rounds": c["max_rounds"],
                "rate_range": f"{c['rate_min']}-{c['rate_max']}%",
                "negotiation_permitted": c["negotiation_permitted"],
            }
            for t, c in TIER_CONFIG.items()
        },
    }


@router.get("/analytics")
async def get_analytics():
    a = _analytics
    total = a["total_negotiations"]
    accepted = a["accepted_count"]
    escalated = a["escalated_count"]

    acceptance_rate = f"{accepted / total * 100:.0f}%" if total else "0%"
    escalation_rate = f"{escalated / total * 100:.0f}%" if total else "0%"
    avg_rounds = round(a["total_rounds"] / accepted, 1) if accepted else 0.0
    avg_concession = f"{a['total_concession'] / total:.2f}%" if total else "0.00%"
    avg_savings = int(a["total_savings"] / total) if total else 0
    most_common_round = (
        max(a["accept_rounds_map"].items(), key=lambda x: x[1])[0]
        if a["accept_rounds_map"] else 0
    )
    top_escalation = (
        max(a["escalation_reasons"].items(), key=lambda x: x[1])[0]
        if a["escalation_reasons"] else "none"
    )

    return {
        "total_negotiations": total,
        "acceptance_rate": acceptance_rate,
        "escalation_rate": escalation_rate,
        "avg_rounds_to_acceptance": avg_rounds,
        "avg_concession_given": avg_concession,
        "avg_savings_per_applicant": avg_savings,
        "most_common_accept_round": most_common_round,
        "top_reason_for_escalation": top_escalation,
        "purpose_distribution": a["purpose_distribution"],
    }


# ─── INTERNAL HELPERS ─────────────────────────────────────────────────────────

def _sync_pipeline_session(session: dict, stage: str, extra: dict) -> None:
    """Keep pipeline session_store in sync with negotiation state."""
    pid = session.get("pipeline_session_id")
    if pid:
        try:
            session_store.update_stage(pid, stage)
            session_store.log_agent(pid, {
                "agent": "negotiation",
                "negotiation_id": session["negotiation_id"],
                **extra,
            })
        except Exception as exc:
            logger.debug("pipeline session sync failed: %s", exc)
