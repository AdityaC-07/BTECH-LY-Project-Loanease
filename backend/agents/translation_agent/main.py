from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from core.groq_client import router as groq_router
from core.config import settings

logger = logging.getLogger("loanease.translation")

router = APIRouter()

# Import Groq endpoints from core
@router.post("/translate")
async def translate_endpoint():
    """Translation endpoint - delegates to Groq service"""
    # This is a placeholder - actual translation handled by Groq client
    return {"message": "Translation handled by Groq service at /ai/translate"}

@router.post("/detect-hinglish-intent")
async def detect_hinglish_intent():
    """Hinglish intent detection endpoint"""
    return {"message": "Hinglish detection handled by Groq service"}

@router.get("/health")
async def translation_health():
    """Translation service health check"""
    return {
        "status": "healthy",
        "service": "translation_agent",
        "groq_integration": True
    }
