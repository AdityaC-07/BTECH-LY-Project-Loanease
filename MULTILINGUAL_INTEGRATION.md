# LoanEase Multilingual Support Integration Guide

## Overview

LoanEase supports English and Hindi natively. The system includes:

1. **Translation Service** (Port 8002) - Backend API for dynamic translations
2. **Hardcoded Critical Strings** - Core messages in both languages for reliability
3. **Language Detection** - Auto-detect user language and switch UI accordingly
4. **Hinglish Support** - Accept Hindi written in English letters (e.g., "loan chahiye")
5. **Number Formatting** - Indian number format (₹5,00,000) in Hindi mode
6. **Intent Detection** - Hinglish intent recognition in negotiation backend

---

## Architecture

### Three Backend Services

```
Port 8000: Credit Underwriting Service
Port 8001: Dynamic Negotiation Service (+ Hinglish intent detection)
Port 8002: Translation Service (NEW)
```

### Frontend

- Language switcher UI in chat header (EN/HI pills)
- franc-min CDN for language detection
- Hardcoded translations in `/src/lib/translations.ts`
- Translation client with caching in `/src/lib/translationClient.ts`
- Language utilities in `/src/lib/languageUtils.ts`
- Language switcher component in `/src/components/LanguageSwitcher.tsx`

---

## Component Structure

### Frontend Files

```
frontend/
├── src/
│   ├── lib/
│   │   ├── translations.ts           # Hardcoded EN/HI strings
│   │   ├── translationClient.ts      # Backend API client + caching
│   │   ├── languageUtils.ts          # Detection, formatting, mapping
│   └── components/
│   │   └── LanguageSwitcher.tsx      # Language selector UI
│   └── hooks/
│       └── useLanguage.tsx           # Language context & hook
```

### Backend (Translation Service)

```
translation_backend/
├── app/
│   ├── main.py                       # FastAPI app, routes
│   ├── schemas.py                    # Pydantic models
│   ├── translation_service.py        # Google Translate wrapper
│   └── hinglish_intent.py            # Hinglish intent detection
├── requirements.txt
└── README.md
```

---

## Usage Guide

### Frontend Components

#### Language Switcher

Import and add to chat interface header:

```tsx
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { useState } from "react";

export const ChatInterface = () => {
  const [language, setLanguage] = useState<"en" | "hi">("en");

  return (
    <div>
      <LanguageSwitcher
        currentLanguage={language}
        onLanguageChange={setLanguage}
      />
      {/* Chat messages and UI */}
    </div>
  );
};
```

#### Using Translations

```tsx
import { TRANSLATIONS, getTranslation } from "@/lib/translations";
import { formatIndianCurrency, formatEMI } from "@/lib/languageUtils";

// Get hardcoded translation
const getWelcomeMessage = (language: "en" | "hi") => {
  return TRANSLATIONS.opening[language];
};

// Format currency in Hindi mode
const showLoanAmount = (amount: number, language: "en" | "hi") => {
  if (language === "hi") {
    return formatIndianCurrency(amount);
  }
  return `$${amount}`;
};

// Format EMI with label
const displayEMI = (amount: number, language: "en" | "hi") => {
  return formatEMI(amount, language);
};
```

#### Auto-detect Language

```tsx
import { detectLanguage } from "@/lib/languageUtils";

const handleUserInput = async (text: string) => {
  const result = await detectLanguage(text);
  if (result.language !== "unknown") {
    setLanguage(result.language);
  }
};
```

#### Fetch Dynamic Translations

For API responses or dynamic content:

```tsx
import { fetchTranslation } from "@/lib/translationClient";

const translateBotResponse = async (message: string, targetLang: "en" | "hi") => {
  const translated = await fetchTranslation(
    message,
    targetLang,
    "en",
    "http://localhost:8002"
  );
  return translated;
};
```

### Backend Services

#### Translation API (Port 8002)

Setup:

```powershell
cd translation_backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8002
```

**Endpoints:**

- `POST /translate` - Translate text (EN ↔ HI)
- `POST /detect-hinglish-intent` - Detect intent from Hinglish
- `GET /health` - Service health

**Example:**

```bash
curl -X POST "http://localhost:8002/translate" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Your loan has been approved",
    "source_language": "en",
    "target_language": "hi"
  }'
```

#### Negotiation Backend (Port 8001) - Enhanced

The existing negotiation backend now also detects Hinglish intents:

```powershell
cd negotiation_backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

When a user sends Hinglish (e.g., "aur kam karo"), the intent detection automatically recognizes:

- `"aur kam karo"` → `COUNTER_REQUEST`
- `"theek hai"` → `ACCEPTANCE`
- `"loan chahiye"` → `LOAN_REQUEST`

No modification needed in the frontend; intents are handled naturally.

---

## Hardcoded Critical Strings

All critical chatbot messages are hardcoded for reliability (no translation API dependency):

**File:** `frontend/src/lib/translations.ts`

### Available Strings

```typescript
TRANSLATIONS.opening          // Greeting message
TRANSLATIONS.kyc_intro        // KYC setup prompt
TRANSLATIONS.kyc_upload       // Document upload instruction
TRANSLATIONS.approved         // Approval message
TRANSLATIONS.rejected         // Rejection message
TRANSLATIONS.low_risk         // Risk tier label
TRANSLATIONS.rate             // "Rate" / "दर"
TRANSLATIONS.emi              // "EMI" / "ईएमआई"
TRANSLATIONS.negotiation_start

