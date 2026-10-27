"""
server.py - FastAPI Local Backend for Corporate AI Desktop & Enterprise Data Management
Provides unified data management across synthetic records and non-synthetic vault data,
multi-format filtering (PDF, MD, CSV, TXT, JSON), RBAC scoping, and role-aware RAG copilot.
"""

import os
import io
import csv
import math
import json
import duckdb
import shutil
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from pydantic import BaseModel

from .auth_db import (
    authenticate_user, get_all_users, SUPPORTED_ROLES,
    DB_ACCESS_ROLES, WRITE_ROLES, ADMIN_ROLES
)
from .session import session
from ..agent.chatbot import CorporateChatbot
from ..synthesis.db import STRUCTURED_DB_PATH
from ..ingestion.vault import DEFAULT_VAULT_PATH
from ..ingestion.ingestor import ingest_file
from ..synthesis.engine import synthesize_from_file
from ..agent.vector_store import build_vector_store, effective_source_scope

app = FastAPI(title="Corporate AI Enterprise Data Management API")

UI_DIR = os.path.join(os.path.dirname(__file__), "ui")
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "raw")

chatbot_instance = None


def _clean_val(v):
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def _safe_records(records: list[dict]) -> list[dict]:
    """Replaces NaN/Inf values with None for JSON compliance."""
    return [{k: _clean_val(v) for k, v in r.items()} for r in records]


def _get_attached_duckdb() -> duckdb.DuckDBPyConnection:
    """Creates a memory connection with both synthetic and vault databases attached."""
    conn = duckdb.connect()
    if os.path.exists(STRUCTURED_DB_PATH):
        conn.execute(f"ATTACH '{STRUCTURED_DB_PATH}' AS synth (READ_ONLY);")
    if os.path.exists(DEFAULT_VAULT_PATH):
        conn.execute(f"ATTACH '{DEFAULT_VAULT_PATH}' AS vault (READ_ONLY);")
    return conn


class LoginRequest(BaseModel):
    username: str
    password: str


class ChatRequest(BaseModel):
    question: str
    role: str = "Employee"
    department: str = "Operations"


class RecordUpdateRequest(BaseModel):
    role: str
    title: Optional[str] = None
    content: Optional[str] = None
    department: Optional[str] = None
    clearance_level: Optional[str] = None
    compliance_label: Optional[int] = None


