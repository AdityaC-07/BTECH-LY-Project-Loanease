from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.schemas import (
    HealthResponse, TranslateRequest, TranslateResponse,
    ChatRequest, ChatResponse, IntentClassificationRequest, IntentClassificationResponse,
    CreditExplanationRequest, NegotiationExplanationRequest, RejectionMessageRequest
)
from app.translation_service import TranslationService
from app.hinglish_intent import detect_hinglish_intent
from app.groq_service import groq_service

app = FastAPI(title="LoanEase Translation + Groq Service", version="1.0.0")

frontend_domain = "https://loanease.example.com"
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:8081",
        "http://127.0.0.1:8081",
        "http://localhost:8082",
        "http://127.0.0.1:8082",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        frontend_domain,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

service = TranslationService()
boot_time = datetime.now(timezone.utc)


@app.post("/translate", response_model=TranslateResponse)
def translate(payload: TranslateRequest) -> TranslateResponse:
    """
    Translate text between languages.
    Supports 'en' and 'hi'.
    Uses deep-translator (Google Translate free tier).
    """
    try:
        result = service.translate(
            payload.text,
            source_language=payload.source_language,
            target_language=payload.target_language,
        )
        return TranslateResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(exc)}") from exc


@app.post("/detect-hinglish-intent")
def detect_hinglish(payload: dict) -> dict:
    """
    Detect intent from Hinglish input.
    Hinglish = Hindi written in English letters.
    """
    message = payload.get("message", "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message required")

    intent = detect_hinglish_intent(message)
    return {"message": message, "intent": intent}


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return groq_service.get_health_status()


# Groq-powered endpoints
@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Process chat message using Groq LLM with intelligent agent orchestration.
    """
    return await groq_service.process_chat_request(request)


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Stream chat response token by token for better UX.
    """
    async def generate():
        async for token in groq_service.stream_chat_response(request):
            yield token
    
    return StreamingResponse(
        generate(),
        media_type="text/plain"
    )


@app.post("/intent/classify", response_model=IntentClassificationResponse)
async def classify_intent(request: IntentClassificationRequest) -> IntentClassificationResponse:
    """
    Classify user intent using Groq for intelligent understanding.
    """
    return await groq_service.classify_intent(request)


@app.post("/explain/credit")
async def explain_credit(request: CreditExplanationRequest):
    """
    Generate credit decision explanation using Groq.
    """
    explanation = await groq_service.generate_credit_explanation(
        request.credit_score,
        request.risk_score,
        request.decision,
        request.rate,
        request.shap_factors,
        request.language
    )
    return {"explanation": explanation}


@app.post("/explain/negotiation")
async def explain_negotiation(request: NegotiationExplanationRequest):
    """
    Generate negotiation explanation using Groq.
    """
    explanation = await groq_service.generate_negotiation_explanation(
        request.starting_rate,
        request.current_rate,
        request.floor_rate,
        request.round,
        request.max_rounds,
        request.risk_tier,
        request.positive_factor,
        request.language
    )
    return {"explanation": explanation}


@app.post("/generate/rejection")
async def generate_rejection(request: RejectionMessageRequest):
    """
    Generate empathetic rejection message using Groq.
    """
    message = await groq_service.generate_rejection_message(
        request.credit_score,
        request.language
    )
    return {"message": message}


# Groq health endpoint
@app.get("/groq/health")
def groq_health():
    """
    Get detailed Groq API health and usage statistics.
    """
    return groq_service.client.get_health_status()
