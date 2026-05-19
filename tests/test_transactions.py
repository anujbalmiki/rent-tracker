"""Unit tests for CSV parsing and analytics (no database required)."""

import io

import pandas as pd
import pytest

from core.analytics import analyze_transactions
from core.transactions import TransactionError, parse_csv_data


def test_parse_csv_valid():
    csv = "Date,Amount,Remark\n01-03-2024,5000,Rent\n02-03-2024,-2000,Payment\n"
    df = parse_csv_data(io.StringIO(csv))
    assert list(df.columns) == ["date", "amount", "remark"]
    assert len(df) == 2
    assert df.iloc[0]["date"] == "2024-03-01"


def test_parse_csv_missing_columns():
    csv = "Date,Amount\n01-03-2024,100\n"
    with pytest.raises(TransactionError, match="missing required columns"):
        parse_csv_data(io.StringIO(csv))


def test_parse_csv_bad_date():
    csv = "Date,Amount,Remark\n2024-03-01,100,Rent\n"
    with pytest.raises(TransactionError, match="Dates must use format"):
        parse_csv_data(io.StringIO(csv))


def test_analyze_empty():
    result = analyze_transactions(pd.DataFrame())
    assert result["current_balance"] == 0.0
    assert result["avg_monthly_rent"] == 0.0


def test_current_balance_uses_chronological_order_not_running_total():
    """Same-day payment after rent: balance is the last row in time, not max running_total."""
    df = pd.DataFrame(
        {
            "id": ["aaa", "bbb"],
            "date": ["2026-05-18", "2026-05-18"],
            "amount": [3200.0, -15000.0],
            "remark": ["April Rent 2026", "Paid Online"],
            "running_total": [48302.0, 33302.0],
        }
    )
    result = analyze_transactions(df)
    assert result["current_balance"] == 33302.0


def test_analyze_no_nan_averages():
    df = pd.DataFrame(
        {
            "date": ["2024-01-01"],
            "amount": [100.0],
            "remark": ["Misc"],
            "running_total": [100.0],
        }
    )
    result = analyze_transactions(df)
    assert result["avg_monthly_rent"] == 0.0
    assert result["current_balance"] == 100.0
