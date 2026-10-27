"""
chat_view.py — Role-Aware RAG Copilot Chat Screen
Queries vector embeddings of synthetic enterprise data in Chroma DB with strict pre-retrieval
clearance filters and generates verified corporate responses using Google Gemini without GUI freezing.
"""

import os
import threading
import customtkinter as ctk
from ...agent.chatbot import CorporateChatbot
from ..session import session


class ChatView(ctk.CTkFrame):
    """Interactive conversational copilot with role-aware pre-retrieval retrieval and citations."""

    def __init__(self, master):
        super().__init__(master, corner_radius=0, fg_color="#0F172A")
        self.chatbot = None
        self.is_generating = False

        # Top Bar with active role clearance status
        self.top_bar = ctk.CTkFrame(self, height=54, fg_color="#1E293B", corner_radius=0)
        self.top_bar.pack(fill="x", side="top")

        self.title_lbl = ctk.CTkLabel(
            self.top_bar,
            text="💬 Corporate AI Copilot (RAG with RBAC)",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#F8FAFC",
        )
        self.title_lbl.pack(side="left", padx=20, pady=12)

        self.clearance_tag = ctk.CTkLabel(
            self.top_bar,
            text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#334155",
            corner_radius=6,
            padx=10,
            pady=4,
            text_color="#38BDF8",
        )
        self.clearance_tag.pack(side="right", padx=20, pady=12)

        # Chat Message Scroll Area
        self.chat_scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="#0F172A",
            corner_radius=0,
        )
        self.chat_scroll.pack(fill="both", expand=True, padx=20, pady=(15, 10))

        # Bottom Input Bar
        self.input_frame = ctk.CTkFrame(self, height=70, fg_color="#1E293B", corner_radius=12)
        self.input_frame.pack(fill="x", padx=20, pady=(0, 20))

        self.query_entry = ctk.CTkEntry(
            self.input_frame,
            height=46,
            placeholder_text="Ask about ongoing corporate operations, department projects, trading policies, or compliance reviews...",
            fg_color="#0F172A",
            border_color="#475569",
            font=ctk.CTkFont(size=13),
        )
        self.query_entry.pack(side="left", fill="x", expand=True, padx=(15, 10), pady=12)
        self.query_entry.bind("<Return>", lambda e: self._send_message())

        self.send_btn = ctk.CTkButton(
            self.input_frame,
            text="Send",
            font=ctk.CTkFont(size=13, weight="bold"),
            width=90,
            height=44,
            fg_color="#3B82F6",
            hover_color="#2563EB",
            command=self._send_message,
        )
        self.send_btn.pack(side="right", padx=(0, 15), pady=12)

        self.clear_btn = ctk.CTkButton(
            self.input_frame,
            text="Clear",
            font=ctk.CTkFont(size=12),
            width=70,
            height=44,
            fg_color="#334155",
            hover_color="#475569",
            command=self._clear_chat,
        )
        self.clear_btn.pack(side="right", padx=(0, 10), pady=12)

    def on_view_activated(self):
        """Called when this view becomes visible. Initializes or updates the chatbot for current role."""
        role = session.role
        dept = session.department
        self.clearance_tag.configure(text=f"Active Role: {role} | {session.clearance_description}")

        # Initialize or rebind chatbot with current user's role
        try:
            if not self.chatbot:
                self.chatbot = CorporateChatbot(user_role=role, user_department=dept)
            else:
                self.chatbot.set_user(user_role=role, user_department=dept)
        except Exception as e:
            self._add_system_message(f"⚠️ Chatbot initialization note: {e}")

        # Show welcome greeting if chat is empty
        if len(self.chat_scroll.winfo_children()) == 0:
            self._add_assistant_message(
                f"Hello {session.full_name}! I am the Corporate AI Assistant.\n"
                f"I am initialized with clearance level **{session.clearance_description}**.\n\n"
                f"All questions you ask will be retrieved strictly through your authorized RBAC clearance filters.",
                sources=[],
            )

    def _send_message(self):
        if self.is_generating:
            return
        query = self.query_entry.get().strip()
        if not query:
            return

        self.query_entry.delete(0, "end")
        self._add_user_message(query)

        # Show typing indicator
        self.typing_label = ctk.CTkLabel(
            self.chat_scroll,
            text="Corporate AI is searching vector store and generating response...",
            font=ctk.CTkFont(size=12, slant="italic"),
            text_color="#94A3B8",
        )
        self.typing_label.pack(anchor="w", padx=15, pady=(5, 5))
        self.chat_scroll._parent_canvas.yview_moveto(1.0)

        self.is_generating = True
        self.send_btn.configure(state="disabled")

        # Execute RAG query in background thread so GUI stays responsive
        thread = threading.Thread(target=self._run_rag_worker, args=(query,), daemon=True)
        thread.start()

    def _run_rag_worker(self, query: str):
        try:
            if not self.chatbot:
                self.chatbot = CorporateChatbot(
                    user_role=session.role,
                    user_department=session.department,
                )
            result = self.chatbot.ask(query)
            answer = result["answer"]
            sources = result.get("sources", [])
        except Exception as e:
            answer = f"Error generating answer: {str(e)}\n(Verify GEMINI_API_KEY is configured in your .env file)"
            sources = []

        # Update GUI on main thread
        self.after(0, self._render_assistant_response, answer, sources)

    def _render_assistant_response(self, answer: str, sources: list):
        if hasattr(self, "typing_label") and self.typing_label.winfo_exists():
            self.typing_label.destroy()

        self._add_assistant_message(answer, sources)
        self.is_generating = False
        self.send_btn.configure(state="normal")
        self.chat_scroll._parent_canvas.yview_moveto(1.0)

    def _add_user_message(self, text: str):
        msg_frame = ctk.CTkFrame(self.chat_scroll, fg_color="#1E3A8A", corner_radius=12)
        msg_frame.pack(anchor="e", padx=(80, 10), pady=(8, 8))

        ctk.CTkLabel(
            msg_frame,
            text=f"You ({session.role})",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#93C5FD",
        ).pack(anchor="e", padx=14, pady=(8, 2))

        ctk.CTkLabel(
            msg_frame,
            text=text,
            font=ctk.CTkFont(size=13),
            text_color="#F8FAFC",
            wraplength=650,
            justify="left",
        ).pack(padx=14, pady=(0, 10))

    def _add_assistant_message(self, text: str, sources: list):
        msg_frame = ctk.CTkFrame(self.chat_scroll, fg_color="#1E293B", corner_radius=12, border_width=1, border_color="#334155")
        msg_frame.pack(anchor="w", padx=(10, 80), pady=(8, 8))

        ctk.CTkLabel(
            msg_frame,
            text="Corporate AI Assistant",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#38BDF8",
        ).pack(anchor="w", padx=14, pady=(8, 4))

        ctk.CTkLabel(
            msg_frame,
            text=text,
            font=ctk.CTkFont(size=13),
            text_color="#F1F5F9",
            wraplength=680,
            justify="left",
        ).pack(padx=14, pady=(0, 8))

        # Citations / Authorized sources container
        if sources:
            cite_frame = ctk.CTkFrame(msg_frame, fg_color="#0F172A", corner_radius=8)
            cite_frame.pack(fill="x", padx=12, pady=(0, 10))

            ctk.CTkLabel(
                cite_frame,
                text="📎 Authorized Sources Cited:",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color="#94A3B8",
            ).pack(anchor="w", padx=10, pady=(6, 4))

            chips_frame = ctk.CTkFrame(cite_frame, fg_color="transparent")
            chips_frame.pack(fill="x", padx=10, pady=(0, 6))

            for s in sources:
                risk_tag = " | ⚠️ AUDIT REQUIRED" if s.get("compliance_label") == 1 else ""
                chip_text = f"[{s.get('id')}] {s.get('title')[:30]} ({s.get('clearance')}{risk_tag})"
                chip_color = "#991B1B" if s.get("compliance_label") == 1 else "#1E293B"

                pill = ctk.CTkLabel(
                    chips_frame,
                    text=chip_text,
                    font=ctk.CTkFont(size=10),
                    fg_color=chip_color,
                    corner_radius=4,
                    padx=6,
                    pady=2,
                    text_color="#E2E8F0",
                )
                pill.pack(side="left", padx=(0, 6), pady=2)

    def _add_system_message(self, text: str):
        lbl = ctk.CTkLabel(
            self.chat_scroll,
            text=text,
            font=ctk.CTkFont(size=12),
            text_color="#F59E0B",
        )
        lbl.pack(anchor="center", pady=6)

    def _clear_chat(self):
        for widget in self.chat_scroll.winfo_children():
            widget.destroy()
        if self.chatbot:
            self.chatbot.clear_history()
        self.on_view_activated()
