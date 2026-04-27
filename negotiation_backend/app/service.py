from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import uuid4

from app.constants import CONCESSION_STEP, MAX_ROUNDS, RATE_CEILING, RATE_FLOOR, RISK_CONCESSION_LIMITS
from app.intent import detect_intent
from app.utils import calculate_emi_components, round_to_step, with_currency_format


def analyze_counter_request(
    user_message: str,
    current_rate: float,
    floor_rate: float
) -> dict:
    """
    Analyze the applicant's counter-offer to extract their requested rate
    and assess the aggressiveness and feasibility of their proposal.
    """
    # Try to extract a specific rate from the user's message
    rate_patterns = [
        r'(\d+\.?\d*)\s*%',
        r'(\d+\.?\d*)\s*percent',
        r'(\d+\.?\d*)\s*प्रतिशत',
    ]
    
    requested_rate = None
    for pattern in rate_patterns:
        match = re.search(pattern, user_message.lower())
        if match:
            requested_rate = float(match.group(1))
            break
    
    if requested_rate:
        gap = current_rate - requested_rate
        
        if requested_rate < floor_rate:
            aggressiveness = 1.0
            feasibility = "impossible"
        elif gap <= 0.25:
            aggressiveness = 0.3
            feasibility = "likely"
        elif gap <= 0.50:
            aggressiveness = 0.6
            feasibility = "possible"
        else:
            aggressiveness = 0.9
            feasibility = "unlikely"
    else:
        aggressiveness = 0.5
        feasibility = "possible"
        requested_rate = current_rate - 0.25
    
    return {
        "requested_rate": requested_rate,
        "aggressiveness": aggressiveness,
        "feasibility": feasibility,
        "gap_from_current": current_rate - (requested_rate or current_rate)
    }


def calculate_concession(
    risk_score: int,
    current_rate: float,
    floor_rate: float,
    round_number: int,
    max_rounds: int,
    aggressiveness: float,
    requested_rate: float
) -> dict:
    """
    Calculate a smart concession based on risk profile, negotiation progress,
    and the applicant's counter-offer aggressiveness.
    """
    from app.utils import calculate_emi_components
    
    headroom = current_rate - floor_rate
    
    if headroom <= 0:
        return {
            "action": "HOLD_FIRM",
            "new_rate": current_rate,
            "concession": 0.0,
            "reason": "floor_reached"
        }
    
    # Determine max step based on risk score
    if risk_score >= 80:
        max_step = 0.50
    elif risk_score >= 65:
        max_step = 0.25
    else:
        max_step = 0.0
    
    # Round factor decreases as negotiation progresses
    round_factor = 1 - ((round_number - 1) / max(max_rounds, 1)) * 0.5
    
    concession = min(max_step * round_factor, headroom)
    
    # If applicant requested a specific rate, consider it
    if requested_rate and requested_rate >= floor_rate:
        halfway = (current_rate - requested_rate) / 2
        concession = min(concession, max(halfway, 0.25))
    
    # Round to step (0.25 increments)
    concession = round(round(concession / 0.25) * 0.25, 2)
    
    if concession == 0:
        return {
            "action": "HOLD_FIRM",
            "new_rate": current_rate,
            "concession": 0.0,
            "reason": "profile_insufficient"
        }
    
    new_rate = round(current_rate - concession, 2)
    
    # Calculate savings for display
    old_emi = calculate_emi_components(500000, current_rate, 60)["emi"]
    new_emi = calculate_emi_components(500000, new_rate, 60)["emi"]
    
    return {
        "action": "CONCEDE",
        "new_rate": max(new_rate, floor_rate),
        "concession": concession,
        "reason": "profile_merit",
        "savings_per_month": old_emi - new_emi
    }


