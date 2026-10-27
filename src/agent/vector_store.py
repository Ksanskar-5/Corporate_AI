"""
vector_store.py — Chroma DB Vector Store for Synthetic Enterprise Data
Persists vector embeddings of synthesized enterprise records to data/chroma_db
and provides semantic retrieval for the LangChain Corporate AI Chatbot.
"""

import os
import duckdb
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
import chromadb.utils.embedding_functions as ef

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DUCKDB_PATH = os.path.join(ROOT_DIR, "data", "synthetic_database.duckdb")
CHROMA_DIR = os.path.join(ROOT_DIR, "data", "chroma_db")
COLLECTION_NAME = "synthetic_enterprise_records"


class LocalONNXEmbeddings(Embeddings):
    """
    Lightweight, fast, 100% offline ONNX embeddings (all-MiniLM-L6-v2, 384 dimensions).
    Requires zero API keys and generates embeddings locally in milliseconds.
    """

    def __init__(self):
        self._fn = ef.DefaultEmbeddingFunction()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, vec)) for vec in self._fn(texts)]

    def embed_query(self, text: str) -> list[float]:
        return [list(map(float, vec)) for vec in self._fn([text])][0]


def get_embedding_function() -> Embeddings:
    """Returns the embedding model for Chroma DB."""
    return LocalONNXEmbeddings()


def build_vector_store(force_reindex: bool = False) -> Chroma:
    """
    Loads synthetic enterprise records from DuckDB, computes vector embeddings,
    and stores them persistently in Chroma DB.
    """
    if not os.path.exists(DUCKDB_PATH):
        raise FileNotFoundError(f"Synthetic database not found at {DUCKDB_PATH}. Run synthesis first.")

    if force_reindex and os.path.exists(CHROMA_DIR):
        import shutil
        shutil.rmtree(CHROMA_DIR)

    os.makedirs(CHROMA_DIR, exist_ok=True)
    embeddings = get_embedding_function()

    # If Chroma already exists and reindex not forced, load it directly
    if not force_reindex and os.path.exists(os.path.join(CHROMA_DIR, "chroma.sqlite3")):
        return Chroma(
            persist_directory=CHROMA_DIR,
            embedding_function=embeddings,
            collection_name=COLLECTION_NAME,
        )

    # Read records from DuckDB
    conn = duckdb.connect(DUCKDB_PATH, read_only=True)
    try:
        rows = conn.execute("""
            SELECT id, source_doc_id, data_type, title, content, department, author,
                   recipient, compliance_label, is_executive,
                   COALESCE(allowed_roles, 'All') as allowed_roles,
                   COALESCE(clearance_level, 'Internal') as clearance_level
            FROM synthetic_records;
        """).fetchdf()
    finally:
        conn.close()

    documents = []
    for _, r in rows.iterrows():
        title_text = str(r.get("title") or "Enterprise Process")
        dept_text = str(r.get("department") or "Corporate Operations")
        author_text = str(r.get("author") or "employee@company.internal")
        recipient_text = str(r.get("recipient") or "team@company.internal")
        content = (
            f"Title: {title_text}\n"
            f"Department: {dept_text}\n"
            f"Type: {r['data_type']}\n"
            f"From: {author_text} -> {recipient_text}\n"
            f"Content: {r['content']}"
        )
        metadata = {
            "id": str(r["id"]),
            "source_doc_id": str(r.get("source_doc_id") or ""),
            "data_type": str(r["data_type"]),
            "department": dept_text,
            "compliance_label": int(r["compliance_label"]),
            "is_executive": bool(r["is_executive"]),
            "allowed_roles": str(r.get("allowed_roles") or "All"),
            "clearance_level": str(r.get("clearance_level") or "Internal"),
            "title": title_text,
        }
        documents.append(Document(page_content=content, metadata=metadata))

    # Initialize Chroma and persist
    vectorstore = Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        persist_directory=CHROMA_DIR,
        collection_name=COLLECTION_NAME,
    )
    return vectorstore


def get_vector_store() -> Chroma:
    """Returns the persistent Chroma vector store instance."""
    return build_vector_store(force_reindex=False)


def get_retriever(
    k: int = 4,
    user_role: str = "Admin",
    user_department: str = None,
    department_filter: str = None,
):
    """
    Returns a LangChain vector retriever with Role-Based Access Control (RBAC).
    Enforces pre-retrieval filtering at the Chroma DB vector layer:
    - Admin    : Full visibility across all departments and clearance levels.
    - Analyst  : Full cross-department access (read-only, all clearance levels).
    - Manager  : Own department only, up to Confidential clearance.
    - Employee : Public/Internal only, records marked allowed_roles='All'.
    """
    vectorstore = get_vector_store()
    filter_dict = {}

    if user_role == "Employee":
        filter_dict = {
            "$and": [
                {"clearance_level": {"$in": ["Public", "Internal"]}},
                {"allowed_roles": {"$eq": "All"}},
            ]
        }
    elif user_role == "Manager":
        dept = user_department or department_filter
        if dept:
            filter_dict = {
                "$and": [
                    {"clearance_level": {"$in": ["Public", "Internal", "Confidential"]}},
                    {"department": {"$eq": dept}},
                ]
            }
        else:
            filter_dict = {
                "clearance_level": {"$in": ["Public", "Internal", "Confidential"]}
            }
    elif department_filter:
        # Admin and Analyst — optional department narrowing if explicitly requested
        filter_dict = {"department": {"$eq": department_filter}}

    search_kwargs = {"k": k}
    if filter_dict:
        search_kwargs["filter"] = filter_dict

    return vectorstore.as_retriever(search_kwargs=search_kwargs)