// ... and many more (see translations.ts for full list)
```

---

## Hinglish Intent Detection

### Supported Hinglish Phrases

Detected by both:
- `translation_backend/app/hinglish_intent.py`
- `negotiation_backend/app/intent.py` (enhanced)

**LOAN_REQUEST:**
- "loan chahiye", "mujhe loan", "loan lena hai", "loan de do", "meko loan"

**RATE_QUERY:**
- "kitna rate", "rate kya hai", "rate kitna", "interest kya", "interest kitna"

**COUNTER_REQUEST:**
- "aur kam karo", "ar kam karo", "aur neeche", "neeche lao", "kamtar karo", "discount do"

**ACCEPTANCE:**
- "theek hai", "manzoor", "accept", "bilkul", "ok beta", "chalo theek hai"

**CANCELLATION:**
- "cancel", "nahi chahiye", "band karo", "nahin", "na", "nahi"

**KYC_PROMPT:**
- "documents", "kyc", "pan card", "aadhar", "aadhaar", "pdf", "upload"

---

## Number & Currency Formatting

### Indian Number Format

```typescript
// ₹5,00,000 instead of ₹500,000
formatIndianNumber(500000);     // "5,00,000"
formatIndianCurrency(500000);   // "₹5,00,000"
```

### Time & Unit Labels

In Hindi mode:

```
"per month"     → "प्रति माह"
"per annum"     → "प्रति वर्ष"
"months"        → "महीने"
"years"         → "साल"
"minutes"       → "मिनट"
```

---

## Translation Caching

Translations are cached locally (24-hour TTL) to minimize API calls:

```typescript
// Automatic: first call hits backend, subsequent calls use cache
const translated = await fetchTranslation("Hello", "hi");

// Clear cache if needed
import { clearTranslationCache } from "@/lib/translationClient";
clearTranslationCache();
```

---

## Adding a New Language

### Step 1: Update Translation Service

**File:** `translation_backend/app/translation_service.py`

```python
SUPPORTED_LANGUAGES = {
    "en": "english",
    "hi": "hindi",
    "ta": "tamil",  # Add new language
}
```

### Step 2: Add Hardcoded Strings

**File:** `frontend/src/lib/translations.ts`

```typescript
export const TRANSLATIONS = {
  // Add Tamil translations alongside EN/HI
  opening: {
    en: "Hello!",
    hi: "नमस्ते!",
    ta: "வணக்கம்!",  // Add Tamil
  },
  // ... add all critical strings in new language
};
```

### Step 3: Update Intent Detection (if needed)

**File:** `translation_backend/app/hinglish_intent.py` or `negotiation_backend/app/intent.py`

Add phrase mappings for the new language.

### Step 4: Update Language Switcher

**File:** `frontend/src/components/LanguageSwitcher.tsx`

Add new language button:

```tsx
<button
  onClick={() => handleLanguageClick("ta")}
  className="..."
>
  TA
</button>
```

### Step 5: Update franc-min (if needed)

Verify language code is supported by franc-min:
- English: "eng"
- Hindi: "hin"
- Tamil: "tam"

---

## Testing

### Test Translation API

```bash
# Terminal 1: Start translation service
cd translation_backend
uvicorn app.main:app --port 8002

# Terminal 2: Test endpoint
curl -X POST "http://localhost:8002/translate" \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello","source_language":"en","target_language":"hi"}'
```

### Test Hinglish Intent Detection

```bash
curl -X POST "http://localhost:8002/detect-hinglish-intent" \
  -H "Content-Type: application/json" \
  -d '{"message":"aur kam karo"}'
```

### Test Frontend Language Switching

1. Start frontend: `cd frontend && npm run dev`
2. Open browser to `http://localhost:8080`
3. Click language switcher (EN/हि)
4. Verify UI text changes
5. Type Hindi or Hinglish text
6. Verify auto-detection toast appears

---

## Production Deployment

### Environment Variables (Translation Service)

Create `.env` in `translation_backend/`:

```
GOOGLE_TRANSLATE_API_KEY=  # Optional - uses free tier by default
FRONTEND_DOMAIN=https://loanease.com
```

### CORS Configuration

All three services have CORS enabled for:
- `http://localhost:8080` (dev)
- `https://loanease.com` (production)

### Scaling

- Use Redis for translation cache (replace localStorage client-side cache)
- Consider LibreTranslate self-hosting for larger deployments
- Monitor translation API rate limits (Google Translate free tier ~500K chars/month)

---

## Troubleshooting

### Translation Service Returns 500 Error

**Solution:** Verify `deep-translator` is installed:

```powershell
pip install deep-translator
```

### Hinglish Intents Not Detected

**Solution:** Check phrase spelling; Hinglish detection is case-insensitive and does substring matching.

Example working phrases:
- `"aur kam karo"` ✅
- `"AUR KAM KARO"` ✅
- `"thoda aur kam karo"` ✅
- `"aur karo kam"` ❌ (word order matters)

### Language Switcher Not Showing

**Solution:** Ensure `franc-min` CDN script is loaded in `index.html`:

```html
<script src="https://cdn.jsdelivr.net/npm/franc-min@6.1.0/index.min.js"></script>
```

### Translations Not Caching

**Solution:** Check browser localStorage is enabled and not full:

```javascript
// Test localStorage
localStorage.setItem("test", "1");
localStorage.removeItem("test");
```

---

## Summary

The multilingual system is designed to be:

✅ **Non-intrusive** - No modification to existing UI components  
✅ **Reliable** - Hardcoded critical strings, no API dependency  
✅ **Smart** - Auto-detects language, maps Hinglish to intents  
✅ **Performant** - Translation caching, CDN-based language detection  
✅ **Extensible** - Easy to add new languages following the pattern  
✅ **Production-ready** - CORS, error handling, fallbacks
