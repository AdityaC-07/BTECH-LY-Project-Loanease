from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Groq
    GROQ_API_KEY: str
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
    
    # OCR
    MAX_UPLOAD_BYTES: int = 5 * 1024 * 1024  # 5MB
    
    # Blockchain
    BLOCKCHAIN_DIFFICULTY: int = 4
    
    # Frontend domains
    FRONTEND_DOMAIN: str = "https://loanease.example.com"
    
    class Config:
        env_file = ".env"

settings = Settings()
