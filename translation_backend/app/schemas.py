from pydantic import BaseModel


class TranslateRequest(BaseModel):
    text: str
    source_language: str = "en"
    target_language: str = "hi"


class TranslateResponse(BaseModel):
    translated_text: str
    source_language: str
    target_language: str
    confidence: float


class HealthResponse(BaseModel):
    status: str
    uptime_seconds: int
