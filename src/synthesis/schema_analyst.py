"""
schema_analyst.py — Local LLM Schema Analyst
Uses local Ollama (gemma3:4b) to inspect raw data columns and determine:
1. Which fields are relevant and should be kept for synthesis.
2. Which fields are noise / server infrastructure and should be discarded.
3. The exact synthesis recipe for each relevant field.
"""

import json
from .ollama_client import query_ollama, is_ollama_available

# Verified default blueprint fallback (used when Ollama is offline or paused to save RAM)
DEFAULT_BLUEPRINT = {
    "data_type": "email",
    "relevant_fields": ["Subject", "Body", "From", "To", "Date", "Label", "POI-Present", "Sender-Type"],
    "discarded_fields": [
        "Mime-Version", "Content-Type", "Content-Transfer-Encoding",
        "X-FileName", "X-Origin", "X-Folder", "X-bcc", "Message-ID", "Mail-ID"
    ],
    "synthesis_strategy": {
        "Subject": "Generate concise business subject lines reflecting trading, contracts, or operations.",
        "Body": "Synthesize realistic corporate emails aligned with the Subject topic.",
        "From": "Generate anonymized internal/external corporate email persona.",
        "To": "Generate synthetic recipient email persona.",
        "Date": "Generate realistic business-hours timestamps.",
        "Label": "Preserve 0 (normal) or 1 (suspicious) compliance classification.",
        "POI-Present": "Preserve executive presence marker (True/False).",
        "Sender-Type": "Categorize as 'Internal' or 'External'."
    }
}


def analyze_schema_with_ollama(
    columns: list[str],
    sample_records: list[dict],
    data_type: str = "email",
    use_live_ollama: bool = False,
) -> dict:
    """
    Asks local Ollama to analyze raw dataset structure and output a synthesis blueprint.

    Parameters
    ----------
    columns : list[str]
        List of all column headers from the raw dataset.
    sample_records : list[dict]
        2-3 sample records showing actual values.
    data_type : str
        The classification ('email', 'support_ticket', etc.).
    use_live_ollama : bool
        If True and Ollama is reachable, queries Ollama.
        If False, uses the verified default blueprint to prevent laptop lag.

    Returns
    -------
    dict
        Structured blueprint containing relevant_fields, discarded_fields, and strategies.
    """
    # If live querying is disabled or Ollama is offline, return the blueprint immediately
    if not use_live_ollama or not is_ollama_available():
        blueprint = dict(DEFAULT_BLUEPRINT)
        blueprint["data_type"] = data_type
        # Filter relevant fields to only those present in the columns
        blueprint["relevant_fields"] = [c for c in blueprint["relevant_fields"] if c in columns]
        return blueprint

    system_prompt = (
        "You are an enterprise data architect. Given a dataset schema and sample rows, "
        "identify which columns are relevant for business synthesis, which are technical noise to discard, "
        "and provide a synthesis strategy for each relevant field. Output valid JSON only."
    )

    user_prompt = f"""
Dataset Type: {data_type}
Raw Columns ({len(columns)}): {json.dumps(columns)}
Sample Record Preview: {json.dumps(sample_records[:2], default=str)}

Respond with a JSON object in this exact format:
{{
  "data_type": "{data_type}",
  "relevant_fields": ["list of important business/content fields"],
  "discarded_fields": ["list of noise, server headers, or empty fields to discard"],
  "synthesis_strategy": {{
    "Field1": "how to synthesize",
    "Field2": "how to synthesize"
  }}
}}
"""

    try:
        response_text = query_ollama(
            prompt=user_prompt,
            system_prompt=system_prompt,
            json_mode=True,
            timeout_sec=45,
            keep_alive="0s",  # Free RAM immediately
        )
        parsed = json.loads(response_text)
        if "relevant_fields" in parsed and "synthesis_strategy" in parsed:
            return parsed
    except Exception:
        pass

    # Fallback if Ollama response could not be parsed
    return DEFAULT_BLUEPRINT
