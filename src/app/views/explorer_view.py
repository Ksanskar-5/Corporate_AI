"""
explorer_view.py - Enterprise Knowledge & Data Explorer Screen (CustomTkinter)
Browse, filter, and inspect authorized enterprise records across both synthetic
and non-synthetic vault data, with multi-format filtering (PDF, MD, CSV, TXT, JSON) and RBAC.
"""

import os
import json
import duckdb
import customtkinter as ctk
from ...synthesis.db import STRUCTURED_DB_PATH
from ...ingestion.vault import DEFAULT_VAULT_PATH
from ..session import session


class RecordDetailModal(ctk.CTkToplevel):
    """Detailed popup modal inspecting a single enterprise record with format-aware layout."""

    def __init__(self, master, record: dict):
        super().__init__(master)
        ftype = (record.get("file_type") or "txt").upper()
        src = (record.get("source") or "synthetic").title()
        self.title(f"Document Inspection [{ftype} | {src}] - {record.get('id')}")
        self.geometry("740x600")
        self.configure(fg_color="#0F172A")
        self.grab_set()

        header = ctk.CTkFrame(self, fg_color="#1E293B", corner_radius=0)
        header.pack(fill="x", padx=0, pady=0)

        # Title
        ctk.CTkLabel(
            header,
            text=f"📄 {record.get('title')}",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#F8FAFC",
            wraplength=700,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(15, 6))

        # Metadata Row
        meta_row = ctk.CTkFrame(header, fg_color="transparent")
        meta_row.pack(fill="x", padx=20, pady=(0, 15))

        fmt_colors = {
            "PDF": "#DC2626",
            "MD": "#4F46E5",
            "CSV": "#059669",
            "TXT": "#7C3AED",
            "JSON": "#D97706",
        }
        fmt_color = fmt_colors.get(ftype, "#475569")

        badges = [
            (f"Format: {ftype}", fmt_color),
            (f"Source: {src}", "#3B82F6" if src == "Vault" else "#8B5CF6"),
            (f"ID: {record.get('id')}", "#334155"),
            (f"Dept: {record.get('department')}", "#1E3A8A"),
            (f"Clearance: {record.get('clearance_level')}", "#065F46" if record.get('clearance_level') == 'Internal' else "#991B1B"),
        ]
        if record.get("compliance_label") == 1:
            badges.append(("⚠️ AUDIT RISK FLAG", "#7F1D1D"))

        for text, color in badges:
            lbl = ctk.CTkLabel(
                meta_row,
                text=text,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color=color,
                corner_radius=6,
                padx=8,
                pady=3,
                text_color="#F8FAFC",
            )
            lbl.pack(side="left", padx=(0, 6))

        # Content Box
        body_scroll = ctk.CTkScrollableFrame(self, fg_color="#1E293B", corner_radius=10)
        body_scroll.pack(fill="both", expand=True, padx=20, pady=15)

        author_str = record.get('author') or record.get('source_file') or 'system'
        recipient_str = record.get('recipient') or 'all'
        info_grid = f"Source/Author: {author_str}    ->    Audience: {recipient_str}\nTimestamp: {record.get('created_at') or record.get('timestamp')}"
        ctk.CTkLabel(
            body_scroll,
            text=info_grid,
            font=ctk.CTkFont(size=11, slant="italic"),
            text_color="#94A3B8",
            justify="left",
        ).pack(anchor="w", padx=10, pady=(10, 10))

        content_text = record.get("content", "")

        # Format-specific container banner
        if ftype == "PDF":
            pdf_banner = ctk.CTkFrame(body_scroll, fg_color="#0F172A", corner_radius=6)
            pdf_banner.pack(fill="x", padx=10, pady=(0, 10))
            ctk.CTkLabel(
                pdf_banner,
                text="📄 PDF DOCUMENT PAGE READER",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color="#F87171",
            ).pack(anchor="w", padx=10, pady=6)
        elif ftype == "CSV":
            csv_banner = ctk.CTkFrame(body_scroll, fg_color="#0F172A", corner_radius=6)
            csv_banner.pack(fill="x", padx=10, pady=(0, 10))
            ctk.CTkLabel(
                csv_banner,
                text="📊 SPREADSHEET / TABULAR DATASET",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color="#34D399",
            ).pack(anchor="w", padx=10, pady=6)

        ctk.CTkLabel(
            body_scroll,
            text=content_text,
            font=ctk.CTkFont(size=12, family="Courier" if ftype in ["CSV", "TXT", "JSON"] else "sans-serif"),
            text_color="#F1F5F9",
            wraplength=660,
            justify="left",
        ).pack(anchor="w", padx=10, pady=(0, 15))

        close_btn = ctk.CTkButton(
            self,
            text="Close Document",
            width=130,
            height=34,
            fg_color="#334155",
            hover_color="#475569",
            command=self.destroy,
        )
        close_btn.pack(pady=(0, 15))