@app.get("/", response_class=HTMLResponse)
def serve_index():
    index_file = os.path.join(UI_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return "<h1>Corporate AI Desktop initializing...</h1>"


@app.get("/api/auth/users")
def get_users_list():
    return get_all_users()


@app.get("/api/session")
def get_session_endpoint():
    """Returns the desktop-authenticated user so the UI can match its role."""
    if not session.is_authenticated:
        return {"authenticated": False, "user": None}
    return {
        "authenticated": True,
        "user": {
            "username": session.username,
            "full_name": session.full_name,
            "role": session.role,
            "department": session.department,
        },
        "can_access_database": session.role in DB_ACCESS_ROLES,
        "can_write": session.role in WRITE_ROLES,
        "can_admin": session.role in ADMIN_ROLES,
    }


@app.post("/api/auth/login")
def login_endpoint(req: LoginRequest):
    user = authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    session.login(user)
    return {
        "status": "success",
        "user": user,
        "can_access_database": user["role"] in DB_ACCESS_ROLES,
        "can_write": user["role"] in WRITE_ROLES,
        "can_admin": user["role"] in ADMIN_ROLES,
    }


@app.post("/api/chat")
def chat_endpoint(req: ChatRequest):
    """Executes role-aware RAG query against Chroma and Gemini (role decides source, all formats)."""
    global chatbot_instance
    try:
        role = req.role if req.role in SUPPORTED_ROLES else "Employee"
        dept = req.department or "Operations"

        if not chatbot_instance:
            chatbot_instance = CorporateChatbot(user_role=role, user_department=dept)
        else:
            chatbot_instance.set_user(user_role=role, user_department=dept)

        result = chatbot_instance.ask(question=req.question)
        return {
            "status": "success",
            "answer": result["answer"],
            "sources": result.get("sources", []),
            "user_role": result.get("user_role", role),
            "source_scope": result.get("source_scope", "synthetic"),
            "file_type_filter": "all",
        }
    except Exception as e:
        return {
            "status": "error",
            "answer": f"Error: {str(e)}\n(Verify GEMINI_API_KEY is present in your .env file)",
            "sources": [],
        }


@app.get("/api/stats")
def get_stats_endpoint(role: str = "Employee", department: str = "Operations"):
    """Returns database summary stats respecting user RBAC clearance."""
    conn = _get_attached_duckdb()
    try:
        # Build base unified query with RBAC; fail closed to Employee.
        if role not in SUPPORTED_ROLES:
            role = "Employee"
        where_clauses = []
        params = []

        if role == "Admin":
            pass
        elif role == "Manager":
            where_clauses.append("clearance_level IN ('Public', 'Internal', 'Confidential') AND (department = ? OR department IN ('Corporate Operations', 'Operations'))")
            params.append(department)
        elif role == "Analyst":
            where_clauses.append("clearance_level IN ('Public', 'Internal', 'Confidential', 'Restricted')")
        else:
            where_clauses.append("clearance_level IN ('Public', 'Internal') AND allowed_roles LIKE '%All%'")

        # Only Admin may see vault data; every other role sees synthetic only.
        if role != "Admin":
            where_clauses.append("source = 'synthetic'")

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        query = f"""
        WITH unified AS (
            SELECT 
                id,
                department,
                clearance_level,
                CASE 
                    WHEN data_type = 'document_pdf' THEN 'pdf'
                    WHEN data_type IN ('meeting_note', 'notes') THEN 'md'
                    WHEN data_type = 'email' THEN 'csv'
                    WHEN data_type = 'support_ticket' THEN 'json'
                    ELSE 'txt'
                END AS file_type,
                'synthetic' AS source,
                compliance_label,
                COALESCE(allowed_roles, 'All') AS allowed_roles
            FROM synth.synthetic_records

            UNION ALL

            SELECT 
                doc_id AS id,
                department,
                clearance_level,
                file_type,
                'vault' AS source,
                CASE WHEN json_extract_string(attributes, '$.compliance_label') = '1' THEN 1 ELSE 0 END AS compliance_label,
                COALESCE(allowed_roles, 'All') AS allowed_roles
            FROM vault.documents
        )
        SELECT 
            source,
            file_type,
            department,
            clearance_level,
            compliance_label
        FROM unified
        {where_sql};
        """
        df = conn.execute(query, params).fetchdf()

        total = len(df)
        synth_cnt = int((df["source"] == "synthetic").sum()) if total > 0 else 0
        vault_cnt = int((df["source"] == "vault").sum()) if total > 0 else 0

        fmt_counts = df["file_type"].value_counts().to_dict() if total > 0 else {}
        dept_counts = df["department"].value_counts().head(8).to_dict() if total > 0 else {}
        cl_counts = df["clearance_level"].value_counts().to_dict() if total > 0 else {}
        flagged_cnt = int((df["compliance_label"] == 1).sum()) if total > 0 else 0

        return {
            "total_records": total,
            "synthetic_count": synth_cnt,
            "vault_count": vault_cnt,
            "format_counts": {k: int(v) for k, v in fmt_counts.items()},
            "department_counts": {k: int(v) for k, v in dept_counts.items()},
            "clearance_counts": {k: int(v) for k, v in cl_counts.items()},
            "flagged_count": flagged_cnt,
        }
    except Exception as e:
        return {
            "total_records": 0,
            "synthetic_count": 0,
            "vault_count": 0,
            "format_counts": {},
            "department_counts": {},
            "clearance_counts": {},
            "flagged_count": 0,
            "error": str(e),
        }
    finally:
        conn.close()


@app.get("/api/records")
def get_records_endpoint(
    role: str = "Employee",
    department: str = "Operations",
    source_scope: str = "all",
    file_type: str = "all",
    keyword: str = "",
    dept_filter: str = "All",
    clearance_filter: str = "All",
    compliance_filter: str = "All",
    limit: int = 150,
    offset: int = 0,
):
    """
    Returns unified enterprise records (synthetic and/or non-synthetic vault data)
    filtered by user role clearance, source scope, and document format (PDF, MD, CSV, TXT, JSON).
    """
    if role not in DB_ACCESS_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Access denied for your role.",
        )

    conn = _get_attached_duckdb()
    try:
        where_clauses = []
        params = []

        # 1. RBAC enforcement
        if role == "Employee":
            where_clauses.append("clearance_level IN ('Public', 'Internal') AND allowed_roles LIKE '%All%'")
        elif role == "Manager":
            where_clauses.append("clearance_level IN ('Public', 'Internal', 'Confidential') AND (department = ? OR department IN ('Corporate Operations', 'Operations'))")
            params.append(department)
        elif role == "Analyst":
            where_clauses.append("clearance_level IN ('Public', 'Internal', 'Confidential', 'Restricted')")

        # 2. Source Scope filter (All / Synthetic / Vault).
        # Only Admin may see vault data; every other role sees synthetic only.
        effective_scope = effective_source_scope(role, source_scope)
        if effective_scope == "synthetic":
            where_clauses.append("source = 'synthetic'")
        elif effective_scope == "vault":
            where_clauses.append("source = 'vault'")

        # 3. File Format filter (All / PDF / MD / CSV / TXT / JSON)
        if file_type and file_type != "all":
            where_clauses.append("file_type = ?")
            params.append(file_type.lower())

        # 4. Keyword search
        if keyword.strip():
            where_clauses.append("(title ILIKE ? OR content ILIKE ? OR id ILIKE ? OR author ILIKE ? OR source_file ILIKE ?)")
            kw = f"%{keyword.strip()}%"
            params.extend([kw, kw, kw, kw, kw])

        # 5. Department filter
        if dept_filter != "All":
            where_clauses.append("department = ?")
            params.append(dept_filter)

        # 6. Clearance filter
        if clearance_filter != "All":
            where_clauses.append("clearance_level = ?")
            params.append(clearance_filter)

        # 7. Compliance status filter
        if compliance_filter == "Flagged":
            where_clauses.append("compliance_label = 1")
        elif compliance_filter == "Clean":
            where_clauses.append("compliance_label = 0")

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        query = f"""
        WITH unified AS (
            SELECT 
                id,
                title,
                content,
                department,
                clearance_level,
                CASE 
                    WHEN data_type = 'document_pdf' THEN 'pdf'
                    WHEN data_type IN ('meeting_note', 'notes') THEN 'md'
                    WHEN data_type = 'email' THEN 'csv'
                    WHEN data_type = 'support_ticket' THEN 'json'
                    ELSE 'txt'
                END AS file_type,
                data_type,
                'synthetic' AS source,
                TRUE AS is_synthetic,
                author,
                recipient,
                'synthetic_records' AS source_file,
                CAST(created_at AS VARCHAR) AS created_at,
                compliance_label,
                COALESCE(allowed_roles, 'All') AS allowed_roles,
                metadata
            FROM synth.synthetic_records

            UNION ALL

            SELECT 
                doc_id AS id,
                title,
                body_text AS content,
                department,
                clearance_level,
                file_type,
                data_type,
                'vault' AS source,
                FALSE AS is_synthetic,
                COALESCE(json_extract_string(attributes, '$.author'), 'system') AS author,
                COALESCE(json_extract_string(attributes, '$.recipient'), 'all') AS recipient,
                source_file,
                CAST(ingested_at AS VARCHAR) AS created_at,
                CASE WHEN json_extract_string(attributes, '$.compliance_label') = '1' THEN 1 ELSE 0 END AS compliance_label,
                COALESCE(allowed_roles, 'All') AS allowed_roles,
                attributes AS metadata
            FROM vault.documents
        )
        SELECT 
            id,
            title,
            substring(content, 1, 300) AS snippet,
            department,
            clearance_level,
            file_type,
            data_type,
            source,
            is_synthetic,
            author,
            recipient,
            source_file,
            created_at,
            compliance_label,
            length(content) AS char_length
        FROM unified
        {where_sql}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?;
        """
        params.extend([limit, offset])

        df = conn.execute(query, params).fetchdf()
        return _safe_records(df.to_dict(orient="records"))
    except Exception as e:
        print(f"[Error querying records]: {e}")
        return []
    finally:
        conn.close()


