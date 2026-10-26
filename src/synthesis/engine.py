"""
engine.py — Generalized Batch JSON LLM Synthesis Engine
Synthesizes privacy-safe enterprise records across all 5 file types:
1. Emails & Communications (.csv, .json, .eml)
2. Support & IT Tickets (.csv, .json, .jsonl)
3. Corporate Policies & Reports (.pdf)
4. Meeting Notes & Executive Memos (.txt, .md)
5. Structured Operational Logs & Financial Transactions (.csv, .json)

All records are stored in data/synthetic_database.duckdb to power the AI Agent
with full context on ongoing company processes without leaking raw confidential data.
"""

import os
import re
import json
import random
import urllib.request
import urllib.error
from .db import save_synthetic_batch, get_synthetic_stats, get_synthetic_records
from ..ingestion.vault import get_connection as get_vault_conn
from ..ingestion.parsers import parse_csv, parse_json, parse_pdf, parse_text

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "gemma3:4b"

# Department personas by domain
ENTERPRISE_DEPARTMENTS = [
    "Legal & Regulatory Compliance",
    "Trading & Risk Management",
    "Corporate Operations",
    "Engineering & IT Systems",
    "Finance & Accounting Audit",
    "Executive Leadership",
    "Customer Support & Success",
]


def _call_ollama_batch(prompt: str, model: str = DEFAULT_MODEL, timeout: int = 90) -> list[dict]:
    """Sends a single request to Ollama asking for a JSON array of records."""
    payload = {
        "model": model,
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "keep_alive": "0s",  # Instantly unload model from memory after generation
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        raw_text = res.get("response", "[]").strip()
        parsed = json.loads(raw_text)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            for v in parsed.values():
                if isinstance(v, list):
                    return v
            return [parsed]
        return []


def _apply_user_constraints(
    text: str,
    forbidden_terms: list[str] = None,
    custom_replacements: dict = None,
) -> str:
    """Applies user redactions and custom aliases to generated text."""
    if not text:
        return ""

    # 1. Custom replacements (e.g. "Enron" -> "ApexGlobal")
    if custom_replacements:
        for secret, alias in custom_replacements.items():
            if secret:
                pattern = rf"\b{re.escape(secret)}\b" if secret.isalnum() else re.escape(secret)
                text = re.sub(pattern, alias, text, flags=re.IGNORECASE)

    # 2. Redact forbidden terms with word boundaries
    if forbidden_terms:
        for term in forbidden_terms:
            if term:
                pattern = rf"\b{re.escape(term)}\b" if term.isalnum() else re.escape(term)
                text = re.sub(pattern, "[REDACTED]", text, flags=re.IGNORECASE)

    # 3. Clean any residual real emails or phone numbers
    text = re.sub(r"[a-zA-Z0-9._%+-]+@enron\.com", "employee@company.internal", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b", "555-0199", text)
    return text


def _get_type_guidance(data_type: str) -> tuple[str, str, str]:
    """Returns domain instructions, title label, and content label for each data type."""
    data_type_lower = (data_type or "general").lower()
    if "email" in data_type_lower:
        return (
            "corporate communications, operational updates, and deal approvals",
            "Subject line",
            "Natural 2-3 paragraph corporate email body",
        )
    if "ticket" in data_type_lower:
        return (
            "technical support tickets, system incident investigations, and resolution workflows",
            "Issue Summary / Ticket Title",
            "Incident description, root cause investigation, and resolution notes",
        )
    if "pdf" in data_type_lower or "policy" in data_type_lower:
        return (
            "corporate governance policies, compliance manuals, and standard operating procedures (SOP)",
            "Policy / Procedure Title",
            "Detailed regulatory standards, enforcement rules, and compliance requirements",
        )
    if "note" in data_type_lower or "meeting" in data_type_lower or "memo" in data_type_lower:
        return (
            "executive syncs, weekly departmental standups, and strategic project roadmaps",
            "Meeting Topic / Memo Title",
            "Meeting minutes, key decisions, process bottlenecks, and action items",
        )
    return (
        "enterprise operations, business workflows, and departmental audit processes",
        "Document / Process Title",
        "Comprehensive operational narrative detailing the company process, decisions, and status",
    )


def _build_synthesis_prompt(
    data_type: str,
    reference_items: list[dict],
    batch_size: int,
    user_rules_text: str,
) -> str:
    """Builds a generalized LLM prompt tailored to the specific enterprise data type."""
    type_domain, title_hint, body_hint = _get_type_guidance(data_type)

    # Prepare reference summaries
    ref_summaries = []
    has_audit_risk = False
    has_exec = False
    for item in reference_items[:batch_size]:
        t = item.get("title") or item.get("subject") or "Operations"
        snippet = (item.get("primary_text") or item.get("content") or item.get("body") or "")[:120]
        ref_summaries.append(f"- Topic: {t} | Context: {snippet}")
        if item.get("compliance_label", 0) == 1:
            has_audit_risk = True
        if item.get("is_executive", False):
            has_exec = True

    topics_block = "\n".join(ref_summaries) if ref_summaries else "- General enterprise operations and governance"

    return f"""
You are an enterprise AI data synthesizer.
Generate a JSON object containing a "records" array with {batch_size} distinct, realistic synthetic enterprise {data_type} records.

DOMAIN FOCUS:
Generate {type_domain}.
The synthetic data must reflect realistic ongoing corporate processes, team interactions, and operational status
so an AI agent can understand company workflows and operations without seeing private raw data.

INPUT REFERENCE CONTEXT (Mirror these real operational themes):
{topics_block}

BATCH FLAGS:
- Contains High-Risk / Audit Signals: {has_audit_risk}
- Executive Leadership Involved: {has_exec}

USER CONFIDENTIALITY CONSTRAINTS:
{user_rules_text}

SCHEMA REQUIREMENTS:
Respond ONLY with a JSON object in this exact structure:
{{
  "records": [
    {{
      "title": "Concise summary or subject line",
      "content": "Detailed 2-3 paragraph enterprise text detailing the ongoing company process, status, and decisions",
      "data_type": "{data_type}",
      "department": "One of: Legal & Regulatory Compliance, Trading & Risk Management, Corporate Operations, Engineering & IT Systems, Finance & Accounting Audit, Executive Leadership",
      "author_or_sender": "first.last@company.internal or Department Lead",
      "recipient_or_audience": "first.last@company.internal or All Employees",
      "compliance_label": 0,
      "is_executive": false
    }}
  ]
}}
"""


def _generate_fallback_records(
    reference_items: list[dict],
    data_type: str,
    batch_size: int,
) -> list[dict]:
    """Fast, deterministic fallback generator preserving ongoing process details."""
    records = []
    type_domain, _, _ = _get_type_guidance(data_type)

    for i in range(batch_size):
        ref = reference_items[i] if i < len(reference_items) else {}
        base_title = ref.get("title") or ref.get("subject") or f"Enterprise Review #{i+1}"
        base_text = ref.get("primary_text") or ref.get("content") or ref.get("body") or "Standard ongoing enterprise workflow."
        first_clause = base_text.split(".")[0] if "." in base_text else base_text[:120]

        dept = random.choice(ENTERPRISE_DEPARTMENTS)
        is_risk = ref.get("compliance_label", 0) == 1 or (i % 6 == 0)
        is_exec = ref.get("is_executive", False) or ("executive" in dept.lower())

        records.append({
            "title": f"Synthetic Process: {base_title[:60]}",
            "content": f"Operational Process Review regarding {base_title}. Context: {first_clause.strip()}. All associated enterprise procedures, documentation, and compliance checkpoints have been audited in accordance with {dept} protocols.",
            "data_type": data_type,
            "department": dept,
            "author_or_sender": f"lead.{dept.split()[0].lower()}@company.internal",
            "recipient_or_audience": "corporate-audit@company.internal" if is_risk else "operations-team@company.internal",
            "compliance_label": 1 if is_risk else 0,
            "is_executive": is_exec,
        })
    return records


def synthesize_batch(
    batch_size: int = 5,
    data_type: str = "general",
    forbidden_terms: list[str] = None,
    custom_replacements: dict = None,
    additional_context: str = None,
    model: str = DEFAULT_MODEL,
    use_ollama: bool = True,
) -> dict:
    """
    Synthesizes a single batch of records for any data_type using Ollama or fallback,
    referencing samples from unified_vault, and saving into synthetic_database.duckdb.
    """
    # Grab reference samples from vault if available
    vault_conn = get_vault_conn()
    try:
        if data_type and data_type != "general":
            sample_rows = vault_conn.execute(
                "SELECT title, primary_text, data_type, attributes FROM unified_vault WHERE data_type = ? LIMIT ?;",
                [data_type, batch_size],
            ).fetchall()
        else:
            sample_rows = vault_conn.execute(
                "SELECT title, primary_text, data_type, attributes FROM unified_vault LIMIT ?;",
                [batch_size],
            ).fetchall()

        reference_items = [{"title": r[0], "primary_text": r[1], "data_type": r[2]} for r in sample_rows]
    finally:
        vault_conn.close()

    # Format user constraints
    constraints_prompt = []
    if forbidden_terms:
        constraints_prompt.append(f"STRICTLY FORBIDDEN WORDS: {', '.join(forbidden_terms)}")
    if custom_replacements:
        rep_str = ", ".join([f"'{k}' -> '{v}'" for k, v in custom_replacements.items()])
        constraints_prompt.append(f"MANDATORY ALIASES: {rep_str}")
    if additional_context:
        constraints_prompt.append(f"USER FOCUS / PROCESS DIRECTIVE: {additional_context}")

    user_rules_text = "\n".join(constraints_prompt) if constraints_prompt else "Ensure professional enterprise tone."
    prompt = _build_synthesis_prompt(data_type, reference_items, batch_size, user_rules_text)

    raw_records = []
    if use_ollama:
        try:
            raw_records = _call_ollama_batch(prompt, model=model)
        except Exception as e:
            print(f"[Ollama Warning] Live call failed ({e}). Using fast generator.")
            use_ollama = False

    if not raw_records:
        raw_records = _generate_fallback_records(reference_items, data_type, batch_size)

    # Clean & enforce constraints
    cleaned_records = []
    for r in raw_records:
        title = _apply_user_constraints(r.get("title") or r.get("subject", ""), forbidden_terms, custom_replacements)
        content = _apply_user_constraints(r.get("content") or r.get("body", ""), forbidden_terms, custom_replacements)
        cleaned_records.append({
            "data_type": r.get("data_type", data_type),
            "title": title,
            "content": content,
            "department": r.get("department", "Corporate Operations"),
            "author_or_sender": r.get("author_or_sender") or r.get("sender", "employee@company.internal"),
            "recipient_or_audience": r.get("recipient_or_audience") or r.get("recipient", "team@company.internal"),
            "timestamp": "2024-03-15 10:00:00",
            "compliance_label": int(r.get("compliance_label", 0)),
            "is_executive": bool(r.get("is_executive", False)),
        })

    saved_count = save_synthetic_batch(cleaned_records)
    stats = get_synthetic_stats()

    return {
        "status": "success",
        "method": "batch_json_llm" if use_ollama else "fast_fallback",
        "data_type": data_type,
        "records_synthesized": saved_count,
        "database_total": stats["total_records"],
        "data_type_breakdown": stats["data_type_breakdown"],
        "compliance_breakdown": stats["compliance_breakdown"],
        "sample": cleaned_records[0] if cleaned_records else {},
    }


def synthesize_from_file(
    source_file: str,
    n_records: int = 50,
    batch_chunk_size: int = 5,
    forbidden_terms: list[str] = None,
    custom_replacements: dict = None,
    additional_context: str = None,
    use_ollama: bool = True,
    model: str = DEFAULT_MODEL,
) -> dict:
    """
    Universal Synthesis from ANY File Format:
    Parses CSV, JSON/JSONL, PDF, TXT, or MD into canonical enterprise documents,
    extracts the ongoing business processes and workflows, and synthesizes clean,
    privacy-protected records into data/synthetic_database.duckdb.
    """
    if not os.path.exists(source_file):
        raise FileNotFoundError(f"Source file not found: {source_file}")

    ext = os.path.splitext(source_file)[1].lower()

    # 1. Parse using universal parsers
    if ext == ".csv":
        docs = parse_csv(source_file, sample_size=n_records)
    elif ext in [".json", ".jsonl"]:
        docs = parse_json(source_file, sample_size=n_records)
    elif ext == ".pdf":
        docs = parse_pdf(source_file)
        if n_records:
            docs = docs[:n_records]
    elif ext in [".txt", ".md"]:
        docs = parse_text(source_file)
    else:
        raise ValueError(f"Unsupported file format: {ext}. Supported: .csv, .json, .pdf, .txt, .md")

    if not docs:
        return {"status": "empty", "records_synthesized": 0}

    detected_type = docs[0].get("data_type", "general")
    print(f"Loaded {len(docs)} documents from {os.path.basename(source_file)} (detected type: {detected_type})")

    # Format user constraints
    constraints_prompt = []
    if forbidden_terms:
        constraints_prompt.append(f"STRICTLY FORBIDDEN WORDS: {', '.join(forbidden_terms)}")
    if custom_replacements:
        rep_str = ", ".join([f"'{k}' -> '{v}'" for k, v in custom_replacements.items()])
        constraints_prompt.append(f"MANDATORY ALIASES: {rep_str}")
    if additional_context:
        constraints_prompt.append(f"USER FOCUS / TOPIC GUIDANCE: {additional_context}")

    user_rules_text = "\n".join(constraints_prompt) if constraints_prompt else "Ensure professional enterprise tone."

    total_generated = 0
    all_synthesized = []
    n_chunks = (len(docs) + batch_chunk_size - 1) // batch_chunk_size

    print(f"Synthesizing {len(docs)} records in {n_chunks} batch chunks of {batch_chunk_size}...")

    for chunk_idx in range(n_chunks):
        chunk_docs = docs[chunk_idx * batch_chunk_size : (chunk_idx + 1) * batch_chunk_size]
        prompt = _build_synthesis_prompt(detected_type, chunk_docs, len(chunk_docs), user_rules_text)

        raw_records = []
        if use_ollama:
            try:
                raw_records = _call_ollama_batch(prompt, model=model, timeout=90)
            except Exception as e:
                print(f"  [Chunk {chunk_idx + 1}] Ollama call note ({e}). Using local generator.")
                use_ollama = False

        if not raw_records:
            raw_records = _generate_fallback_records(chunk_docs, detected_type, len(chunk_docs))

        # Clean, redact, and prepare records
        cleaned_batch = []
        for i, r in enumerate(raw_records):
            fallback_doc = chunk_docs[i] if i < len(chunk_docs) else {}
            raw_title = (
                r.get("title")
                or r.get("subject")
                or r.get("ticket_title")
                or r.get("summary")
                or fallback_doc.get("title")
                or "Enterprise Process"
            )
            raw_content = (
                r.get("content")
                or r.get("body")
                or r.get("description")
                or r.get("text")
                or fallback_doc.get("primary_text")
                or ""
            )

            title = _apply_user_constraints(raw_title, forbidden_terms, custom_replacements)
            content = _apply_user_constraints(raw_content, forbidden_terms, custom_replacements)
            dept = r.get("department") or fallback_doc.get("attributes", {}).get("department", "Corporate Operations")

            cleaned_batch.append({
                "data_type": r.get("data_type", detected_type),
                "title": title,
                "content": content,
                "department": dept,
                "author_or_sender": r.get("author_or_sender") or r.get("sender", "employee@company.internal"),
                "recipient_or_audience": r.get("recipient_or_audience") or r.get("recipient", "team@company.internal"),
                "timestamp": "2024-03-15 10:00:00",
                "compliance_label": int(r.get("compliance_label", 0)),
                "is_executive": bool(r.get("is_executive", False)),
            })

        save_synthetic_batch(cleaned_batch)
        total_generated += len(cleaned_batch)
        all_synthesized.extend(cleaned_batch)
        print(f"  Processed chunk {chunk_idx + 1}/{n_chunks}: {total_generated} records saved.", end="\r")

    print(f"\nCompleted! Total {total_generated} synthetic records saved to database.")
    stats = get_synthetic_stats()

    return {
        "status": "success",
        "file": os.path.basename(source_file),
        "data_type": detected_type,
        "input_records_processed": len(docs),
        "records_synthesized": total_generated,
        "database_total": stats["total_records"],
        "data_type_breakdown": stats["data_type_breakdown"],
        "department_breakdown": stats["department_breakdown"],
        "compliance_breakdown": stats["compliance_breakdown"],
        "sample": all_synthesized[0] if all_synthesized else {},
    }


def synthesize_from_vault(
    data_type: str = None,
    n_records: int = 50,
    batch_chunk_size: int = 5,
    forbidden_terms: list[str] = None,
    custom_replacements: dict = None,
    additional_context: str = None,
    use_ollama: bool = True,
    model: str = DEFAULT_MODEL,
) -> dict:
    """
    Synthesizes across ALL files and data types currently in the unified vault,
    giving the AI agent a unified, privacy-safe 360-degree knowledge base of
    all ongoing enterprise processes.
    """
    vault_conn = get_vault_conn()
    try:
        if data_type:
            rows = vault_conn.execute(
                "SELECT doc_id, source_file, data_type, title, primary_text, attributes FROM unified_vault WHERE data_type = ? LIMIT ?;",
                [data_type, n_records],
            ).fetchall()
        else:
            rows = vault_conn.execute(
                "SELECT doc_id, source_file, data_type, title, primary_text, attributes FROM unified_vault LIMIT ?;",
                [n_records],
            ).fetchall()

        docs = [
            {
                "doc_id": r[0],
                "source_file": r[1],
                "data_type": r[2],
                "title": r[3],
                "primary_text": r[4],
                "attributes": json.loads(r[5]) if isinstance(r[5], str) else r[5],
            }
            for r in rows
        ]
    finally:
        vault_conn.close()

    if not docs:
        return {"status": "empty", "message": "Unified vault is empty. Ingest files first."}

    # Group by data_type and synthesize each group
    grouped = {}
    for d in docs:
        grouped.setdefault(d["data_type"], []).append(d)

    total_saved = 0
    for dt, group_docs in grouped.items():
        # Synthesize in chunks of batch_chunk_size
        n_chunks = (len(group_docs) + batch_chunk_size - 1) // batch_chunk_size
        for c in range(n_chunks):
            sub_chunk = group_docs[c * batch_chunk_size : (c + 1) * batch_chunk_size]
            prompt = _build_synthesis_prompt(dt, sub_chunk, len(sub_chunk), additional_context or "")
            raw = []
            if use_ollama:
                try:
                    raw = _call_ollama_batch(prompt, model=model)
                except Exception:
                    pass
            if not raw:
                raw = _generate_fallback_records(sub_chunk, dt, len(sub_chunk))

            batch_to_save = []
            for r in raw:
                batch_to_save.append({
                    "data_type": dt,
                    "title": _apply_user_constraints(r.get("title") or r.get("subject", ""), forbidden_terms, custom_replacements),
                    "content": _apply_user_constraints(r.get("content") or r.get("body", ""), forbidden_terms, custom_replacements),
                    "department": r.get("department", "Corporate Operations"),
                    "author_or_sender": r.get("author_or_sender") or r.get("sender", "employee@company.internal"),
                    "recipient_or_audience": r.get("recipient_or_audience") or r.get("recipient", "team@company.internal"),
                    "timestamp": "2024-03-15 10:00:00",
                    "compliance_label": int(r.get("compliance_label", 0)),
                    "is_executive": bool(r.get("is_executive", False)),
                })
            save_synthetic_batch(batch_to_save)
            total_saved += len(batch_to_save)

    stats = get_synthetic_stats()
    return {
        "status": "success",
        "records_synthesized": total_saved,
        "database_total": stats["total_records"],
        "data_type_breakdown": stats["data_type_breakdown"],
        "department_breakdown": stats["department_breakdown"],
        "compliance_breakdown": stats["compliance_breakdown"],
    }
