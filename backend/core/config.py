from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Groq
    GROQ_API_KEY: str = ""
    GROQ_MODEL_PRIMARY: str = "llama-3.3-70b-versatile"
    GROQ_MODEL_FALLBACK: str = "llama-3.1-8b-instant"
    GROQ_TIMEOUT: int = 8
    
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
    
    # OCR
    MAX_UPLOAD_BYTES: int = 5 * 1024 * 1024  # 5MB

    # OTP verification
    OTP_EXPIRY_MINUTES: int = 5
    SMS_PROVIDER: str = "fast2sms"
    FAST2SMS_API_KEY: str = ""
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""
    
    # Blockchain
    BLOCKCHAIN_DIFFICULTY: int = 4
    
    # Frontend domains
    FRONTEND_DOMAIN: str = "https://loanease.example.com"
    
    # Demo mode — bypass OCR, use hardcoded scores, add artificial delays
    DEMO_MODE: bool = False
    
    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()