@app.get("/api/suggest")
def suggest_endpoint(
    q: str = "",
    role: str = "Employee",
    department: str = "Operations",
    source_scope: str = "all",
    file_type: str = "all",
    limit: int = 8,
):
    """
    Returns top title/ID autocomplete suggestions for the search box.
    Same RBAC scoping as /api/records; only matches titles/IDs the
    caller's role is cleared to see. Frontend triggers at 2+ chars.
    """
    if role not in DB_ACCESS_ROLES:
        raise HTTPException(status_code=403, detail="Access denied for your role.")
    query = (q or "").strip()
    if len(query) < 2:
        return []
    limit = max(1, min(limit, 20))

    conn = _get_attached_duckdb()
    try:
        where_clauses = []
        params = []

        # 1. RBAC enforcement (mirrors /api/records)
        if role == "Employee":
            where_clauses.append("clearance_level IN ('Public', 'Internal') AND allowed_roles LIKE '%All%'")
        elif role == "Manager":
            where_clauses.append("clearance_level IN ('Public', 'Internal', 'Confidential') AND (department = ? OR department IN ('Corporate Operations', 'Operations'))")
            params.append(department)
        elif role == "Analyst":
            where_clauses.append("clearance_level IN ('Public', 'Internal', 'Confidential', 'Restricted')")

        # 2. Source scope (non-Admin roles forced to synthetic only).
        effective_scope = effective_source_scope(role, source_scope)
        if effective_scope == "synthetic":
            where_clauses.append("source = 'synthetic'")
        elif effective_scope == "vault":
            where_clauses.append("source = 'vault'")

        # 3. Format filter
        if file_type and file_type != "all":
            where_clauses.append("file_type = ?")
            params.append(file_type.lower())

        # 4. Prefix-ranked title/ID match
        where_clauses.append("(title ILIKE ? OR id ILIKE ?)")
        like = f"%{query}%"
        params.extend([like, like])
        prefix = f"{query}%"
        params.append(prefix)

        where_sql = f"WHERE {' AND '.join(where_clauses)}"

        sql = f"""
        WITH unified AS (
            SELECT
                id, title, department, clearance_level,
                CASE
                    WHEN data_type = 'document_pdf' THEN 'pdf'
                    WHEN data_type IN ('meeting_note', 'notes') THEN 'md'
                    WHEN data_type = 'email' THEN 'csv'
                    WHEN data_type = 'support_ticket' THEN 'json'
                    ELSE 'txt'
                END AS file_type,
                'synthetic' AS source,
                TRUE AS is_synthetic,
                COALESCE(allowed_roles, 'All') AS allowed_roles
            FROM synth.synthetic_records
            UNION ALL
            SELECT
                doc_id AS id, title, department, clearance_level,
                file_type, 'vault' AS source, FALSE AS is_synthetic,
                COALESCE(allowed_roles, 'All') AS allowed_roles
            FROM vault.documents
        )
        SELECT id, title, file_type, source, is_synthetic, department, clearance_level
        FROM unified
        {where_sql}
        ORDER BY CASE WHEN title ILIKE ? THEN 0 ELSE 1 END, title
        LIMIT ?;
        """
        params.append(limit)

        df = conn.execute(sql, params).fetchdf()
        return _safe_records(df.to_dict(orient="records"))
    except Exception as e:
        print(f"[Error suggesting records]: {e}")
        return []
    finally:
        conn.close()


