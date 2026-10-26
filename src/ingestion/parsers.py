"""
parsers.py — Simple, readable parsers for enterprise files (CSV, JSON, PDF, TXT).
Converts any file format into a standard canonical document structure.
"""

import os
import uuid
import pandas as pd
import pypdf

# Common text column candidates across enterprise datasets
TEXT_CANDIDATES = [
    "body", "email_body", "text", "content", "message",
    "description", "issue_description", "notes", "statement", "transcript"
]

# Common title/subject column candidates
TITLE_CANDIDATES = [
    "subject", "title", "summary", "topic", "ticket_title", "header"
]


def _auto_detect_column(columns: list, candidates: list) -> str:
    """Finds the best matching column name from a list of candidates."""
    col_map = {str(c).lower().strip(): c for c in columns}
    for candidate in candidates:
        if candidate in col_map:
            return col_map[candidate]
    return None


def _infer_data_type(columns: list, file_ext: str) -> str:
    """Guesses the enterprise data type based on headers or file extension."""
    cols_lower = [str(c).lower() for c in columns]
    if any(k in cols_lower for k in ["from", "to", "subject", "message-id", "mail-id"]):
        return "email"
    if any(k in cols_lower for k in ["ticket", "priority", "ticket_id", "severity", "resolution"]):
        return "support_ticket"
    if file_ext == ".pdf":
        return "document_pdf"
    if file_ext in [".txt", ".md"]:
        return "meeting_note"
    return "general"


def parse_csv(
    file_path: str,
    sample_size: int = None,
    text_col: str = None,
    title_col: str = None,
) -> list[dict]:
    """Parses a CSV file into canonical document records."""
    df = pd.read_csv(file_path, nrows=sample_size, low_memory=False)
    if df.empty:
        return []

    source_file = os.path.basename(file_path)
    columns = df.columns.tolist()

    # Detect text and title columns
    text_column = text_col or _auto_detect_column(columns, TEXT_CANDIDATES) or columns[0]
    title_column = title_col or _auto_detect_column(columns, TITLE_CANDIDATES)
    data_type = _infer_data_type(columns, ".csv")

    metadata_cols = [c for c in columns if c != text_column]

    docs = []
    for idx, row in df.iterrows():
        primary_text = str(row[text_column]) if pd.notnull(row[text_column]) else ""
        title = str(row[title_column]) if title_column and pd.notnull(row[title_column]) else f"{source_file} #{idx + 1}"

        # Collect all remaining columns into attributes
        attributes = {}
        for c in metadata_cols:
            val = row[c]
            if pd.isna(val):
                attributes[c] = None
            elif isinstance(val, (int, float, bool, str)):
                attributes[c] = val
            else:
                attributes[c] = str(val)

        doc_id = f"{data_type}_{source_file}_{idx + 1}"
        docs.append({
            "doc_id": doc_id,
            "source_file": source_file,
            "data_type": data_type,
            "title": title,
            "primary_text": primary_text,
            "attributes": attributes,
            "token_count": len(primary_text.split()),
        })

    return docs


def parse_json(
    file_path: str,
    sample_size: int = None,
    text_col: str = None,
) -> list[dict]:
    """Parses a JSON or JSONL file into canonical document records."""
    is_jsonl = file_path.endswith(".jsonl")
    if is_jsonl:
        df = pd.read_json(file_path, lines=True, nrows=sample_size)
    else:
        df = pd.read_json(file_path)
        if sample_size and not df.empty:
            df = df.head(sample_size)
    if df.empty:
        return []

    source_file = os.path.basename(file_path)
    columns = df.columns.tolist()

    text_column = text_col or _auto_detect_column(columns, TEXT_CANDIDATES) or columns[0]
    title_column = _auto_detect_column(columns, TITLE_CANDIDATES)
    data_type = _infer_data_type(columns, ".json")

    metadata_cols = [c for c in columns if c != text_column]

    docs = []
    for idx, row in df.iterrows():
        primary_text = str(row[text_column]) if pd.notnull(row[text_column]) else ""
        title = str(row[title_column]) if title_column and pd.notnull(row[title_column]) else f"{source_file} #{idx + 1}"

        attributes = {c: (None if pd.isna(row[c]) else row[c]) for c in metadata_cols}

        docs.append({
            "doc_id": f"{data_type}_{source_file}_{idx + 1}",
            "source_file": source_file,
            "data_type": data_type,
            "title": title,
            "primary_text": primary_text,
            "attributes": attributes,
            "token_count": len(primary_text.split()),
        })

    return docs


def parse_pdf(file_path: str) -> list[dict]:
    """
    Parses a PDF file page by page into canonical document records.
    Preserves page numbers, total pages, and document metadata.
    """
    source_file = os.path.basename(file_path)
    reader = pypdf.PdfReader(file_path)
    total_pages = len(reader.pages)

    # Extract document-level info if available
    pdf_info = reader.metadata or {}
    author = str(pdf_info.get("/Author", "Unknown"))
    doc_title = str(pdf_info.get("/Title", os.path.splitext(source_file)[0]))

    docs = []
    for page_idx, page in enumerate(reader.pages):
        page_text = page.extract_text() or ""
        if not page_text.strip():
            continue

        page_num = page_idx + 1
        docs.append({
            "doc_id": f"pdf_{source_file}_p{page_num}",
            "source_file": source_file,
            "data_type": "document_pdf",
            "title": f"{doc_title} (Page {page_num})",
            "primary_text": page_text.strip(),
            "attributes": {
                "document_title": doc_title,
                "page_number": page_num,
                "total_pages": total_pages,
                "author": author,
            },
            "token_count": len(page_text.split()),
        })

    return docs


def parse_text(file_path: str) -> list[dict]:
    """Parses plain text (.txt) or markdown (.md) into a canonical document."""
    source_file = os.path.basename(file_path)
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read().strip()

    if not content:
        return []

    # Title is first non-empty line or filename
    first_line = content.split("\n")[0].strip("# ")
    title = first_line if len(first_line) < 100 else os.path.splitext(source_file)[0]

    return [{
        "doc_id": f"text_{source_file}",
        "source_file": source_file,
        "data_type": "meeting_note",
        "title": title,
        "primary_text": content,
        "attributes": {
            "file_size_bytes": os.path.getsize(file_path),
            "line_count": len(content.splitlines()),
        },
        "token_count": len(content.split()),
    }]
