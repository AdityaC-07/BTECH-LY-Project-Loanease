"""
Graceful degradation fallback map for LoanEase components.

Every critical component has a documented primary → fallback path.
When a fallback is activated, it is logged clearly so the team can
diagnose issues immediately during a demo.
"""

import logging
from typing import Optional

logger = logging.getLogger("loanease.fallback")

FALLBACK_MAP = {
    "vlm_kyc_engine": {
        "primary": "amazon-bedrock-llama-3.2-11b-vision",
        "fallback": "amazon-bedrock-llama-3.2-11b-vision",
        "trigger": "Bedrock Converse returns error or raises exception",
    },
    "groq_api": {
        "primary": "llama-3.3-70b-versatile",
        "fallback_1": "llama-3.1-8b-instant",
        "fallback_2": "rule_based_responses",
        "trigger": "RateLimitError or APITimeoutError",
    },
    "xgboost_model": {
        "primary": "loan_model.pkl",
        "fallback": "rule_based_credit_scoring",
        "trigger": "model file not found or prediction error",
    },
    "blockchain_ledger": {
        "primary": "in_memory_chain",
        "fallback": "simple_hash_store",
        "trigger": "chain validation fails",
    },
}


def activate_fallback(
    component: str,
    fallback_name: str,
    reason: str,
    extra: Optional[str] = None,
) -> None:
    """Log a clearly formatted fallback activation warning."""
    msg = (
        f"⚠️ FALLBACK ACTIVATED: {component} → {fallback_name}. "
        f"Reason: {reason}"
    )
    if extra:
        msg += f" | {extra}"
    logger.warning(msg)
