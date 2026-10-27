"""
chatbot.py — LangChain RAG Chatbot with Role-Based Access Control (RBAC)
Queries vector embeddings of synthetic enterprise data in Chroma DB with strict pre-retrieval
clearance filters and generates verified corporate responses with citations using Google Gemini.
"""

import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.output_parsers import StrOutputParser
from .vector_store import get_retriever, build_vector_store

load_dotenv()

SYSTEM_PROMPT = """You are the Corporate AI Assistant, an internal enterprise copilot.
Your job is to answer employee, manager, and leadership questions about company operations,
process reviews, ongoing projects, and compliance status.

CURRENT USER IDENTITY & CLEARANCE:
- User Role: {user_role}
- Department: {user_department}

RETRIEVED ENTERPRISE CONTEXT (strictly filtered by RBAC pre-retrieval clearance):
{context}

STRICT OPERATIONAL RULES:
1. Ground your answers ONLY in the retrieved enterprise context above. Do not hallucinate or invent company details.
2. If no matching records were retrieved, politely inform the user: "No authorized records were found within your clearance level."
3. Always cite the Record ID (e.g. `[Record: synth_xxxx]`) and Department when referencing information.
4. Maintain a professional, clear, executive tone.
5. If the user asks about compliance, security, or audit issues, explicitly highlight any records flagged with an audit requirement (`compliance_label == 1`).
"""

SUPPORTED_ROLES = [
    "Employee",
    "Analyst",
    "Manager",
    "Admin",
]


class CorporateChatbot:
    """
    Role-Aware RAG Chatbot using Chroma DB vector retrieval and Google Gemini.
    Enforces pre-retrieval data filtering so unauthorized records never enter LLM context.
    """

    def __init__(
        self,
        user_role: str = "Employee",
        user_department: str = None,
        api_key: str = None,
        model: str = "gemini-2.5-flash",
        temperature: float = 0.2,
        k: int = 4,
    ):
        load_dotenv()
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self.user_role = user_role if user_role in SUPPORTED_ROLES else "Employee"
        self.user_department = user_department or "Operations"
        self.model = model
        self.k = k
        self.history = []

        if not self.api_key:
            raise ValueError(
                "Gemini API key not found. Please set GEMINI_API_KEY in your .env file "
                "or pass api_key to CorporateChatbot(api_key='...')."
            )

        # Initialize vector retriever with strict RBAC pre-retrieval filtering
        self.retriever = get_retriever(
            k=self.k,
            user_role=self.user_role,
            user_department=self.user_department,
        )

        # Initialize Gemini via LangChain
        self.llm = ChatGoogleGenerativeAI(
            model=self.model,
            google_api_key=self.api_key,
            temperature=temperature,
        )

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{question}"),
        ])

        self.chain = self.prompt | self.llm | StrOutputParser()

    def set_user(self, user_role: str, user_department: str = None):
        """Updates user role and rebinds the RBAC retriever."""
        self.user_role = user_role if user_role in SUPPORTED_ROLES else "Employee"
        if user_department:
            self.user_department = user_department
        self.retriever = get_retriever(
            k=self.k,
            user_role=self.user_role,
            user_department=self.user_department,
        )
        self.clear_history()

    def ask(self, question: str) -> dict:
        """
        Retrieves authorized synthetic documents from Chroma DB,
        invokes Gemini RAG chain, and returns the response with citations.
        """
        # Step 1: Retrieve matching documents (filtered by RBAC)
        docs = self.retriever.invoke(question)

        # Format retrieved docs into readable context string
        context_parts = []
        sources = []
        for i, doc in enumerate(docs, 1):
            meta = doc.metadata
            doc_id = meta.get("id", f"doc_{i}")
            dept = meta.get("department", "Corporate Operations")
            sources.append({
                "id": doc_id,
                "department": dept,
                "title": meta.get("title", "Enterprise Record"),
                "compliance_label": meta.get("compliance_label", 0),
                "clearance": meta.get("clearance_level", "Internal"),
            })
            context_parts.append(
                f"--- [Record {i}: ID `{doc_id}` | Dept: {dept} | Clearance: {meta.get('clearance_level', 'Internal')} | Risk Flag: {meta.get('compliance_label', 0)}] ---\n"
                f"{doc.page_content}\n"
            )

        context_str = "\n".join(context_parts) if context_parts else "No authorized enterprise records found."

        # Step 2: Format conversation history for LangChain
        formatted_history = []
        for msg in self.history[-6:]:
            if msg["role"] == "user":
                formatted_history.append(HumanMessage(content=msg["content"]))
            else:
                formatted_history.append(AIMessage(content=msg["content"]))

        # Step 3: Generate response with Gemini
        answer = self.chain.invoke({
            "user_role": self.user_role,
            "user_department": self.user_department,
            "context": context_str,
            "history": formatted_history,
            "question": question,
        })

        # Step 4: Save to conversation memory
        self.history.append({"role": "user", "content": question})
        self.history.append({"role": "assistant", "content": answer})

        return {
            "answer": answer.strip(),
            "sources": sources,
            "user_role": self.user_role,
            "raw_context": context_str,
        }

    def clear_history(self):
        """Resets the conversation history."""
        self.history = []


