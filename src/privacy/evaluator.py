"""
evaluator.py - Privacy & Semantic Utility Scorecard Engine
Quantifies three key enterprise metrics:
1. PII Leakage Rate: Verifies 0% leakage of real emails, names, phone numbers, or account IDs.
2. Semantic Utility Preservation: Measures cosine similarity between vault records and synthetic twins.
3. RBAC Isolation Rate: Validates 100% pre-retrieval shielding of restricted records from unauthorized roles.
"""

import re
import duckdb
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from ..synthesis.db import STRUCTURED_DB_PATH
from ..ingestion.vault import DEFAULT_VAULT_PATH
from ..agent.vector_store import get_retriever

# Known real-world sensitive patterns from Enron/raw sources to scan for leakage
KNOWN_POI_NAMES = [
    r"\blay\b", r"\bskilling\b", r"\bfastow\b",
    r"\bkopper\b", r"\bglisan\b", r"\bcausey\b",
    r"\bhannon\b", r"\bdelainey\b", r"\bkean\b", r"\bkaminski\b"
]

LEAKAGE_REGEXES = {
    "raw_enron_emails": re.compile(r"[a-zA-Z0-9._%+-]+@enron\.com", re.IGNORECASE),
    "ssn_patterns": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "phone_patterns": re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "known_poi_names": re.compile("|".join(KNOWN_POI_NAMES), re.IGNORECASE),
}


def evaluate_pii_leakage(synth_db_path: str = STRUCTURED_DB_PATH) -> dict:
    """
    Scans every synthesized record in synthetic_database.duckdb for PII or raw identity leakage.
    Returns leakage counts, scanned volume, and safety percentage.
    """
    conn = duckdb.connect(synth_db_path, read_only=True)
    try:
        rows = conn.execute("SELECT id, title, content, author, recipient FROM synthetic_records;").fetchall()
    finally:
        conn.close()

    total_records = len(rows)
    if total_records == 0:
        return {
            "status": "empty",
            "total_records_scanned": 0,
            "leakage_count": 0,
            "leakage_rate_pct": 0.0,
            "safety_score_pct": 100.0,
            "breakdown": {},
        }

    leakage_incidents = []
    breakdown = {k: 0 for k in LEAKAGE_REGEXES}

    for r in rows:
        rec_id, title, content, author, recipient = r
        combined_text = f"{title} {content} {author} {recipient}"

        rec_leaked = False
        for leak_type, pattern in LEAKAGE_REGEXES.items():
            matches = pattern.findall(combined_text)
            if matches:
                breakdown[leak_type] += len(matches)
                rec_leaked = True

        if rec_leaked:
            leakage_incidents.append(rec_id)

    leak_count = len(leakage_incidents)
    leak_rate = (leak_count / total_records) * 100.0
    safety_score = 100.0 - leak_rate

    return {
        "status": "success",
        "total_records_scanned": total_records,
        "clean_records_count": total_records - leak_count,
        "leakage_count": leak_count,
        "leakage_rate_pct": round(leak_rate, 2),
        "safety_score_pct": round(safety_score, 2),
        "breakdown": breakdown,
    }


def evaluate_semantic_utility(
    vault_db_path: str = DEFAULT_VAULT_PATH,
    synth_db_path: str = STRUCTURED_DB_PATH,
    sample_size: int = 50,
) -> dict:
    """
    Measures semantic process retention between raw vault records and their synthetic counterparts.
    Calculates TF-IDF vector cosine similarity across operational terminology.
    """
    v_conn = duckdb.connect(vault_db_path, read_only=True)
    s_conn = duckdb.connect(synth_db_path, read_only=True)
    try:
        vault_texts = [r[0] for r in v_conn.execute("SELECT body_text FROM documents WHERE length(body_text) > 40 LIMIT ?;", [sample_size]).fetchall()]
        synth_texts = [r[0] for r in s_conn.execute("SELECT content FROM synthetic_records WHERE length(content) > 40 LIMIT ?;", [sample_size]).fetchall()]
    finally:
        v_conn.close()
        s_conn.close()

    if not vault_texts or not synth_texts:
        return {"status": "insufficient_data", "mean_cosine_similarity": 0.0}

    # Vectorize and calculate average similarity across shared business concepts
    vectorizer = TfidfVectorizer(max_features=1000, stop_words="english")
    tfidf_matrix = vectorizer.fit_transform(vault_texts + synth_texts)

    vault_matrix = tfidf_matrix[:len(vault_texts)]
    synth_matrix = tfidf_matrix[len(vault_texts):]

    sim_matrix = cosine_similarity(synth_matrix, vault_matrix)
    # Average highest similarity per synthetic document
    best_matches = sim_matrix.max(axis=1)
    mean_sim = float(best_matches.mean())

    return {
        "status": "success",
        "samples_compared": min(len(vault_texts), len(synth_texts)),
        "mean_process_similarity": round(mean_sim, 3),
        "utility_grade": "HIGH" if mean_sim >= 0.40 else "MODERATE" if mean_sim >= 0.25 else "LOW",
    }


def evaluate_rbac_isolation() -> dict:
    """
    Simulates cross-role vector retrievals to verify that 100% of restricted records
    are strictly invisible to Employee queries.
    """
    test_queries = [
        "executive compensation and board restructuring",
        "confidential trading strategy and risk investigation",
        "compliance audit and fraud review",
    ]

    retriever_emp = get_retriever(k=10, user_role="Employee")
    leaked_to_employee = 0
    total_retrieved = 0

    for q in test_queries:
        docs = retriever_emp.invoke(q)
        total_retrieved += len(docs)
        for d in docs:
            clearance = d.metadata.get("clearance_level", "Internal")
            roles = d.metadata.get("allowed_roles", "All")
            # If a restricted or confidential document leaked to an employee:
            if clearance in ["Restricted", "Confidential"] or "All" not in roles:
                leaked_to_employee += 1

    isolation_rate = 100.0 if total_retrieved == 0 else ((total_retrieved - leaked_to_employee) / total_retrieved) * 100.0

    return {
        "status": "success",
        "test_queries_run": len(test_queries),
        "total_documents_retrieved": total_retrieved,
        "unauthorized_leaks_detected": leaked_to_employee,
        "rbac_isolation_rate_pct": round(isolation_rate, 2),
    }


def run_full_privacy_scorecard() -> dict:
    """Generates the comprehensive Enterprise Privacy & Utility Scorecard."""
    pii_results = evaluate_pii_leakage()
    utility_results = evaluate_semantic_utility()
    rbac_results = evaluate_rbac_isolation()

    return {
        "privacy_safety_score": f"{pii_results['safety_score_pct']}%",
        "pii_leakage_rate": f"{pii_results['leakage_rate_pct']}%",
        "rbac_isolation_rate": f"{rbac_results['rbac_isolation_rate_pct']}%",
        "process_retention_similarity": utility_results.get("mean_process_similarity", 0.0),
        "utility_grade": utility_results.get("utility_grade", "MODERATE"),
        "pii_audit_breakdown": pii_results.get("breakdown", {}),
    }
