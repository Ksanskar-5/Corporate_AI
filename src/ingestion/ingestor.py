"""
ingestor.py — Universal Ingestion Controller
Takes any enterprise file (CSV, JSON, PDF, TXT), automatically parses it,
and stores it in the local DuckDB vault.
"""

import os
from .parsers import parse_csv, parse_json, parse_pdf, parse_text
from .vault import save_documents, get_vault_stats, query_vault, clear_vault


def ingest_file(
    file_path: str,
    sample_size: int = None,
    text_col: str = None,
    title_col: str = None,
    department: str = None,
    allowed_roles: list[str] = None,
    clearance_level: str = None,
) -> dict:
    """
    Ingests a single file into the unified DuckDB vault with RBAC attributes.

    Parameters
    ----------
    file_path : str
        Path to the file to ingest (.csv, .json, .pdf, .txt, .md).
    sample_size : int, optional
        Limit number of rows for large tabular files.
    text_col : str, optional
        Manually override the primary text column name if needed.
    title_col : str, optional
        Manually override the title/subject column name if needed.
    department : str, optional
        Corporate department responsible for this data (e.g. 'Engineering', 'Trading').
    allowed_roles : list[str], optional
        Roles authorized to access this data (e.g. ['Executive', 'Department_Manager'] or ['All']).
    clearance_level : str, optional
        Clearance classification ('Public', 'Internal', 'Confidential', 'Restricted').

    Returns
    -------
    dict
        Summary containing filename, detected format, record count, and vault stats.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()

    # Route to the appropriate parser based on file extension
    if ext == ".csv":
        documents = parse_csv(file_path, sample_size=sample_size, text_col=text_col, title_col=title_col)
    elif ext in [".json", ".jsonl"]:
        documents = parse_json(file_path, sample_size=sample_size, text_col=text_col)
    elif ext == ".pdf":
        documents = parse_pdf(file_path)
    elif ext in [".txt", ".md"]:
        documents = parse_text(file_path)
    else:
        raise ValueError(f"Unsupported file format: {ext}. Supported: .csv, .json, .pdf, .txt, .md")

    if not documents:
        return {
            "status": "empty",
            "file": os.path.basename(file_path),
            "records_ingested": 0,
        }

    # Attach RBAC attributes if specified at ingestion time
    for doc in documents:
        if department:
            doc["department"] = department
        if allowed_roles:
            doc["allowed_roles"] = allowed_roles
        if clearance_level:
            doc["clearance_level"] = clearance_level

    # Save documents into the unified DuckDB vault
    inserted_count = save_documents(documents)
    vault_summary = get_vault_stats()

    first_text = documents[0].get("body_text", "")
    return {
        "status": "success",
        "file": os.path.basename(file_path),
        "data_type": documents[0]["data_type"],
        "records_ingested": inserted_count,
        "sample_title": documents[0]["title"],
        "sample_preview": first_text[:120],
        "vault_total": vault_summary["total_documents"],
        "vault_breakdown": vault_summary["data_type_breakdown"],
        "clearance_breakdown": vault_summary["clearance_breakdown"],
    }


def ingest_files(
    file_paths: list[str],
    sample_size: int = None,
    department: str = None,
    allowed_roles: list[str] = None,
    clearance_level: str = None,
) -> list[dict]:
    """Ingests a list of different files all into the same unified vault."""
    results = []
    for path in file_paths:
        try:
            res = ingest_file(
                path,
                sample_size=sample_size,
                department=department,
                allowed_roles=allowed_roles,
                clearance_level=clearance_level,
            )
            results.append(res)
        except Exception as e:
            results.append({
                "status": "error",
                "file": os.path.basename(path),
                "error": str(e),
            })
    return results
