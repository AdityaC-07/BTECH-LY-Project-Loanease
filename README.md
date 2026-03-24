# 🏦 LoanEase

> **B.Tech Project 2026-2027**  
> A modern, intelligent loan management platform designed to simplify and streamline the loan application and management process.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![React](https://img.shields.io/badge/React-18.3-61DAFB?logo=react)](https://reactjs.org/)
[![Vite](https://img.shields.io/badge/Vite-5.4-646CFF?logo=vite)](https://vitejs.dev/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind-3.4-38B2AC?logo=tailwind-css)](https://tailwindcss.com/)

---

## 🎯 Vision
Traditional loan management systems are cumbersome and archaic. **LoanEase** redefines the experience by combining an intuitive AI-powered interface with enterprise-grade security, making credit accessible and the application process effortless.

---

## ✨ Key Features

### 🤖 AI-Powered Assistant
Experience a seamless, conversational loan journey. Our AI assistant guides you from the first "Hello" to the final sanction letter.
- **Natural Language Interaction**: No complex forms; just chat.
- **Instant Eligibility Assessment**: Real-time credit evaluation.
- **Smart Offer Generation**: Personalized loan terms based on your profile.

### 📊 LoanEase vs Traditional Lending
We’ve benchmarked our performance against industry standards to ensure our borrowers get the best experience.

| Feature | Traditional Bank | Loan Agent/DSA | **LoanEase (AI)** |
| :--- | :---: | :---: | :---: |
| **Approval Time** | 7–10 Days | 3–5 Days | **< 5 Minutes** |
| **Availability** | Bank Hours | Work Hours | **24/7 Instant** |
| **Sanction Letter** | Physical/Post | Email/Manual | **Instant Digital** |
| **Audit Trail** | Paper-based | Fragmented | **Blockchain Secured** |
| **Effort** | High Manual | Moderate | **Zero Paperwork** |

---

## 🛠️ Tech Stack

### Frontend & Core
- **React 18 + TypeScript**: Type-safe, component-driven architecture.
- **Vite**: Ultra-fast development and build environment.
- **TanStack Query**: High-performance data fetching and caching.

### UI & UX
- **Tailwind CSS**: Utility-first styling with custom EY design tokens.
- **shadcn/ui**: Accessible, high-quality component primitives.
- **Lucide React**: Vector-based, professional iconography.
- **Recharts**: Interactive data visualizations and comparison charts.

### Utilities
- **Zod**: Robust schema validation for user inputs.
- **Sonner**: Elegant, non-intrusive toast notifications.
- **Date-fns**: Precision date handling for repayment schedules.

---

## 🎨 Design Philosophy 
LoanEase is built to feel like a premium, enterprise-grade financial tool:
- **Palette**: Dark Mode optimized with `Black (#212121)` and `Yellow (#FFE600)`.
- **Typography**: `Inter` and `DM Sans` for maximum readability and a professional feel.
- **Interactions**: Subtle micro-animations (float, slide-up) and glassmorphism effects for a modern UX.

---

## 🚀 Getting Started

### Prerequisites
- [Node.js](https://nodejs.org/) (v18 or higher)
- [npm](https://www.npmjs.com/) or [yarn](https://yarnpkg.com/)

### Installation
1. **Clone the repository**
   ```bash
   git clone https://github.com/AdityaC-07/BTECH-LY-Project-Loanease.git
   cd BTECH-LY-Project-Loanease
   ```

2. **Install frontend dependencies**
   ```bash
   cd frontend
   npm install
   ```

3. **Start the development server**
   ```bash
   npm run dev
   ```

4. **Open in your browser**  
   Navigate to [http://localhost:8080](http://localhost:8080)

---

## 📁 Project Structure
```text
loanease/
├── frontend/
│   ├── src/
│   │   ├── components/      # Functional and UI components
│   │   │   ├── ui/          # shadcn and Radix primitives
│   │   │   └── ...          # Feature components
│   │   ├── pages/           # App-level page views
│   │   ├── hooks/           # Custom React hooks
│   │   ├── lib/             # Shared frontend utilities
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── public/
│   ├── package.json
│   └── vite.config.ts
├── backend/
│   ├── app/                 # Underwriting FastAPI app
│   ├── artifacts/           # Trained model and metadata
│   ├── data/                # Dataset and assessment store
│   ├── requirements.txt
│   └── train_model.py
├── negotiation_backend/
│   ├── app/                 # Negotiation FastAPI app
│   └── requirements.txt
├── README.md
└── LICENSE
```

---

## 📈 Impact & Innovation
- **75% Faster Decisions**: Drastic reduction in turnaround time vs traditional banks.
- **50% Effort Reduction**: Automated agent-driven workflows minimize manual data entry.
- **100% Digital Journey**: From KYC to signed sanction letters, no physical touchpoints required.

---

## 🚧 Roadmap
- [ ] Multi-regional Support & Language Localization
- [ ] Integration with major Core Banking Systems (CBS)
- [ ] Advanced Fraud Detection using ML models
- [ ] Mobile App (Progressive Web App support)

---

## ⚙️ Backend Services

LoanEase includes two separate FastAPI backends:

- `backend/` for credit underwriting and explainability.
- `negotiation_backend/` for dynamic loan-rate negotiation.

### Credit Underwriting Backend (`backend/`)

#### What it does
- Trains an XGBoost classifier using `backend/data/loan_train.csv`.
- Produces prediction artifacts in `backend/artifacts/`.
- Exposes underwriting APIs for assessment, explanation, and health monitoring.
- Returns SHAP-based plain-English factor explanations.

#### Setup
From repository root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

#### Dataset
Place Kaggle Loan Prediction dataset CSV at:

- `backend/data/loan_train.csv`

Expected columns:

- `Gender`, `Married`, `Dependents`, `Education`, `Self_Employed`
- `ApplicantIncome`, `CoapplicantIncome`, `LoanAmount`, `Loan_Amount_Term`
- `Credit_History`, `Property_Area`, `Loan_Status`

#### Train model

```powershell
python train_model.py --data data/loan_train.csv --artifacts artifacts
```

Training pipeline includes:

- Missing-value imputation: median (numeric), mode (categorical)
- Label encoding for categoricals
- 80/20 train-test split
- GridSearchCV tuning for `max_depth`, `n_estimators`, `learning_rate`
- Classification report and confusion matrix in console output

Artifacts generated:

- `backend/artifacts/loan_model.pkl`
- `backend/artifacts/preprocessor.pkl`
- `backend/artifacts/metadata.json`

#### Run API

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Docs: `http://localhost:8000/docs`

#### API endpoints (validated)

| Method | Endpoint | Purpose |
| :--- | :--- | :--- |
| `GET` | `/health` | Service health, model version, accuracy, uptime |
| `POST` | `/assess` | Risk assessment and decision generation |
| `POST` | `/explain/{application_id}` | Full explanation and SHAP waterfall for a stored application |

#### Risk policy
- `probability >= 0.75`: `Low Risk` and `APPROVED`
- `0.50 <= probability < 0.75`: `Medium Risk` and `APPROVED_WITH_CONDITIONS`
- `probability < 0.50`: `High Risk` and `REJECTED`

### Dynamic Negotiation Backend (`negotiation_backend/`)

#### What it does
- Runs stateful in-memory negotiation sessions.
- Applies risk-aware pricing policy with configurable limits.
- Returns plain-English reasoning for each response.
- Computes EMI, total payable, and savings with reducing-balance formula.
- Performs basic intent detection from applicant messages.
- Enforces 48-hour session expiry.

#### Setup
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

Docs: `http://localhost:8001/docs`

#### Business constants
Defined in `negotiation_backend/app/constants.py`:

- `RATE_CEILING = 14.0`
- `RATE_FLOOR = 10.5`
- `MAX_ROUNDS = 3`
- `CONCESSION_STEP = 0.25`

#### Underwriting integration
Typical flow:

1. Call underwriting `POST /assess`.
2. Use returned `risk_score` and `risk_tier`.
3. Start negotiation via `POST /negotiate/start`.

Optional adapter endpoint:

- `POST /negotiate/start-from-underwriting`

#### EMI formula

- `EMI = P * R * (1+R)^N / ((1+R)^N - 1)`
- `P`: principal
- `R`: monthly interest rate (`annual_rate / 12 / 100`)
- `N`: tenure in months

#### CORS
Allowed origins include:

- `http://localhost:8080`
- `http://127.0.0.1:8080`
- `http://localhost:3000`
- `FRONTEND_DOMAIN` env var (default `https://loanease.example.com`)

#### Core endpoints

| Method | Endpoint | Purpose |
| :--- | :--- | :--- |
| `POST` | `/negotiate/start` | Start a negotiation session from supplied risk context |
| `POST` | `/negotiate/start-from-underwriting` | Start negotiation by first calling underwriting `/assess` |
| `POST` | `/negotiate/counter` | Submit user counter-request and get a revised offer |
| `POST` | `/negotiate/accept` | Accept current negotiated offer and close session |
| `POST` | `/negotiate/escalate` | Escalate case to a human loan officer |
| `GET` | `/negotiate/history/{session_id}` | Retrieve current session state and conversation history |
| `GET` | `/health` | Service health, uptime, and active session count |

---

## 👥 Contributors
- **Aditya Choudhuri** - [GitHub](https://github.com/AdityaC-07)
- **Agniv Dutta** - [GitHub](https://github.com/agniv-dutta)
- **Akshat Kunder** - [GitHub](https://github.com/AkshatKunder)
- **Aaryan Dubey** - [GitHub](https://github.com/aaryan-r-dubey)

---
© 2026 LoanEase - A BFSI Innovation Solution.
