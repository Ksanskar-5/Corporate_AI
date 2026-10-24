"""
synthesizer_pipeline.py — Integrated Synthesis Pipeline
Orchestrates:
1. Schema analysis via Ollama (extracts only relevant fields + synthesis recipe).
2. Local data synthesis following the recipe.
3. Storage of ONLY the synthesized records in the structured database.
"""

import random
import os
from .schema_analyst import analyze_schema_with_ollama
from .rag_synthesizer import RAGSynthesizer
from .statistical_generator import StatisticalSynthesizer
from .structured_db import insert_synthesized_records, get_structured_stats, query_synthesized_records
from ..ingestion.extractor import extract_synthesis_records
from ..ingestion.vault import DEFAULT_VAULT_PATH

# Synthetic email identity pools to prevent leaking real names
SYNTHETIC_FIRST_NAMES = ["Alex", "Morgan", "Jordan", "Taylor", "Casey", "Sam", "Chris", "Pat"]
SYNTHETIC_LAST_NAMES = ["Turner", "Hayes", "Mitchell", "Reynolds", "Carter", "Brooks", "Reed"]
SYNTHETIC_DOMAINS = ["company.internal", "corp-operations.net", "enterprise-partner.org"]


def _generate_synthetic_persona() -> str:
    """Generates a safe synthetic corporate email persona."""
    first = random.choice(SYNTHETIC_FIRST_NAMES).lower()
    last = random.choice(SYNTHETIC_LAST_NAMES).lower()
    domain = random.choice(SYNTHETIC_DOMAINS)
    return f"{first}.{last}@{domain}"


def run_pipeline(
    n_samples: int = 10,
    data_type: str = "email",
    method: str = "rag",
    use_ollama: bool = False,
    db_path: str = DEFAULT_VAULT_PATH,
) -> dict:
    """
    Executes the complete synthesis pipeline:
    1. Extracts real raw records from the input vault.
    2. Consults Ollama for the relevant fields and synthesis strategy.
    3. Synthesizes clean records matching the blueprint.
    4. Stores ONLY the synthesized records in the structured database.

    Parameters
    ----------
    n_samples : int
        Number of synthetic records to generate.
    data_type : str
        Target enterprise data type ('email', 'support_ticket', etc.).
    method : str
        'rag' or 'statistical'.
    use_ollama : bool
        If True, queries live Ollama gemma3:4b for dynamic schema analysis.
        If False, uses the verified schema blueprint (zero laptop lag).
    """
    # Step 1: Extract real records for reference
    raw_records = extract_synthesis_records(data_type=data_type, limit=100, db_path=db_path)
    if not raw_records:
        raise ValueError(f"No records found in vault for data_type='{data_type}'. Ingest data first.")

    # Step 2: Consult Ollama for relevant fields and synthesis blueprint
    sample_columns = list(raw_records[0].get("context", {}).keys()) + ["Subject", "Body"]
    blueprint = analyze_schema_with_ollama(
        columns=sample_columns,
        sample_records=[r["context"] for r in raw_records[:2]],
        data_type=data_type,
        use_live_ollama=use_ollama,
    )

    # Step 3: Run local synthesis following the blueprint
    if method == "rag":
        generator = RAGSynthesizer(top_k=3).fit(raw_records)
    else:
        generator = StatisticalSynthesizer(n_gram_size=2).fit(raw_records)

    raw_synth = generator.generate(n_samples=n_samples, data_type=data_type)

    # Step 4: Map generated items into clean structured enterprise records
    structured_records = []
    for i, item in enumerate(raw_synth):
        ctx = item.get("context", {})
        structured_records.append({
            "synthetic_id": f"synth_{data_type}_{i + 1:04d}",
            "data_type": data_type,
            "subject": item.get("title", "").replace("[SYNTH] ", ""),
            "body": item.get("synthetic_text", ""),
            "sender": _generate_synthetic_persona(),
            "recipient": _generate_synthetic_persona(),
            "date_timestamp": ctx.get("Date", "2024-03-15 09:30:00"),
            "compliance_label": int(ctx.get("Label", random.choice([0, 0, 0, 1]))),
            "is_executive": bool(ctx.get("POI-Present", False)),
            "context": ctx,
        })

    # Step 5: Save ONLY the synthesized data into the clean structured database
    saved_count = insert_synthesized_records(structured_records)
    stats = get_structured_stats()

    return {
        "status": "success",
        "blueprint_used": {
            "relevant_fields": blueprint.get("relevant_fields"),
            "discarded_fields": blueprint.get("discarded_fields"),
        },
        "records_synthesized": saved_count,
        "structured_database_total": stats["total_synthetic_records"],
        "compliance_breakdown": stats["compliance_breakdown"],
        "sample_record": structured_records[0] if structured_records else {},
    }