def run_chatbot():
    """Interactive terminal session with Role-Based Access Control."""
    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    print("=" * 65)
    print("      CORPORATE AI CHATBOT (RAG with RBAC & Chroma DB)")
    print("=" * 65)
    print("Vector Store: Chroma DB (data/chroma_db)")
    print("LLM Engine  : Google Gemini (gemini-2.5-flash)")

    if not api_key:
        print("\n[Notice] No GEMINI_API_KEY found in environment or .env file.")
        api_key = input("Enter your Gemini API key (AIza...): ").strip()
        if api_key:
            with open(".env", "a") as f:
                f.write(f"\nGEMINI_API_KEY={api_key}\n")
            print("Saved to .env file.")
        else:
            print("Error: Gemini API key is required to start the chatbot.")
            return

    # Select initial role
    print("\nSelect your enterprise role:")
    print("  [1] Employee  (Standard operations, public/internal records)")
    print("  [2] Analyst   (Cross-department read access)")
    print("  [3] Manager   (Departmental records + confidential)")
    print("  [4] Admin     (Full C-Suite access, all records)")

    choice = input("Enter choice [1-4] (default 1): ").strip()
    role_map = {
        "1": ("Employee", "Operations"),
        "2": ("Analyst",  "Finance"),
        "3": ("Manager",  "Sales"),
        "4": ("Admin",    "Executive"),
    }
    user_role, user_dept = role_map.get(choice, ("Employee", "Operations"))

    try:
        build_vector_store()
        chatbot = CorporateChatbot(user_role=user_role, user_department=user_dept, api_key=api_key)
        print(f"\nLogged in as: [{chatbot.user_role}] | Department: [{chatbot.user_department}]")
    except Exception as e:
        print(f"Initialization error: {e}")
        return

    print("Commands: 'switch' to change role | 'clear' to reset chat | 'exit' to quit\n")

    while True:
        try:
            query = input(f"\n[{chatbot.user_role}] You: ").strip()
            if not query:
                continue
            if query.lower() in ["exit", "quit", "q"]:
                print("Goodbye.")
                break
            if query.lower() == "clear":
                chatbot.clear_history()
                print("[Chat history cleared]")
                continue
            if query.lower() == "switch":
                print("\nSwitch role to:")
                print("  [1] Employee")
                print("  [2] Analyst")
                print("  [3] Manager")
                print("  [4] Admin")
                new_c = input("Choice [1-4]: ").strip()
                new_r, new_d = role_map.get(new_c, ("Employee", "Operations"))
                chatbot.set_user(new_r, new_d)
                print(f"[Switched to {new_r} ({new_d})]")
                continue

            result = chatbot.ask(query)
            print("\n" + result["answer"])
            if result["sources"]:
                print(f"\n[Authorized Records: {', '.join([s['id'] + ' (' + s['clearance'] + ')' for s in result['sources']])}]")
            else:
                print("\n[No authorized records within your clearance level]")

        except KeyboardInterrupt:
            print("\nSession interrupted.")
            break
        except Exception as e:
            print(f"\n[Error]: {e}")


if __name__ == "__main__":
    run_chatbot()
