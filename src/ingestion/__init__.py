"""
src/ingestion - Universal Enterprise Data Ingestion Layer
Supports CSV, JSON, PDF, and TXT files, storing all records into a local DuckDB vault.
"""

from .ingestor import ingest_file, ingest_files
from .extractor import extract_synthesis_records
from .vault import get_vault_stats, query_vault, clear_vault, get_connection

__all__ = [
    "ingest_file",
    "ingest_files",
    "extract_synthesis_records",
    "get_vault_stats",
    "query_vault",
    "clear_vault",
    "get_connection",
]
