"""
src/synthesis — Local Synthetic Data Generation Engine
"""

from .synthesizer_pipeline import run_pipeline
from .structured_db import (
    insert_synthesized_records,
    query_synthesized_records,
    get_structured_stats,
    STRUCTURED_DB_PATH,
)
from .schema_analyst import analyze_schema_with_ollama
from .ollama_client import query_ollama, is_ollama_available

__all__ = [
    "run_pipeline",
    "insert_synthesized_records",
    "query_synthesized_records",
    "get_structured_stats",
    "analyze_schema_with_ollama",
    "query_ollama",
    "is_ollama_available",
    "STRUCTURED_DB_PATH",
]
