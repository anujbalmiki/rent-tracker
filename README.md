# Rent Tracker

A Streamlit app for tracking rent, utility bills, and payments with a running balance. Data is stored in MongoDB.

**Live app:** [rent-tracker.streamlit.app](https://rent-tracker.streamlit.app)

## Features

- **Dashboard** — balance, average rent, average light bill, and recent transactions
- **Reports** — filter by date range, view totals, download CSV
- **Signed-in actions** — add, edit, or delete transactions; import CSV
- **Running balance** — recalculated automatically after every change

## Project structure

```
rent-tracker/
├── app.py                 # Streamlit UI
├── core/
│   ├── analytics.py       # Totals and balance logic
│   ├── auth.py            # Admin login
│   ├── database.py        # MongoDB connection
│   └── transactions.py    # CRUD and CSV import
├── tests/
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml.example
└── requirements.txt
```

## Requirements

- Python 3.11+
- MongoDB Atlas (or any MongoDB instance)
- [Streamlit](https://streamlit.io) 1.32+

## Local setup

1. **Clone and install**

   ```bash
   git clone https://github.com/anujbalmiki/rent-tracker.git
   cd rent-tracker
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure secrets**

   ```bash
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   ```

   Edit `.streamlit/secrets.toml`:

   ```toml
   [mongo]
   uri = "mongodb+srv://USER:PASSWORD@cluster.mongodb.net/..."

   [admin]
   username = "your-username"
   password = "your-password"
   ```

3. **Run**

   ```bash
   streamlit run app.py
   ```

   Open [http://localhost:8501](http://localhost:8501).

## CSV import format

Import **replaces all existing transactions**. Required columns:

| Column  | Format        | Example        |
|---------|---------------|----------------|
| Date    | `DD-MM-YYYY`  | `18-05-2026`   |
| Amount  | Number        | `3200` or `-15000` |
| Remark  | Text          | `April Rent 2026` |

Sign in, open **Import CSV** in the sidebar, upload the file, and confirm the replacement warning.

## Deploy on Streamlit Cloud

1. Push the repo to GitHub.
2. [Share the app](https://share.streamlit.io) and point it at `app.py`.
3. Add the same `[mongo]` and `[admin]` secrets under **App settings → Secrets**.

## Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -q
```

## Git commits (avoid extra GitHub contributors)

If you use Cursor Agent to commit, it may add this line to commit messages:

```
Co-authored-by: Cursor <cursoragent@cursor.com>
```

That makes **Cursor Agent** appear in GitHub’s contributor list. To avoid it:

- In **Cursor Settings**, turn off co-author attribution on commits (wording may vary by version), or  
- Amend commits before pushing to remove the `Co-authored-by` line, or  
- Commit yourself from the terminal with your own Git identity.

## License

Private / personal use unless otherwise noted.
