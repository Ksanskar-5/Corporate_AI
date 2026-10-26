"""
src/synthesis — Simple Batch JSON LLM Synthesis Engine
"""

from .engine import synthesize_batch, synthesize_from_file
from .db import get_synthetic_records, get_synthetic_stats, get_connection

__all__ = [
    "synthesize_batch",
    "synthesize_from_file",
    "get_synthetic_records",
    "get_synthetic_stats",
    "get_connection",
]
