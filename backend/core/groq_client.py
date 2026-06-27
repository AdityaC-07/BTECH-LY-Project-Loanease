import asyncio
import logging
import re
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services.groq_service import GroqService, get_groq_service

logger = logging.getLogger("loanease.groq")

# ---------------------------------------------------------------------------
# Enhancement 11: Financial Hindi/Hinglish terminology constants
# Keep EMI, PAN, CIBIL as-is (universally understood); Aadhaar → आधार in Hindi.
# ---------------------------------------------------------------------------
_FINANCE_GLOSSARY = """
Financial terminology guide (follow strictly):
- EMI = EMI (do NOT translate; write "EMI" in all languages)
- PAN = PAN (do NOT translate)
- CIBIL score = CIBIL स्कोर (Hindi), CIBIL score (Hinglish)
- Aadhaar = आधार (Hindi script only when replying in pure Hindi)
- Annual interest rate = सालाना ब्याज दर (Hindi) | annual rate (English)
- Loan sanction = ऋण मंजूरी (Hindi) | loan sanction (Hinglish)
- Loan amount = ऋण राशि (Hindi) | loan amount (Hinglish)
- Monthly income = मासिक आय (Hindi) | monthly income (Hinglish)
- Credit score = क्रेडिट स्कोर
- Down payment = डाउन पेमेंट (keep English in Hinglish)
- Processing fee = प्रोसेसिंग फीस (Hinglish) | processing fee (English)
- Repayment tenure = चुकौती अवधि (Hindi) | repayment tenure (Hinglish)
"""

_HINGLISH_FALLBACKS: dict[str, str] = {
    "greeting": "Namaste! Main aapki loan application mein madad karne ke liye yahan hoon.",
    "ask_pan": "Kripaya apna PAN number batayein.",
    "ask_income": "Aapki monthly income kitni hai?",
    "ask_loan": "Aap kitne ka loan lena chahte hain?",
    "processing": "Aapki application process ho rahi hai. Kripaya thoda wait karein.",
    "approved": "Mubarak ho! Aapka loan approve ho gaya hai.",
    "rejected": "Humein khed hai, abhi aap loan ke liye eligible nahi hain.",
    "emi_info": "Aapki monthly EMI {emi} rupaye hogi {tenure} mahine ke liye.",
    "rate_info": "Aapke liye interest rate {rate}% saalana hai.",
    "fallback": "Main samajh nahi paya. Kripaya dobara batayein ya English mein likhein.",
}

# Detect script/language confidence (simple heuristic — no external library needed)
_DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")
_LATIN_RE = re.compile(r"[a-zA-Z]")

def _detect_language(text: str) -> tuple[str, float]:
    """Return (lang, confidence): 'hi', 'hinglish', or 'en'."""
    deva = len(_DEVANAGARI_RE.findall(text))
    latin = len(_LATIN_RE.findall(text))
    total = deva + latin
    if total == 0:
        return "en", 0.5
    deva_ratio = deva / total
    if deva_ratio >= 0.6:
        return "hi", deva_ratio
    if deva_ratio >= 0.1:
        return "hinglish", 0.5 + deva_ratio
    return "en", 1.0 - deva_ratio


def _build_system_prompt(lang: str) -> str:
    """Return a language-appropriate system prompt with financial glossary."""
    base = (
        "You are LoanEase, a professional AI loan assistant at an Indian bank. "
        "Help applicants with loan applications, KYC, credit assessment, and EMI queries. "
        "Be empathetic, clear, and concise.\n\n"
        + _FINANCE_GLOSSARY
    )
    if lang == "hi":
        return (
            "आप LoanEase हैं — एक भारतीय बैंक का पेशेवर AI ऋण सहायक। "
            "आवेदकों को loan application, KYC, credit assessment और EMI queries में मदद करें। "
            "संक्षिप्त, स्पष्ट और सहानुभूतिपूर्ण रहें। केवल हिंदी में उत्तर दें।\n\n"
            + _FINANCE_GLOSSARY
        )
    if lang == "hinglish":
        return (
            "You are LoanEase — ek Indian bank ka AI loan assistant. "
            "Applicants ki loan application, KYC, credit, aur EMI queries mein help karein. "
            "Reply in Hinglish (Hindi-English mix) — friendly aur professional tone rakhein. "
            "Sahi financial terms use karein (EMI, PAN, CIBIL, आधार).\n\n"
            + _FINANCE_GLOSSARY
        )
    return base


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
    detected_language: Optional[str] = None
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


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, groq: GroqService = Depends(get_groq_service)):
    """Chat with AI assistant — supports English, Hindi, and Hinglish."""
    start_time = asyncio.get_event_loop().time()

    try:
        detected_lang, lang_confidence = _detect_language(request.message)
        # Prefer explicitly requested language unless it's 'en' and Devanagari detected
        effective_lang = (
            detected_lang
            if request.language == "en" and detected_lang in ("hi", "hinglish")
            else request.language
        )

        system_prompt = _build_system_prompt(effective_lang)

        try:
            reply, _trace = await asyncio.wait_for(
                groq.chat(
                    system_prompt=system_prompt,
                    messages=[{"role": "user", "content": request.message}],
                ),
                timeout=3.0,  # 3s Groq timeout → fallback on expiry
            )
            fallback_triggered = False
        except (asyncio.TimeoutError, Exception) as exc:
            logger.warning("Groq timeout/error (%s); using rule-based fallback", exc)
            reply = _HINGLISH_FALLBACKS.get("fallback", "Service temporarily unavailable. Please try again.")
            if effective_lang == "en":
                reply = "I'm having trouble connecting right now. Please try again in a moment."
            fallback_triggered = True

        response_time_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)
        status = groq.status() if not fallback_triggered else {"model": None, "fallback_used": True}

        return ChatResponse(
            message=reply,
            session_id=request.session_id,
            language=effective_lang,
            detected_language=detected_lang,
            model_used=status.get("model"),
            fallback_used=fallback_triggered or status.get("fallback_used"),
            response_time_ms=response_time_ms,
        )

    except Exception as e:
        logger.error("Chat endpoint error: %s", e)
        raise HTTPException(status_code=500, detail="Chat service unavailable")

@router.post("/translate", response_model=TranslateResponse)
async def translate_endpoint(
    request: TranslateRequest,
    groq: GroqService = Depends(get_groq_service),
):
    """Translate text using Groq"""
    try:
        if request.source_language == request.target_language:
            return TranslateResponse(
                translated_text=request.text,
                source_language=request.source_language,
                target_language=request.target_language,
                confidence=1.0,
            )

        prompt = (
            "Translate the following text from "
            f"{request.source_language} to {request.target_language}. "
            "Only return the translation, no explanations."
        )
        translated, _trace = await groq.chat(
            system_prompt=prompt,
            messages=[{"role": "user", "content": request.text}],
        )

        status = groq.status()
        return TranslateResponse(
            translated_text=translated,
            source_language=request.source_language,
            target_language=request.target_language,
            confidence=0.3 if status.get("fallback_used") else 0.8,
        )

    except Exception as e:
        logger.error("Translation error: %s", e)
        raise HTTPException(status_code=500, detail="Translation service unavailable")

@router.get("/health")
async def groq_health():
    """Groq service health check"""
    try:
        # Simple health check without dependency injection
        return {
            "connected": False,
            "model": None,
            "fallback_used": True,
            "status": "Groq service initialized"
        }
    except Exception as e:
        return {
            "connected": False,
            "model": None,
            "fallback_used": True,
            "status": f"Groq service error: {str(e)}"
        }