class ExplorerView(ctk.CTkFrame):
    """Enterprise Data Management Explorer supporting synthetic and non-synthetic vault records."""

    def __init__(self, master):
        super().__init__(master, corner_radius=0, fg_color="#0F172A")

        # Top Control Bar
        self.control_bar = ctk.CTkFrame(self, fg_color="#1E293B", corner_radius=0)
        self.control_bar.pack(fill="x", side="top", padx=0, pady=0)

        # Row 1: Title and RBAC Badge
        top_row = ctk.CTkFrame(self.control_bar, fg_color="transparent")
        top_row.pack(fill="x", padx=20, pady=(12, 6))

        ctk.CTkLabel(
            top_row,
            text="📁 Enterprise Data Management & Knowledge Vault",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#F8FAFC",
        ).pack(side="left")

        self.stats_badge = ctk.CTkLabel(
            top_row,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="#38BDF8",
        )
        self.stats_badge.pack(side="right")

        # Row 2: Search and Primary Filters
        filter_row = ctk.CTkFrame(self.control_bar, fg_color="transparent")
        filter_row.pack(fill="x", padx=20, pady=(0, 6))

        self.search_entry = ctk.CTkEntry(
            filter_row,
            placeholder_text="Search documents by keyword, title, ID, author...",
            width=280,
            height=34,
            fg_color="#0F172A",
            border_color="#475569",
        )
        self.search_entry.pack(side="left", padx=(0, 10))
        self.search_entry.bind("<KeyRelease>", lambda e: self._refresh_records())

        # Scope Selector (All Data / Synthetic / Non-Synthetic Vault)
        self.scope_filter = ctk.CTkComboBox(
            filter_row,
            values=["All Enterprise Data", "Synthetic Only", "Non-Synthetic Vault Only"],
            width=180,
            height=34,
            fg_color="#0F172A",
            border_color="#475569",
            command=lambda v: self._refresh_records(),
        )
        self.scope_filter.set("All Enterprise Data")
        self.scope_filter.pack(side="left", padx=(0, 10))

        # Format Selector (PDF / MD / CSV / TXT / JSON)
        self.fmt_filter = ctk.CTkComboBox(
            filter_row,
            values=["All Formats", "PDFs (.pdf)", "Markdown (.md)", "Spreadsheets (.csv)", "Plain Text (.txt)", "JSON (.json)"],
            width=160,
            height=34,
            fg_color="#0F172A",
            border_color="#475569",
            command=lambda v: self._refresh_records(),
        )
        self.fmt_filter.set("All Formats")
        self.fmt_filter.pack(side="left", padx=(0, 10))

        self.dept_filter = ctk.CTkComboBox(
            filter_row,
            values=["All Departments", "Legal & Regulatory Compliance", "Trading & Risk Management", "Corporate Operations", "Engineering & IT Systems", "Finance & Accounting Audit", "Executive Leadership"],
            width=170,
            height=34,
            fg_color="#0F172A",
            border_color="#475569",
            command=lambda v: self._refresh_records(),
        )
        self.dept_filter.set("All Departments")
        self.dept_filter.pack(side="left", padx=(0, 10))

        self.risk_filter = ctk.CTkComboBox(
            filter_row,
            values=["All Risk Levels", "Standard Only", "Audit Risk Only (⚠️)"],
            width=150,
            height=34,
            fg_color="#0F172A",
            border_color="#475569",
            command=lambda v: self._refresh_records(),
        )
        self.risk_filter.set("All Risk Levels")
        self.risk_filter.pack(side="left")

        # Record List Scroll Area
        self.records_scroll = ctk.CTkScrollableFrame(self, fg_color="#0F172A")
        self.records_scroll.pack(fill="both", expand=True, padx=20, pady=12)

    def on_view_activated(self):
        """Called when Explorer view is displayed."""
        self._refresh_records()

    def _get_rbac_records(self) -> list[dict]:
        """Queries records from unified DuckDB connection with RBAC and format filtering."""
        role = session.role
        dept = session.department

        conn = duckdb.connect()
        try:
            if os.path.exists(STRUCTURED_DB_PATH):
                conn.execute(f"ATTACH '{STRUCTURED_DB_PATH}' AS synth (READ_ONLY);")
            if os.path.exists(DEFAULT_VAULT_PATH):
                conn.execute(f"ATTACH '{DEFAULT_VAULT_PATH}' AS vault (READ_ONLY);")

            where_clauses = []
            params = []

            # RBAC policy filter
            if role in ["General_Employee", "Employee"]:
                where_clauses.append("clearance_level IN ('Public', 'Internal') AND allowed_roles LIKE '%All%'")
            elif role in ["Department_Manager", "Manager"]:
                where_clauses.append("clearance_level IN ('Public', 'Internal', 'Confidential') AND (department = ? OR department IN ('Corporate Operations', 'Operations'))")
                params.append(dept)
            # Executive and Compliance_Auditor have full global scope

            # Scope filter
            sel_scope = self.scope_filter.get()
            if sel_scope == "Synthetic Only":
                where_clauses.append("source = 'synthetic'")
            elif sel_scope == "Non-Synthetic Vault Only":
                where_clauses.append("source = 'vault'")

            # Format filter
            fmt_map = {
                "PDFs (.pdf)": "pdf",
                "Markdown (.md)": "md",
                "Spreadsheets (.csv)": "csv",
                "Plain Text (.txt)": "txt",
                "JSON (.json)": "json",
            }
            sel_fmt = fmt_map.get(self.fmt_filter.get())
            if sel_fmt:
                where_clauses.append("file_type = ?")
                params.append(sel_fmt)

            # Search keyword
            kw = self.search_entry.get().strip()
            if kw:
                where_clauses.append("(title ILIKE ? OR content ILIKE ? OR id ILIKE ?)")
                params.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%"])

            # Department filter
            sel_dept = self.dept_filter.get()
            if sel_dept != "All Departments":
                where_clauses.append("department = ?")
                params.append(sel_dept)

            # Compliance filter
            sel_risk = self.risk_filter.get()
            if sel_risk == "Audit Risk Only (⚠️)":
                where_clauses.append("compliance_label = 1")
            elif sel_risk == "Standard Only":
                where_clauses.append("compliance_label = 0")

            where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

            query = f"""
            WITH unified AS (
                SELECT 
                    id,
                    title,
                    content,
                    department,
                    clearance_level,
                    CASE 
                        WHEN data_type = 'document_pdf' THEN 'pdf'
                        WHEN data_type IN ('meeting_note', 'notes') THEN 'md'
                        WHEN data_type = 'email' THEN 'csv'
                        WHEN data_type = 'support_ticket' THEN 'json'
                        ELSE 'txt'
                    END AS file_type,
                    data_type,
                    'synthetic' AS source,
                    TRUE AS is_synthetic,
                    author,
                    recipient,
                    'synthetic_records' AS source_file,
                    CAST(created_at AS VARCHAR) AS created_at,
                    compliance_label,
                    COALESCE(allowed_roles, 'All') AS allowed_roles
                FROM synth.synthetic_records

                UNION ALL

                SELECT 
                    doc_id AS id,
                    title,
                    body_text AS content,
                    department,
                    clearance_level,
                    file_type,
                    data_type,
                    'vault' AS source,
                    FALSE AS is_synthetic,
                    COALESCE(json_extract_string(attributes, '$.author'), 'system') AS author,
                    COALESCE(json_extract_string(attributes, '$.recipient'), 'all') AS recipient,
                    source_file,
                    CAST(ingested_at AS VARCHAR) AS created_at,
                    CASE WHEN json_extract_string(attributes, '$.compliance_label') = '1' THEN 1 ELSE 0 END AS compliance_label,
                    COALESCE(allowed_roles, 'All') AS allowed_roles
                FROM vault.documents
            )
            SELECT * FROM unified {where_sql} ORDER BY created_at DESC LIMIT 100;
            """

            df = conn.execute(query, params).fetchdf()
            return df.to_dict(orient="records")
        except Exception as e:
            print(f"[Explorer Error]: {e}")
            return []
        finally:
            conn.close()

    def _refresh_records(self):
        for widget in self.records_scroll.winfo_children():
            widget.destroy()

        records = self._get_rbac_records()
        self.stats_badge.configure(text=f"Showing {len(records)} records authorized for {session.role}")

        if not records:
            empty_lbl = ctk.CTkLabel(
                self.records_scroll,
                text="No records found matching your filters within your clearance level.",
                font=ctk.CTkFont(size=13, slant="italic"),
                text_color="#64748B",
            )
            empty_lbl.pack(pady=40)
            return

        fmt_colors = {
            "pdf": "#DC2626",
            "md": "#4F46E5",
            "csv": "#059669",
            "txt": "#7C3AED",
            "json": "#D97706",
        }

        for rec in records:
            card = ctk.CTkFrame(self.records_scroll, fg_color="#1E293B", corner_radius=10, border_width=1, border_color="#334155")
            card.pack(fill="x", pady=6, padx=5)

            # Card Header
            header_line = ctk.CTkFrame(card, fg_color="transparent")
            header_line.pack(fill="x", padx=14, pady=(10, 4))

            ftype = (rec.get("file_type") or "txt").lower()
            is_synth = rec.get("is_synthetic", True)

            # Left format & source pills
            pills_frame = ctk.CTkFrame(header_line, fg_color="transparent")
            pills_frame.pack(side="left")

            ctk.CTkLabel(
                pills_frame,
                text=ftype.upper(),
                font=ctk.CTkFont(size=10, weight="bold"),
                fg_color=fmt_colors.get(ftype, "#475569"),
                corner_radius=4,
                padx=6,
                pady=2,
                text_color="#FFFFFF",
            ).pack(side="left", padx=(0, 6))

            ctk.CTkLabel(
                pills_frame,
                text="SYNTHETIC" if is_synth else "VAULT",
                font=ctk.CTkFont(size=9, weight="bold"),
                fg_color="#8B5CF6" if is_synth else "#2563EB",
                corner_radius=4,
                padx=5,
                pady=2,
                text_color="#FFFFFF",
            ).pack(side="left", padx=(0, 10))

            ctk.CTkLabel(
                pills_frame,
                text=rec.get("title", "Untitled Document"),
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color="#F8FAFC",
            ).pack(side="left")

            if rec.get("compliance_label") == 1:
                ctk.CTkLabel(
                    header_line,
                    text="⚠️ AUDIT FLAG",
                    font=ctk.CTkFont(size=10, weight="bold"),
                    fg_color="#991B1B",
                    corner_radius=4,
                    padx=6,
                    pady=2,
                    text_color="#F8FAFC",
                ).pack(side="right")

            # Meta line
            meta_line = ctk.CTkFrame(card, fg_color="transparent")
            meta_line.pack(fill="x", padx=14, pady=(0, 6))

            meta_text = f"ID: {rec.get('id')}  •  Dept: {rec.get('department')}  •  Clearance: {rec.get('clearance_level')}  •  {rec.get('created_at', '')[:10]}"
            ctk.CTkLabel(
                meta_line,
                text=meta_text,
                font=ctk.CTkFont(size=11),
                text_color="#94A3B8",
            ).pack(side="left")

            # Content preview
            preview = str(rec.get("content", ""))[:140] + "..."
            ctk.CTkLabel(
                card,
                text=preview,
                font=ctk.CTkFont(size=12),
                text_color="#CBD5E1",
                justify="left",
            ).pack(anchor="w", padx=14, pady=(0, 10))

            # Inspect Button
            btn = ctk.CTkButton(
                card,
                text="Inspect Document →",
                font=ctk.CTkFont(size=11, weight="bold"),
                width=140,
                height=28,
                fg_color="#3B82F6",
                hover_color="#2563EB",
                command=lambda r=rec: RecordDetailModal(self, r),
            )
            btn.pack(anchor="e", padx=14, pady=(0, 10))
