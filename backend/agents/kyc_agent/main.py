"""Backward-compatible re-export. Canonical KYC router lives in agents.kyc."""

from agents.kyc import router

__all__ = ["router"]
