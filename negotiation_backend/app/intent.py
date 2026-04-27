from __future__ import annotations


def detect_intent(message: str) -> str:
    """
    Detect intent from user message.
    Supports both English and Hinglish (Hindi in English letters).
    """
    text = (message or "").strip().lower()

    # English intent detection
    if any(
        k in text
        for k in [
            "talk to someone",
            "human",
            "manager",
            "loan officer",
            "escalate",
        ]
    ):
        return "ESCALATION_REQUEST"
    if any(k in text for k in ["i accept", "sounds good", "let's go", "lets go", "accept"]):
        return "ACCEPTANCE"
    if any(
        k in text
        for k in ["best you can do", "best offer", "final offer"]
    ):
        return "FINAL_OFFER_REQUEST"
    if any(
        k in text
        for k in ["pay more upfront", "upfront", "down payment"]
    ):
        return "TENURE_QUERY"
    # TENURE_REQUEST - longer tenure
    if any(
        k in text
        for k in [
            "longer",
            "more months",
            "extend tenure",
            "extend period",
            "zyada time",
            "aur samay",
            "more time",
            "increase tenure",
        ]
    ):
        return "TENURE_EXTEND_REQUEST"
    # TENURE_REQUEST - shorter tenure
    if any(
        k in text
        for k in [
            "shorter",
            "less months",
            "reduce tenure",
            "jaldi",
            "kam samay",
            "chhote tenure",
            "kam mahine",
            "faster",
            "quick repayment",
        ]
    ):
        return "TENURE_REDUCE_REQUEST"
    if any(
        k in text for k in ["i'll think", "ill think", "not sure", "later", "maybe"]
    ):
        return "HESITATION"
    if any(
        k in text
        for k in [
            "can you do better",
            "lower",
            "reduce",
            "decrease",
            "reduce the rate",
            "cheaper",
        ]
    ):
        return "COUNTER_REQUEST"

    # Hinglish intent detection (Hindi written in English letters)
    hinglish_intent = detect_hinglish_intent(message)
    if hinglish_intent != "UNKNOWN":
        return hinglish_intent

    return "UNKNOWN"


def detect_hinglish_intent(message: str) -> str:
    """
    Detect intent from Hinglish input (Hindi written in English letters).
    Maps common Hinglish phrases to intents.
    """
    text = (message or "").strip().lower()

    # TENURE_QUERY (Hinglish variants)
    if any(
        k in text
        for k in [
            "tenure",
            "mahine",
            "months",
            "kitne mahine",
            "kitne mahino",
            "time period",
            "duration",
            "mahat",
        ]
    ):
        return "TENURE_QUERY"

    # LOAN_REQUEST
    if any(
        k in text
        for k in [
            "loan chahiye",
            "mujhe loan",
            "loan lena hai",
            "loan de do",
            "meko loan",
            "loan chiye",
            "loan pamta ho",
        ]
    ):
        return "LOAN_REQUEST"

    # RATE_QUERY
    if any(
        k in text
        for k in [
            "kitna rate",
            "rate kya hai",
            "rate kitna",
            "interest kya",
            "interest kitna",
            "rate kitna h",
            "sood kitna",
            "sood kya",
            "percentage kya",
        ]
    ):
        return "RATE_QUERY"

    # COUNTER_REQUEST (negotiation)
    if any(
        k in text
        for k in [
            "aur kam karo",
            "ar kam karo",
            "thoda aur kam karo",
            "aur neeche",
            "neeche lao",
            "kamtar karo",
            "kam ho sakta",
            "discount do",
            "better rate",
            "aur km kro",
        ]
    ):
        return "COUNTER_REQUEST"

    # TENURE_EXTEND_REQUEST (Hinglish)
    if any(
        k in text
        for k in [
            "zyada time",
            "aur samay",
            "jyada mahine",
            "jyade mahine",
            "more time",
            "extend",
            "bada tenure",
            "bada time",
            "lamba tenure",
            "lamba time",
        ]
    ):
        return "TENURE_EXTEND_REQUEST"

    # TENURE_REDUCE_REQUEST (Hinglish)
    if any(
        k in text
        for k in [
            "kam time",
            "kam samay",
            "chhote tenure",
            "chhota tenure",
            "kam mahine",
            "jaldi",
            "jldi",
            "chhota time",
            "chhoti tenure",
            "faster",
        ]
    ):
        return "TENURE_REDUCE_REQUEST"

    # ACCEPTANCE
    if any(
        k in text
        for k in [
            "theek hai",
            "manzoor",
            "accept",
            "sahi h",
            "bilkul",
            "tha k hai",
            "thik hai",
            "ok beta",
            "chalo theek hai",
            "haan accept",
        ]
    ):
        return "ACCEPTANCE"

    # CANCELLATION
    if any(
        k in text
        for k in [
            "cancel",
            "nahi chahiye",
            "band karo",
            "nahin",
            "na",
            "nahi",
            "mujhe nahi",
            "chhod do",
            "hat jao",
            "next please",
        ]
    ):
        return "CANCELLATION"

    # KYC_PROMPT
    if any(
        k in text
        for k in [
            "documents",
            "kyc",
            "pan card",
            "aadhar",
            "aadhaar",
            "pan",
            "adhar",
            "doc",
            "patrakaari",
            "pdf",
            "upload",
        ]
    ):
        return "KYC_PROMPT"

    # ESCALATION_REQUEST (Hinglish variants)
    if any(
        k in text
        for k in [
            "kisi se baat karo",
            "manager se baat",
            "humko escalate karo",
            "dikha diyo",
        ]
    ):
        return "ESCALATION_REQUEST"

    return "UNKNOWN"
