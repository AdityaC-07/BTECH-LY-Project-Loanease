import os
import logging
from typing import Optional, Dict, Any
import asyncio
from groq import Groq
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from core.config import settings

logger = logging.getLogger("loanease.groq")

# Global Groq client
_groq_client: Optional[Groq] = None
_groq_status = {"connected": False, "model": None, "fallback_used": False}

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    language: str = "en"

class ChatResponse(BaseModel):
    message: str
    action: str = "ASK_USER"
    confidence: float = 0.5
    session_id: str
    language: str
    model_used: Optional[str] = None
    fallback_used: Optional[bool] = None
    response_time_ms: Optional[int] = None

class TranslateRequest(BaseModel):
    text: str
    source_language: str = "en"
    target_language: str = "hi"

class TranslateResponse(BaseModel):
    translated_text: str
    source_language: str
    target_language: str
    confidence: float

router = APIRouter()

async def verify_connection() -> bool:
    """Verify Groq API connectivity"""
    global _groq_client, _groq_status
    
    if not settings.GROQ_API_KEY:
        logger.warning("Groq API key not configured")
        _groq_status = {"connected": False, "model": None, "fallback_used": True}
        return False
    
    try:
        # Initialize Groq client
        from groq import Groq
        # Remove any proxy-related parameters that might cause issues
        _groq_client = Groq(api_key=settings.GROQ_API_KEY)
        
        # Test connection with a simple request
        response = _groq_client.chat.completions.create(
            model=settings.GROQ_MODEL_PRIMARY,
            messages=[{"role": "user", "content": "test"}],
            max_tokens=1,
            timeout=settings.GROQ_TIMEOUT
        )
        
        _groq_status = {
            "connected": True,
            "model": settings.GROQ_MODEL_PRIMARY,
            "fallback_used": False
        }
        logger.info("Groq API connection verified")
        return True
        
    except Exception as e:
        logger.error(f"Groq API connection failed: {e}")
        _groq_status = {
            "connected": False,
            "model": None,
            "fallback_used": True
        }
        return False

def groq_status() -> Dict[str, Any]:
    """Get current Groq status"""
    return _groq_status.copy()

async def chat_with_groq(message: str, language: str = "en") -> tuple[str, bool, Optional[str]]:
    """Chat with Groq API"""
    global _groq_client, _groq_status
    
    if not _groq_client or not _groq_status["connected"]:
        # Fallback response
        if language == "hi":
            return "मैं वर्तमान में उपलब्ध नहीं हूं। कृपया बाद में प्रयास करें।", True, None
        return "I'm currently unavailable. Please try again later.", True, None
    
    try:
        system_prompt = "You are a helpful loan assistant. Be concise and professional."
        if language == "hi":
            system_prompt = "आप एक सहायक ऋण सहायक हैं। संक्षिप्त और पेशेवर रहें।"
        
        response = _groq_client.chat.completions.create(
            model=settings.GROQ_MODEL_PRIMARY,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ],
            max_tokens=150,
            timeout=settings.GROQ_TIMEOUT
        )
        
        reply = response.choices[0].message.content.strip()
        return reply, False, settings.GROQ_MODEL_PRIMARY
        
    except Exception as e:
        logger.error(f"Groq chat error: {e}")
        
        # Try fallback model
        if settings.GROQ_MODEL_FALLBACK != settings.GROQ_MODEL_PRIMARY:
            try:
                response = _groq_client.chat.completions.create(
                    model=settings.GROQ_MODEL_FALLBACK,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": message}
                    ],
                    max_tokens=150,
                    timeout=settings.GROQ_TIMEOUT
                )
                
                reply = response.choices[0].message.content.strip()
                _groq_status["fallback_used"] = True
                return reply, False, settings.GROQ_MODEL_FALLBACK
                
            except Exception as fallback_error:
                logger.error(f"Fallback model also failed: {fallback_error}")
        
        # Final fallback
        if language == "hi":
            return "मैं वर्तमान में उपलब्ध नहीं हूं। कृपया बाद में प्रयास करें।", True, None
        return "I'm currently unavailable. Please try again later.", True, None

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """Chat with AI assistant"""
    start_time = asyncio.get_event_loop().time()
    
    try:
        reply, fallback_used, model_used = await chat_with_groq(request.message, request.language)
        
        response_time_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)
        
        return ChatResponse(
            message=reply,
            session_id=request.session_id,
            language=request.language,
            model_used=model_used,
            fallback_used=fallback_used,
            response_time_ms=response_time_ms
        )
        
    except Exception as e:
        logger.error(f"Chat endpoint error: {e}")
        raise HTTPException(status_code=500, detail="Chat service unavailable")

@router.post("/translate", response_model=TranslateResponse)
async def translate_endpoint(request: TranslateRequest):
    """Translate text using Groq"""
    try:
        if request.source_language == request.target_language:
            return TranslateResponse(
                translated_text=request.text,
                source_language=request.source_language,
                target_language=request.target_language,
                confidence=1.0
            )
        
        prompt = f"Translate the following text from {request.source_language} to {request.target_language}. Only return the translation, no explanations:\n\n{request.text}"
        
        translated, fallback_used, model_used = await chat_with_groq(prompt, "en")
        
        return TranslateResponse(
            translated_text=translated,
            source_language=request.source_language,
            target_language=request.target_language,
            confidence=0.3 if fallback_used else 0.8
        )
        
    except Exception as e:
        logger.error(f"Translation error: {e}")
        raise HTTPException(status_code=500, detail="Translation service unavailable")

@router.get("/health")
async def groq_health():
    """Groq service health check"""
    return groq_status()
