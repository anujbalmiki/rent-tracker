import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import sqlite3
import os

# Initialize SQLite database
def init_db():
    conn = sqlite3.connect('rent_tracker.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         date TEXT NOT NULL,
         amount REAL NOT NULL,
         remark TEXT,
         running_total REAL)
    ''')
    conn.commit()
    conn.close()


def parse_csv_data(csv_path):
    # Read CSV with proper date parsing
    df = pd.read_csv(csv_path)
    
    # Convert date to consistent format
    df['Date'] = pd.to_datetime(df['Date'], format='%d-%m-%Y').dt.strftime('%Y-%m-%d')
    
    # Ensure amount is numeric
    df['Amount'] = pd.to_numeric(df['Amount'])
    
    # Rename columns to match database structure
    df = df.rename(columns={
        'Date': 'date',
        'Amount': 'amount',
        'Remark': 'remark'
    })
    
    # Sort by date
    df = df.sort_values('date')
    
    return df

def import_csv_to_db(csv_path):
    conn = sqlite3.connect('rent_tracker.db')
    c = conn.cursor()
    
    # Clear existing data
    c.execute('DELETE FROM transactions')
    
    # Parse and import CSV data
    df = parse_csv_data(csv_path)
    
    # Calculate running total
    running_total = 0
    for _, row in df.iterrows():
        running_total += row['amount']
        c.execute('INSERT INTO transactions (date, amount, remark, running_total) VALUES (?, ?, ?, ?)',
                 (row['date'], row['amount'], row['remark'], running_total))
    
    conn.commit()
    conn.close()

def add_transaction(date, amount, remark):
    conn = sqlite3.connect('rent_tracker.db')
    c = conn.cursor()
    
    c.execute('SELECT running_total FROM transactions ORDER BY date DESC LIMIT 1')
    last_total = c.fetchone()
    running_total = (last_total[0] if last_total else 0) + amount
    
    c.execute('INSERT INTO transactions (date, amount, remark, running_total) VALUES (?, ?, ?, ?)',
              (date, amount, remark, running_total))
    conn.commit()
    conn.close()

def get_transactions():
    conn = sqlite3.connect('rent_tracker.db')
    df = pd.read_sql_query('SELECT * FROM transactions ORDER BY date DESC', conn)
    conn.close()
    return df

def generate_report(start_date, end_date):
    conn = sqlite3.connect('rent_tracker.db')
    query = '''
    SELECT * FROM transactions 
    WHERE date BETWEEN ? AND ?
    ORDER BY date
    '''
    df = pd.read_sql_query(query, conn, params=[start_date, end_date])
    conn.close()
    return df

def analyze_transactions(df):
    """Generate detailed analysis of transactions"""
    rent_entries = df[df['remark'].str.contains('Rent', na=False)]
    light_bill_entries = df[df['remark'].str.contains('Light Bill', na=False)]
    payments = df[df['remark'].str.contains('Payment', na=False)]
    
    analysis = {
        'total_rent': rent_entries['amount'].sum(),
        'total_light_bills': light_bill_entries['amount'].sum(),
        'total_payments': abs(payments['amount'].sum()),
        'avg_monthly_rent': rent_entries['amount'].mean(),
        'avg_light_bill': light_bill_entries['amount'].mean(),
        'num_payments': len(payments),
        'current_balance': df['running_total'].iloc[0] if not df.empty else 0
    }
    
    return analysis

# Function to update the transaction in the database
def update_transaction(transaction_id, new_date, new_amount, new_remark):
    # Connect to the SQLite database
    conn = sqlite3.connect('rent_tracker.db')
    cursor = conn.cursor()
    query = """
    UPDATE transactions
    SET date = ?, amount = ?, remark = ?
    WHERE id = ?
    """
    cursor.execute(query, (new_date, new_amount, new_remark, transaction_id))
    conn.commit()

# Function to delete a transaction from the database
def delete_transaction(transaction_id):
    # Connect to the SQLite database
    conn = sqlite3.connect('rent_tracker.db')
    cursor = conn.cursor()
    query = "DELETE FROM transactions WHERE id = ?"
    cursor.execute(query, (transaction_id,))
    conn.commit()

# Initialize the database
init_db()

# Add this to the start of your code
import hashlib

# Hardcoded users (username: hashed_password)
USERS = {
    "admin": hashlib.sha256("admin123".encode()).hexdigest(),
}

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
            st.experimental_rerun()
    else:
        username = st.sidebar.text_input("Username")
        password = st.sidebar.text_input("Password", type="password")
        if st.sidebar.button("Login"):
            if authenticate_user(username, password):
                st.session_state.logged_in = True
                st.session_state.username = username
                st.sidebar.success("Login successful!")
                st.experimental_rerun()
            else:
                st.sidebar.error("Invalid username or password!")

# Call login function
login()

# Restrict access to functionalities based on login status
if st.session_state.logged_in:
    page = st.sidebar.selectbox("Select Page", ["Add Transaction", "View Transactions", "Generate Report", "Import CSV"])
else:
    page = "View Transactions"
    st.sidebar.info("Login to access more functionalities.")
    
    
# Streamlit UI
# st.title("🏠 Rent Tracker")

# Sidebar for navigation
# page = st.sidebar.selectbox("Select Page", ["Add Transaction", "View Transactions", "Generate Report", "Import CSV"])

if page == "Import CSV" and st.session_state.logged_in:
    st.header("Import CSV Data")
    
    uploaded_file = st.file_uploader("Choose a CSV file", type="csv")
    if uploaded_file is not None:
        if st.button("Import Data"):
            # Save the uploaded file temporarily
            with open("temp.csv", "wb") as f:
                f.write(uploaded_file.getvalue())
            
            try:
                import_csv_to_db("temp.csv")
                st.success("CSV data imported successfully!")
            except Exception as e:
                st.error(f"Error importing CSV: {str(e)}")
            finally:
                # Clean up temporary file
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
            add_transaction(date.strftime('%Y-%m-%d'), amount, remark)
            st.success("Transaction added successfully!")

# In the View Transactions page
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
                df,
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
                                for _, row in df.iterrows()]
            selected_transactions = st.multiselect(
                "Select transactions to delete:",
                options=transaction_options
            )
            
            # Add delete button for selected records
            if st.button("Delete Selected Records", type="primary"):
                if selected_transactions:
                    # Extract IDs from selected transactions
                    selected_ids = [int(trans.split(' - ')[0].replace('ID: ', '')) for trans in selected_transactions]
                    
                    # Delete selected records
                    conn = sqlite3.connect('rent_tracker.db')
                    cursor = conn.cursor()
                    cursor = conn.cursor()
                    
                    for record_id in selected_ids:
                        cursor.execute("DELETE FROM transactions WHERE id = ?", (record_id,))
                    
                    conn.commit()
                    conn.close()
                    
                    st.success(f"Successfully deleted {len(selected_ids)} record(s)!")
                    st.rerun()
                else:
                    st.warning("Please select at least one record to delete.")
        else:
            st.dataframe(df)
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

# Add CSS for better styling
st.markdown("""
    <style>
        .stMetric {
            background-color: #f0f2f6;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .stDataFrame {
            margin-top: 20px;
            margin-bottom: 20px;
        }
        .plot-container {
            margin-top: 30px;
            margin-bottom: 30px;
        }
    </style>
""", unsafe_allow_html=True)