async def generate_counter_response(
    concession_result: dict,
    counter_analysis: dict,
    loan_context: dict,
    language: str
) -> str:
    """
    Generate a Groq-powered counter-response that references
    the applicant's specific rate request.
    """
    try:
        from backend.groq_client import groq_client
    except ImportError:
        # Fallback if groq_client not available
        return _generate_fallback_response(concession_result, counter_analysis, loan_context)
    
    requested_rate = counter_analysis.get("requested_rate") or loan_context.get("current_rate", 0)
    current_rate = loan_context.get("current_rate", 0)
    new_rate = concession_result.get("new_rate", current_rate)
    savings = concession_result.get("savings_per_month", 0)
    
    if concession_result["action"] == "HOLD_FIRM":
        prompt = f"""
The applicant requested {requested_rate:.2f}% but we cannot reduce below {current_rate:.2f}%.

Explain firmly but kindly why this rate is our best offer.
Reference their risk profile: score {loan_context.get('risk_score', 'N/A')}, tier {loan_context.get('risk_tier', 'N/A')}.
Offer escalation as an alternative.
Language: {language}. Max 60 words.
Sound like a helpful relationship manager.
"""
    else:
        prompt = f"""
We're reducing the rate from {current_rate:.2f}% to {new_rate:.2f}%.

The applicant asked for {requested_rate:.2f}%.
We met them partway.

Explain this positively.
Mention they save ₹{savings:.0f}/month.
Language: {language}. Max 70 words.
Sound like a helpful relationship manager.
"""
    
    try:
        response = await groq_client.complete(
            [{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.35
        )
        return response.content
    except Exception as e:
        # Fallback to template response
        return _generate_fallback_response(concession_result, counter_analysis, loan_context)


def _generate_fallback_response(
    concession_result: dict,
    counter_analysis: dict,
    loan_context: dict
) -> str:
    """Generate a simple fallback response when Groq is unavailable."""
    current_rate = loan_context.get("current_rate", 0)
    new_rate = concession_result.get("new_rate", current_rate)
    savings = concession_result.get("savings_per_month", 0)
    requested_rate = counter_analysis.get("requested_rate") or current_rate
    
    if concession_result["action"] == "HOLD_FIRM":
        return (
            f"We appreciate your counter-offer of {requested_rate:.2f}%. "
            f"However, based on your risk profile (score: {loan_context.get('risk_score', 'N/A')}), "
            f"our current rate of {current_rate:.2f}% is the best we can offer. "
            f"If you'd like us to review this further, please use the escalation option."
        )
    else:
        return (
            f"Thank you for your counter-offer of {requested_rate:.2f}%. "
            f"We're happy to reduce your rate from {current_rate:.2f}% to {new_rate:.2f}%. "
            f"This means you save ₹{savings:.0f} every month on your EMI. "
            f"We appreciate your negotiation and are glad to meet you partway."
        )


def normalize_tier(risk_tier: str, risk_score: int) -> str:
    tier = (risk_tier or "").strip().lower()
    if "low" in tier:
        return "Low"
    if "medium" in tier:
        return "Medium"
    if "high" in tier:
        return "High"

    if risk_score >= 75:
        return "Low"
    if risk_score >= 50:
        return "Medium"
    return "High"


def starting_rate_for_tier(risk_score: int, risk_tier: str) -> float:
    if risk_tier == "Low":
        # 75 -> 11.5 and 100 -> 10.5
        raw = 11.5 - ((risk_score - 75) / 25) * 1.0
        return max(10.5, min(11.5, round_to_step(raw)))
    if risk_tier == "Medium":
        # 50 -> 13.0 and 74 -> 12.0
        raw = 13.0 - ((risk_score - 50) / 24) * 1.0
        return max(12.0, min(13.0, round_to_step(raw)))

    # High: 0 -> 14.0 and 49 -> 13.5
    raw = 14.0 - (risk_score / 49) * 0.5 if risk_score > 0 else 14.0
    return max(13.5, min(14.0, round_to_step(raw)))


def build_offer(loan_amount: int, tenure_months: int, rate: float, opening_total_payable: int | None = None) -> dict:
    components = calculate_emi_components(loan_amount, rate, tenure_months)
    payload = {
        "rate": round(rate, 2),
        "tenure_months": tenure_months,
        "loan_amount": int(loan_amount),
        "emi": components["emi"],
        "total_payable": components["total_payable"],
        "total_interest": components["total_interest"],
    }
    if opening_total_payable is not None:
        payload["savings_vs_opening"] = int(opening_total_payable - components["total_payable"])
    return with_currency_format(payload)


def start_session(payload: dict) -> dict:
    score = payload["risk_score"]
    tier = normalize_tier(payload["risk_tier"], score)
    starting_rate = starting_rate_for_tier(score, tier)
    max_concessions = RISK_CONCESSION_LIMITS[tier]
    can_negotiate = tier in {"Low", "Medium"}

    if tier == "High" and score < 35:
        can_negotiate = False

    # Use max_negotiation_rounds from payload (comes from credit band in underwriting)
    # Default to 3 if not provided for backward compatibility
    max_rounds = payload.get("max_negotiation_rounds", MAX_ROUNDS)

    opening_offer = build_offer(
        loan_amount=payload["loan_amount"],
        tenure_months=payload["tenure_months"],
        rate=starting_rate,
    )

    reasoning = (
        f"Based on your risk score of {score}, you qualify for our {tier} Risk rate tier. "
        f"Your starting offer is {starting_rate:.2f}% per annum for {payload['tenure_months']} months."
    )

    if tier == "High":
        reasoning = (
            f"Based on your current risk profile, the offered rate of {starting_rate:.2f}% is fixed and cannot be negotiated. "
            f"Your risk score of {score} does not qualify for rate adjustments under our current policy."
        )

    return {
        "session_id": str(uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "applicant_name": payload["applicant_name"],
        "risk_score": score,
        "risk_tier": tier,
        "loan_amount": payload["loan_amount"],
        "tenure_months": payload["tenure_months"],
        "top_positive_factor": payload.get("top_positive_factor", "credit history"),
        "current_rate": starting_rate,
        "starting_rate": starting_rate,
        "floor_rate": RATE_FLOOR,
        "rounds_completed": 0,
        "concessions_given": 0,
        "max_concessions": max_concessions,
        "max_negotiation_rounds": max_rounds,
        "status": "active",
        "opening_offer": opening_offer,
        "history": [
            {
                "round": 1,
                "system_offer": starting_rate,
                "applicant_action": "start",
                "reasoning": reasoning,
                "detected_intent": "START",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ],
        "can_negotiate": can_negotiate,
    }


def counter_session(session: dict, applicant_message: str, requested_rate: float | None) -> dict:
    intent = detect_intent(applicant_message)
    score = session["risk_score"]
    tier = session["risk_tier"]
    current_rate = float(session["current_rate"])
    floor_rate = float(session["floor_rate"])

    if session["status"] != "active":
        offer = build_offer(session["loan_amount"], session["tenure_months"], current_rate, session["opening_offer"]["total_payable"])
        return {
            "offer": offer,
            "reasoning": f"Negotiation is no longer active because this session is {session['status']}.",
            "intent": intent,
            "can_negotiate_further": False,
        }

    if intent == "ACCEPTANCE":
        offer = build_offer(session["loan_amount"], session["tenure_months"], current_rate, session["opening_offer"]["total_payable"])
        return {
            "offer": offer,
            "reasoning": "You indicated acceptance. Please confirm via the accept endpoint to finalize this offer.",
            "intent": intent,
            "can_negotiate_further": False,
        }

    if intent == "ESCALATION_REQUEST":
        offer = build_offer(session["loan_amount"], session["tenure_months"], current_rate, session["opening_offer"]["total_payable"])
        return {
            "offer": offer,
            "reasoning": "You requested a human review. Please use the escalation endpoint and we will route your case.",
            "intent": intent,
            "can_negotiate_further": False,
        }

    session["rounds_completed"] += 1
    max_rounds = session.get("max_negotiation_rounds", MAX_ROUNDS)
    rounds_remaining = max(0, max_rounds - session["rounds_completed"])

    no_concession = tier == "High" or session["concessions_given"] >= session["max_concessions"]

    beyond_floor_request = requested_rate is not None and requested_rate < floor_rate

    if no_concession:
        if tier == "High":
            reasoning = (
                f"Based on your current risk profile, the offered rate of {current_rate:.2f}% is fixed and cannot be negotiated. "
                f"Your risk score of {score} does not qualify for rate adjustments under our current policy."
            )
        elif beyond_floor_request or current_rate <= floor_rate:
            reasoning = (
                "You have reached the minimum rate available for your risk tier. Further reduction is not possible within automated limits. "
                "Would you like me to escalate this to a human loan officer for a manual review?"
            )
        elif session["rounds_completed"] >= session.get("max_negotiation_rounds", MAX_ROUNDS):
            reasoning = (
                f"This concludes our negotiation. Your final approved rate is {current_rate:.2f}% per annum. "
                "This offer is valid for 48 hours. Shall I generate your sanction letter?"
            )
        else:
            reasoning = (
                f"This is our best possible offer for your risk profile at {current_rate:.2f}%. "
                "We cannot provide additional automated concessions."
            )

        offer = build_offer(session["loan_amount"], session["tenure_months"], current_rate, session["opening_offer"]["total_payable"])
        can_more = rounds_remaining > 0 and current_rate > floor_rate and tier != "High"
        return {
            "offer": offer,
            "reasoning": reasoning,
            "intent": intent,
            "can_negotiate_further": can_more,
        }

    proposed_rate = max(floor_rate, round_to_step(current_rate - CONCESSION_STEP))
    if requested_rate is not None:
        proposed_rate = max(proposed_rate, min(current_rate, requested_rate))
        proposed_rate = max(floor_rate, round_to_step(proposed_rate))

    if proposed_rate >= current_rate:
        offer = build_offer(session["loan_amount"], session["tenure_months"], current_rate, session["opening_offer"]["total_payable"])
        reasoning = (
            "You have reached the minimum negotiable rate available in this round. "
            "No additional reduction can be applied right now."
        )
        return {
            "offer": offer,
            "reasoning": reasoning,
            "intent": intent,
            "can_negotiate_further": rounds_remaining > 0,
        }

    session["current_rate"] = proposed_rate
    session["concessions_given"] += 1

    if session["concessions_given"] == 1:
        reasoning = (
            f"Given your strong {session['top_positive_factor']} and this being your first negotiation request, "
            f"we can reduce the rate by {CONCESSION_STEP:.2f}% to {proposed_rate:.2f}%. "
            "This is a goodwill adjustment based on your profile."
        )
    else:
        reasoning = (
            "This is our best possible offer for your risk profile. "
            f"Your {session['top_positive_factor']} qualifies you for one additional reduction to {proposed_rate:.2f}%. "
            "We cannot go lower than this floor rate."
        )

    if session["rounds_completed"] >= session.get("max_negotiation_rounds", MAX_ROUNDS):
        reasoning = (
            f"This concludes our negotiation. Your final approved rate is {proposed_rate:.2f}% per annum. "
            "This offer is valid for 48 hours. Shall I generate your sanction letter?"
        )

    offer = build_offer(session["loan_amount"], session["tenure_months"], proposed_rate, session["opening_offer"]["total_payable"])
    can_more = (
        rounds_remaining > 0
        and session["concessions_given"] < session["max_concessions"]
        and proposed_rate > floor_rate
    )

    return {
        "offer": offer,
        "reasoning": reasoning,
        "intent": intent,
        "can_negotiate_further": can_more,
    }


def append_history(session: dict, applicant_action: str, reasoning: str, intent: str) -> None:
    session["history"].append(
        {
            "round": len(session["history"]) + 1,
            "system_offer": session["current_rate"],
            "applicant_action": applicant_action,
            "reasoning": reasoning,
            "detected_intent": intent,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


def build_sanction_reference() -> str:
    year = datetime.now(timezone.utc).year
    suffix = str(uuid4().int)[-5:]
    return f"LE-{year}-{suffix}"


def build_escalation_reference() -> str:
    suffix = str(uuid4().int)[-5:]
    return f"ESC-{suffix}"


def extract_top_positive_factor(shap_explanation: list[str] | None) -> str:
    if not shap_explanation:
        return "credit history"

    first_line = str(shap_explanation[0]).lower()
    if "credit" in first_line:
        return "credit history"
    if "income" in first_line:
        return "income profile"
    if "loan amount" in first_line or "loan" in first_line:
        return "loan amount alignment"
    if "co-applicant" in first_line or "coapplicant" in first_line:
        return "co-applicant support"
    return "profile strength"
