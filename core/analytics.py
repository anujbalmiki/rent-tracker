"""Transaction analytics and chart helpers."""

from __future__ import annotations

import pandas as pd


def _safe_sum(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    return float(series.sum())


def _safe_mean(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    value = series.mean()
    if pd.isna(value):
        return 0.0
    return float(value)


def analyze_transactions(df: pd.DataFrame) -> dict[str, float | int]:
    if df.empty:
        return {
            "total_rent": 0.0,
            "total_light_bills": 0.0,
            "total_payments": 0.0,
            "avg_monthly_rent": 0.0,
            "avg_light_bill": 0.0,
            "num_payments": 0,
            "current_balance": 0.0,
        }

    remarks = df["remark"].astype(str)
    rent_entries = df[remarks.str.contains("Rent", case=False, na=False)]
    light_bill_entries = df[remarks.str.contains("Light Bill", case=False, na=False)]
    payments = df[
        remarks.str.contains(r"Payment|Paid", case=False, na=False, regex=True)
    ]

    # Chronological order must match DB recalc: date, then id (ObjectId insert order).
    # Do not sort by running_total — same-day rows can have lower totals after payments.
    sort_cols = ["date", "id"] if "id" in df.columns else ["date"]
    sorted_df = df.sort_values(sort_cols)
    current_balance = float(sorted_df["running_total"].iloc[-1])

    return {
        "total_rent": _safe_sum(rent_entries["amount"]),
        "total_light_bills": _safe_sum(light_bill_entries["amount"]),
        "total_payments": abs(_safe_sum(payments["amount"])),
        "avg_monthly_rent": _safe_mean(rent_entries["amount"]),
        "avg_light_bill": _safe_mean(light_bill_entries["amount"]),
        "num_payments": int(len(payments)),
        "current_balance": current_balance,
    }
