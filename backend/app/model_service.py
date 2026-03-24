from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap  # type: ignore[import-not-found]


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
        raw_row = {dataset_col: payload[request_col] for request_col, dataset_col in REQUEST_TO_DATASET_COLUMN.items()}
        X_encoded = self._normalize_input(payload)
        probability = self._approval_probability(X_encoded)
        decision, risk_tier = self._risk_decision(probability)
        risk_score = int(round(probability * 100))
        waterfall, top_explanations = self._build_shap_breakdown(X_encoded, raw_row)

        return {
            "decision": decision,
            "approval_probability": round(probability, 4),
            "risk_tier": risk_tier,
            "risk_score": risk_score,
            "shap_explanation": top_explanations,
            "threshold_used": self.threshold,
            "raw_input": raw_row,
            "shap_waterfall": waterfall,
        }
