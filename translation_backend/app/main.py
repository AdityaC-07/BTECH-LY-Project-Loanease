from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import HealthResponse, TranslateRequest, TranslateResponse
from app.translation_service import TranslationService
from app.hinglish_intent import detect_hinglish_intent

app = FastAPI(title="LoanEase Translation Service", version="1.0.0")

frontend_domain = "https://loanease.example.com"
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:3000",
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
    uptime_seconds = int((datetime.now(timezone.utc) - boot_time).total_seconds())
    return HealthResponse(status="ok", uptime_seconds=uptime_seconds)
