# LoanEase Credit Underwriting Backend

FastAPI backend service for LoanEase's Credit Underwriting Agent.

## What This Service Does

- Trains an XGBoost classifier from Kaggle `loan_train.csv`.
- Stores model as `artifacts/loan_model.pkl` and preprocessing metadata as `artifacts/preprocessor.pkl`.
- Exposes REST APIs:
  - `POST /assess`
  - `POST /explain/{application_id}`
  - `GET /health`
- Generates SHAP explainability output for each assessment.

## 1) Setup

From the `backend` directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2) Dataset

Download Kaggle Loan Prediction dataset and place `loan_train.csv` at:

- `backend/data/loan_train.csv`

Expected columns:

- `Gender`, `Married`, `Dependents`, `Education`, `Self_Employed`
- `ApplicantIncome`, `CoapplicantIncome`, `LoanAmount`, `Loan_Amount_Term`
- `Credit_History`, `Property_Area`, `Loan_Status`

## 3) Train Model

```powershell
python train_model.py --data data/loan_train.csv --artifacts artifacts
```

Training includes:

- Missing values: median (numeric), mode (categorical)
- Label encoding for categorical features
- 80/20 train-test split
- GridSearchCV tuning: `max_depth`, `n_estimators`, `learning_rate`
- Console output of classification report and confusion matrix

Artifacts produced:

- `artifacts/loan_model.pkl`
- `artifacts/preprocessor.pkl`
- `artifacts/metadata.json`

## 4) Run API

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Swagger docs:

- `http://localhost:8000/docs`

## 5) API Contracts

### `POST /assess`

Request:

```json
{
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
```

Response (example):

```json
{
  "application_id": "8a206e59-3fbe-4c9e-a361-f4f1c4b67597",
  "decision": "APPROVED",
  "approval_probability": 0.87,
  "risk_tier": "Low Risk",
  "risk_score": 87,
  "shap_explanation": [
    "Strong credit history significantly supports approval",
    "Income profile improves repayment confidence",
    "Requested loan amount is aligned with applicant profile"
  ],
  "threshold_used": 0.65
}
```

Risk logic:

- `probability >= 0.75`: `Low Risk` and `APPROVED`
- `0.50 <= probability < 0.75`: `Medium Risk` and `APPROVED_WITH_CONDITIONS`
- `probability < 0.50`: `High Risk` and `REJECTED`

### `POST /explain/{application_id}`

Returns full SHAP waterfall payload for stored application.

### `GET /health`

Returns model version, test accuracy, and uptime.
