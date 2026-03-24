from __future__ import annotations


def detect_intent(message: str) -> str:
    text = (message or "").strip().lower()

    if any(k in text for k in ["talk to someone", "human", "manager", "loan officer", "escalate"]):
        return "ESCALATION_REQUEST"
    if any(k in text for k in ["i accept", "sounds good", "let's go", "lets go", "accept"]):
        return "ACCEPTANCE"
    if any(k in text for k in ["best you can do", "best offer", "final offer"]):
        return "FINAL_OFFER_REQUEST"
    if any(k in text for k in ["pay more upfront", "upfront", "down payment"]):
        return "TENURE_QUERY"
    if any(k in text for k in ["i'll think", "ill think", "not sure", "later", "maybe"]):
        return "HESITATION"
    if any(k in text for k in ["can you do better", "lower", "reduce", "decrease", "reduce the rate", "cheaper"]):
        return "COUNTER_REQUEST"

    return "UNKNOWN"
