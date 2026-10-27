import os
import uuid
import json
import duckdb
import pandas as pd

STRUCTURED_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data",
    "synthetic_database.duckdb",
)


def get_connection(db_path: str = STRUCTURED_DB_PATH) -> duckdb.DuckDBPyConnection:
    """Connects to the structured synthetic database."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = duckdb.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS synthetic_records (
            id VARCHAR PRIMARY KEY,
            source_doc_id VARCHAR,
            data_type VARCHAR,
            title VARCHAR,
            content TEXT,
            department VARCHAR,
            author VARCHAR,
            recipient VARCHAR,
            timestamp VARCHAR,
            compliance_label INTEGER DEFAULT 0,
            is_executive BOOLEAN DEFAULT FALSE,
            allowed_roles VARCHAR DEFAULT 'All',
            clearance_level VARCHAR DEFAULT 'Internal',
            metadata JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    return conn


def save_synthetic_batch(records: list[dict], db_path: str = STRUCTURED_DB_PATH) -> int:
    """Saves a batch of synthesized records into the structured database."""
    if not records:
        return 0

    rows = []
    for r in records:
        title = r.get("title") or r.get("subject") or "Enterprise Update"
        content = r.get("content") or r.get("body") or ""
        author = r.get("author") or r.get("author_or_sender") or r.get("sender") or "employee@company.internal"
        recipient = r.get("recipient") or r.get("recipient_or_audience") or "team@company.internal"
        dept = r.get("department") or "Corporate Operations"
        
        meta = r.get("metadata") or r.get("metadata_json") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}

        is_exec = bool(r.get("is_executive", False))
        comp_lbl = int(r.get("compliance_label", 0))

        # Access roles: either user-specified or inferred from sensitivity
        roles = r.get("allowed_roles")
        if not roles:
            if is_exec:
                roles = "Executive,Compliance_Auditor"
            elif comp_lbl == 1:
                roles = "Compliance_Auditor,Executive"
            else:
                roles = "All"
        elif isinstance(roles, list):
            roles = ",".join(roles)

        clearance = r.get("clearance_level")
        if not clearance:
            if is_exec:
                clearance = "Restricted"
            elif comp_lbl == 1:
                clearance = "Confidential"
            else:
                clearance = "Internal"

        rows.append({
            "id": r.get("id") or f"synth_{uuid.uuid4().hex[:8]}",
            "source_doc_id": r.get("source_doc_id"),
            "data_type": r.get("data_type", "general"),
            "title": title,
            "content": content,
            "department": dept,
            "author": author,
            "recipient": recipient,
            "timestamp": str(r.get("timestamp", "2024-03-15 10:00:00")),
            "compliance_label": comp_lbl,
            "is_executive": is_exec,
            "allowed_roles": str(roles),
            "clearance_level": str(clearance),
            "metadata": json.dumps(meta, default=str),
        })

    df = pd.DataFrame(rows)
    conn = get_connection(db_path)
    try:
        conn.register("incoming_batch", df)
        conn.execute("""
            INSERT OR REPLACE INTO synthetic_records (
                id, source_doc_id, data_type, title, content, department, author,
                recipient, timestamp, compliance_label, is_executive,
                allowed_roles, clearance_level, metadata
            )
            SELECT id, source_doc_id, data_type, title, content, department, author,
                   recipient, timestamp, compliance_label, is_executive,
                   allowed_roles, clearance_level, metadata
            FROM incoming_batch;
        """)
        conn.unregister("incoming_batch")
        return len(rows)
    finally:
        conn.close()


def get_synthetic_records(limit: int = 10, db_path: str = STRUCTURED_DB_PATH) -> list[dict]:
    """Queries records from the structured synthetic database."""
    conn = get_connection(db_path)
    try:
        df = conn.execute(
            "SELECT * FROM synthetic_records ORDER BY created_at DESC LIMIT ?;",
            [limit],
        ).fetchdf()
        return df.to_dict(orient="records")
    finally:
        conn.close()


def get_synthetic_stats(db_path: str = STRUCTURED_DB_PATH) -> dict:
    """Returns total count, data_type, department, and compliance breakdowns."""
    conn = get_connection(db_path)
    try:
        total = conn.execute("SELECT count(*) FROM synthetic_records;").fetchone()[0]
        compliance_breakdown = conn.execute("""
            SELECT compliance_label, count(*) 
            FROM synthetic_records 
            GROUP BY compliance_label;
        """).fetchall()
        type_breakdown = conn.execute("""
            SELECT data_type, count(*) 
            FROM synthetic_records 
            GROUP BY data_type;
        """).fetchall()
        dept_breakdown = conn.execute("""
            SELECT department, count(*) 
            FROM synthetic_records 
            GROUP BY department;
        """).fetchall()

        return {
            "total_records": total,
            "data_type_breakdown": {row[0]: row[1] for row in type_breakdown},
            "department_breakdown": {row[0]: row[1] for row in dept_breakdown},
            "compliance_breakdown": {f"label_{r[0]}": r[1] for r in compliance_breakdown},
        }
    finally:
        conn.close()
