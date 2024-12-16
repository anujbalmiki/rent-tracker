import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from pymongo import MongoClient
from bson.objectid import ObjectId
import os
import hashlib

# MongoDB connection setup
uri = st.secrets["mongo"]["uri"]
client = MongoClient(uri)
db = client["rent_tracker"]
transactions_collection = db["transactions"]

# Parse CSV Data
def parse_csv_data(csv_path):
    df = pd.read_csv(csv_path)
    df["Date"] = pd.to_datetime(df["Date"], format="%d-%m-%Y").dt.strftime("%Y-%m-%d")
    df["Amount"] = pd.to_numeric(df["Amount"])
    df = df.rename(columns={"Date": "date", "Amount": "amount", "Remark": "remark"})
    df = df.sort_values("date")
    return df

# Import CSV to MongoDB
def import_csv_to_db(csv_path):
    df = parse_csv_data(csv_path)
    transactions_collection.delete_many({})
    running_total = 0
    for _, row in df.iterrows():
        running_total += row["amount"]
        transaction = {
            "date": row["date"],
            "amount": row["amount"],
            "remark": row["remark"],
            "running_total": running_total,
        }
        transactions_collection.insert_one(transaction)

# Add Transaction
def add_transaction(date, amount, remark):
    last_transaction = transactions_collection.find_one(sort=[("date", -1)])
    running_total = (last_transaction["running_total"] if last_transaction else 0) + amount
    transaction = {
        "date": date,
        "amount": amount,
        "remark": remark,
        "running_total": running_total,
    }
    transactions_collection.insert_one(transaction)

# Get Transactions
def get_transactions():
    transactions = list(transactions_collection.find())
    df = pd.DataFrame(transactions)
    if not df.empty:
        df["id"] = df["_id"].apply(str)
        df.drop(columns=["_id"], inplace=True)
    return df

# Generate Report
def generate_report(start_date, end_date):
    query = {"date": {"$gte": start_date, "$lte": end_date}}
    transactions = list(transactions_collection.find(query))
    return pd.DataFrame(transactions)

# Analyze Transactions
def analyze_transactions(df):
    rent_entries = df[df["remark"].str.contains("Rent", na=False)]
    light_bill_entries = df[df["remark"].str.contains("Light Bill", na=False)]
    payments = df[df["remark"].str.contains("Payment", na=False)]
    analysis = {
        "total_rent": rent_entries["amount"].sum(),
        "total_light_bills": light_bill_entries["amount"].sum(),
        "total_payments": abs(payments["amount"].sum()),
        "avg_monthly_rent": rent_entries["amount"].mean(),
        "avg_light_bill": light_bill_entries["amount"].mean(),
        "num_payments": len(payments),
        "current_balance": df["running_total"].iloc[-1] if not df.empty else 0,
    }
    return analysis

# Update Transaction
def update_transaction(transaction_id, new_date, new_amount, new_remark):
    transaction = transactions_collection.find_one({"_id": ObjectId(transaction_id)})
    if transaction:
        old_amount = transaction["amount"]
        difference = new_amount - old_amount
        transactions_collection.update_one(
            {"_id": ObjectId(transaction_id)},
            {"$set": {"date": new_date, "amount": new_amount, "remark": new_remark}},
        )

        # Recalculate running totals
        cursor = transactions_collection.find(sort=[("date", 1)])
        running_total = 0
        for doc in cursor:
            running_total += doc["amount"]
            transactions_collection.update_one(
                {"_id": doc["_id"]}, {"$set": {"running_total": running_total}}
            )

# Delete Transaction
def delete_transaction(transaction_id):
    transactions_collection.delete_one({"_id": ObjectId(transaction_id)})

# User Authentication
USERS = {st.secrets["admin"]["username"]: hashlib.sha256(st.secrets["admin"]["password"].encode()).hexdigest()}

def authenticate_user(username, password):
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    return USERS.get(username) == hashed_password

def login():
    st.sidebar.subheader("Login")
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.username = ""
    if st.session_state.logged_in:
        st.sidebar.write(f"Logged in as: **{st.session_state.username}**")
        if st.sidebar.button("Logout"):
            st.session_state.logged_in = False
            st.rerun()
    else:
        username = st.sidebar.text_input("Username")
        password = st.sidebar.text_input("Password", type="password")
        if st.sidebar.button("Login"):
            if authenticate_user(username, password):
                st.session_state.logged_in = True
                st.session_state.username = username
                st.sidebar.success("Login successful!")
                st.rerun()
            else:
                st.sidebar.error("Invalid username or password!")

# Application Logic
login()
if st.session_state.logged_in:
    page = st.sidebar.selectbox(
        "Select Page",
        ["Add Transaction", "View Transactions", "Generate Report", "Import CSV"],
    )
else:
    page = "View Transactions"
    st.sidebar.info("Login to access more functionalities.")

if page == "Import CSV" and st.session_state.logged_in:
    st.header("Import CSV Data")
    uploaded_file = st.file_uploader("Choose a CSV file", type="csv")
    if uploaded_file is not None:
        if st.button("Import Data"):
            with open("temp.csv", "wb") as f:
                f.write(uploaded_file.getvalue())
            try:
                import_csv_to_db("temp.csv")
                st.success("CSV data imported successfully!")
            except Exception as e:
                st.error(f"Error importing CSV: {str(e)}")
            finally:
                if os.path.exists("temp.csv"):
                    os.remove("temp.csv")

