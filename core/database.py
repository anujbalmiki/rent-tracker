"""MongoDB connection helpers."""

from __future__ import annotations

import streamlit as st
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

DB_NAME = "rent_tracker"
COLLECTION_NAME = "transactions"


@st.cache_resource(show_spinner=False)
def get_mongo_client() -> MongoClient:
    """Create a cached MongoDB client and verify connectivity."""
    uri = st.secrets["mongo"]["uri"]
    client = MongoClient(
        uri,
        serverSelectionTimeoutMS=10_000,
        connectTimeoutMS=10_000,
        retryWrites=True,
    )
    client.admin.command("ping")
    return client


def get_transactions_collection() -> Collection:
    return get_mongo_client()[DB_NAME][COLLECTION_NAME]


def check_database_connection() -> tuple[bool, str]:
    """Return (ok, message) for health display."""
    try:
        get_mongo_client().admin.command("ping")
        return True, "Connected to database"
    except PyMongoError as exc:
        return False, f"Database unavailable: {exc}"
