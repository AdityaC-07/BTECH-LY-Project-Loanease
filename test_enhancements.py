"""Quick validation tests for SHAP narration and Hinglish detection enhancements."""
import sys
sys.path.insert(0, "backend")
sys.path.insert(0, "translation_backend/app")

import numpy as np
from services.shap_narrator import generate_shap_narration, format_structured_shap_for_groq
from hinglish_intent import detect_language_and_style


def test_structured_shap_narration():
    """Test structured SHAP narration generation."""
    print("=" * 60)
    print("TEST 1: Structured SHAP Narration (English)")
    print("=" * 60)

    shap_values = np.array([0.15, -0.08, 0.05, -0.02, 0.01])
    feature_names = [
        "Credit_History",
        "ApplicantIncome",
        "LoanAmount",
        "Loan_Amount_Term",
        "CoapplicantIncome",
    ]
    feature_values = {
        "Credit_History": 1.0,
        "ApplicantIncome": 50000,
        "LoanAmount": 200000,
        "Loan_Amount_Term": 360,
        "CoapplicantIncome": 0,
    }

    result = generate_shap_narration(
        shap_values, feature_names, feature_values, "APPROVED", "en"
    )

    print(f"Summary: {result['summary']}")
    print(f"Primary Reason: {result['primary_reason']}")
    print(f"Positive factors: {len(result['positive_factors'])}")
    print(f"Negative factors: {len(result['negative_factors'])}")
    print(f"Improvement tips: {result['improvement_tips']}")
    assert result["language"] == "en"
    assert len(result["positive_factors"]) > 0
    assert "primary_reason" in result
    print("PASS\n")


def test_structured_shap_narration_hindi():
    """Test structured SHAP narration in Hindi."""
    print("=" * 60)
    print("TEST 2: Structured SHAP Narration (Hindi)")
    print("=" * 60)

    shap_values = np.array([0.15, -0.08, 0.05, -0.02, 0.01])
    feature_names = [
        "Credit_History",
        "ApplicantIncome",
        "LoanAmount",
        "Loan_Amount_Term",
        "CoapplicantIncome",
    ]
    feature_values = {
        "Credit_History": 1.0,
        "ApplicantIncome": 50000,
        "LoanAmount": 200000,
        "Loan_Amount_Term": 360,
        "CoapplicantIncome": 0,
    }

    result = generate_shap_narration(
        shap_values, feature_names, feature_values, "APPROVED_WITH_CONDITIONS", "hi"
    )

    print(f"Summary: {result['summary']}")
    print(f"Primary Reason: {result['primary_reason']}")
    assert result["language"] == "hi"
    assert "आपकी" in result["primary_reason"] or "credit" in result["primary_reason"]
    print("PASS\n")


def test_format_for_groq():
    """Test formatting structured SHAP for Groq prompt injection."""
    print("=" * 60)
    print("TEST 3: Format Structured SHAP for Groq")
    print("=" * 60)

    shap_values = np.array([0.15, -0.08, 0.05])
    feature_names = ["Credit_History", "ApplicantIncome", "LoanAmount"]
    feature_values = {
        "Credit_History": 1.0,
        "ApplicantIncome": 50000,
        "LoanAmount": 200000,
    }

    narration = generate_shap_narration(
        shap_values, feature_names, feature_values, "APPROVED", "en"
    )
    formatted = format_structured_shap_for_groq(narration)

    print(formatted[:400])
    assert "Decision:" in formatted
    assert "Positive Factors" in formatted
    print("\nPASS\n")


def test_detect_language_and_style():
    """Test enhanced Hinglish detection."""
    print("=" * 60)
    print("TEST 4: Hinglish Detection")
    print("=" * 60)

    # Test 1: Pure English
    result = detect_language_and_style("I want a loan of 5 lakhs")
    print(f"English input: {result}")
    assert result["input_style"] == "english"
    assert result["respond_in"] == "en"
    assert not result["is_hinglish"]

    # Test 2: Hindi Devanagari
    result = detect_language_and_style("मुझे लोन चाहिए")
    print(f"Devanagari input: {result}")
    assert result["input_style"] == "hindi_devanagari"
    assert result["respond_in"] == "hi"

    # Test 3: Hinglish (Latin script Hindi)
    result = detect_language_and_style("mujhe loan chahiye kitna rate hai")
    print(f"Hinglish input: {result}")
    assert result["input_style"] == "hinglish_latin"
    assert result["respond_in"] == "hi"
    assert result["is_hinglish"]
    assert result["hinglish_markers_found"] >= 2

    # Test 4: Mixed Hinglish with loan terms
    result = detect_language_and_style("bhai emi kam karo thoda")
    print(f"Mixed Hinglish: {result}")
    assert result["input_style"] == "hinglish_latin"

    print("PASS\n")


def test_stage_prompts():
    """Test stage prompt integration."""
    print("=" * 60)
    print("TEST 5: Stage Prompt Integration")
    print("=" * 60)

    sys.path.insert(0, "backend")
    from agents.prompts import get_system_prompt, STAGE_PROMPTS

    # Test that stage prompts exist
    assert "INITIATED" in STAGE_PROMPTS
    assert "KYC_PENDING" in STAGE_PROMPTS
    assert "CREDIT_ASSESSED" in STAGE_PROMPTS
    assert "NEGOTIATING" in STAGE_PROMPTS
    assert "SANCTIONED" in STAGE_PROMPTS

    # Test get_system_prompt with current_stage
    prompt = get_system_prompt("kyc", current_stage="KYC_PENDING")
    assert "KYC_PENDING" in prompt or "upload" in prompt.lower()
    print(f"KYC prompt length: {len(prompt)} chars")

    prompt = get_system_prompt("credit", current_stage="CREDIT_ASSESSED")
    assert "CREDIT_ASSESSED" in prompt or "credit assessment" in prompt.lower()
    print(f"Credit prompt length: {len(prompt)} chars")

    print("PASS\n")


if __name__ == "__main__":
    test_structured_shap_narration()
    test_structured_shap_narration_hindi()
    test_format_for_groq()
    test_detect_language_and_style()
    test_stage_prompts()
    print("=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)

