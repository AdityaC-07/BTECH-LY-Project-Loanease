from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap  # type: ignore[import-not-found]

from app.credit_score import get_credit_score, get_credit_band


REQUEST_TO_DATASET_COLUMN = {
    "gender": "Gender",
    "married": "Married",
    "dependents": "Dependents",
    "education": "Education",
    "self_employed": "Self_Employed",
    "applicant_income": "ApplicantIncome",
    "coapplicant_income": "CoapplicantIncome",
    "loan_amount": "LoanAmount",
    "loan_amount_term": "Loan_Amount_Term",
    "credit_history": "Credit_History",
    "property_area": "Property_Area",
}


class ModelService:
    def __init__(self, artifacts_dir: Path, threshold: float = 0.65) -> None:
        self.artifacts_dir = artifacts_dir
        self.threshold = threshold

        self.model = joblib.load(self.artifacts_dir / "loan_model.pkl")
        self.preprocessor = joblib.load(self.artifacts_dir / "preprocessor.pkl")

        self.feature_columns: list[str] = self.preprocessor["feature_columns"]
        self.numeric_columns: list[str] = self.preprocessor["numeric_columns"]
        self.categorical_columns: list[str] = self.preprocessor["categorical_columns"]
        self.medians: dict = self.preprocessor["medians"]
        self.modes: dict = self.preprocessor["modes"]
        self.feature_encoders: dict = self.preprocessor["feature_encoders"]
        self.target_encoder = self.preprocessor["target_encoder"]
        self.model_version: str = self.preprocessor.get("model_version", "unknown")
        self.metrics: dict = self.preprocessor.get("metrics", {})

        self.explainer = shap.TreeExplainer(self.model)

    def _normalize_input(self, payload: dict) -> pd.DataFrame:
        row = {dataset_col: payload[request_col] for request_col, dataset_col in REQUEST_TO_DATASET_COLUMN.items()}
        df = pd.DataFrame([row], columns=self.feature_columns)

        for col in self.numeric_columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(self.medians[col])

        for col in self.categorical_columns:
            df[col] = df[col].fillna(self.modes[col]).astype(str)
            enc = self.feature_encoders[col]
            default_value = self.modes[col]
            default_encoded = int(enc.transform([default_value])[0])
            mapped = []
            valid_values = set(enc.classes_.tolist())
            for value in df[col].tolist():
                if value in valid_values:
                    mapped.append(int(enc.transform([value])[0]))
                else:
                    mapped.append(default_encoded)
            df[col] = mapped

        return df

    def _approval_probability(self, X: pd.DataFrame) -> float:
        positive_encoded = int(self.target_encoder.transform(["Y"])[0])
        class_positions = {int(label): idx for idx, label in enumerate(self.model.classes_)}
        positive_idx = class_positions[positive_encoded]
        probabilities = self.model.predict_proba(X)[0]
        return float(probabilities[positive_idx])

    def _risk_decision(self, probability: float) -> tuple[str, str]:
        if probability >= 0.75:
            return "APPROVED", "Low Risk"
        if probability >= 0.50:
            return "APPROVED_WITH_CONDITIONS", "Medium Risk"
        return "REJECTED", "High Risk"

    def _feature_phrase(self, feature: str, value: float | str, shap_value: float) -> str:
        supports = shap_value >= 0
        direction = "supports" if supports else "reduces"

        if feature == "Credit_History":
            if supports:
                return "Strong credit history significantly supports approval"
            return "Weak or missing credit history increases rejection risk"

        if feature in {"ApplicantIncome", "CoapplicantIncome"}:
            if supports:
                return "Income profile improves repayment confidence"
            return "Income profile appears weaker for the requested loan"

        if feature == "LoanAmount":
            if supports:
                return "Requested loan amount is aligned with applicant profile"
            return "Higher requested loan amount raises risk concerns"

        pretty = feature.replace("_", " ")
        return f"{pretty} {direction} the approval outcome"

    def _build_shap_breakdown(self, X_encoded: pd.DataFrame, raw_row: dict) -> tuple[list[dict], list[str]]:
        shap_values = self.explainer.shap_values(X_encoded)

        if isinstance(shap_values, list):
            shap_row = np.array(shap_values[0][0], dtype=float)
        else:
            shap_array = np.array(shap_values)
            if shap_array.ndim == 3:
                shap_row = shap_array[0, :, 0].astype(float)
            else:
                shap_row = shap_array[0].astype(float)

        waterfall = []
        for idx, feature in enumerate(self.feature_columns):
            value = raw_row[feature]
            score = float(shap_row[idx])
            waterfall.append(
                {
                    "feature": feature,
                    "value": value,
                    "shap_value": score,
                    "impact": "positive" if score >= 0 else "negative",
                    "plain_english": self._feature_phrase(feature, value, score),
                }
            )

        waterfall_sorted = sorted(waterfall, key=lambda item: abs(item["shap_value"]), reverse=True)
        top_explanations = [item["plain_english"] for item in waterfall_sorted[:3]]
        return waterfall_sorted, top_explanations

    def assess(self, payload: dict) -> dict:
        """
        Assess loan application with credit score pre-filter.
        STEP 1: Get credit score from PAN
        STEP 2: Apply hard reject if score < 700
        STEP 3: Run XGBoost only if eligible
        STEP 4: Combine scores for final decision
        STEP 5: Determine interest rate from credit band
        """
        # STEP 1: Get credit score from PAN
        pan_number = payload.get("pan_number", "")
        preferred_language = payload.get("preferred_language", "en")
        
        credit_score = get_credit_score(pan_number)
        credit_band = get_credit_band(credit_score)

        # STEP 2: Hard reject if below 700
        if not credit_band["eligible"]:
            improvement_tips = [
                "Pay all existing EMIs on time",
                "Clear any outstanding credit card dues",
                "Avoid multiple loan applications in a short period",
                "Maintain credit utilization below 30%",
                "Wait 6 months before reapplying",
            ]
            
            message = (
                credit_band["message_en"].format(score=credit_score)
                if preferred_language == "en"
                else credit_band["message_hi"].format(score=credit_score)
            )
            
            return {
                "decision": "REJECTED",
                "credit_score": credit_score,
                "credit_score_out_of": 900,
                "credit_band": credit_band["label"],
                "credit_band_color": credit_band["color"],
                "risk_score": None,
                "risk_score_out_of": 100,
                "approval_probability": 0.0,
                "risk_tier": "High Risk",
                "offered_rate": None,
                "rate_range": None,
                "negotiation_allowed": False,
                "max_negotiation_rounds": 0,
                "xgboost_probability": 0.0,
                "xgboost_ran": False,
                "shap_explanation": [
                    f"Credit score {credit_score} below minimum threshold of 700",
                    "Applicant ineligible for loan at this time",
                    f"Score needs to improve by {700 - credit_score} points",
                ],
                "threshold_used": self.threshold,
                "raw_input": payload,
                "shap_waterfall": [],
                "message": message,
                "minimum_required": 700,
                "improvement_tips": improvement_tips,
            }

        # STEP 3: Run XGBoost only if eligible
        raw_row = {
            dataset_col: payload[request_col]
            for request_col, dataset_col in REQUEST_TO_DATASET_COLUMN.items()
        }
        X_encoded = self._normalize_input(payload)
        probability = self._approval_probability(X_encoded)
        xgboost_probability = probability
        decision, risk_tier = self._risk_decision(probability)
        waterfall, top_explanations = self._build_shap_breakdown(X_encoded, raw_row)

        # STEP 4: Combine scores (60% credit + 40% XGBoost)
        normalized_credit = (credit_score - 300) / 600 * 100  # Maps 300→0, 900→100
        combined_score = round((normalized_credit * 0.60) + (xgboost_probability * 100 * 0.40))

        # Final decision uses combined score
        if combined_score >= 75:
            final_decision = "APPROVED"
            final_risk_tier = "Low Risk"
        elif combined_score >= 50:
            final_decision = "APPROVED_WITH_CONDITIONS"
            final_risk_tier = "Medium Risk"
        else:
            final_decision = "REJECTED"
            final_risk_tier = "High Risk"

        # STEP 5: Determine interest rate from credit band
        # Use credit score band to set rate range
        # Fine-tune within range using XGBoost score
        rate = credit_band["rate_max"] - (
            (xgboost_probability) * (credit_band["rate_max"] - credit_band["rate_min"])
        )
        rate = round(rate * 4) / 4  # Round to nearest 0.25%

        return {
            "decision": final_decision,
            "credit_score": credit_score,
            "credit_score_out_of": 900,
            "credit_band": credit_band["label"],
            "credit_band_color": credit_band["color"],
            "risk_score": combined_score,
            "risk_score_out_of": 100,
            "approval_probability": round(probability, 4),
            "risk_tier": final_risk_tier,
            "offered_rate": rate,
            "rate_range": {
                "min": credit_band["rate_min"],
                "max": credit_band["rate_max"],
            },
            "negotiation_allowed": credit_band.get("negotiation_allowed", False),
            "max_negotiation_rounds": credit_band.get("max_negotiation_rounds", 0),
            "xgboost_probability": round(xgboost_probability, 2),
            "xgboost_ran": True,
            "shap_explanation": top_explanations,
            "threshold_used": self.threshold,
            "raw_input": raw_row,
            "shap_waterfall": waterfall,
        }
