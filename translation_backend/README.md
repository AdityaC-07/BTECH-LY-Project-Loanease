# LoanEase Translation Service

FastAPI backend service for multilingual support (English & Hindi).

## What This Service Does

- Translates text between English and Hindi using Google Translate free tier.
- Detects intent from Hinglish input (Hindi written in English letters).
- Provides language detection and fallback handling.
- CORS enabled for frontend cross-origin requests.

## Setup

From repository root:

```powershell
cd translation_backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run Service

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8002
```

Swagger docs: `http://localhost:8002/docs`

## API Endpoints

### `POST /translate`

Translates text between English and Hindi.

**Request:**

```json
{
  "text": "Hello! What loan amount do you need?",
  "source_language": "en",
  "target_language": "hi"
}
```

**Response:**

```json
{
  "translated_text": "नमस्ते! आपको कितनी राशि की आवश्यकता है?",
  "source_language": "en",
  "target_language": "hi",
  "confidence": 0.95
}
```

### `POST /detect-hinglish-intent`

Detects intent from Hinglish (Hindi in English letters).

**Request:**

```json
{
  "message": "loan chahiye"
}
```

**Response:**

```json
{
  "message": "loan chahiye",
  "intent": "LOAN_REQUEST"
}
```

**Supported Hinglish Intents:**

- `LOAN_REQUEST` - "loan chahiye", "mujhe loan", "loan lena hai"
- `RATE_QUERY` - "kitna rate", "rate kya hai", "interest kya"
- `COUNTER_REQUEST` - "aur kam karo", "aur neeche", "kamtar karo"
- `ACCEPTANCE` - "theek hai", "manzoor", "accept"
- `CANCELLATION` - "cancel", "nahi chahiye", "band karo"
- `KYC_PROMPT` - "documents", "kyc", "pan card", "aadhar"

### `GET /health`

Returns service health and uptime.

## Environment Variables

None required. Service uses Google Translate free tier via deep-translator.

## How to Add a New Language

1. Update `SUPPORTED_LANGUAGES` in `app/translation_service.py`:

```python
SUPPORTED_LANGUAGES = {
    "en": "english",
    "hi": "hindi",
    "ta": "tamil",  # Add new language code
}
```

2. Add Hinglish mappings to `app/hinglish_intent.py` if needed.

3. Add hardcoded critical message strings to frontend translation constants.

4. Update franc-min language detection codes in frontend (if added).

## CORS Configuration

Allowed origins:

- `http://localhost:8080` (frontend dev)
- `http://127.0.0.1:8080`
- `http://localhost:3000`
- `https://loanease.example.com` (production)