elif page == "Add Transaction" and st.session_state.logged_in:
    st.header("Add New Transaction")
    with st.form("transaction_form"):
        date = st.date_input("Date", datetime.today())
        amount = st.number_input("Amount", step=100.0)
        remark = st.text_input("Remark")
        submitted = st.form_submit_button("Add Transaction")
        if submitted:
            add_transaction(date.strftime("%Y-%m-%d"), amount, remark)
            st.success("Transaction added successfully!")
            
    # Get the data
    df = get_transactions()
    st.dataframe(df.sort_values("date", ascending=False))

elif page == "View Transactions":
    st.header("Transaction History")
    
    # Get the data
    df = get_transactions()
    
    if not df.empty:
        # Allow editing and deleting only if logged in
        if st.session_state.logged_in:
            # Allow editing in a separate section
            st.subheader("Edit Transactions")
            edited_df = st.data_editor(
                df.sort_values("date", ascending=False),
                hide_index=True,
                key="edit_transactions_table"
            )

            # Check if any row was edited
            if not df.equals(edited_df):
                # Loop over rows to check which ones were edited
                for index, row in edited_df.iterrows():
                    original_row = df.loc[df['id'] == row['id']].iloc[0]
                    if (row['amount'] != original_row['amount'] or 
                        row['remark'] != original_row['remark'] or
                        row['date'] != original_row['date']):
                        # Update the transaction in the database if edited
                        update_transaction(row['id'], row['date'], row['amount'], row['remark'])
                        st.success(f"Transaction ID {row['id']} updated successfully!")
                        st.rerun()
                        
            
            # Create a multiselect for choosing records to delete
            transaction_options = [f"ID: {row['id']} - Date: {row['date']} - Amount: ₹{row['amount']} - {row['remark']}" 
                                for _, row in df.sort_values("date", ascending=False).iterrows()]
            selected_transactions = st.multiselect(
                "Select transactions to delete:",
                options=transaction_options
            )
            
            ## Add delete button for selected records
            if st.button("Delete Selected Records", type="primary"):
                if selected_transactions:
                    try:
                        # Extract ObjectId from selected transactions
                        selected_ids = [
                            ObjectId(trans.split(" - ")[0].replace("ID: ", ""))
                            for trans in selected_transactions
                        ]
                        
                        # Perform deletion
                        for record_id in selected_ids:
                            delete_transaction(record_id)

                        st.success(f"Successfully deleted {len(selected_ids)} record(s)!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"An error occurred during deletion: {e}")
                else:
                    st.warning("Please select at least one record to delete.")
        else:
            st.dataframe(df.sort_values("date", ascending=False))
    else:
        st.write("No transactions available.")
    
    # Display Analytics and Charts
    if not df.empty:
        # Get analysis
        analysis = analyze_transactions(df)
        
        # Display current balance prominently
        st.metric("Current Balance", f"₹{analysis['current_balance']:,.2f}")
        
        # Create three columns for key metrics
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Average Monthly Rent", f"₹{analysis['avg_monthly_rent']:,.2f}")
        with col2:
            st.metric("Average Light Bill", f"₹{analysis['avg_light_bill']:,.2f}")
        with col3:
            st.metric("Total Payments Made", f"₹{analysis['total_payments']:,.2f}")
        
        # Plot transaction history
        fig = px.line(df.sort_values('date'), 
                    x='date', 
                    y='running_total',
                    title='Balance History')
        st.plotly_chart(fig)
        
        # Plot monthly breakdown
        st.subheader("Monthly Breakdown")
        monthly_rent = df[df['remark'].str.contains('Rent', na=False)].copy()
        monthly_rent['month'] = pd.to_datetime(monthly_rent['date']).dt.strftime('%Y-%m')
        monthly_fig = px.bar(monthly_rent.groupby('month')['amount'].sum().reset_index(),
                        x='month',
                        y='amount',
                        title='Monthly Rent')
        st.plotly_chart(monthly_fig)
        
        # Light bill trends
        st.subheader("Light Bill Trends")
        light_bills = df[df['remark'].str.contains('Light Bill', na=False)].copy()
        light_bills['month'] = pd.to_datetime(light_bills['date']).dt.strftime('%Y-%m')
        light_fig = px.line(light_bills.sort_values('date'),
                        x='date',
                        y='amount',
                        title='Light Bill Trends')
        st.plotly_chart(light_fig)


elif page == "Generate Report" and st.session_state.logged_in:
    st.header("Generate Report")
    
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start Date")
    with col2:
        end_date = st.date_input("End Date")
    
    if st.button("Generate Report"):
        report_df = generate_report(start_date.strftime('%Y-%m-%d'), 
                                end_date.strftime('%Y-%m-%d'))
        
        if not report_df.empty:
            analysis = analyze_transactions(report_df)
            
            st.subheader("Transaction Summary")
            st.dataframe(report_df)
            
            # Display summary metrics
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Rent", f"₹{analysis['total_rent']:,.2f}")
            col2.metric("Total Light Bills", f"₹{analysis['total_light_bills']:,.2f}")
            col3.metric("Total Payments", f"₹{analysis['total_payments']:,.2f}")
            
            # Download report as CSV
            csv = report_df.to_csv(index=False)
            st.download_button(
                label="Download Report",
                data=csv,
                file_name=f"rent_report_{start_date}_{end_date}.csv",
                mime="text/csv"
            )