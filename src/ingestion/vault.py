"""
vault.py — DuckDB Storage Manager for the Unified Data Vault with Role-Based Access Control (RBAC).
Stores all ingested enterprise data (emails, tickets, PDFs, notes) in a local file with
explicit department, allowed_roles, and clearance_level security attributes.
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
    """Connects to the DuckDB vault and ensures the table exists with RBAC schema."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = duckdb.connect(db_path)

    # Create the unified storage table with explicit RBAC columns
    conn.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            doc_id VARCHAR PRIMARY KEY,
            source_file VARCHAR,
            file_type VARCHAR,
            data_type VARCHAR,
            title VARCHAR,
            body_text TEXT,
            department VARCHAR DEFAULT 'Corporate Operations',
            allowed_roles VARCHAR DEFAULT 'All',
            clearance_level VARCHAR DEFAULT 'Internal',
            attributes JSON,
            token_count INTEGER,
            ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    return conn


def save_documents(documents: list[dict], db_path: str = DEFAULT_VAULT_PATH) -> int:
    """
    Saves a list of parsed documents into the vault with RBAC attributes.
    
    Each document dict can have:
    - doc_id: str
    - source_file: str
    - file_type: str (optional, inferred from source_file if missing)
    - data_type: str
    - title: str
    - body_text: str (or primary_text)
    - department: str (optional)
    - allowed_roles: list[str] | str (optional)
    - clearance_level: str (optional, e.g. 'Public', 'Internal', 'Confidential', 'Restricted')
    - attributes: dict (metadata)
    - token_count: int
    """
    if not documents:
        return 0

    records = []
    for doc in documents:
        attrs = doc.get("attributes", {})
        if isinstance(attrs, str):
            try:
                attrs = json.loads(attrs)
            except Exception:
                attrs = {}

        # 1. Department determination
        dept = (
            doc.get("department")
            or attrs.get("department")
            or "Corporate Operations"
        )

        # 2. RBAC Allowed Roles determination
        roles = doc.get("allowed_roles") or attrs.get("allowed_roles")
        is_exec = bool(attrs.get("is_executive") or attrs.get("POI-Present") or False)
        comp_flag = int(attrs.get("compliance_label") or attrs.get("Label") or 0)

        if not roles:
            if is_exec:
                roles = "Executive,Compliance_Auditor"
            elif comp_flag == 1:
                roles = "Compliance_Auditor,Executive"
            else:
                roles = "All"
        elif isinstance(roles, list):
            roles = ",".join(roles)

        # 3. Clearance Level determination
        clearance = doc.get("clearance_level") or attrs.get("clearance_level")
        if not clearance:
            if is_exec:
                clearance = "Restricted"
            elif comp_flag == 1:
                clearance = "Confidential"
            else:
                clearance = "Internal"

        source_file = doc.get("source_file", "")
        file_type = doc.get("file_type")
        if not file_type and source_file:
            file_type = os.path.splitext(source_file)[1].lstrip(".").lower()

        text_content = doc.get("body_text") if doc.get("body_text") is not None else doc.get("primary_text", "")

        records.append({
            "doc_id": doc.get("doc_id"),
            "source_file": source_file,
            "file_type": file_type or "unknown",
            "data_type": doc.get("data_type", "general"),
            "title": doc.get("title", ""),
            "body_text": text_content,
            "department": str(dept),
            "allowed_roles": str(roles),
            "clearance_level": str(clearance),
            "attributes": json.dumps(attrs, default=str),
            "token_count": int(doc.get("token_count", 0)),
        })

    df = pd.DataFrame(records)

    conn = get_connection(db_path)
    try:
        conn.register("incoming_df", df)
        conn.execute("""
            INSERT OR REPLACE INTO documents (
                doc_id, source_file, file_type, data_type, title, body_text,
                department, allowed_roles, clearance_level, attributes, token_count
            )
            SELECT doc_id, source_file, file_type, data_type, title, body_text,
                   department, allowed_roles, clearance_level, attributes, token_count
            FROM incoming_df;
        """)
        conn.unregister("incoming_df")
    finally:
        conn.close()

    return len(records)


def get_vault_stats(db_path: str = DEFAULT_VAULT_PATH) -> dict:
    """Returns a summary of total documents, formats, departments, and clearance levels."""
    conn = get_connection(db_path)
    try:
        total_docs = conn.execute("SELECT count(*) FROM documents;").fetchone()[0]
        type_counts = conn.execute("""
            SELECT data_type, count(*) 
            FROM documents 
            GROUP BY data_type;
        """).fetchall()
        dept_counts = conn.execute("""
            SELECT department, count(*) 
            FROM documents 
            GROUP BY department;
        """).fetchall()
        clearance_counts = conn.execute("""
            SELECT clearance_level, count(*) 
            FROM documents 
            GROUP BY clearance_level;
        """).fetchall()

        return {
            "total_documents": total_docs,
            "data_type_breakdown": {row[0]: row[1] for row in type_counts},
            "department_breakdown": {row[0]: row[1] for row in dept_counts},
            "clearance_breakdown": {row[0]: row[1] for row in clearance_counts},
        }
    finally:
        conn.close()


def query_vault(
    data_type: str = None,
    user_role: str = "Executive",
    user_department: str = None,
    limit: int = 10,
    db_path: str = DEFAULT_VAULT_PATH,
) -> list[dict]:
    """
    Queries documents from the vault enforcing Role-Based Access Control (RBAC).

    RBAC Policy:
    - General_Employee: Can ONLY access clearance_level in ('Public', 'Internal') and allowed_roles containing 'All'.
    - Department_Manager: Can access own department records + Corporate Operations up to 'Confidential'.
    - Compliance_Auditor: Can access all departments, audit investigations, and risk files.
    - Executive: Full unrestricted visibility across all departments and 'Restricted' files.
    """
    conn = get_connection(db_path)
    try:
        where_clauses = []
        params = []

        if data_type:
            where_clauses.append("data_type = ?")
            params.append(data_type)

        # Enforce RBAC filtering at SQL layer
        if user_role == "General_Employee":
            where_clauses.append("clearance_level IN ('Public', 'Internal') AND allowed_roles LIKE '%All%'")
        elif user_role == "Department_Manager":
            dept = user_department or "Corporate Operations"
            where_clauses.append("clearance_level IN ('Public', 'Internal', 'Confidential') AND (department = ? OR department = 'Corporate Operations')")
            params.append(dept)
        # Executive and Compliance_Auditor have global access

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        query_sql = f"""
            SELECT * FROM documents
            {where_sql}
            ORDER BY ingested_at DESC
            LIMIT ?;
        """
        params.append(limit)

        res = conn.execute(query_sql, params).fetchdf()

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
    """Empties the documents table in vault."""
    conn = get_connection(db_path)
    try:
        conn.execute("DELETE FROM documents;")
    finally:
        conn.close()
