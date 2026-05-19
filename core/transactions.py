"""Transaction persistence and CSV import."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import BinaryIO

import pandas as pd
from bson.objectid import ObjectId
from pymongo import UpdateOne
from pymongo.errors import PyMongoError

from core.database import get_transactions_collection

logger = logging.getLogger(__name__)

REQUIRED_CSV_COLUMNS = ("Date", "Amount", "Remark")
DATE_FORMAT = "%d-%m-%Y"


class TransactionError(Exception):
    """Raised when a transaction operation fails validation or persistence."""


def recalculate_running_totals() -> None:
    """Recompute running_total for all rows in chronological order."""
    coll = get_transactions_collection()
    ops: list[UpdateOne] = []
    running_total = 0.0
    for doc in coll.find(sort=[("date", 1), ("_id", 1)]):
        running_total += float(doc["amount"])
        if doc.get("running_total") != running_total:
            ops.append(
                UpdateOne({"_id": doc["_id"]}, {"$set": {"running_total": running_total}})
            )
    if ops:
        coll.bulk_write(ops, ordered=True)


def parse_csv_data(source: str | Path | BinaryIO) -> pd.DataFrame:
    """Parse and validate rent-tracker CSV data."""
    df = pd.read_csv(source)
    missing = [col for col in REQUIRED_CSV_COLUMNS if col not in df.columns]
    if missing:
        raise TransactionError(f"CSV missing required columns: {', '.join(missing)}")

    df = df[list(REQUIRED_CSV_COLUMNS)].copy()
    if df.empty:
        raise TransactionError("CSV file contains no data rows.")

    try:
        df["Date"] = pd.to_datetime(df["Date"], format=DATE_FORMAT)
    except (ValueError, TypeError) as exc:
        raise TransactionError(
            f"Dates must use format {DATE_FORMAT} (e.g. 15-03-2024)."
        ) from exc

    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce")
    if df["Amount"].isna().any():
        raise TransactionError("CSV contains invalid non-numeric amounts.")

    df["Remark"] = df["Remark"].astype(str).str.strip()
    if (df["Remark"] == "").any():
        raise TransactionError("CSV contains empty remarks.")

    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
    df = df.rename(columns={"Date": "date", "Amount": "amount", "Remark": "remark"})
    return df.sort_values(["date", "remark"]).reset_index(drop=True)


def import_csv_to_db(source: str | Path | BinaryIO) -> int:
    """Replace all transactions with validated CSV contents. Returns row count."""
    df = parse_csv_data(source)
    coll = get_transactions_collection()
    coll.delete_many({})
    documents = [
        {
            "date": row["date"],
            "amount": float(row["amount"]),
            "remark": row["remark"],
            "running_total": 0.0,
        }
        for _, row in df.iterrows()
    ]
    if documents:
        coll.insert_many(documents)
    recalculate_running_totals()
    return len(documents)


def validate_transaction_input(date: str, amount: float, remark: str) -> None:
    if not date:
        raise TransactionError("Date is required.")
    if remark is None or not str(remark).strip():
        raise TransactionError("Remark is required.")
    if amount == 0:
        raise TransactionError("Amount cannot be zero.")


def add_transaction(date: str, amount: float, remark: str) -> None:
    validate_transaction_input(date, amount, remark)
    coll = get_transactions_collection()
    coll.insert_one(
        {
            "date": date,
            "amount": float(amount),
            "remark": str(remark).strip(),
            "running_total": 0.0,
        }
    )
    recalculate_running_totals()


def get_transactions_dataframe() -> pd.DataFrame:
    transactions = list(get_transactions_collection().find())
    if not transactions:
        return pd.DataFrame(columns=["id", "date", "amount", "remark", "running_total"])
    df = pd.DataFrame(transactions)
    df["id"] = df["_id"].astype(str)
    df = df.drop(columns=["_id"])
    return df[["id", "date", "amount", "remark", "running_total"]]


def generate_report(start_date: str, end_date: str) -> pd.DataFrame:
    if start_date > end_date:
        raise TransactionError("Start date must be on or before end date.")
    query = {"date": {"$gte": start_date, "$lte": end_date}}
    transactions = list(
        get_transactions_collection().find(query, sort=[("date", 1), ("_id", 1)])
    )
    if not transactions:
        return pd.DataFrame(columns=["date", "amount", "remark", "running_total"])
    df = pd.DataFrame(transactions)
    df = df.drop(columns=["_id"], errors="ignore")
    return df[["date", "amount", "remark", "running_total"]]


def update_transaction(transaction_id: str, new_date: str, new_amount: float, new_remark: str) -> bool:
    validate_transaction_input(new_date, new_amount, new_remark)
    try:
        oid = ObjectId(transaction_id)
    except Exception as exc:
        raise TransactionError("Invalid transaction id.") from exc

    coll = get_transactions_collection()
    result = coll.update_one(
        {"_id": oid},
        {
            "$set": {
                "date": new_date,
                "amount": float(new_amount),
                "remark": str(new_remark).strip(),
            }
        },
    )
    if result.matched_count == 0:
        return False
    recalculate_running_totals()
    return True


def delete_transactions(transaction_ids: list[str]) -> int:
    if not transaction_ids:
        return 0
    try:
        oids = [ObjectId(tid) for tid in transaction_ids]
    except Exception as exc:
        raise TransactionError("One or more transaction ids are invalid.") from exc

    coll = get_transactions_collection()
    result = coll.delete_many({"_id": {"$in": oids}})
    if result.deleted_count:
        recalculate_running_totals()
    return result.deleted_count


def import_uploaded_csv(uploaded_bytes: bytes) -> int:
    """Import from uploaded file bytes using a secure temp file."""
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp.write(uploaded_bytes)
        tmp_path = Path(tmp.name)
    try:
        return import_csv_to_db(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def run_db_operation(operation, success_message: str) -> tuple[bool, str]:
    """Execute a DB mutation with consistent error handling."""
    try:
        operation()
    except TransactionError as exc:
        return False, str(exc)
    except PyMongoError as exc:
        logger.exception("Database operation failed")
        return False, f"Database error: {exc}"
    return True, success_message
