from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from core.config import settings
from services.emi import calculate_emi as calc_emi


class IntakeState(str, Enum):
    WAITING_FOR_NAME = "WAITING_FOR_NAME"
    WAITING_FOR_MONTHLY_INCOME = "WAITING_FOR_MONTHLY_INCOME"
    WAITING_FOR_LOAN_AMOUNT = "WAITING_FOR_LOAN_AMOUNT"
    GENERATING_PREVIEW = "GENERATING_PREVIEW"
    COMPLETED = "COMPLETED"


class IntakeSessionData(BaseModel):
    full_name: Optional[str] = None
    monthly_income: Optional[int] = None
    loan_amount: Optional[int] = None


class IntakeResponse(BaseModel):
    session_id: str
    current_state: IntakeState
    message: str
    validation_error: Optional[str] = None
    eligibility_preview: Optional[Dict[str, Any]] = None
    proceed_to_kyc: bool = False


_INTRO_WELCOME = (
    "Welcome to LoanEase.\n"
    "I will first collect a few details before checking your eligibility."
)


_STATE_MESSAGES: Dict[IntakeState, str] = {
    IntakeState.WAITING_FOR_NAME: (
        "What is your full legal name as per your Aadhaar or PAN?"
    ),
    IntakeState.WAITING_FOR_MONTHLY_INCOME: (
        "Thanks, {name}.\nWhat is your monthly income (INR)?\n\n"
        "You can enter amounts like: 10000, 10,000, or ₹10,000"
    ),
    IntakeState.WAITING_FOR_LOAN_AMOUNT: (
        "Great.\nWhat loan amount would you like to apply for (INR)?\n\n"
        "You can enter amounts like: 200000, 2 lakh, 2L, or ₹2,00,000\n"
        "Maximum eligible amount: ₹{max_eligible:,}"
    ),
}

_INCOME_RE = re.compile(
    r"(?:₹|rs\.?|inr)?\s*([0-9][0-9,]*)\s*(?:/month)?",
    re.IGNORECASE,
)

_AMOUNT_RE = re.compile(
    r"(?:₹|rs\.?|inr)?\s*([0-9][0-9,]*)\s*(lakh|lakhs|lac|lacs|l|crore|cr|k|thousand)?",
    re.IGNORECASE,
)

_NAME_INVALID_RE = re.compile(r"[^a-zA-Z\s]")


