from pydantic import BaseModel
from typing import Optional, List, Dict, Any


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
    groq_api_reachable: Optional[bool] = None
    primary_model: Optional[str] = None
    fallback_model: Optional[str] = None
    requests_today: Optional[int] = None
    fallback_activations: Optional[int] = None
    current_mode: Optional[str] = None
    last_error: Optional[str] = None
    active_sessions: Optional[int] = None


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


class IntentClassificationRequest(BaseModel):
    text: str


class IntentClassificationResponse(BaseModel):
    intent: str
    confidence: float
    language: str
    extracted: Dict[str, Any]
    model_used: Optional[str] = None
    fallback_used: Optional[bool] = None


class CreditExplanationRequest(BaseModel):
    credit_score: int
    risk_score: int
    decision: str
    rate: float
    shap_factors: List[str]
    language: str = "en"


class NegotiationExplanationRequest(BaseModel):
    starting_rate: float
    current_rate: float
    floor_rate: float
    round: int
    max_rounds: int
    risk_tier: str
    positive_factor: str
    language: str = "en"


class RejectionMessageRequest(BaseModel):
    credit_score: int
    language: str = "en"
