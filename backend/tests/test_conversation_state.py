from __future__ import annotations

import pytest

from services.conversation_state import ConversationState, IntakeState


class TestConversationState:
    def test_initial_state(self):
        state = ConversationState("test-1")
        assert state.state == IntakeState.WAITING_FOR_NAME
        assert state.data.full_name is None
        assert state.data.monthly_income is None
        assert state.data.loan_amount is None

    def test_welcome_message(self):
        state = ConversationState("test-welcome")
        msg = state.get_welcome_message()
        assert "LoanEase" in msg

    def test_get_current_question_initial(self):
        state = ConversationState("test-q")
        q = state.get_current_question()
        assert "full legal name" in q.lower() or "name" in q.lower()

    def test_valid_name_transitions_to_income_state(self):
        state = ConversationState("test-name")
        resp = state.process_message("Priya Sharma")
        assert resp.current_state == IntakeState.WAITING_FOR_MONTHLY_INCOME
        assert resp.validation_error is None
        assert state.data.full_name == "Priya Sharma"

    def test_invalid_name_with_numbers(self):
        state = ConversationState("test-invalid-name")
        resp = state.process_message("Priya123")
        assert resp.current_state == IntakeState.WAITING_FOR_NAME
        assert resp.validation_error is not None

    def test_invalid_name_too_short(self):
        state = ConversationState("test-short")
        resp = state.process_message("A")
        assert resp.current_state == IntakeState.WAITING_FOR_NAME
        assert resp.validation_error is not None

    def test_empty_message(self):
        state = ConversationState("test-empty")
        resp = state.process_message("")
        assert resp.validation_error is not None

    def test_valid_income_with_number(self):
        state = ConversationState("test-income")
        state.data.full_name = "Amit"
        state.state = IntakeState.WAITING_FOR_MONTHLY_INCOME
        resp = state.process_message("75000")
        assert resp.current_state == IntakeState.WAITING_FOR_LOAN_AMOUNT
        assert state.data.monthly_income == 75000

    def test_valid_income_with_rupee_symbol(self):
        state = ConversationState("test-income-rs")
        state.data.full_name = "Amit"
        state.state = IntakeState.WAITING_FOR_MONTHLY_INCOME
        resp = state.process_message("₹75000")
        assert resp.current_state == IntakeState.WAITING_FOR_LOAN_AMOUNT
        assert state.data.monthly_income == 75000

    def test_valid_income_with_comma(self):
        state = ConversationState("test-income-comma")
        state.data.full_name = "Amit"
        state.state = IntakeState.WAITING_FOR_MONTHLY_INCOME
        resp = state.process_message("75,000")
        assert resp.current_state == IntakeState.WAITING_FOR_LOAN_AMOUNT
        assert state.data.monthly_income == 75000

    def test_income_below_minimum(self):
        state = ConversationState("test-income-low")
        state.data.full_name = "Amit"
        state.state = IntakeState.WAITING_FOR_MONTHLY_INCOME
        resp = state.process_message("5000")
        assert resp.current_state == IntakeState.WAITING_FOR_MONTHLY_INCOME
        assert resp.validation_error is not None
        assert "below" in resp.message.lower() or "minimum" in resp.message.lower()

    def test_income_above_maximum(self):
        state = ConversationState("test-income-high")
        state.data.full_name = "Amit"
        state.state = IntakeState.WAITING_FOR_MONTHLY_INCOME
        resp = state.process_message("5000000")
        assert resp.current_state == IntakeState.WAITING_FOR_MONTHLY_INCOME
        assert resp.validation_error is not None

    def test_income_edge_lowest_accepted(self):
        state = ConversationState("test-income-edge-low")
        state.data.full_name = "Amit"
        state.state = IntakeState.WAITING_FOR_MONTHLY_INCOME
        resp = state.process_message("10000")
        assert resp.current_state == IntakeState.WAITING_FOR_LOAN_AMOUNT
        assert state.data.monthly_income == 10000

    def test_income_edge_highest_accepted(self):
        state = ConversationState("test-income-edge-high")
        state.data.full_name = "Amit"
        state.state = IntakeState.WAITING_FOR_MONTHLY_INCOME
        resp = state.process_message("2000000")
        assert resp.current_state == IntakeState.WAITING_FOR_LOAN_AMOUNT
        assert state.data.monthly_income == 2000000

    def test_valid_loan_amount(self):
        state = ConversationState("test-loan")
        state.data.full_name = "Amit"
        state.data.monthly_income = 75000
        state.state = IntakeState.WAITING_FOR_LOAN_AMOUNT
        resp = state.process_message("500000")
        assert resp.current_state == IntakeState.COMPLETED
        assert state.data.loan_amount == 500000
        assert resp.proceed_to_kyc is True
        assert resp.eligibility_preview is not None

    def test_loan_amount_in_lakhs(self):
        state = ConversationState("test-loan-lakh")
        state.data.full_name = "Amit"
        state.data.monthly_income = 75000
        state.state = IntakeState.WAITING_FOR_LOAN_AMOUNT
        resp = state.process_message("5 lakh")
        assert resp.current_state == IntakeState.COMPLETED
        assert state.data.loan_amount == 500000

    def test_loan_amount_short_form_lakh(self):
        state = ConversationState("test-loan-5l")
        state.data.full_name = "Amit"
        state.data.monthly_income = 75000
        state.state = IntakeState.WAITING_FOR_LOAN_AMOUNT
        resp = state.process_message("5L")
        assert resp.current_state == IntakeState.COMPLETED
        assert state.data.loan_amount == 500000

    def test_loan_amount_with_rupee_symbol(self):
        state = ConversationState("test-loan-rs")
        state.data.full_name = "Amit"
        state.data.monthly_income = 75000
        state.state = IntakeState.WAITING_FOR_LOAN_AMOUNT
        resp = state.process_message("₹5,00,000")
        assert resp.current_state == IntakeState.COMPLETED
        assert state.data.loan_amount == 500000

    def test_loan_amount_below_minimum(self):
        state = ConversationState("test-loan-low")
        state.data.full_name = "Amit"
        state.data.monthly_income = 75000
        state.state = IntakeState.WAITING_FOR_LOAN_AMOUNT
        resp = state.process_message("10000")
        assert resp.current_state == IntakeState.WAITING_FOR_LOAN_AMOUNT
        assert resp.validation_error is not None

    def test_loan_amount_exceeds_cap(self):
        state = ConversationState("test-loan-high")
        state.data.full_name = "Amit"
        state.data.monthly_income = 75000
        state.state = IntakeState.WAITING_FOR_LOAN_AMOUNT
        resp = state.process_message("2000000")
        assert resp.current_state == IntakeState.WAITING_FOR_LOAN_AMOUNT
        assert resp.validation_error is not None

    def test_loan_amount_edge_lowest_accepted(self):
        state = ConversationState("test-loan-edge-low")
        state.data.full_name = "Amit"
        state.data.monthly_income = 100000
        state.state = IntakeState.WAITING_FOR_LOAN_AMOUNT
        resp = state.process_message("50000")
        assert resp.current_state == IntakeState.COMPLETED
        assert state.data.loan_amount == 50000

    def test_full_intake_flow(self):
        state = ConversationState("test-full")
        assert state.state == IntakeState.WAITING_FOR_NAME

        r1 = state.process_message("Rahul Verma")
        assert r1.current_state == IntakeState.WAITING_FOR_MONTHLY_INCOME

        r2 = state.process_message("60000")
        assert r2.current_state == IntakeState.WAITING_FOR_LOAN_AMOUNT

        r3 = state.process_message("300000")
        assert r3.current_state == IntakeState.COMPLETED
        assert r3.proceed_to_kyc is True
        assert r3.eligibility_preview is not None

        ep = r3.eligibility_preview
        assert ep["applicant_name"] == "Rahul Verma"
        assert ep["monthly_income"] == 60000
        assert ep["loan_amount"] == 300000

    def test_preview_eligibility_strong(self):
        state = ConversationState("test-strong")
        state.data.full_name = "Test"
        state.data.monthly_income = 200000
        state.data.loan_amount = 500000
        preview = state._generate_preview()
        assert preview["status"] == "Strong"
        assert preview["emi_to_income_ratio"] <= 0.50

    def test_preview_eligibility_consistent(self):
        state = ConversationState("test-consistent")
        state.data.full_name = "Test"
        state.data.monthly_income = 100000
        state.data.loan_amount = 1400000
        preview = state._generate_preview()
        assert preview["status"] == "Strong"
        assert preview["emi_to_income_ratio"] > 0

    def test_out_of_order_rejected(self):
        state = ConversationState("test-order")
        assert state.state == IntakeState.WAITING_FOR_NAME
        r = state.process_message("500000")
        assert r.current_state == IntakeState.WAITING_FOR_NAME

    def test_reset(self):
        state = ConversationState("test-reset")
        state.data.full_name = "John"
        state.data.monthly_income = 50000
        state.data.loan_amount = 200000
        state.state = IntakeState.COMPLETED
        state.reset()
        assert state.state == IntakeState.WAITING_FOR_NAME
        assert state.data.full_name is None

    def test_serialize_round_trip(self):
        state = ConversationState("test-serialize")
        state.data.full_name = "John"
        state.data.monthly_income = 60000
        state.data.loan_amount = 300000
        state.state = IntakeState.COMPLETED
        d = state.to_dict()
        restored = ConversationState.from_dict("test-serialize", d)
        assert restored.data.full_name == "John"
        assert restored.data.monthly_income == 60000
        assert restored.data.loan_amount == 300000
        assert restored.state == IntakeState.COMPLETED
