"""
synthesizer_pipeline.py — Integrated Synthesis Pipeline
Orchestrates:
1. Schema analysis via Ollama (extracts only relevant fields + synthesis recipe).
2. Local data synthesis following the recipe.
3. Storage of ONLY the synthesized records in the structured database.
"""

import random
import os
import uuid
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


from .confidentiality import ConfidentialityGuardrail


def run_pipeline(
    n_samples: int = 10,
    data_type: str = "email",
    method: str = "rag",
    use_ollama: bool = False,
    forbidden_terms: list[str] = None,
    custom_replacements: dict = None,
    additional_context: str = None,
    mask_pii: bool = True,
    db_path: str = DEFAULT_VAULT_PATH,
) -> dict:
    """
    Executes the complete synthesis pipeline:
    1. Extracts real raw records from the input vault.
    2. Applies user-defined confidentiality & disclosure rules (forbidden terms, aliases).
    3. Consults Ollama for the relevant fields and synthesis strategy.
    4. Synthesizes clean records matching the blueprint and privacy guardrails.
    5. Stores ONLY the synthesized records in the structured database.

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
    forbidden_terms : list[str], optional
        User-specified terms/names/codenames that must NEVER be disclosed.
    custom_replacements : dict, optional
        Mapping of sensitive terms to safe aliases (e.g. {'Enron': 'ApexCorp'}).
    additional_context : str, optional
        User guidance on topics to emphasize or synthesize.
    mask_pii : bool
        Whether to automatically mask emails, phones, and IP addresses.
    """
    # Initialize user confidentiality guardrail
    guardrail = ConfidentialityGuardrail(
        forbidden_terms=forbidden_terms,
        custom_replacements=custom_replacements,
        mask_pii=mask_pii,
        additional_context=additional_context,
    )

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

    # Step 3: Run local synthesis following the blueprint and guardrails
    if method == "rag":
        generator = RAGSynthesizer(top_k=3, guardrail=guardrail).fit(raw_records)
    else:
        generator = StatisticalSynthesizer(n_gram_size=2).fit(raw_records)

    raw_synth = generator.generate(n_samples=n_samples, data_type=data_type)

    # Step 4: Map generated items into clean structured enterprise records & sanitize
    structured_records = []
    for i, item in enumerate(raw_synth):
        ctx = item.get("context", {})
        raw_subject = item.get("title", "").replace("[SYNTH] ", "")
        raw_body = item.get("synthetic_text", "")

        # Enforce user confidentiality guardrails on both subject and body
        safe_subject = guardrail.sanitize(raw_subject)
        safe_body = guardrail.sanitize(raw_body)

        batch_uuid = uuid.uuid4().hex[:8]
        structured_records.append({
            "synthetic_id": f"synth_{data_type}_{batch_uuid}_{i + 1:03d}",
            "data_type": data_type,
            "subject": safe_subject,
            "body": safe_body,
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
        "confidentiality_rules": {
            "forbidden_terms_count": len(guardrail.forbidden_terms),
            "custom_replacements_count": len(guardrail.custom_replacements),
            "mask_pii_enabled": guardrail.mask_pii,
            "user_context_provided": bool(guardrail.additional_context),
        },
        "records_synthesized": saved_count,
        "structured_database_total": stats["total_synthetic_records"],
        "compliance_breakdown": stats["compliance_breakdown"],
        "sample_record": structured_records[0] if structured_records else {},
    }
