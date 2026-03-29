from __future__ import annotations


def detect_hinglish_intent(message: str) -> str:
    """
    Detect intent from Hinglish input (Hindi written in English letters).
    Maps common Hinglish phrases to intents.
    """
    text = (message or "").strip().lower()

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

    # Default
    return "UNKNOWN"
