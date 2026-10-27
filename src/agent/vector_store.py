"""
vector_store.py - Chroma DB Vector Store for Enterprise Data (Synthetic + Vault)
Persists vector embeddings of synthesized and ingested vault records (PDFs, MD notes, CSVs, TXT)
to data/chroma_db and provides semantic retrieval with RBAC, source scope, and format filtering.
"""

import os
import json
import duckdb
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
import chromadb.utils.embedding_functions as ef

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
SYNTH_DB_PATH = os.path.join(ROOT_DIR, "data", "synthetic_database.duckdb")
VAULT_DB_PATH = os.path.join(ROOT_DIR, "data", "vault.duckdb")
CHROMA_DIR = os.path.join(ROOT_DIR, "data", "chroma_db")
COLLECTION_NAME = "enterprise_knowledge_vault"


# Metadata keys that carry no retrievable meaning (server noise, raw ids).
_ATTR_EXCLUDE = {
    "mime-version", "content-type", "content-transfer-encoding",
    "x-filename", "x-origin", "x-folder", "x-bcc",
    "message-id", "mail-id", "source",
}


def _render_attribute_details(attrs) -> str:
    """Renders salient record attributes as searchable text.

    Facts like ticket resolutions or email subjects otherwise stay hidden
    in metadata the index never embeds.
    """
    if isinstance(attrs, str):
        try:
            attrs = json.loads(attrs)
        except Exception:
            return ""
    if not isinstance(attrs, dict):
        return ""
    lines = []
    for key, val in attrs.items():
        key_lower = str(key).lower().strip()
        if key_lower in _ATTR_EXCLUDE or val is None:
            continue
        val_text = str(val).strip()
        if not val_text or val_text.lower() in ("", "nan", "none"):
            continue
        lines.append(f"{key}: {val_text[:300]}")
    return "\n".join(lines)[:1500]


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
    Loads both synthetic enterprise records and non-synthetic vault documents
    (PDFs, Markdown notes, plain text memos, support tickets, and sample emails),
    computes vector embeddings, and stores them in Chroma DB.
    """
    if force_reindex and os.path.exists(CHROMA_DIR):
        import shutil
        shutil.rmtree(CHROMA_DIR)

    os.makedirs(CHROMA_DIR, exist_ok=True)
    embeddings = get_embedding_function()

    # If Chroma collection already exists and reindex not forced, load it directly
    if not force_reindex and os.path.exists(os.path.join(CHROMA_DIR, "chroma.sqlite3")):
        try:
            vs = Chroma(
                persist_directory=CHROMA_DIR,
                embedding_function=embeddings,
                collection_name=COLLECTION_NAME,
            )
            if vs._collection.count() > 50:
                return vs
        except Exception:
            pass

    documents = []

    # 1. Load Synthetic Records
    if os.path.exists(SYNTH_DB_PATH):
        try:
            s_conn = duckdb.connect(SYNTH_DB_PATH, read_only=True)
            s_rows = s_conn.execute("""
                SELECT id, source_doc_id, data_type, title, content, department, author,
                       recipient, compliance_label, is_executive,
                       COALESCE(allowed_roles, 'All') as allowed_roles,
                       COALESCE(clearance_level, 'Internal') as clearance_level
                FROM synthetic_records;
            """).fetchdf()
            s_conn.close()

            for _, r in s_rows.iterrows():
                title_text = str(r.get("title") or "Synthetic Process")
                dept_text = str(r.get("department") or "Corporate Operations")
                author_text = str(r.get("author") or "system@corporate.internal")
                dtype = str(r["data_type"])
                
                # Derive file_type for synthetic data
                if dtype == "document_pdf":
                    ftype = "pdf"
                elif dtype in ["meeting_note", "notes"]:
                    ftype = "md"
                elif dtype == "support_ticket":
                    ftype = "json"
                elif dtype == "email":
                    ftype = "csv"
                else:
                    ftype = "txt"

                content = (
                    f"[{title_text}] (Format: {ftype.upper()} | Source: Synthetic | Dept: {dept_text})\n"
                    f"From: {author_text}\n"
                    f"Content:\n{r['content']}"
                )
                metadata = {
                    "id": str(r["id"]),
                    "title": title_text,
                    "department": dept_text,
                    "file_type": ftype,
                    "data_type": dtype,
                    "source": "synthetic",
                    "is_synthetic": "true",
                    "compliance_label": int(r["compliance_label"]),
                    "is_executive": bool(r["is_executive"]),
                    "allowed_roles": str(r.get("allowed_roles") or "All"),
                    "clearance_level": str(r.get("clearance_level") or "Internal"),
                }
                documents.append(Document(page_content=content, metadata=metadata))
        except Exception as e:
            print(f"[Vector Store] Error indexing synthetic records: {e}")

    # 2. Load Non-Synthetic Vault Records (PDFs, MD files, Text memos, JSON tickets, and email sample)
    if os.path.exists(VAULT_DB_PATH):
        try:
            v_conn = duckdb.connect(VAULT_DB_PATH, read_only=True)
            # Fetch all non-csv files (PDF, MD, TXT, JSON)
            v_special = v_conn.execute("""
                SELECT doc_id, source_file, file_type, data_type, title, body_text,
                       department, allowed_roles, clearance_level, attributes
                FROM documents
                WHERE file_type IN ('pdf', 'md', 'txt', 'json');
            """).fetchdf()

            # Plus sample of 150 emails / CSV files
            v_csv = v_conn.execute("""
                SELECT doc_id, source_file, file_type, data_type, title, body_text,
                       department, allowed_roles, clearance_level, attributes
                FROM documents
                WHERE file_type = 'csv'
                ORDER BY ingested_at DESC
                LIMIT 150;
            """).fetchdf()
            v_conn.close()

            import pandas as pd
            v_all = pd.concat([v_special, v_csv], ignore_index=True)

            for _, r in v_all.iterrows():
                title_text = str(r.get("title") or "Vault Document")
                dept_text = str(r.get("department") or "Corporate Operations")
                ftype = str(r.get("file_type") or "txt").lower()
                dtype = str(r.get("data_type") or "general")
                body = str(r.get("body_text") or "")
                
                # Extract compliance flag if present in attributes
                attrs = r.get("attributes")
                attrs_d = {}
                if isinstance(attrs, str):
                    try:
                        attrs_d = json.loads(attrs)
                    except Exception:
                        pass
                elif isinstance(attrs, dict):
                    attrs_d = attrs
                try:
                    comp_lbl = int(attrs_d.get("compliance_label", 0))
                except (ValueError, TypeError):
                    comp_lbl = 0

                details = _render_attribute_details(attrs_d)
                content = (
                    f"[{title_text}] (Format: {ftype.upper()} | Source: Original Vault | Dept: {dept_text})\n"
                    f"Content:\n{body[:2500]}"
                    + (f"\nDetails:\n{details}" if details else "")
                )
                metadata = {
                    "id": str(r["doc_id"]),
                    "title": title_text,
                    "department": dept_text,
                    "file_type": ftype,
                    "data_type": dtype,
                    "source": "vault",
                    "is_synthetic": "false",
                    "compliance_label": comp_lbl,
                    "is_executive": False,
                    "allowed_roles": str(r.get("allowed_roles") or "All"),
                    "clearance_level": str(r.get("clearance_level") or "Internal"),
                }
                documents.append(Document(page_content=content, metadata=metadata))
        except Exception as e:
            print(f"[Vector Store] Error indexing vault records: {e}")

    if not documents:
        raise ValueError("No records found to index in vector store.")

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


def effective_source_scope(user_role: str, requested: str = "all") -> str:
    """Resolves the data source a role may see.

    Only Admin may see vault (non-synthetic) data; every other role is
    restricted to synthetic data regardless of what was requested.
    """
    if user_role == "Admin" and requested in ("all", "synthetic", "vault"):
        return requested
    if user_role == "Admin":
        return "all"
    return "synthetic"


def get_retriever(
    k: int = 4,
    user_role: str = "Employee",
    user_department: str = None,
    source_scope: str = "all",
    file_type_filter: str = "all",
    department_filter: str = None,
):
    """
    Returns a LangChain vector retriever with Role-Based Access Control (RBAC),
    Source Scope filtering (all / synthetic / vault), and Document Format filtering.

    RBAC Policy (canonical roles: Employee, Manager, Analyst, Admin):
    - Admin: Full visibility across all departments and clearance levels.
    - Analyst: Cross-department read access (up to Confidential & Audit flagged).
    - Manager: Departmental records + Corporate Operations (up to Confidential).
    - Employee: Public and Internal clearance records with allowed_roles='All'.
    Unknown roles fail closed to Employee.
    Only Admin may see vault data; all other roles see synthetic data only.
    """
    vectorstore = get_vector_store()
    conditions = []

    # Normalize to canonical roles; fail closed to least privilege.
    if user_role not in ("Employee", "Manager", "Analyst", "Admin"):
        user_role = "Employee"

    # 1. RBAC Clearance & Department Filters
    if user_role == "Employee":
        conditions.append({"clearance_level": {"$in": ["Public", "Internal"]}})
        conditions.append({"allowed_roles": {"$eq": "All"}})
    elif user_role == "Manager":
        dept = user_department or department_filter
        conditions.append({"clearance_level": {"$in": ["Public", "Internal", "Confidential"]}})
        if dept and dept != "All":
            conditions.append({"department": {"$in": [dept, "Corporate Operations", "Operations"]}})
    elif user_role == "Analyst":
        conditions.append({"clearance_level": {"$in": ["Public", "Internal", "Confidential", "Restricted"]}})
        if department_filter and department_filter != "All":
            conditions.append({"department": {"$eq": department_filter}})
    elif user_role == "Admin":
        if department_filter and department_filter != "All":
            conditions.append({"department": {"$eq": department_filter}})

    # 2. Source Scope Filter (Synthetic vs Vault vs All).
    # Non-Admin roles are forced to synthetic regardless of the request.
    effective_scope = effective_source_scope(user_role, source_scope)
    if effective_scope == "synthetic":
        conditions.append({"source": {"$eq": "synthetic"}})
    elif effective_scope == "vault":
        conditions.append({"source": {"$eq": "vault"}})

    # 3. Document Format Filter (PDF, MD, CSV, TXT, JSON)
    if file_type_filter and file_type_filter != "all":
        conditions.append({"file_type": {"$eq": file_type_filter.lower()}})

    search_kwargs = {"k": k}
    if len(conditions) == 1:
        search_kwargs["filter"] = conditions[0]
    elif len(conditions) > 1:
        search_kwargs["filter"] = {"$and": conditions}

    return vectorstore.as_retriever(search_kwargs=search_kwargs)
