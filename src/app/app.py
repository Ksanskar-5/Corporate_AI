"""
app.py — Main CustomTkinter Application Window & Shell
Manages window layout, top profile header, left navigation rail, and dynamic view switching.
"""

import customtkinter as ctk
from .session import session
from .views.login_view import LoginView
from .views.chat_view import ChatView
from .views.explorer_view import ExplorerView
from .views.pipeline_view import PipelineView

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class CorporateAIApp(ctk.CTk):
    """Main Desktop Window for the Corporate AI Assistant & Enterprise Copilot."""

    def __init__(self):
        super().__init__()

        self.title("Corporate AI Desktop — Privacy-Preserving Enterprise Intelligence")
        self.geometry("1180x760")
        self.minsize(980, 640)

        # Container for screens
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Login Screen
        self.login_view = LoginView(self, on_login_success=self._on_login_success)
        self.login_view.grid(row=0, column=0, sticky="nsew")

        # Workspace Container (Header + Nav + Content)
        self.workspace_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="#0F172A")

        self._build_header()
        self._build_workspace_body()

        # Show Login View first
        self._show_login()

    def _build_header(self):
        self.header = ctk.CTkFrame(self.workspace_frame, height=60, fg_color="#1E293B", corner_radius=0)
        self.header.pack(fill="x", side="top")

        # Brand on left
        brand_frame = ctk.CTkFrame(self.header, fg_color="transparent")
        brand_frame.pack(side="left", padx=20, pady=10)

        ctk.CTkLabel(
            brand_frame,
            text="🏢 CORPORATE AI",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#F8FAFC",
        ).pack(side="left")

        # User Profile on right
        self.profile_frame = ctk.CTkFrame(self.header, fg_color="transparent")
        self.profile_frame.pack(side="right", padx=20, pady=10)

        self.user_lbl = ctk.CTkLabel(
            self.profile_frame,
            text="",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#F8FAFC",
        )
        self.user_lbl.pack(side="left", padx=(0, 10))

        self.role_badge = ctk.CTkLabel(
            self.profile_frame,
            text="",
            font=ctk.CTkFont(size=11, weight="bold"),
            corner_radius=6,
            padx=8,
            pady=3,
        )
        self.role_badge.pack(side="left", padx=(0, 15))

        self.logout_btn = ctk.CTkButton(
            self.profile_frame,
            text="Sign Out",
            font=ctk.CTkFont(size=11),
            width=70,
            height=28,
            fg_color="#334155",
            hover_color="#DC2626",
            command=self._handle_logout,
        )
        self.logout_btn.pack(side="left")

    def _build_workspace_body(self):
        body_frame = ctk.CTkFrame(self.workspace_frame, corner_radius=0, fg_color="#0F172A")
        body_frame.pack(fill="both", expand=True)

        # Left Nav Rail
        self.nav_rail = ctk.CTkFrame(body_frame, width=200, corner_radius=0, fg_color="#1E293B")
        self.nav_rail.pack(side="left", fill="y", padx=0, pady=0)
        self.nav_rail.pack_propagate(False)

        ctk.CTkLabel(
            self.nav_rail,
            text="NAVIGATION",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#64748B",
        ).pack(anchor="w", padx=20, pady=(20, 10))

        # Nav Buttons
        self.nav_buttons = {}

        self.btn_chat = self._create_nav_button("💬  RAG Copilot", "chat")
        self.btn_explorer = self._create_nav_button("📁  Explorer", "explorer")
        self.btn_pipeline = self._create_nav_button("⚙️  Pipeline Studio", "pipeline")

        # Bottom Version Note
        version_lbl = ctk.CTkLabel(
            self.nav_rail,
            text="v2.5 Enterprise\nRBAC Enabled",
            font=ctk.CTkFont(size=10),
            text_color="#475569",
            justify="center",
        )
        version_lbl.pack(side="bottom", pady=15)

        # Dynamic View Container on Right
        self.views_container = ctk.CTkFrame(body_frame, corner_radius=0, fg_color="#0F172A")
        self.views_container.pack(side="right", fill="both", expand=True)

        # Initialize Child Views
        self.chat_view = ChatView(self.views_container)
        self.explorer_view = ExplorerView(self.views_container)
        self.pipeline_view = PipelineView(self.views_container)

        self.views = {
            "chat": self.chat_view,
            "explorer": self.explorer_view,
            "pipeline": self.pipeline_view,
        }

    def _create_nav_button(self, text: str, view_key: str) -> ctk.CTkButton:
        btn = ctk.CTkButton(
            self.nav_rail,
            text=text,
            font=ctk.CTkFont(size=13, weight="bold"),
            height=40,
            fg_color="transparent",
            text_color="#CBD5E1",
            hover_color="#334155",
            anchor="w",
            command=lambda k=view_key: self._switch_view(k),
        )
        btn.pack(fill="x", padx=10, pady=3)
        self.nav_buttons[view_key] = btn
        return btn

    def _show_login(self):
        self.workspace_frame.grid_forget()
        self.login_view.grid(row=0, column=0, sticky="nsew")

    def _on_login_success(self):
        self.login_view.grid_forget()
        self.workspace_frame.grid(row=0, column=0, sticky="nsew")

        # Update Profile Bar
        self.user_lbl.configure(text=f"{session.full_name}  ({session.department})")

        role_colors = {
            "Executive": ("#065F46", "#34D399"),
            "Compliance_Auditor": ("#4C1D95", "#A78BFA"),
            "Department_Manager": ("#78350F", "#FBBF24"),
            "General_Employee": ("#1E293B", "#94A3B8"),
        }
        bg_col, txt_col = role_colors.get(session.role, ("#1E293B", "#94A3B8"))
        self.role_badge.configure(
            text=f"[{session.role.upper()}]",
            fg_color=bg_col,
            text_color=txt_col,
        )

        # Enforce RBAC on Pipeline Studio button
        if session.can_access_pipeline:
            self.btn_pipeline.pack(fill="x", padx=10, pady=3)
        else:
            self.btn_pipeline.pack_forget()

        # Default to Chat View
        self._switch_view("chat")

    def _switch_view(self, view_key: str):
        # Update Nav button highlights
        for key, btn in self.nav_buttons.items():
            if key == view_key:
                btn.configure(fg_color="#3B82F6", text_color="#FFFFFF")
            else:
                btn.configure(fg_color="transparent", text_color="#CBD5E1")

        # Show selected view
        for key, view in self.views.items():
            if key == view_key:
                view.pack(fill="both", expand=True)
                if hasattr(view, "on_view_activated"):
                    view.on_view_activated()
            else:
                view.pack_forget()

    def _handle_logout(self):
        session.logout()
        self._show_login()


def launch_app():
    """Starts the CustomTkinter desktop application."""
    app = CorporateAIApp()
    app.mainloop()


if __name__ == "__main__":
    launch_app()