class ConversationState:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.state: IntakeState = IntakeState.WAITING_FOR_NAME
        self.data = IntakeSessionData()

    def get_current_question(self) -> str:
        if self.state == IntakeState.WAITING_FOR_NAME:
            return _STATE_MESSAGES[IntakeState.WAITING_FOR_NAME]
        if self.state == IntakeState.WAITING_FOR_MONTHLY_INCOME:
            name = self.data.full_name or ""
            return _STATE_MESSAGES[IntakeState.WAITING_FOR_MONTHLY_INCOME].format(name=name)
        if self.state == IntakeState.WAITING_FOR_LOAN_AMOUNT:
            max_eligible = self._calc_max_eligible()
            return _STATE_MESSAGES[IntakeState.WAITING_FOR_LOAN_AMOUNT].format(max_eligible=max_eligible)
        if self.state == IntakeState.GENERATING_PREVIEW:
            return "Thank you.\nPreparing your quick eligibility preview..."
        return ""

    def get_welcome_message(self) -> str:
        return _INTRO_WELCOME

    def process_message(self, message: str) -> IntakeResponse:
        stripped = message.strip()
        if not stripped:
            return IntakeResponse(
                session_id=self.session_id,
                current_state=self.state,
                message=self.get_current_question(),
                validation_error="Input cannot be empty. Please enter the requested information.",
            )

        if self.state == IntakeState.WAITING_FOR_NAME:
            return self._handle_name(stripped)
        elif self.state == IntakeState.WAITING_FOR_MONTHLY_INCOME:
            return self._handle_income(stripped)
        elif self.state == IntakeState.WAITING_FOR_LOAN_AMOUNT:
            return self._handle_loan_amount(stripped)
        elif self.state == IntakeState.GENERATING_PREVIEW:
            preview = self._generate_preview()
            return IntakeResponse(
                session_id=self.session_id,
                current_state=self.state,
                message="Your quick eligibility preview is ready below.",
                eligibility_preview=preview,
                proceed_to_kyc=True,
            )

        return IntakeResponse(
            session_id=self.session_id,
            current_state=self.state,
            message=self.get_current_question(),
        )

    def _handle_name(self, name: str) -> IntakeResponse:
        if _NAME_INVALID_RE.search(name):
            return IntakeResponse(
                session_id=self.session_id,
                current_state=self.state,
                message="The name contains invalid characters. Please use only alphabetic characters and spaces.",
                validation_error="Invalid characters in name",
            )
        if len(name) < 2:
            return IntakeResponse(
                session_id=self.session_id,
                current_state=self.state,
                message="Please enter your full name (at least 2 characters).",
                validation_error="Name too short",
            )
        self.data.full_name = name.strip().title()
        self.state = IntakeState.WAITING_FOR_MONTHLY_INCOME
        return IntakeResponse(
            session_id=self.session_id,
            current_state=self.state,
            message=self.get_current_question(),
        )

    def _handle_income(self, raw: str) -> IntakeResponse:
        income = self._parse_income(raw)
        if income is None:
            return IntakeResponse(
                session_id=self.session_id,
                current_state=self.state,
                message="Please enter your monthly income as a valid number between INR 10,000 and INR 20,00,000. "
                        "Do not include currency symbols or commas.",
                validation_error="Could not parse income",
            )
        if income <= 0:
            return IntakeResponse(
                session_id=self.session_id,
                current_state=self.state,
                message="Monthly income must be greater than zero.",
                validation_error="Income must be positive",
            )
        if income < 10000:
            return IntakeResponse(
                session_id=self.session_id,
                current_state=self.state,
                message=f"Minimum monthly income required is INR 10,000. You entered INR {income:,}.",
                validation_error="Income below minimum",
            )
        if income > 2_000_000:
            return IntakeResponse(
                session_id=self.session_id,
                current_state=self.state,
                message=f"Maximum monthly income accepted is INR 20,00,000. You entered INR {income:,}.",
                validation_error="Income above maximum",
            )
        self.data.monthly_income = income
        self.state = IntakeState.WAITING_FOR_LOAN_AMOUNT
        return IntakeResponse(
            session_id=self.session_id,
            current_state=self.state,
            message=self.get_current_question(),
        )

    def _handle_loan_amount(self, raw: str) -> IntakeResponse:
        amount = self._parse_amount(raw)
        if amount is None:
            return IntakeResponse(
                session_id=self.session_id,
                current_state=self.state,
                message="Please enter a valid loan amount. Examples: 200000, 2 lakh, 2L, ₹2,00,000.",
                validation_error="Could not parse loan amount",
            )
        if amount < 50000:
            return IntakeResponse(
                session_id=self.session_id,
                current_state=self.state,
                message=f"Minimum loan amount is INR 50,000. You entered INR {amount:,}.",
                validation_error="Loan amount below minimum",
            )
        max_eligible = self._calc_max_eligible()
        if amount > max_eligible:
            return IntakeResponse(
                session_id=self.session_id,
                current_state=self.state,
                message=f"Maximum loan amount is INR {max_eligible:,} (15x your monthly income). "
                        f"Please enter a lower amount.",
                validation_error="Loan amount exceeds cap",
            )
        self.data.loan_amount = amount
        self.state = IntakeState.GENERATING_PREVIEW
        preview = self._generate_preview()
        return IntakeResponse(
            session_id=self.session_id,
            current_state=IntakeState.COMPLETED,
            message="Your quick eligibility preview is ready below.",
            eligibility_preview=preview,
            proceed_to_kyc=True,
        )

    def _parse_income(self, raw: str) -> Optional[int]:
        match = _INCOME_RE.search(raw)
        if not match:
            return None
        cleaned = match.group(1).replace(",", "")
        try:
            value = int(float(cleaned))
        except (ValueError, TypeError):
            return None
        return value

    def _parse_amount(self, raw: str) -> Optional[int]:
        match = _AMOUNT_RE.search(raw)
        if not match:
            return None
        cleaned = match.group(1).replace(",", "")
        try:
            value = int(float(cleaned))
        except (ValueError, TypeError):
            return None
        suffix = (match.group(2) or "").lower()
        if suffix in ("lakh", "lakhs", "lac", "lacs", "l"):
            value *= 100_000
        elif suffix in ("crore", "cr"):
            value *= 10_000_000
        elif suffix in ("k", "thousand"):
            value *= 1_000
        return value

    def _calc_max_eligible(self) -> int:
        if self.data.monthly_income:
            return min(self.data.monthly_income * 15, 2_500_000)
        return 2_500_000

    def _generate_preview(self) -> Dict[str, Any]:
        loan_amount = self.data.loan_amount or 0
        income = self.data.monthly_income or 0

        emi_result = calc_emi(float(loan_amount), 13.0, 5)
        estimated_emi = emi_result["monthly_emi"]
        emi_ratio = round(estimated_emi / income, 4) if income > 0 else 1.0

        if emi_ratio <= 0.50 and loan_amount <= income * 15:
            status = "Strong"
            status_text = "Strong. You meet our lending criteria."
        elif emi_ratio <= 0.60 and loan_amount <= income * 12:
            status = "Moderate"
            status_text = "Moderate. Subject to credit verification."
        else:
            status = "Weak"
            status_text = "Weak. May require additional documentation or co-applicant."

        return {
            "applicant_name": self.data.full_name or "",
            "loan_amount": loan_amount,
            "monthly_income": income,
            "tenure_months": 60,
            "assumed_rate": 13.0,
            "estimated_emi": round(estimated_emi, 2),
            "emi_to_income_ratio": emi_ratio,
            "status": status,
            "status_text": status_text,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "current_state": self.state.value,
            "data": self.data.model_dump(),
        }

    @classmethod
    def from_dict(cls, session_id: str, data: Dict[str, Any]) -> ConversationState:
        state = cls(session_id)
        state.state = IntakeState(data.get("current_state", IntakeState.WAITING_FOR_NAME.value))
        session_data = data.get("data", {})
        state.data = IntakeSessionData(
            full_name=session_data.get("full_name"),
            monthly_income=session_data.get("monthly_income"),
            loan_amount=session_data.get("loan_amount"),
        )
        return state

    def reset(self) -> None:
        self.state = IntakeState.WAITING_FOR_NAME
        self.data = IntakeSessionData()
