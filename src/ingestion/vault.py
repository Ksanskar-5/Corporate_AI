"""
vault.py — DuckDB Storage Manager for the Unified Data Vault.
Stores all ingested enterprise data (emails, tickets, PDFs, notes) in a local file.
"""

import os
import json
import duckdb
import pandas as pd

# Path to the local DuckDB vault file
DEFAULT_VAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data",
    "vault.duckdb",
)


def get_connection(db_path: str = DEFAULT_VAULT_PATH) -> duckdb.DuckDBPyConnection:
    """Connects to the DuckDB vault and ensures the table exists."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = duckdb.connect(db_path)

    # Create the unified storage table if it does not already exist
    conn.execute("""
        CREATE TABLE IF NOT EXISTS unified_vault (
            doc_id VARCHAR PRIMARY KEY,
            source_file VARCHAR,
            data_type VARCHAR,
            title VARCHAR,
            primary_text TEXT,
            attributes JSON,
            token_count INTEGER,
            ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    return conn


def save_documents(documents: list[dict], db_path: str = DEFAULT_VAULT_PATH) -> int:
    """
    Saves a list of parsed documents into the unified vault.
    
    Each document dict must have:
    - doc_id: str
    - source_file: str
    - data_type: str
    - title: str
    - primary_text: str
    - attributes: dict (metadata)
    - token_count: int
    """
    if not documents:
        return 0

    # Convert list of dicts to DataFrame for fast bulk insertion
    records = []
    for doc in documents:
        records.append({
            "doc_id": doc.get("doc_id"),
            "source_file": doc.get("source_file"),
            "data_type": doc.get("data_type", "general"),
            "title": doc.get("title", ""),
            "primary_text": doc.get("primary_text", ""),
            "attributes": json.dumps(doc.get("attributes", {}), default=str),
            "token_count": int(doc.get("token_count", 0)),
        })

    df = pd.DataFrame(records)

    conn = get_connection(db_path)
    try:
        # Insert or replace records by doc_id
        conn.register("incoming_df", df)
        conn.execute("""
            INSERT OR REPLACE INTO unified_vault (
                doc_id, source_file, data_type, title, primary_text, attributes, token_count
            )
            SELECT doc_id, source_file, data_type, title, primary_text, attributes, token_count
            FROM incoming_df;
        """)
        conn.unregister("incoming_df")
    finally:
        conn.close()

    return len(records)


def get_vault_stats(db_path: str = DEFAULT_VAULT_PATH) -> dict:
    """Returns a quick summary of total documents and counts per data type."""
    conn = get_connection(db_path)
    try:
        total_docs = conn.execute("SELECT count(*) FROM unified_vault;").fetchone()[0]
        type_counts = conn.execute("""
            SELECT data_type, count(*) 
            FROM unified_vault 
            GROUP BY data_type;
        """).fetchall()

        return {
            "total_documents": total_docs,
            "breakdown": {row[0]: row[1] for row in type_counts},
        }
    finally:
        conn.close()


def query_vault(
    data_type: str = None,
    limit: int = 10,
    db_path: str = DEFAULT_VAULT_PATH,
) -> list[dict]:
    """Queries documents from the vault as clean Python dictionaries."""
    conn = get_connection(db_path)
    try:
        if data_type:
            res = conn.execute(
                "SELECT * FROM unified_vault WHERE data_type = ? LIMIT ?;",
                [data_type, limit],
            ).fetchdf()
        else:
            res = conn.execute(
                "SELECT * FROM unified_vault LIMIT ?;",
                [limit],
            ).fetchdf()

        records = res.to_dict(orient="records")
        for r in records:
            if isinstance(r.get("attributes"), str):
                try:
                    r["attributes"] = json.loads(r["attributes"])
                except Exception:
                    pass
        return records
    finally:
        conn.close()


def clear_vault(db_path: str = DEFAULT_VAULT_PATH) -> None:
    """Empties the vault table."""
    conn = get_connection(db_path)
    try:
        conn.execute("DELETE FROM unified_vault;")
    finally:
        conn.close()
