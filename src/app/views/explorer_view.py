"""
explorer_view.py — Enterprise Knowledge Explorer Screen
Browse, filter, and inspect authorized synthetic corporate records with strict RBAC enforcement.
"""

import duckdb
import customtkinter as ctk
from ...synthesis.db import STRUCTURED_DB_PATH
from ..session import session


class RecordDetailModal(ctk.CTkToplevel):
    """Detailed popup modal inspecting a single enterprise record."""

    def __init__(self, master, record: dict):
        super().__init__(master)
        self.title(f"Record Inspection — {record.get('id')}")
        self.geometry("700x550")
        self.configure(fg_color="#0F172A")
        self.grab_set()

        header = ctk.CTkFrame(self, fg_color="#1E293B", corner_radius=0)
        header.pack(fill="x", padx=0, pady=0)

        ctk.CTkLabel(
            header,
            text=f"📄 {record.get('title')}",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#F8FAFC",
            wraplength=660,
            justify="left",
        ).pack(anchor="w", padx=20, pady=(15, 6))

        # Metadata Row
        meta_row = ctk.CTkFrame(header, fg_color="transparent")
        meta_row.pack(fill="x", padx=20, pady=(0, 15))

        badges = [
            (f"ID: {record.get('id')}", "#334155"),
            (f"Dept: {record.get('department')}", "#1E3A8A"),
            (f"Clearance: {record.get('clearance_level')}", "#065F46" if record.get('clearance_level') == 'Internal' else "#991B1B"),
            (f"Type: {record.get('data_type')}", "#475569"),
        ]
        if record.get("compliance_label") == 1:
            badges.append(("⚠️ AUDIT RISK FLAG", "#7F1D1D"))

        for text, color in badges:
            lbl = ctk.CTkLabel(
                meta_row,
                text=text,
                font=ctk.CTkFont(size=11),
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

        info_grid = f"From: {record.get('author')}    ->    To: {record.get('recipient')}\nTimestamp: {record.get('timestamp')}\nAllowed Roles: {record.get('allowed_roles')}"
        ctk.CTkLabel(
            body_scroll,
            text=info_grid,
            font=ctk.CTkFont(size=12, slant="italic"),
            text_color="#94A3B8",
            justify="left",
        ).pack(anchor="w", padx=10, pady=(10, 12))

        ctk.CTkLabel(
            body_scroll,
            text=record.get("content", ""),
            font=ctk.CTkFont(size=13),
            text_color="#F1F5F9",
            wraplength=620,
            justify="left",
        ).pack(anchor="w", padx=10, pady=(0, 15))

        close_btn = ctk.CTkButton(
            self,
            text="Close Document",
            width=120,
            height=36,
            fg_color="#334155",
            hover_color="#475569",
            command=self.destroy,
        )
        close_btn.pack(pady=(0, 15))


class ExplorerView(ctk.CTkFrame):
    """Search and browse synthetic enterprise records under the active user's clearance."""

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
            text="📁 Enterprise Knowledge Explorer",
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

        # Row 2: Search and Filters
        filter_row = ctk.CTkFrame(self.control_bar, fg_color="transparent")
        filter_row.pack(fill="x", padx=20, pady=(0, 12))

        self.search_entry = ctk.CTkEntry(
            filter_row,
            placeholder_text="Search documents by keyword, title, or ID...",
            width=320,
            height=36,
            fg_color="#0F172A",
            border_color="#475569",
        )
        self.search_entry.pack(side="left", padx=(0, 10))
        self.search_entry.bind("<KeyRelease>", lambda e: self._refresh_records())

        self.dept_filter = ctk.CTkComboBox(
            filter_row,
            values=["All Departments", "Legal & Regulatory Compliance", "Trading & Risk Management", "Corporate Operations", "Engineering & IT Systems", "Finance & Accounting Audit", "Executive Leadership"],
            width=200,
            height=36,
            fg_color="#0F172A",
            border_color="#475569",
            command=lambda v: self._refresh_records(),
        )
        self.dept_filter.set("All Departments")
        self.dept_filter.pack(side="left", padx=(0, 10))

        self.risk_filter = ctk.CTkComboBox(
            filter_row,
            values=["All Risk Levels", "Standard Only", "Audit Risk Only (⚠️)"],
            width=160,
            height=36,
            fg_color="#0F172A",
            border_color="#475569",
            command=lambda v: self._refresh_records(),
        )
        self.risk_filter.set("All Risk Levels")
        self.risk_filter.pack(side="left")

        # Record List Scroll Area
        self.records_scroll = ctk.CTkScrollableFrame(self, fg_color="#0F172A")
        self.records_scroll.pack(fill="both", expand=True, padx=20, pady=15)

    def on_view_activated(self):
        """Called when Explorer view is displayed."""
        self._refresh_records()

    def _get_rbac_records(self) -> list[dict]:
        """Queries records from DuckDB with SQL-level RBAC filtering."""
        role = session.role
        dept = session.department

        conn = duckdb.connect(STRUCTURED_DB_PATH, read_only=True)
        try:
            where_clauses = []
            params = []

            # RBAC policy filter
            if role == "General_Employee":
                where_clauses.append("clearance_level IN ('Public', 'Internal') AND allowed_roles LIKE '%All%'")
            elif role == "Department_Manager":
                where_clauses.append("clearance_level IN ('Public', 'Internal', 'Confidential') AND (department = ? OR department = 'Corporate Operations')")
                params.append(dept)
            # Executive and Compliance_Auditor have full global scope

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
            query = f"SELECT * FROM synthetic_records {where_sql} ORDER BY created_at DESC LIMIT 100;"

            df = conn.execute(query, params).fetchdf()
            return df.to_dict(orient="records")
        except Exception as e:
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

        for rec in records:
            card = ctk.CTkFrame(self.records_scroll, fg_color="#1E293B", corner_radius=10, border_width=1, border_color="#334155")
            card.pack(fill="x", pady=6, padx=5)

            # Card Header
            header_line = ctk.CTkFrame(card, fg_color="transparent")
            header_line.pack(fill="x", padx=14, pady=(10, 4))

            ctk.CTkLabel(
                header_line,
                text=rec.get("title", "Untitled Process"),
                font=ctk.CTkFont(size=14, weight="bold"),
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

            # Meta row
            meta_line = ctk.CTkFrame(card, fg_color="transparent")
            meta_line.pack(fill="x", padx=14, pady=(0, 6))

            meta_text = f"ID: {rec.get('id')}  •  Dept: {rec.get('department')}  •  Clearance: {rec.get('clearance_level')}  •  {rec.get('timestamp')}"
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
                text="View Full Record →",
                font=ctk.CTkFont(size=11, weight="bold"),
                width=130,
                height=28,
                fg_color="#3B82F6",
                hover_color="#2563EB",
                command=lambda r=rec: RecordDetailModal(self, r),
            )
            btn.pack(anchor="e", padx=14, pady=(0, 10))
