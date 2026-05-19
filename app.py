"""Rent Tracker — Streamlit application."""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from core.analytics import analyze_transactions
from core.auth import authenticate_user
from core.database import check_database_connection
from core.transactions import (
    TransactionError,
    add_transaction,
    delete_transactions,
    generate_report,
    get_transactions_dataframe,
    import_uploaded_csv,
    run_db_operation,
    update_transaction,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TABLE_COLUMNS = ("date", "amount", "remark", "running_total")
TABLE_LABELS = {
    "date": "Date",
    "amount": "Amount (₹)",
    "remark": "Description",
    "running_total": "Balance (₹)",
}


def init_session_state() -> None:
    for key, value in (("logged_in", False), ("username", ""), ("data_version", 0)):
        if key not in st.session_state:
            st.session_state[key] = value


def bump_data_version() -> None:
    st.session_state.data_version += 1


@st.cache_data(show_spinner=False, ttl=30)
def load_transactions(version: int) -> pd.DataFrame:
    del version
    return get_transactions_dataframe()


def format_currency(value: float) -> str:
    return f"₹{value:,.0f}"


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] { background-color: #f7f8fa; }

        /* Metric cards — parent overflow:hidden was clipping the top edge */
        [data-testid="stMetric"] {
            background: #fff;
            border: 1px solid #e8eaed;
            border-radius: 10px;
            padding: 0.85rem 1rem 0.75rem;
            margin-top: 0.35rem;
            overflow: visible;
        }
        [data-testid="element-container"]:has([data-testid="stMetric"]),
        [data-testid="stHorizontalBlock"],
        [data-testid="column"] {
            overflow: visible !important;
        }
        .block-container { padding-top: 2rem; overflow: visible; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def table_column_config(*, editable: bool) -> dict:
    disabled = not editable
    return {
        "date": st.column_config.TextColumn(TABLE_LABELS["date"], disabled=disabled),
        "amount": st.column_config.NumberColumn(
            TABLE_LABELS["amount"], format="%.0f", disabled=disabled
        ),
        "remark": st.column_config.TextColumn(TABLE_LABELS["remark"], disabled=disabled),
        "running_total": st.column_config.NumberColumn(
            TABLE_LABELS["running_total"], format="%.0f", disabled=True
        ),
    }


def prepare_display_df(df: pd.DataFrame) -> pd.DataFrame:
    view = df.sort_values(["date", "id"], ascending=[False, False]).reset_index(drop=True)
    return view[["id", *TABLE_COLUMNS]]


def prepare_table_view(display_df: pd.DataFrame) -> pd.DataFrame:
    return display_df[list(TABLE_COLUMNS)].rename(columns=TABLE_LABELS)


def render_sidebar() -> str:
    """Sidebar: auth, navigation, quick actions. Returns selected page key."""
    with st.sidebar:
        st.markdown("### Rent Tracker")
        st.caption("Rent & utility ledger")

        render_login()

        st.divider()
        page = st.radio(
            "Go to",
            options=["dashboard", "report"],
            format_func=lambda k: "Dashboard" if k == "dashboard" else "Report",
            label_visibility="collapsed",
        )

        if st.session_state.logged_in:
            render_sidebar_actions()

        return page


def render_login() -> None:
    if st.session_state.logged_in:
        st.success(f"Signed in as **{st.session_state.username}**")
        if st.button("Sign out", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.username = ""
            st.rerun()
        return

    with st.form("login"):
        username = st.text_input("Username", label_visibility="collapsed", placeholder="Username")
        password = st.text_input(
            "Password",
            type="password",
            label_visibility="collapsed",
            placeholder="Password",
        )
        if st.form_submit_button("Sign in", use_container_width=True, type="primary"):
            if authenticate_user(username, password):
                st.session_state.logged_in = True
                st.session_state.username = username.strip()
                st.rerun()
            st.error("Invalid credentials.")


def render_sidebar_actions() -> None:
    with st.expander("Add transaction", expanded=False):
        with st.form("add_txn", clear_on_submit=True):
            txn_date = st.date_input("Date", value=date.today(), max_value=date.today())
            amount = st.number_input("Amount (₹)", step=100.0, format="%.0f")
            remark = st.text_input("Description", placeholder="Rent, light bill, payment…")
            if st.form_submit_button("Save", use_container_width=True, type="primary"):
                ok, message = run_db_operation(
                    lambda: add_transaction(
                        txn_date.strftime("%Y-%m-%d"), amount, remark
                    ),
                    "Saved.",
                )
                if ok:
                    bump_data_version()
                    load_transactions.clear()
                    st.toast(message, icon="✅")
                    st.rerun()
                st.error(message)

    with st.expander("Import CSV", expanded=False):
        st.caption("Replaces all data. Columns: Date (DD-MM-YYYY), Amount, Remark.")
        uploaded = st.file_uploader("CSV file", type=["csv"], label_visibility="collapsed")
        confirm = st.checkbox("Replace all existing data")
        if uploaded and confirm and st.button("Import", use_container_width=True):
            result: dict[str, int] = {}

            def _import() -> None:
                result["count"] = import_uploaded_csv(uploaded.getvalue())

            ok, err = run_db_operation(_import, "")
            if ok:
                bump_data_version()
                load_transactions.clear()
                st.toast(f"Imported {result['count']} rows.", icon="✅")
                st.rerun()
            st.error(err)


def render_summary(analysis: dict) -> None:
    c1, c2, c3 = st.columns(3)
    c1.metric("Balance", format_currency(analysis["current_balance"]))
    c2.metric("Avg rent", format_currency(analysis["avg_monthly_rent"]))
    c3.metric("Avg light bill", format_currency(analysis["avg_light_bill"]))


def apply_transaction_edits(
    display_df: pd.DataFrame, edited_view: pd.DataFrame
) -> tuple[bool, str]:
    edited = edited_view.rename(
        columns={v: k for k, v in TABLE_LABELS.items()}
    )
    edited["id"] = display_df["id"].values
    original = display_df.set_index("id")

    for _, row in edited.iterrows():
        row_id = row["id"]
        prev = original.loc[row_id]
        if (
            str(row["date"]) == str(prev["date"])
            and float(row["amount"]) == float(prev["amount"])
            and str(row["remark"]) == str(prev["remark"])
        ):
            continue

        def _save(
            rid: str = row_id,
            d: str = str(row["date"]),
            a: float = float(row["amount"]),
            r: str = str(row["remark"]),
        ) -> None:
            if not update_transaction(rid, d, a, r):
                raise TransactionError("Could not save changes.")

        ok, msg = run_db_operation(_save, "Saved.")
        if not ok:
            return False, msg
    return True, "Changes saved."


def render_dashboard() -> None:
    try:
        df = load_transactions(st.session_state.data_version)
    except Exception as exc:
        logger.exception("Failed to load transactions")
        st.error(f"Could not load data: {exc}")
        return

    if df.empty:
        st.info("No transactions yet. Sign in to add entries or import a CSV.")
        return

    display_df = prepare_display_df(df)
    analysis = analyze_transactions(df)
    render_summary(analysis)

    st.subheader("Recent transactions")
    table_view = prepare_table_view(display_df)
    row_height = min(520, 48 + len(table_view) * 36)

    if st.session_state.logged_in:
        edited_view = st.data_editor(
            table_view,
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            column_config=table_column_config(editable=True),
            key="txn_editor",
            height=row_height,
        )
        action_col, delete_col = st.columns([1, 2])
        with action_col:
            if st.button("Save edits", type="primary", use_container_width=True):
                if table_view.equals(edited_view):
                    st.info("No changes to save.")
                else:
                    ok, msg = apply_transaction_edits(display_df, edited_view)
                    if ok:
                        bump_data_version()
                        load_transactions.clear()
                        st.toast(msg, icon="✅")
                        st.rerun()
                    st.error(msg)
        with delete_col:
            labels = {
                f"{r['date']} · {r['remark']} · {format_currency(r['amount'])}": r["id"]
                for _, r in display_df.iterrows()
            }
            to_delete = st.multiselect(
                "Remove entries",
                options=list(labels.keys()),
                placeholder="Select to delete…",
                label_visibility="visible",
            )
            if st.button("Delete selected", use_container_width=True) and to_delete:
                ids = [labels[x] for x in to_delete]
                ok, msg = run_db_operation(
                    lambda: delete_transactions(ids),
                    f"Removed {len(ids)}.",
                )
                if ok:
                    bump_data_version()
                    load_transactions.clear()
                    st.toast(msg, icon="✅")
                    st.rerun()
                st.error(msg)
    else:
        st.dataframe(
            table_view,
            hide_index=True,
            use_container_width=True,
            height=row_height,
        )
        st.caption("Sign in to add, edit, or import data.")

    with st.expander("Balance over time", expanded=False):
        chart_df = df.sort_values(["date", "id"])
        fig = px.area(
            chart_df,
            x="date",
            y="running_total",
            labels={"date": "", "running_total": "Balance (₹)"},
        )
        fig.update_layout(
            margin=dict(l=0, r=0, t=8, b=0),
            height=320,
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)


def render_report() -> None:
    st.subheader("Report")
    today = date.today()
    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        start = st.date_input("From", value=today.replace(month=1, day=1), key="report_start")
    with c2:
        end = st.date_input("To", value=today, key="report_end")
    with c3:
        st.write("")
        run = st.button("Run report", type="primary", use_container_width=True)

    if not run:
        st.caption("Pick a date range and run the report to see totals and download CSV.")
        return

    try:
        report_df = generate_report(
            start.strftime("%Y-%m-%d"),
            end.strftime("%Y-%m-%d"),
        )
    except TransactionError as exc:
        st.error(str(exc))
        return
    except Exception as exc:
        logger.exception("Report failed")
        st.error(f"Report failed: {exc}")
        return

    if report_df.empty:
        st.info("No transactions in this period.")
        return

    stats = analyze_transactions(report_df)
    m1, m2, m3 = st.columns(3)
    m1.metric("Rent", format_currency(stats["total_rent"]))
    m2.metric("Light bills", format_currency(stats["total_light_bills"]))
    m3.metric("Payments", format_currency(stats["total_payments"]))

    shown = report_df.rename(columns=TABLE_LABELS)
    st.dataframe(shown, hide_index=True, use_container_width=True)

    st.download_button(
        "Download CSV",
        data=report_df.to_csv(index=False),
        file_name=f"rent_report_{start}_{end}.csv",
        mime="text/csv",
        use_container_width=True,
    )


def main() -> None:
    st.set_page_config(
        page_title="Rent Tracker",
        page_icon="🏠",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_styles()
    init_session_state()

    try:
        db_ok, db_message = check_database_connection()
    except (KeyError, FileNotFoundError):
        st.error("Missing `.streamlit/secrets.toml` — see `secrets.toml.example`.")
        st.stop()
    except Exception as exc:
        st.error(f"Database error: {exc}")
        st.stop()
    if not db_ok:
        st.error(db_message)
        st.stop()

    page = render_sidebar()

    if page == "report":
        render_report()
    else:
        render_dashboard()


if __name__ == "__main__":
    main()
