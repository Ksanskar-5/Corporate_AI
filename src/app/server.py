"""
server.py — FastAPI Local Backend for Desktop Application

Role access matrix:
  Admin    — full: chat, records (view/edit/delete), upload
  Manager  — chat, records (view), upload
  Analyst  — chat, records (view, read-only)
  Employee — chat only
"""

import os
import math
import json
import duckdb
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import Optional
import shutil

from .auth_db import (
    authenticate_user, get_all_users, SUPPORTED_ROLES,
    DB_ACCESS_ROLES, WRITE_ROLES, ADMIN_ROLES
)
from .session import session
from ..agent.chatbot import CorporateChatbot
from ..synthesis.db import STRUCTURED_DB_PATH, get_synthetic_stats
from ..ingestion.vault import DEFAULT_VAULT_PATH, get_vault_stats
from ..ingestion.ingestor import ingest_file
from ..synthesis.engine import synthesize_from_file
from ..agent.vector_store import build_vector_store

app = FastAPI(title="Corporate AI Desktop Backend")

UI_DIR = os.path.join(os.path.dirname(__file__), "ui")
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "raw")

chatbot_instance = None


def _safe_records(records: list[dict]) -> list[dict]:
    """Replace NaN/Inf float values (non-JSON-compliant) with None."""
    def _clean(v):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        return v
    return [{k: _clean(v) for k, v in r.items()} for r in records]


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
    """Executes role-aware RAG query against Chroma and Gemini."""
    global chatbot_instance
    try:
        role = req.role if req.role in SUPPORTED_ROLES else "Employee"
        dept = req.department or "Operations"

        if not chatbot_instance:
            chatbot_instance = CorporateChatbot(user_role=role, user_department=dept)
        else:
            chatbot_instance.set_user(user_role=role, user_department=dept)

        result = chatbot_instance.ask(req.question)
        return {
            "status": "success",
            "answer": result["answer"],
            "sources": result.get("sources", []),
            "user_role": result.get("user_role", role),
        }
    except Exception as e:
        return {
            "status": "error",
            "answer": f"Error: {str(e)}\n(Verify GEMINI_API_KEY is present in your .env file)",
            "sources": [],
        }


@app.get("/api/records")
def get_records_endpoint(
    role: str = "Employee",
    department: str = "Operations",
    keyword: str = "",
    dept_filter: str = "All",
    clearance_filter: str = "All",
    compliance_filter: str = "All",
    limit: int = 200,
):
    """
    Returns synthetic database records.
    Blocked for Employee role — use the assistant instead.
    Manager sees their department scope; Admin and Analyst see all.
    """
    if role not in DB_ACCESS_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Employees do not have direct database access. Please use the AI Assistant.",
        )

    conn = duckdb.connect(STRUCTURED_DB_PATH, read_only=True)
    try:
        where_clauses = []
        params = []

        # Manager: scoped to their department + Internal/below clearance
        if role == "Manager":
            where_clauses.append(
                "clearance_level IN ('Public', 'Internal', 'Confidential') "
                "AND (department = ? OR department = 'Operations')"
            )
            params.append(department)

        if keyword.strip():
            where_clauses.append("(title ILIKE ? OR content ILIKE ? OR id ILIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])

        if dept_filter != "All":
            where_clauses.append("department = ?")
            params.append(dept_filter)

        if clearance_filter != "All":
            where_clauses.append("clearance_level = ?")
            params.append(clearance_filter)

        if compliance_filter == "Flagged":
            where_clauses.append("compliance_label = 1")
        elif compliance_filter == "Clean":
            where_clauses.append("compliance_label = 0")

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        query = f"SELECT * FROM synthetic_records {where_sql} ORDER BY created_at DESC LIMIT ?;"
        params.append(limit)

        df = conn.execute(query, params).fetchdf()
        return _safe_records(df.to_dict(orient="records"))
    except Exception:
        return []
    finally:
        conn.close()


@app.get("/api/records/{record_id}")
def get_single_record(record_id: str, role: str = "Employee"):
    """Returns a single full record for detail/edit view."""
    if role not in DB_ACCESS_ROLES:
        raise HTTPException(status_code=403, detail="Access denied.")

    conn = duckdb.connect(STRUCTURED_DB_PATH, read_only=True)
    try:
        row = conn.execute(
            "SELECT * FROM synthetic_records WHERE id = ?;", [record_id]
        ).fetchdf()
        if row.empty:
            raise HTTPException(status_code=404, detail="Record not found.")
        return _safe_records(row.to_dict(orient="records"))[0]
    finally:
        conn.close()


@app.patch("/api/records/{record_id}")
def update_record(record_id: str, req: RecordUpdateRequest):
    """
    Updates editable fields of a synthetic record.
    Restricted to Admin only.
    """
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

    conn = duckdb.connect(STRUCTURED_DB_PATH, read_only=False)
    try:
        set_clauses = ", ".join([f"{k} = ?" for k in updates.keys()])
        params = list(updates.values()) + [record_id]
        conn.execute(
            f"UPDATE synthetic_records SET {set_clauses} WHERE id = ?;",
            params,
        )
        return {"status": "success", "record_id": record_id, "updated_fields": list(updates.keys())}
    finally:
        conn.close()


@app.delete("/api/records/{record_id}")
def delete_record(record_id: str, role: str = "Employee"):
    """
    Permanently deletes a synthetic record.
    Restricted to Admin only.
    """
    if role not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Only Admin users can delete records.")

    conn = duckdb.connect(STRUCTURED_DB_PATH, read_only=False)
    try:
        result = conn.execute(
            "SELECT id FROM synthetic_records WHERE id = ?;", [record_id]
        ).fetchdf()
        if result.empty:
            raise HTTPException(status_code=404, detail="Record not found.")
        conn.execute("DELETE FROM synthetic_records WHERE id = ?;", [record_id])
        return {"status": "success", "deleted_id": record_id}
    finally:
        conn.close()


@app.post("/api/upload")
async def upload_file_endpoint(
    file: UploadFile = File(...),
    department: str = Form("Operations"),
    clearance_level: str = Form("Internal"),
    role: str = Form("Employee"),
):
    """
    Ingests and synthesizes new uploaded enterprise files.
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
            n_records=20,
            use_ollama=False,
            clearance_level=clearance_level,
        )
        build_vector_store(force_reindex=True)

        return {
            "status": "success",
            "filename": file.filename,
            "records_ingested": ingest_res.get("records_ingested", 0),
            "records_synthesized": synth_res.get("records_synthesized", 0),
            "message": f"Ingested '{file.filename}' ({clearance_level} clearance).",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