@app.get("/api/records/{record_id}")
def get_single_record(record_id: str, role: str = "Employee", department: str = "Operations"):
    """
    Returns full record content formatted according to its document type:
    PDF (pages and metadata), Markdown (rendered/raw), CSV (parsed table grid), or Text/Email.
    """
    if role not in DB_ACCESS_ROLES:
        raise HTTPException(status_code=403, detail="Access denied.")

    conn = _get_attached_duckdb()
    try:
        query = """
        WITH unified AS (
            SELECT 
                id,
                title,
                content,
                department,
                clearance_level,
                CASE 
                    WHEN data_type = 'document_pdf' THEN 'pdf'
                    WHEN data_type IN ('meeting_note', 'notes') THEN 'md'
                    WHEN data_type = 'email' THEN 'csv'
                    WHEN data_type = 'support_ticket' THEN 'json'
                    ELSE 'txt'
                END AS file_type,
                data_type,
                'synthetic' AS source,
                TRUE AS is_synthetic,
                author,
                recipient,
                'synthetic_records' AS source_file,
                CAST(created_at AS VARCHAR) AS created_at,
                compliance_label,
                COALESCE(allowed_roles, 'All') AS allowed_roles,
                metadata
            FROM synth.synthetic_records

            UNION ALL

            SELECT 
                doc_id AS id,
                title,
                body_text AS content,
                department,
                clearance_level,
                file_type,
                data_type,
                'vault' AS source,
                FALSE AS is_synthetic,
                COALESCE(json_extract_string(attributes, '$.author'), 'system') AS author,
                COALESCE(json_extract_string(attributes, '$.recipient'), 'all') AS recipient,
                source_file,
                CAST(ingested_at AS VARCHAR) AS created_at,
                CASE WHEN json_extract_string(attributes, '$.compliance_label') = '1' THEN 1 ELSE 0 END AS compliance_label,
                COALESCE(allowed_roles, 'All') AS allowed_roles,
                attributes AS metadata
            FROM vault.documents
        )
        SELECT * FROM unified WHERE id = ?;
        """
        row = conn.execute(query, [record_id]).fetchdf()
        if row.empty:
            raise HTTPException(status_code=404, detail="Record not found.")

        rec = _safe_records(row.to_dict(orient="records"))[0]
        meta = rec.get("metadata")
        if isinstance(meta, str):
            try:
                rec["metadata"] = json.loads(meta)
            except Exception:
                rec["metadata"] = {}

        ftype = rec.get("file_type", "txt").lower()
        content = rec.get("content", "")

        # Format-specific enrichment
        parsed_view = {}
        if ftype == "csv":
            # Attempt to parse CSV rows if content looks like tabular/csv data
            try:
                reader = csv.reader(io.StringIO(content.strip()))
                rows = list(reader)
                if len(rows) > 1 and len(rows[0]) > 1:
                    headers = rows[0]
                    data_rows = rows[1:60]
                    parsed_view["type"] = "csv_table"
                    parsed_view["headers"] = headers
                    parsed_view["rows"] = data_rows
                    parsed_view["total_rows"] = len(rows)
            except Exception:
                pass

        elif ftype == "pdf":
            parsed_view["type"] = "pdf_doc"
            parsed_view["page_number"] = rec["metadata"].get("page_number", 1)
            parsed_view["total_pages"] = rec["metadata"].get("total_pages", 1)
            parsed_view["document_title"] = rec["metadata"].get("document_title", rec.get("title"))

        elif ftype == "md":
            parsed_view["type"] = "markdown"
            parsed_view["line_count"] = len(content.splitlines())
            parsed_view["word_count"] = len(content.split())

        elif ftype == "json":
            try:
                parsed_view["type"] = "json_tree"
                parsed_view["json_data"] = json.loads(content)
            except Exception:
                pass

        rec["parsed_view"] = parsed_view
        return rec
    finally:
        conn.close()


