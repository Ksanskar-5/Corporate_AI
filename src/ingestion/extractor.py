"""
extractor.py — Universal Feature Extractor for Synthesis
Extracts the target text, conditioning prompts, and relevant context attributes
from DuckDB, filtering out technical noise (MIME, server hashes, nulls).
"""

import json
from .vault import get_connection, DEFAULT_VAULT_PATH

# Metadata keys that represent server infrastructure or noise (to exclude)
NOISE_KEYS = {
    "mime-version", "content-type", "content-transfer-encoding",
    "x-filename", "x-origin", "x-folder", "x-bcc",
    "message-id", "mail-id", "source"
}


def _clean_context_attributes(attributes: dict) -> dict:
    """
    Cleans raw metadata dictionary:
    - Removes infrastructure noise (MIME, hashes, lotus notes paths)
    - Drops null / empty values
    - Keeps meaningful business context (dates, actors, labels, priorities)
    """
    clean_meta = {}
    for key, val in attributes.items():
        k_lower = str(key).lower().strip()
        if k_lower in NOISE_KEYS:
            continue
        if val is None or val == "" or str(val).lower() == "nan":
            continue
        clean_meta[key] = val
    return clean_meta


def extract_synthesis_records(
    data_type: str = None,
    limit: int = None,
    min_word_count: int = 5,
    db_path: str = DEFAULT_VAULT_PATH,
) -> list[dict]:
    """
    Extracts structured training records from the DuckDB vault.

    Parameters
    ----------
    data_type : str, optional
        Filter by data type ('email', 'support_ticket', 'document_pdf', 'meeting_note').
    limit : int, optional
        Maximum number of records to extract.
    min_word_count : int
        Filter out empty or near-empty texts.

    Returns
    -------
    list[dict]
        List of standardized records:
        {
            "doc_id": str,
            "data_type": str,
            "target_text": str,           # The core text to synthesize
            "conditioning_prompt": str,   # Seed / title / subject
            "context": dict,              # Cleaned business metadata
            "token_count": int
        }
    """
    conn = get_connection(db_path)
    try:
        query = """
            SELECT doc_id, data_type, title, primary_text, attributes, token_count
            FROM unified_vault
            WHERE token_count >= ?
        """
        params = [min_word_count]

        if data_type:
            query += " AND data_type = ?"
            params.append(data_type)

        query += " ORDER BY doc_id"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        df = conn.execute(query, params).fetchdf()
    finally:
        conn.close()

    if df.empty:
        return []

    records = []
    for _, row in df.iterrows():
        raw_attrs = row["attributes"]
        if isinstance(raw_attrs, str):
            try:
                raw_attrs = json.loads(raw_attrs)
            except Exception:
                raw_attrs = {}
        elif not isinstance(raw_attrs, dict):
            raw_attrs = {}

        clean_context = _clean_context_attributes(raw_attrs)

        records.append({
            "doc_id": row["doc_id"],
            "data_type": row["data_type"],
            "target_text": str(row["primary_text"]).strip(),
            "conditioning_prompt": str(row["title"]).strip(),
            "context": clean_context,
            "token_count": int(row["token_count"]),
        })

    return records
