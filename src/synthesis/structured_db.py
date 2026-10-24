"""
structured_db.py — Dedicated Structured Database for Synthesized Data ONLY.
Contains zero raw or private data. Stores only clean, verified synthetic records.
"""

import os
import json
import duckdb
import pandas as pd

STRUCTURED_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data",
    "synthetic_database.duckdb",
)


def get_structured_connection(db_path: str = STRUCTURED_DB_PATH) -> duckdb.DuckDBPyConnection:
    """Connects to the structured synthetic database and ensures schema exists."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = duckdb.connect(db_path)

    # Clean structured table holding ONLY synthesized records
    conn.execute("""
        CREATE TABLE IF NOT EXISTS synthetic_enterprise_records (
            id INTEGER PRIMARY KEY,
            synthetic_id VARCHAR UNIQUE,
            data_type VARCHAR,
            subject VARCHAR,
            body TEXT,
            sender VARCHAR,
            recipient VARCHAR,
            date_timestamp VARCHAR,
            compliance_label INTEGER,
            is_executive BOOLEAN,
            metadata_json JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE SEQUENCE IF NOT EXISTS seq_synth_id START 1;
    """)
    return conn


def insert_synthesized_records(
    records: list[dict],
    db_path: str = STRUCTURED_DB_PATH,
) -> int:
    """
    Inserts newly generated synthetic records into the structured database.

    Each record should contain:
    - synthetic_id, data_type, subject, body, sender, recipient,
      date_timestamp, compliance_label, is_executive, metadata_json
    """
    if not records:
        return 0

    conn = get_structured_connection(db_path)
    try:
        rows_to_insert = []
        for r in records:
            # Extract fields with safe fallbacks
            ctx = r.get("context", {})
            rows_to_insert.append({
                "synthetic_id": r.get("synthetic_id", ""),
                "data_type": r.get("data_type", "email"),
                "subject": r.get("subject", r.get("title", "")),
                "body": r.get("body", r.get("synthetic_text", "")),
                "sender": r.get("sender", ctx.get("From", "alex.turner@company.internal")),
                "recipient": r.get("recipient", ctx.get("To", "team@company.internal")),
                "date_timestamp": str(r.get("date_timestamp", ctx.get("Date", "2024-03-15 10:00:00"))),
                "compliance_label": int(r.get("compliance_label", ctx.get("Label", 0))),
                "is_executive": bool(r.get("is_executive", ctx.get("POI-Present", False))),
                "metadata_json": json.dumps(ctx, default=str),
            })

        df = pd.DataFrame(rows_to_insert)
        conn.register("incoming_synth_df", df)

        conn.execute("""
            INSERT INTO synthetic_enterprise_records (
                id, synthetic_id, data_type, subject, body, sender, recipient,
                date_timestamp, compliance_label, is_executive, metadata_json
            )
            SELECT 
                nextval('seq_synth_id'),
                synthetic_id, data_type, subject, body, sender, recipient,
                date_timestamp, compliance_label, is_executive, metadata_json
            FROM incoming_synth_df;
        """)
        conn.unregister("incoming_synth_df")
        return len(rows_to_insert)
    finally:
        conn.close()


def query_synthesized_records(
    limit: int = 10,
    compliance_label: int = None,
    db_path: str = STRUCTURED_DB_PATH,
) -> list[dict]:
    """Queries records from the clean synthetic database."""
    conn = get_structured_connection(db_path)
    try:
        query = "SELECT * FROM synthetic_enterprise_records"
        params = []
        if compliance_label is not None:
            query += " WHERE compliance_label = ?"
            params.append(compliance_label)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        df = conn.execute(query, params).fetchdf()
        return df.to_dict(orient="records")
    finally:
        conn.close()


def get_structured_stats(db_path: str = STRUCTURED_DB_PATH) -> dict:
    """Returns total count and compliance breakdown of synthesized data."""
    conn = get_structured_connection(db_path)
    try:
        total = conn.execute("SELECT count(*) FROM synthetic_enterprise_records;").fetchone()[0]
        breakdown = conn.execute("""
            SELECT compliance_label, count(*) 
            FROM synthetic_enterprise_records 
            GROUP BY compliance_label;
        """).fetchall()

        return {
            "total_synthetic_records": total,
            "compliance_breakdown": {f"label_{row[0]}": row[1] for row in breakdown},
        }
    finally:
        conn.close()
