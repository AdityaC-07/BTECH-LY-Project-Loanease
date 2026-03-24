from __future__ import annotations

from math import pow


def round_to_step(value: float, step: float = 0.25) -> float:
    return round(round(value / step) * step, 2)


def indian_number_format(value: int) -> str:
    s = str(abs(value))
    if len(s) <= 3:
        out = s
    else:
        out = s[-3:]
        s = s[:-3]
        while s:
            out = s[-2:] + "," + out
            s = s[:-2]
    return f"-{out}" if value < 0 else out


def calculate_emi_components(principal: int, annual_rate_percent: float, tenure_months: int) -> dict:
    monthly_rate = annual_rate_percent / 12 / 100
    if monthly_rate == 0:
        emi = principal / tenure_months
    else:
        factor = pow(1 + monthly_rate, tenure_months)
        emi = principal * monthly_rate * factor / (factor - 1)

    emi_rounded = int(round(emi))
    total_payable = int(round(emi_rounded * tenure_months))
    total_interest = int(round(total_payable - principal))

    return {
        "emi": emi_rounded,
        "total_payable": total_payable,
        "total_interest": total_interest,
    }


def with_currency_format(data: dict) -> dict:
    enriched = dict(data)
    for key in ["loan_amount", "emi", "total_payable", "total_interest", "savings_vs_opening"]:
        if key in enriched and enriched[key] is not None:
            enriched[f"{key}_formatted"] = indian_number_format(int(enriched[key]))
    return enriched
