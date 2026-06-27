from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_ENV_FILE = _BACKEND_DIR / ".env"
load_dotenv(_ENV_FILE, override=False)


class Settings(BaseSettings):    # Groq
    GROQ_API_KEY: str = ""
    GROQ_MODEL_PRIMARY: str = "llama-3.3-70b-versatile"
    GROQ_MODEL_FALLBACK: str = "llama-3.1-8b-instant"
    GROQ_TIMEOUT: int = 8
    CIBIL_BANDS: dict[str, dict[str, object]] = {
        "POOR": {"min": 300, "max": 549, "label": "Poor", "color": "red", "eligible": False},
        "FAIR": {"min": 550, "max": 649, "label": "Fair", "color": "orange", "eligible": True},
        "GOOD": {"min": 650, "max": 749, "label": "Good", "color": "yellow", "eligible": True},
        "VERY_GOOD": {"min": 750, "max": 799, "label": "Very Good", "color": "green", "eligible": True},
        "EXCELLENT": {"min": 800, "max": 900, "label": "Excellent", "color": "green", "eligible": True},
    }
    
    # Credit scoring
    CREDIT_SCORE_MIN: int = 300
    CREDIT_SCORE_MAX: int = 900
    HARD_REJECT_THRESHOLD: int = 300
    
    # Rate bands
    RATE_CEILING: float = 14.0
    RATE_FLOOR: float = 10.5
    CONCESSION_STEP: float = 0.25
    
    # XGBoost weights
    CIBIL_WEIGHT: float = 0.60
    XGBOOST_WEIGHT: float = 0.40
    
    # Session
    SESSION_TTL_HOURS: int = 24

    # Infra
    REDIS_URL: str | None = None
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://localhost:5174",
            "http://localhost:5175",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:5174",
            "http://127.0.0.1:5175",
        ]
    )
    
    # OCR / VLM KYC
    MAX_UPLOAD_BYTES: int = 5 * 1024 * 1024  # 5MB
    VLM_PROVIDER: str = "bedrock"  # bedrock | gemini
    GEMINI_API_KEY: str = ""
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    VLM_PRIMARY: str = "us.meta.llama3-2-11b-instruct-v1:0"
    VLM_FALLBACK: str = "us.meta.llama3-2-11b-instruct-v1:0"
    VLM_TIMEOUT: int = 60

    # OTP verification
    OTP_EXPIRY_MINUTES: int = 5
    SMS_PROVIDER: str = "auto"
    FAST2SMS_API_KEY: str = ""
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_VERIFY_SERVICE_SID: str = ""
    TWILIO_FROM_NUMBER: str = ""
    TEXTBELT_API_KEY: str = ""
    SMS_WEBHOOK_URL: str = ""
    
    # Blockchain
    BLOCKCHAIN_DIFFICULTY: int = 4
    
    # Frontend domains
    FRONTEND_DOMAIN: str = "https://loanease.example.com"
    
    # Demo mode — bypass OCR, use hardcoded scores, add artificial delays
    DEMO_MODE: bool = False

    # Run heavy checks (Groq ping, XGBoost predict) in background after server is up
    STARTUP_SELFTEST: bool = True
    
    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()


# ---------------------------------------------------------------------------
# CIBIL band lookup — enriches a raw score with rate, eligibility, and
# negotiation metadata expected by AssessResponse / credit-score endpoint.
# ---------------------------------------------------------------------------

_BAND_META: dict[str, dict] = {
    "POOR": {
        "label": "Poor",
        "display": "Poor Credit",
        "cibil_classification": "POOR",
        "color": "red",
        "eligible": False,
        "conditional": False,
        "rate_min": None,
        "rate_max": None,
        "max_rounds": 0,
    },
    "FAIR": {
        "label": "Fair",
        "display": "Fair / Below Average",
        "cibil_classification": "FAIR",
        "color": "orange",
        "eligible": True,
        "conditional": True,
        "rate_min": 13.5,
        "rate_max": 14.0,
        "max_rounds": 1,
    },
    "GOOD": {
        "label": "Good",
        "display": "Good Credit",
        "cibil_classification": "GOOD",
        "color": "yellow",
        "eligible": True,
        "conditional": False,
        "rate_min": 12.5,
        "rate_max": 14.0,
        "max_rounds": 2,
    },
    "VERY_GOOD": {
        "label": "Very Good",
        "display": "Very Good Credit",
        "cibil_classification": "VERY_GOOD",
        "color": "green",
        "eligible": True,
        "conditional": False,
        "rate_min": 11.0,
        "rate_max": 12.5,
        "max_rounds": 2,
    },
    "EXCELLENT": {
        "label": "Excellent",
        "display": "Excellent Credit",
        "cibil_classification": "EXCELLENT",
        "color": "green",
        "eligible": True,
        "conditional": False,
        "rate_min": 10.5,
        "rate_max": 11.5,
        "max_rounds": 3,
    },
}

_CIBIL_RANGES = [
    ("POOR",      300, 549),
    ("FAIR",      550, 649),
    ("GOOD",      650, 749),
    ("VERY_GOOD", 750, 799),
    ("EXCELLENT", 800, 900),
]


def get_band(score: int) -> dict:
    """Return enriched band metadata for a CIBIL score."""
    score = max(300, min(900, int(score)))
    for key, lo, hi in _CIBIL_RANGES:
        if lo <= score <= hi:
            return _BAND_META[key]
    return _BAND_META["POOR"]