@app.patch("/api/records/{record_id}")
def update_record(record_id: str, req: RecordUpdateRequest):
    """Updates editable fields of a synthetic record. Restricted to Admin only."""
    if req.role not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Only Admin users can edit records.")

    updates = {}
    if req.title is not None:
        updates["title"] = req.title
    if req.content is not None:
        updates["content"] = req.content
    if req.department is not None:
        updates["department"] = req.department
    if req.clearance_level is not None:
        updates["clearance_level"] = req.clearance_level
    if req.compliance_label is not None:
        updates["compliance_label"] = req.compliance_label

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update.")

    # Try synthetic DB first
    conn = duckdb.connect(STRUCTURED_DB_PATH, read_only=False)
    try:
        set_clauses = ", ".join([f"{k} = ?" for k in updates.keys()])
        params = list(updates.values()) + [record_id]
        res = conn.execute(
            f"UPDATE synthetic_records SET {set_clauses} WHERE id = ?;",
            params,
        )
        return {"status": "success", "record_id": record_id, "updated_fields": list(updates.keys())}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.delete("/api/records/{record_id}")
def delete_record(record_id: str, role: str = "Employee"):
    """Permanently deletes a record. Restricted to Admin only."""
    if role not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Only Admin users can delete records.")

    # Check synthetic DB
    s_conn = duckdb.connect(STRUCTURED_DB_PATH, read_only=False)
    try:
        chk = s_conn.execute("SELECT id FROM synthetic_records WHERE id = ?;", [record_id]).fetchall()
        if chk:
            s_conn.execute("DELETE FROM synthetic_records WHERE id = ?;", [record_id])
            return {"status": "success", "deleted_id": record_id, "source": "synthetic"}
    finally:
        s_conn.close()

    # Check vault DB
    v_conn = duckdb.connect(DEFAULT_VAULT_PATH, read_only=False)
    try:
        chk = v_conn.execute("SELECT doc_id FROM documents WHERE doc_id = ?;", [record_id]).fetchall()
        if chk:
            v_conn.execute("DELETE FROM documents WHERE doc_id = ?;", [record_id])
            return {"status": "success", "deleted_id": record_id, "source": "vault"}
    finally:
        v_conn.close()

    raise HTTPException(status_code=404, detail="Record not found.")


