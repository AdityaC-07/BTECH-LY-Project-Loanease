from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from typing import Any

from app.constants import CONCESSION_STEP, MAX_ROUNDS, RATE_CEILING, RATE_FLOOR, RISK_CONCESSION_LIMITS
from app.intent import detect_intent
from app.utils import calculate_emi_components, round_to_step, with_currency_format


logger = logging.getLogger(__name__)

COMPETITOR_KEYWORDS = [
    "hdfc",
    "sbi",
    "icici",
    "bajaj",
    "axis",
    "kotak",
    "fullerton",
    "tata capital",
]

TONE_CLASSIFICATION_PROMPT = """
Classify this loan negotiation message into exactly one tone:

AGGRESSIVE: demanding, threatening to go elsewhere, very pushy
("I'll just go to HDFC", "This rate is a joke")

MODERATE: reasonable counteroffer, politely pushing
("Can you do a bit better?", "11% seems high for my profile")

PASSIVE: accepting but checking, mild curiosity
("Is this the best you can do?", "Okay, but just checking...")

CONFUSED: doesn't understand the offer
("What does p.a. mean?", "How is EMI calculated?")

Respond with JSON only:
{"tone": "...", "confidence": 0.0-1.0}
"""


def _safe_json_parse(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                return {}
    return {}


def detect_competitor_mentions(message: str) -> list[str]:
    text = (message or "").lower()
    mentions = [competitor for competitor in COMPETITOR_KEYWORDS if competitor in text]
    # Keep unique values and preserve simple display names.
    normalized: list[str] = []
    for item in mentions:
        display = item.upper() if item in {"sbi", "icici"} else item.title()
        if display not in normalized:
            normalized.append(display)
    return normalized


def build_competitor_response(competitors: list[str]) -> str:
    competitor_text = ", ".join(competitors) if competitors else "other banks"
    return (
        f"{competitor_text} are a great choice too. What sets us apart: instant decision, SHAP-explained approval, "
        "negotiable rates, and blockchain sanction letter - all in 5 minutes. Most banks take 3-5 days minimum. "
        "If the rate is the main factor, tell me what rate you've been quoted and I'll see what I can do."
    )


def build_memory_reference(session: dict) -> str | None:
    history = session.get("history") or []
    if not history:
        return None

    loan_amount = session.get("loan_amount")
    tenure_months = session.get("tenure_months")
    if not loan_amount or not tenure_months:
        return None

    amount_text = f"₹{int(loan_amount):,}"
    return f"Last time you were considering {amount_text} at {int(tenure_months)} months. Would you like to continue with those terms or adjust?"


def _minutes_remaining(valid_until: str | None) -> int | None:
    if not valid_until:
        return None
    try:
        remaining = datetime.fromisoformat(valid_until) - datetime.now(timezone.utc)
        return max(0, int(remaining.total_seconds() // 60))
    except Exception:
        return None


def _refresh_quote_if_needed(session: dict) -> bool:
    valid_until = session.get("offer_valid_until")
    if not valid_until:
        return False

    try:
        if datetime.now(timezone.utc) <= datetime.fromisoformat(valid_until):
            return False
    except Exception:
        return False

    # Re-quote to the same opening rate to keep the offer realistic and time-bound.
    session["offer_valid_until"] = (datetime.now(timezone.utc) + timedelta(minutes=48)).isoformat()
    session["quote_refresh_count"] = int(session.get("quote_refresh_count", 0)) + 1
    session["quote_refreshed_at"] = datetime.now(timezone.utc).isoformat()
    return True


def _tone_policy(tone: str) -> dict[str, Any]:
    tone_upper = (tone or "MODERATE").upper()
    if tone_upper == "AGGRESSIVE":
        return {
            "max_step": 0.25,
            "escalate_early": True,
            "explain_before_concession": False,
            "concession_bias": 0.75,
        }
    if tone_upper == "PASSIVE":
        return {
            "max_step": 0.25,
            "escalate_early": False,
            "explain_before_concession": False,
            "concession_bias": 0.5,
        }
    if tone_upper == "CONFUSED":
        return {
            "max_step": 0.0,
            "escalate_early": False,
            "explain_before_concession": True,
            "concession_bias": 0.0,
        }
    return {
        "max_step": 0.5,
        "escalate_early": False,
        "explain_before_concession": False,
        "concession_bias": 1.0,
    }


async def classify_applicant_tone(user_message: str) -> dict[str, Any]:
    try:
        from backend.groq_client import groq_client
    except Exception:
        groq_client = None

    if groq_client is None:
        return _rule_based_tone_classification(user_message)

    prompt = f"{TONE_CLASSIFICATION_PROMPT}\n\nMessage: {user_message.strip()}"
    try:
        response = await groq_client.complete(
            [{"role": "user", "content": prompt}],
            max_tokens=80,
            temperature=0.0,
            require_json=True,
        )
        parsed = _safe_json_parse(response.content)
        tone = str(parsed.get("tone", "MODERATE")).upper()
        confidence = parsed.get("confidence", 0.5)
        return {"tone": tone, "confidence": float(confidence) if confidence is not None else 0.5}
    except Exception as exc:
        logger.warning("Tone classification fallback used: %s", exc)
        return _rule_based_tone_classification(user_message)


def _rule_based_tone_classification(user_message: str) -> dict[str, Any]:
    text = (user_message or "").lower()
    if any(word in text for word in ["joke", "go elsewhere", "hdfc", "sbi", "icici", "bajaj", "axis", "kotak"]):
        tone = "AGGRESSIVE"
    elif any(word in text for word in ["what does", "how is emi", "meaning", "p.a", "emi calculated", "explain"]):
        tone = "CONFUSED"
    elif any(word in text for word in ["is this the best", "just checking", "okay", "fine", "sounds good"]):
        tone = "PASSIVE"
    else:
        tone = "MODERATE"
    return {"tone": tone, "confidence": 0.55}


def build_first_counter_anchor(current_rate: float, risk_tier: str, top_positive_factor: str) -> str:
    reference_rate = 12.5 if (risk_tier or "").strip().lower() == "low" else 13.0 if (risk_tier or "").strip().lower() == "medium" else 14.0
    return (
        f"Your current rate of {current_rate:.2f}% already reflects a {risk_tier} profile - most applicants at your CIBIL band start at {reference_rate:.1f}% or higher. "
        f"That said, given your {top_positive_factor}, I can offer a better rate."
    )


def build_urgency_signal() -> str:
    return (
        "This rate is valid for the next 47 minutes. After that, I'll need to re-run the credit assessment as rates are updated daily."
    )


def build_relationship_manager_note(tone: str) -> str | None:
    tone_upper = (tone or "MODERATE").upper()
    if tone_upper == "AGGRESSIVE":
        return "I've applied our most competitive policy-standard adjustment for your profile."
    if tone_upper == "PASSIVE":
        return "I'm glad we could find a rate that works for you."
    if tone_upper == "CONFUSED":
        return "I'm here to ensure you're fully comfortable with the terms before we proceed."
    return None


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
    requested_rate: float,
    tone: str = "MODERATE"
) -> dict:
    """
    Calculate a smart concession based on risk profile, negotiation progress,
    and the applicant's counter-offer aggressiveness.
    """
    from app.utils import calculate_emi_components
    
    headroom = current_rate - floor_rate
    tone_upper = (tone or "MODERATE").upper()
    tone_policy = _tone_policy(tone_upper)
    
    if headroom <= 0:
        return {
            "action": "HOLD_FIRM",
            "new_rate": current_rate,
            "concession": 0.0,
            "reason": "floor_reached"
        }

    if tone_upper == "CONFUSED":
        return {
            "action": "EXPLAIN",
            "new_rate": current_rate,
            "concession": 0.0,
            "reason": "needs_clarity"
        }
    
    # Determine max step based on risk score
    if risk_score >= 80:
        max_step = 0.50
    elif risk_score >= 65:
        max_step = 0.25
    else:
        max_step = 0.0

    max_step = min(max_step, tone_policy["max_step"])

    if tone_upper == "AGGRESSIVE" and round_number == 1 and aggressiveness >= 0.7:
        max_step = min(max_step, 0.25)

    if tone_upper == "PASSIVE" and round_number == 1:
        max_step = min(max_step, 0.25)
    
    # Round factor decreases as negotiation progresses
    round_factor = 1 - ((round_number - 1) / max(max_rounds, 1)) * 0.5
    
    concession = min(max_step * round_factor * tone_policy["concession_bias"], headroom)
    
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
            "reason": "profile_insufficient",
            "tone": tone_upper,
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
        "savings_per_month": old_emi - new_emi,
        "tone": tone_upper,
    }


async def generate_counter_response(
    concession_result: dict,
    counter_analysis: dict,
    loan_context: dict,
    language: str,
    tone: str = "MODERATE",
    competitors: list[str] | None = None,
    memory_reference: str | None = None,
    urgency_signal: str | None = None,
    anchor_note: str | None = None,
    relationship_manager_note: str | None = None,
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
    tone_upper = (tone or "MODERATE").upper()
    competitor_note = build_competitor_response(competitors or []) if competitors else None
    reason = concession_result.get("reason", "profile_merit")
    response_style = {
        "AGGRESSIVE": "firm, calm, and policy-driven",
        "PASSIVE": "warm, reassuring, and concise",
        "CONFUSED": "educational before negotiation",
    }.get(tone_upper, "helpful and balanced")
    
    if concession_result["action"] == "EXPLAIN":
        prompt = f"""
The applicant does not fully understand the offer.

Explain p.a., EMI, and the rate in simple terms before negotiating.
Tone detected: {tone_upper}
Style: {response_style}
Language: {language}
Max 80 words.
Sound like a helpful relationship manager.
"""
    elif concession_result["action"] == "HOLD_FIRM":
        prompt = f"""
The applicant requested {requested_rate:.2f}% but we cannot reduce below {current_rate:.2f}%.

Explain firmly but kindly why this rate is our best offer.
Reference their risk profile: score {loan_context.get('risk_score', 'N/A')}, tier {loan_context.get('risk_tier', 'N/A')}.
Offer escalation as an alternative.
Tone detected: {tone_upper}
Style: {response_style}
{f'Competitor mention: {", ".join(competitors or [])}. Use it to stay confident, not defensive.' if competitors else ''}
{f'Memory reference: {memory_reference}' if memory_reference else ''}
{f'Anchor note: {anchor_note}' if anchor_note else ''}
Language: {language}. Max 60 words.
Sound like a helpful relationship manager.
"""
    else:
        prompt = f"""
We're reducing the rate from {current_rate:.2f}% to {new_rate:.2f}%.

The applicant asked for {requested_rate:.2f}%.
We met them partway.
{f'Anchor note: {anchor_note}' if anchor_note else ''}
{f'Competitor note: {competitor_note}' if competitor_note else ''}
{f'Memory reference: {memory_reference}' if memory_reference else ''}
{f'Urgency signal: {urgency_signal}' if urgency_signal else ''}
{f'Relationship manager note: {relationship_manager_note}' if relationship_manager_note else ''}

Explain this positively.
Mention they save ₹{savings:.0f}/month.
Tone detected: {tone_upper}
Style: {response_style}
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
        return _generate_fallback_response(
            concession_result,
            counter_analysis,
            loan_context,
            tone=tone_upper,
            competitors=competitors or [],
            memory_reference=memory_reference,
            urgency_signal=urgency_signal,
            anchor_note=anchor_note,
        )


def _generate_fallback_response(
    concession_result: dict,
    counter_analysis: dict,
    loan_context: dict,
    tone: str = "MODERATE",
    competitors: list[str] | None = None,
    memory_reference: str | None = None,
    urgency_signal: str | None = None,
    anchor_note: str | None = None,
) -> str:
    """Generate a simple fallback response when Groq is unavailable."""
    current_rate = loan_context.get("current_rate", 0)
    new_rate = concession_result.get("new_rate", current_rate)
    savings = concession_result.get("savings_per_month", 0)
    requested_rate = counter_analysis.get("requested_rate") or current_rate
    competitor_text = build_competitor_response(competitors or []) if competitors else None
    memory_text = f" {memory_reference}" if memory_reference else ""
    urgency_text = f" {urgency_signal}" if urgency_signal else ""
    anchor_text = f" {anchor_note}" if anchor_note else ""
    tone_upper = (tone or "MODERATE").upper()
    
    if concession_result["action"] == "EXPLAIN":
        return (
            f"Let me break this down simply: p.a. means per annum, so your interest is annualized. "
            f"EMI is your monthly instalment amount. {memory_text}{anchor_text}".strip()
        )
    if concession_result["action"] == "HOLD_FIRM":
        return (
            f"We appreciate your counter-offer of {requested_rate:.2f}%. "
            f"However, based on your risk profile (score: {loan_context.get('risk_score', 'N/A')}), "
            f"our current rate of {current_rate:.2f}% is the best we can offer. "
            f"If you'd like us to review this further, please use the escalation option."
            f"{memory_text}{anchor_text}"
        )
    else:
        return (
            f"Thank you for your counter-offer of {requested_rate:.2f}%. "
            f"We're happy to reduce your rate from {current_rate:.2f}% to {new_rate:.2f}%. "
            f"This means you save ₹{savings:.0f} every month on your EMI. "
            f"We appreciate your negotiation and are glad to meet you partway."
            f"{competitor_text or ''}{memory_text}{urgency_text}{anchor_text}"
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


def handle_tenure_request(
    user_message: str,
    current_tenure: int,
    loan_amount: float,
    current_rate: float
) -> dict:
    """
    Handle tenure modification requests from applicants.
    
    Supports:
    - Extending tenure (up to 84 months) - lowers EMI but increases total interest
    - Reducing tenure - may qualify for rate discount (lower risk = better rate)
    """
    text = (user_message or "").strip().lower()
    
    # Detect longer tenure keywords
    longer = any(
        w in text
        for w in [
            "longer", "more months", "extend", "zyada time",
            "aur samay", "more time", "increase tenure",
            "bada", "lamba", "jyada", "upar"
        ]
    )
    
    # Detect shorter tenure keywords
    shorter = any(
        w in text
        for w in [
            "shorter", "less months", "reduce tenure",
            "jaldi", "kam samay", "chhote", "kam mahine",
            "faster", "quick", "chhota", "kam"
        ]
    )
    
    # Handle longer tenure request
    if longer and current_tenure < 84:
        new_tenure = min(current_tenure + 12, 84)
        new_emi = calculate_emi_components(int(loan_amount), current_rate, new_tenure)["emi"]
        old_emi = calculate_emi_components(int(loan_amount), current_rate, current_tenure)["emi"]
        
        old_total = old_emi * current_tenure
        new_total = new_emi * new_tenure
        extra_interest = new_total - old_total
        
        return {
            "action": "EXTEND_TENURE",
            "new_tenure": new_tenure,
            "new_emi": new_emi,
            "emi_reduction": old_emi - new_emi,
            "extra_interest": extra_interest,
            "message": (
                f"Extended tenure to {new_tenure} months. "
                f"EMI reduces by ₹{old_emi - new_emi:.0f} "
                f"but total interest increases by ₹{extra_interest:.0f}. "
                f"New EMI: ₹{new_emi:,}/month"
            )
        }
    
    # Handle shorter tenure request with rate discount opportunity
    if shorter and current_tenure > 12:
        reduction = current_tenure - max(current_tenure - 18, 12)
        
        # If significantly reducing tenure, offer rate discount
        if reduction >= 12:
            rate_discount = 0.25
            new_rate = max(current_rate - rate_discount, 10.5)
            new_tenure = max(current_tenure - 12, 12)
            
            old_emi = calculate_emi_components(int(loan_amount), current_rate, current_tenure)["emi"]
            new_emi = calculate_emi_components(int(loan_amount), new_rate, new_tenure)["emi"]
            
            return {
                "action": "REDUCE_TENURE_WITH_RATE",
                "new_tenure": new_tenure,
                "new_rate": new_rate,
                "rate_discount": rate_discount,
                "new_emi": new_emi,
                "emi_change": new_emi - old_emi,
                "message": (
                    f"Reduced tenure to {new_tenure} months with {rate_discount}% rate discount. "
                    f"Shorter tenure = lower risk. "
                    f"New rate: {new_rate:.2f}%, New EMI: ₹{new_emi:,}/month"
                )
            }
        
        # Just reduce tenure without rate change
        new_tenure = max(current_tenure - 12, 12)
        new_emi = calculate_emi_components(int(loan_amount), current_rate, new_tenure)["emi"]
        old_emi = calculate_emi_components(int(loan_amount), current_rate, current_tenure)["emi"]
        
        return {
            "action": "REDUCE_TENURE",
            "new_tenure": new_tenure,
            "new_emi": new_emi,
            "emi_increase": new_emi - old_emi,
            "interest_savings": old_emi * current_tenure - new_emi * new_tenure,
            "message": (
                f"Reduced tenure to {new_tenure} months. "
                f"EMI increases by ₹{new_emi - old_emi:.0f} "
                f"but you save ₹{old_emi * current_tenure - new_emi * new_tenure:.0f} in total interest."
            )
        }
    
    # No valid tenure change request
    return {"action": "NO_CHANGE"}


def generate_negotiation_summary(session: dict) -> dict:
    """
    Generate a comprehensive summary after negotiation acceptance.
    
    Shows the actual savings achieved through negotiation,
    proving the negotiation changed real numbers.
    """
    history = session.get("history", [])
    
    if not history or len(history) < 2:
        # No negotiation happened, just accepted opening offer
        return {
            "rounds_taken": 0,
            "opening_rate": session.get("starting_rate", session.get("current_rate", 0)),
            "final_rate": session.get("current_rate", 0),
            "total_rate_reduction": 0.0,
            "monthly_emi_savings": 0,
            "total_interest_savings": 0,
            "negotiation_outcome": "accepted_opening_offer",
            "message_en": "You accepted the opening offer without negotiation.",
            "message_hi": "आपने बिना negotiation के opening offer accept किया।"
        }
    
    # Extract rates from history
    opening_rate = history[0].get("system_offer", session.get("starting_rate", 0))
    final_rate = session.get("current_rate", history[-1].get("system_offer", 0))
    total_concession = round(opening_rate - final_rate, 2)
    
    loan_amount = session.get("loan_amount", 0)
    tenure = session.get("tenure_months", 60)
    
    # Calculate EMI at opening and final rates
    opening_emi = calculate_emi_components(int(loan_amount), opening_rate, tenure)["emi"]
    final_emi = calculate_emi_components(int(loan_amount), final_rate, tenure)["emi"]
    
    monthly_savings = round(opening_emi - final_emi, 0)
    total_savings = round(monthly_savings * tenure, 0)
    
    # Determine outcome
    outcome = "successful" if total_concession > 0 else "accepted_opening_offer"
    
    # Build messages
    if total_concession > 0:
        message_en = (
            f"🎉 Congratulations! You negotiated a {total_concession}% rate reduction "
            f"(from {opening_rate:.2f}% to {final_rate:.2f}%), "
            f"saving ₹{monthly_savings:,}/month on EMI and ₹{total_savings:,.0f} "
            f"in total interest over {tenure} months."
        )
        message_hi = (
            f"🎉 बधाई! आपने {total_concession}% rate कम करवाई "
            f"({opening_rate:.2f}% से {final_rate:.2f}% तक), "
            f"हर महीने ₹{monthly_savings:,} बचत और कुल ₹{total_savings:,.0f} "
            f"interest बचत {tenure} महीनों में।"
        )
    else:
        message_en = "You accepted the opening offer without further negotiation."
        message_hi = "आपने बिना आगे negotiation के opening offer accept किया।"
    
    return {
        "rounds_taken": len(history) - 1,
        "opening_rate": opening_rate,
        "final_rate": final_rate,
        "total_rate_reduction": total_concession,
        "monthly_emi_savings": int(monthly_savings),
        "total_interest_savings": int(total_savings),
        "negotiation_outcome": outcome,
        "message_en": message_en,
        "message_hi": message_hi,
        "opening_emi": opening_emi,
        "final_emi": final_emi,
        "loan_amount": loan_amount,
        "tenure_months": tenure,
    }


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

    # Set initial validity (48 minutes)
    offer_valid_until = (datetime.now(timezone.utc) + timedelta(minutes=48)).isoformat()

    return {
        "session_id": str(uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "offer_valid_until": offer_valid_until,
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


async def counter_session(session: dict, applicant_message: str, requested_rate: float | None) -> dict:
    intent = detect_intent(applicant_message)
    score = session["risk_score"]
    tier = session["risk_tier"]
    current_rate = float(session["current_rate"])
    floor_rate = float(session["floor_rate"])

    # 1. Tone Detection
    tone_data = await classify_applicant_tone(applicant_message)
    tone = tone_data["tone"]
    
    # 2. Competitor Detection
    competitors = detect_competitor_mentions(applicant_message)
    
    # 3. Urgency Check & Refresh
    refreshed = _refresh_quote_if_needed(session)
    if refreshed:
        current_rate = session["starting_rate"] # Reset to start on refresh
        session["current_rate"] = current_rate
        session["concessions_given"] = 0
        session["rounds_completed"] = 0

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
        summary = generate_negotiation_summary(session)
        return {
            "offer": offer,
            "reasoning": "You indicated acceptance. Please confirm via the accept endpoint to finalize this offer.",
            "intent": intent,
            "can_negotiate_further": False,
            "negotiation_summary": summary,
        }

    if intent == "ESCALATION_REQUEST":
        offer = build_offer(session["loan_amount"], session["tenure_months"], current_rate, session["opening_offer"]["total_payable"])
        return {
            "offer": offer,
            "reasoning": "You requested a human review. Please use the escalation endpoint and we will route your case.",
            "intent": intent,
            "can_negotiate_further": False,
        }

    # Handle tenure modification requests
    if intent in ("TENURE_EXTEND_REQUEST", "TENURE_REDUCE_REQUEST"):
        if "previous_tenure" not in session:
            session["previous_tenure"] = session["tenure_months"]
        
        tenure_result = handle_tenure_request(
            user_message=applicant_message,
            current_tenure=session["tenure_months"],
            loan_amount=session["loan_amount"],
            current_rate=current_rate
        )
        
        if tenure_result["action"] == "NO_CHANGE":
            offer = build_offer(session["loan_amount"], session["tenure_months"], current_rate, session["opening_offer"]["total_payable"])
            return {
                "offer": offer,
                "reasoning": f"I couldn't understand your tenure request. Current tenure is {session['tenure_months']} months.",
                "intent": intent,
                "can_negotiate_further": True,
            }
        
        if tenure_result["action"] == "EXTEND_TENURE":
            session["tenure_months"] = tenure_result["new_tenure"]
            reasoning = tenure_result["message"]
        elif tenure_result["action"] == "REDUCE_TENURE_WITH_RATE":
            session["tenure_months"] = tenure_result["new_tenure"]
            session["current_rate"] = tenure_result["new_rate"]
            reasoning = tenure_result["message"]
        elif tenure_result["action"] == "REDUCE_TENURE":
            session["tenure_months"] = tenure_result["new_tenure"]
            reasoning = tenure_result["message"]
        else:
            reasoning = tenure_result.get("message", "Tenure updated.")
        
        offer = build_offer(session["loan_amount"], session["tenure_months"], session["current_rate"], session["opening_offer"]["total_payable"])
        return {
            "offer": offer,
            "reasoning": reasoning,
            "intent": intent,
            "can_negotiate_further": True,
            "tenure_change": {
                "action": tenure_result["action"],
                "old_tenure": session.get("previous_tenure", session["tenure_months"]),
                "new_tenure": session["tenure_months"],
            }
        }

    session["rounds_completed"] += 1
    max_rounds = session.get("max_negotiation_rounds", MAX_ROUNDS)
    rounds_remaining = max(0, max_rounds - session["rounds_completed"])

    # 4. Memory Reference
    memory_ref = build_memory_reference(session) if session["rounds_completed"] > 1 else None

    # 5. Counter Analysis
    analysis = analyze_counter_request(applicant_message, current_rate, floor_rate)
    
    # 6. Concession Logic with Tone
    concession_result = calculate_concession(
        risk_score=score,
        current_rate=current_rate,
        floor_rate=floor_rate,
        round_number=session["rounds_completed"],
        max_rounds=max_rounds,
        aggressiveness=analysis["aggressiveness"],
        requested_rate=analysis["requested_rate"],
        tone=tone
    )

    # 7. Anchoring (On first counter offer)
    anchor_note = None
    if session["rounds_completed"] == 1 and concession_result["action"] == "CONCEDE":
        anchor_note = build_first_counter_anchor(current_rate, tier, session["top_positive_factor"])

    # 8. Urgency Signal (After round 2)
    urgency_signal = None
    if session["rounds_completed"] >= 2:
        urgency_signal = build_urgency_signal()

    # 9. Relationship Manager Note
    rm_note = build_relationship_manager_note(tone)

    # 10. Generate Final AI Response
    ai_reasoning = await generate_counter_response(
        concession_result=concession_result,
        counter_analysis=analysis,
        loan_context={
            "risk_score": score,
            "risk_tier": tier,
            "current_rate": current_rate,
            "top_positive_factor": session["top_positive_factor"]
        },
        language="en", # Could be passed from session
        tone=tone,
        competitors=competitors,
        memory_reference=memory_ref,
        urgency_signal=urgency_signal,
        anchor_note=anchor_note,
        relationship_manager_note=rm_note
    )

    # Update session state if conceded
    if concession_result["action"] == "CONCEDE":
        session["current_rate"] = concession_result["new_rate"]
        session["concessions_given"] += 1

    proposed_rate = session["current_rate"]
    offer = build_offer(session["loan_amount"], session["tenure_months"], proposed_rate, session["opening_offer"]["total_payable"])
    
    can_more = (
        rounds_remaining > 0
        and session["concessions_given"] < session["max_concessions"]
        and proposed_rate > floor_rate
        and tier != "High"
        and tone.upper() != "AGGRESSIVE" # Aggressive tone might limit further automated negotiation
    )

    return {
        "offer": offer,
        "reasoning": ai_reasoning,
        "intent": intent,
        "can_negotiate_further": can_more,
        "tone": tone,
        "tone_confidence": tone_data["confidence"],
        "competitors": competitors,
        "urgency_signal": urgency_signal,
        "minutes_remaining": _minutes_remaining(session.get("offer_valid_until")),
        "memory_reference": memory_ref,
        "relationship_manager_note": rm_note
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
