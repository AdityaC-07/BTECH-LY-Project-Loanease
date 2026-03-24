# LoanEase Dynamic Negotiation Backend

Separate FastAPI service for real-time loan rate negotiation. This service is independent from the Credit Underwriting backend and does not modify frontend code.

## Features

- Stateful in-memory negotiation sessions.
- Risk-aware rate policy with configurable boundaries.
- Plain-English reasoning for every negotiation decision.
- EMI, total payable, and savings calculations using reducing balance formula.
- Basic keyword intent detection from applicant messages.
- 48-hour session expiry handling.

## Tech Stack

- Python 3.10+
- FastAPI
- Uvicorn
- Built-ins: uuid, datetime, math

## Project Structure

- `negotiation_backend/app/main.py` FastAPI app and endpoints.
- `negotiation_backend/app/service.py` policy logic and reasoning engine.
- `negotiation_backend/app/store.py` in-memory session store.
- `negotiation_backend/app/intent.py` keyword intent detection.
- `negotiation_backend/app/utils.py` EMI + Indian number formatting helpers.
- `negotiation_backend/app/constants.py` business boundaries.

## Business Constants

Defined in `app/constants.py`:

- `RATE_CEILING = 14.0`
- `RATE_FLOOR = 10.5`
- `MAX_ROUNDS = 3`
- `CONCESSION_STEP = 0.25`

## Setup

From repository root:

```powershell
cd negotiation_backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Run service:

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

Swagger docs:

- `http://localhost:8001/docs`

## Connect to Underwriting Agent

Typical flow:

1. Call Underwriting `POST /assess` first.
2. Use `risk_score` and `risk_tier` from that response.
3. Call Negotiation `POST /negotiate/start`.

Optional adapter:

- Call `POST /negotiate/start-from-underwriting` to let this service call Underwriting `POST /assess` for you and auto-seed negotiation context.

Example handoff payload:

```json
{
  "applicant_name": "Rahul Sharma",
  "risk_score": 87,
  "risk_tier": "Low",
  "loan_amount": 500000,
  "tenure_months": 60,
  "top_positive_factor": "credit history"
}
```

## EMI Formula

Used exactly as requested:

- `EMI = P * R * (1+R)^N / ((1+R)^N - 1)`
- `P` principal
- `R` monthly interest rate = annual_rate / 12 / 100
- `N` tenure in months

Returned monetary fields are rounded to nearest rupee and include Indian-format string fields (example: `5,00,000`).

## Session Expiry

- Each session stores `created_at` timestamp.
- Expiry window is 48 hours.
- Expiry is checked on counter, accept, escalate, and history calls.
- Expired sessions return `expired` status or HTTP `410` for counter.

## CORS

Allowed origins:

- `http://localhost:8080`
- `http://127.0.0.1:8080`
- `http://localhost:3000`
- `FRONTEND_DOMAIN` env var (defaults to `https://loanease.example.com`)

## Example curl Commands

### 1) Start negotiation

```bash
curl -X POST "http://localhost:8001/negotiate/start" \
  -H "Content-Type: application/json" \
  -d '{
    "applicant_name": "Rahul Sharma",
    "risk_score": 87,
    "risk_tier": "Low",
    "loan_amount": 500000,
    "tenure_months": 60,
    "top_positive_factor": "credit history"
  }'
```

### 1b) Start negotiation via underwriting adapter

```bash
curl -X POST "http://localhost:8001/negotiate/start-from-underwriting" \
  -H "Content-Type: application/json" \
  -d '{
    "applicant_name": "Rahul Sharma",
    "loan_amount": 500000,
    "tenure_months": 60,
    "underwriting_base_url": "http://localhost:8000",
    "assess_payload": {
      "gender": "Male",
      "married": "Yes",
      "dependents": "1",
      "education": "Graduate",
      "self_employed": "No",
      "applicant_income": 5000,
      "coapplicant_income": 1500,
      "loan_amount": 150,
      "loan_amount_term": 360,
      "credit_history": 1,
      "property_area": "Urban"
    }
  }'
```

### 2) Counter negotiation

```bash
curl -X POST "http://localhost:8001/negotiate/counter" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "<SESSION_ID>",
    "applicant_message": "Can you reduce the rate further?",
    "requested_rate": 10.5
  }'
```

### 3) Accept offer

```bash
curl -X POST "http://localhost:8001/negotiate/accept" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "<SESSION_ID>"
  }'
```

### 4) Escalate to human officer

```bash
curl -X POST "http://localhost:8001/negotiate/escalate" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "<SESSION_ID>",
    "reason": "applicant_requested"
  }'
```

### 5) Get negotiation history

```bash
curl "http://localhost:8001/negotiate/history/<SESSION_ID>"
```

### 6) Health check

```bash
curl "http://localhost:8001/health"
```
