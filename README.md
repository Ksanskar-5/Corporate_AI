# Corporate_AI - Privacy-Preserving Enterprise Copilot

A native desktop AI assistant and data synthesis platform with Role-Based Access Control (RBAC).

## Quickstart - Launch Desktop Application

Run the desktop app directly:

```bash
# Using Python:
python main.py

# Or via virtual environment directly:
.venv/bin/python main.py
```

### Pre-Seeded Test Accounts

| Username | Password | Role | Department | Scope |
| :--- | :--- | :--- | :--- | :--- |
| `employee` | `pass123` | `Employee` | Corporate Operations | Chatbot access only |
| `analyst` | `pass123` | `Analyst` | Market Analytics | Chatbot + Read-only Database Viewer |
| `manager` | `pass123` | `Manager` | Trading & Risk | Chatbot + Database Viewer |
| `admin` | `pass123` | `Admin` | Executive Leadership | Full Access (Chatbot + DB Viewer + Edit/Delete records) |

*Tip: You can also click the Quick Login chips directly on the login screen.*

## Project Structure

```
├── main.py                    # Desktop Application Entrypoint (FastAPI + pywebview)
├── configs/                   # Central configuration files
├── data/                      # Data directory (processed datasets)
│   └── processed/             # Cleaned corporate email & document dataset
├── src/
│   ├── app/                   # Desktop Application & API Server
│   │   ├── auth_db.py         # SQLite authentication and hashing
│   │   ├── server.py          # FastAPI backend service & record API
│   │   └── ui/                # Modern desktop webview UI
│   ├── agent/                 # RAG chatbot & vector store
│   ├── ingestion/             # Multi-format data parser, vault & extractor
│   ├── synthesis/             # Data synthesis engine & sanitizers
│   └── privacy/               # Differential privacy & auditing
├── pyproject.toml             # Project configuration
└── requirements.txt           # Python dependencies
```
