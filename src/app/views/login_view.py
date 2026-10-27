"""
login_view.py — Sleek Login & Quick Role Switcher View
Allows direct credential login or instant 1-click test role access.
"""

import customtkinter as ctk
from ..auth_db import authenticate_user, register_user, SUPPORTED_ROLES
from ..session import session


class LoginView(ctk.CTkFrame):
    """Modern dark authentication screen with Quick Test Role chips."""

    def __init__(self, master, on_login_success):
        super().__init__(master, corner_radius=0, fg_color="#0F172A")
        self.on_login_success = on_login_success

        # Center card container
        self.card = ctk.CTkFrame(self, width=540, corner_radius=16, fg_color="#1E293B", border_width=1, border_color="#334155")
        self.card.place(relx=0.5, rely=0.5, anchor="center")

        # App Brand Header
        self.title_label = ctk.CTkLabel(
            self.card,
            text="Corporate AI Desktop",
            font=ctk.CTkFont(size=26, weight="bold"),
            text_color="#F8FAFC",
        )
        self.title_label.pack(pady=(28, 4))

        self.subtitle_label = ctk.CTkLabel(
            self.card,
            text="Privacy-Preserving Enterprise Intelligence & RBAC Copilot",
            font=ctk.CTkFont(size=13),
            text_color="#94A3B8",
        )
        self.subtitle_label.pack(pady=(0, 20))

        # Tabview for Login vs Register
        self.tabview = ctk.CTkTabview(
            self.card,
            width=460,
            fg_color="#1E293B",
            segmented_button_selected_color="#3B82F6",
            segmented_button_selected_hover_color="#2563EB",
            segmented_button_unselected_color="#334155",
        )
        self.tabview.pack(padx=20, pady=(0, 15))

        self.login_tab = self.tabview.add("Sign In")
        self.register_tab = self.tabview.add("New Account")

        self._build_login_tab()
        self._build_register_tab()

        # Status / Error Banner
        self.status_label = ctk.CTkLabel(
            self.card,
            text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#EF4444",
        )
        self.status_label.pack(pady=(0, 10))

        # Quick Test Role Selector
        self._build_quick_test_section()

    def _build_login_tab(self):
        tab = self.login_tab

        ctk.CTkLabel(tab, text="Username", font=ctk.CTkFont(size=12), text_color="#CBD5E1").pack(anchor="w", padx=25, pady=(12, 2))
        self.username_entry = ctk.CTkEntry(
            tab,
            width=410,
            height=40,
            placeholder_text="e.g. executive, manager, auditor, employee",
            fg_color="#0F172A",
            border_color="#475569",
        )
        self.username_entry.pack(padx=25, pady=(0, 10))

        ctk.CTkLabel(tab, text="Password", font=ctk.CTkFont(size=12), text_color="#CBD5E1").pack(anchor="w", padx=25, pady=(5, 2))
        self.password_entry = ctk.CTkEntry(
            tab,
            width=410,
            height=40,
            placeholder_text="Enter password (default: pass123)",
            show="•",
            fg_color="#0F172A",
            border_color="#475569",
        )
        self.password_entry.pack(padx=25, pady=(0, 18))
        self.password_entry.bind("<Return>", lambda e: self._handle_login())

        self.login_btn = ctk.CTkButton(
            tab,
            text="Sign In to Enterprise Workspace",
            font=ctk.CTkFont(size=14, weight="bold"),
            width=410,
            height=42,
            fg_color="#3B82F6",
            hover_color="#2563EB",
            command=self._handle_login,
        )
        self.login_btn.pack(padx=25, pady=(0, 15))

    def _build_register_tab(self):
        tab = self.register_tab

        ctk.CTkLabel(tab, text="Full Name", font=ctk.CTkFont(size=12), text_color="#CBD5E1").pack(anchor="w", padx=25, pady=(8, 2))
        self.reg_fullname = ctk.CTkEntry(tab, width=410, height=36, fg_color="#0F172A", border_color="#475569")
        self.reg_fullname.pack(padx=25, pady=(0, 6))

        ctk.CTkLabel(tab, text="Username", font=ctk.CTkFont(size=12), text_color="#CBD5E1").pack(anchor="w", padx=25, pady=(4, 2))
        self.reg_username = ctk.CTkEntry(tab, width=410, height=36, fg_color="#0F172A", border_color="#475569")
        self.reg_username.pack(padx=25, pady=(0, 6))

        ctk.CTkLabel(tab, text="Password", font=ctk.CTkFont(size=12), text_color="#CBD5E1").pack(anchor="w", padx=25, pady=(4, 2))
        self.reg_password = ctk.CTkEntry(tab, width=410, height=36, show="•", fg_color="#0F172A", border_color="#475569")
        self.reg_password.pack(padx=25, pady=(0, 6))

        ctk.CTkLabel(tab, text="Assigned RBAC Role", font=ctk.CTkFont(size=12), text_color="#CBD5E1").pack(anchor="w", padx=25, pady=(4, 2))
        self.reg_role_combo = ctk.CTkComboBox(
            tab,
            values=SUPPORTED_ROLES,
            width=410,
            height=36,
            fg_color="#0F172A",
            border_color="#475569",
        )
        self.reg_role_combo.set("General_Employee")
        self.reg_role_combo.pack(padx=25, pady=(0, 12))

        self.reg_btn = ctk.CTkButton(
            tab,
            text="Create Employee Account",
            font=ctk.CTkFont(size=13, weight="bold"),
            width=410,
            height=38,
            fg_color="#10B981",
            hover_color="#059669",
            command=self._handle_register,
        )
        self.reg_btn.pack(padx=25, pady=(0, 10))

    def _build_quick_test_section(self):
        quick_frame = ctk.CTkFrame(self.card, fg_color="#0F172A", corner_radius=10)
        quick_frame.pack(fill="x", padx=20, pady=(0, 20))

        ctk.CTkLabel(
            quick_frame,
            text="⚡ Instant 1-Click Role Logins (Pre-configured)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#94A3B8",
        ).pack(pady=(10, 8))

        btn_grid = ctk.CTkFrame(quick_frame, fg_color="transparent")
        btn_grid.pack(pady=(0, 10))

        roles = [
            ("General Employee", "employee", "#64748B"),
            ("Dept Manager", "manager", "#D97706"),
            ("Compliance Auditor", "auditor", "#8B5CF6"),
            ("Executive Leader", "executive", "#059669"),
        ]

        for i, (label, uname, color) in enumerate(roles):
            row = i // 2
            col = i % 2
            btn = ctk.CTkButton(
                btn_grid,
                text=label,
                font=ctk.CTkFont(size=11, weight="bold"),
                width=190,
                height=32,
                fg_color=color,
                hover_color="#334155",
                command=lambda u=uname: self._quick_login(u),
            )
            btn.grid(row=row, column=col, padx=6, pady=4)

    def _handle_login(self):
        uname = self.username_entry.get().strip()
        pwd = self.password_entry.get().strip()
        if not uname or not pwd:
            self._show_status("Please enter both username and password.", is_error=True)
            return

        user = authenticate_user(uname, pwd)
        if user:
            session.login(user)
            self._show_status(f"Welcome, {user['full_name']}!", is_error=False)
            self.on_login_success()
        else:
            self._show_status("Invalid username or password.", is_error=True)

    def _quick_login(self, username: str):
        user = authenticate_user(username, "pass123")
        if user:
            session.login(user)
            self.on_login_success()
        else:
            self._show_status(f"Could not load account for {username}", is_error=True)

    def _handle_register(self):
        fullname = self.reg_fullname.get().strip()
        uname = self.reg_username.get().strip()
        pwd = self.reg_password.get().strip()
        role = self.reg_role_combo.get()

        if not fullname or not uname or not pwd:
            self._show_status("All registration fields are required.", is_error=True)
            return

        dept_map = {
            "Executive": "Executive Leadership",
            "Compliance_Auditor": "Legal & Regulatory Compliance",
            "Department_Manager": "Trading & Risk Management",
            "General_Employee": "Corporate Operations",
        }
        dept = dept_map.get(role, "Corporate Operations")

        success, msg = register_user(uname, pwd, fullname, role, dept)
        if success:
            self._show_status("Account created! Please sign in.", is_error=False)
            self.tabview.set("Sign In")
            self.username_entry.delete(0, "end")
            self.username_entry.insert(0, uname)
            self.password_entry.delete(0, "end")
            self.password_entry.focus()
        else:
            self._show_status(msg, is_error=True)

    def _show_status(self, message: str, is_error: bool = True):
        self.status_label.configure(
            text=message,
            text_color="#EF4444" if is_error else "#10B981",
        )
