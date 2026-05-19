"""Authentication helpers."""

from __future__ import annotations

import hashlib
import hmac

import streamlit as st


def _admin_credentials() -> tuple[str, str]:
    admin = st.secrets["admin"]
    return str(admin["username"]), str(admin["password"])


def authenticate_user(username: str, password: str) -> bool:
    """Verify username and password against Streamlit secrets."""
    expected_user, expected_password = _admin_credentials()
    if not username or not password:
        return False
    user_ok = hmac.compare_digest(username.strip(), expected_user)
    password_ok = hmac.compare_digest(
        hashlib.sha256(password.encode("utf-8")).hexdigest(),
        hashlib.sha256(expected_password.encode("utf-8")).hexdigest(),
    )
    return user_ok and password_ok