@app.post("/api/upload")
async def upload_file_endpoint(
    file: UploadFile = File(...),
    department: str = Form("Operations"),
    clearance_level: str = Form("Internal"),
    role: str = Form("Employee"),
    fidelity: str = Form("balanced"),
):
    """
    Ingests new enterprise files (.pdf, .md, .csv, .txt, .json) into the vault,
    synthesizes representative records, and updates the vector store.
    Restricted to Admin and Manager.
    """
    if role not in WRITE_ROLES:
        raise HTTPException(status_code=403, detail="Only Admin and Manager can upload files.")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    dest_path = os.path.join(UPLOAD_DIR, file.filename)

    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        ingest_res = ingest_file(
            file_path=dest_path,
            department=department,
            clearance_level=clearance_level,
        )
        synth_res = synthesize_from_file(
            source_file=dest_path,
            n_records=200,
            use_ollama=False,
            clearance_level=clearance_level,
            fidelity=fidelity,
            department=department,
        )
        build_vector_store(force_reindex=True)

        return {
            "status": "success",
            "filename": file.filename,
            "records_ingested": ingest_res.get("records_ingested", 0),
            "records_synthesized": synth_res.get("records_synthesized", 0),
            "message": f"Successfully ingested and indexed '{file.filename}' ({clearance_level} clearance).",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
