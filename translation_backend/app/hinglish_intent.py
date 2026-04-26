from __future__ import annotations


# Hinglish markers for language detection (Hindi written in Latin script)
HINGLISH_MARKERS = [
    "mujhe", "chahiye", "kitna", "kya",
    "hai", "hoga", "nahi", "theek",
    "bhai", "yaar", "aur", "kam",
    "zyada", "lena", "dena", "batao",
    "karo", "thoda", "bahut", "accha",
    "loan", "rate", "emi",  # mixed loan terms
    "rupee", "paisa", "bank", "salary",
    "monthly", "saal", "mahina", "din",
    "aap", "tum", "mera", "tera",
    "kaise", "kyun", "kab", "kahan",
    "batao", "samajh", "matlab", "sahi",
    "galat", "problem", "tension", "fikar",
    "jaldi", "der", "time", "abhi",
    "pehle", "baad", "andar", "bahar",
    "chota", "bada", "kam", "zyada",
]


def detect_language_and_style(text: str) -> dict:
    """
    Detect the language and input style of user text.

    Handles three cases:
    1. Hindi in Devanagari script -> respond in Hindi Devanagari
    2. Hinglish (Hindi in Latin script) -> respond in Hindi Devanagari
    3. English -> respond in English

    Args:
        text: The user's input message.

    Returns:
        Dict with keys:
        - input_language: "en" or "hi"
        - input_style: "hindi_devanagari" | "hinglish_latin" | "english"
        - respond_in: "en" or "hi"
        - is_hinglish: bool
        - hinglish_markers_found: int
    """
    text = (text or "").strip()

    # Check Devanagari script
    has_devanagari = any(
        '\u0900' <= c <= '\u097F'
        for c in text
    )

    # Check Hinglish patterns (Hindi in Latin script)
    text_lower = text.lower()
    hinglish_count = sum(
        1 for marker in HINGLISH_MARKERS
        if marker in text_lower
    )

    is_hinglish = (
        hinglish_count >= 2 and
        not has_devanagari
    )

    # Determine response language
    if has_devanagari:
        response_lang = "hi"
        input_style = "hindi_devanagari"
    elif is_hinglish:
        response_lang = "hi"
        input_style = "hinglish_latin"
    else:
        response_lang = "en"
        input_style = "english"

    return {
        "input_language": response_lang,
        "input_style": input_style,
        "respond_in": response_lang,
        "is_hinglish": is_hinglish,
        "hinglish_markers_found": hinglish_count,
    }


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

