"""
confidentiality.py — User-Defined Confidentiality & Disclosure Guardrails
Allows the user to specify:
1. Forbidden terms / secrets that must NEVER appear in the synthetic output.
2. Custom replacements (e.g. replacing 'Enron' with 'ApexCorp', 'Project Raptor' with 'Project Nova').
3. PII masking (emails, phones, monetary values).
4. Additional user-provided context to guide synthesis.
"""

import re
from typing import Dict, List, Optional


class ConfidentialityGuardrail:
    """
    Applies user-defined privacy and disclosure rules to synthetic data.
    """

    def __init__(
        self,
        forbidden_terms: Optional[List[str]] = None,
        custom_replacements: Optional[Dict[str, str]] = None,
        mask_pii: bool = True,
        additional_context: Optional[str] = None,
    ):
        self.forbidden_terms = [t.strip() for t in (forbidden_terms or []) if t.strip()]
        self.custom_replacements = custom_replacements or {}
        self.mask_pii = mask_pii
        self.additional_context = (additional_context or "").strip()

    def sanitize(self, text: str) -> str:
        """
        Applies redactions, custom replacements, and PII masking to generated text.
        """
        if not text:
            return ""

        sanitized = text

        # 1. Apply user custom replacements (e.g. "Enron" -> "ApexCorp")
        for secret, replacement in self.custom_replacements.items():
            if secret:
                pattern = re.compile(re.escape(secret), re.IGNORECASE)
                sanitized = pattern.sub(replacement, sanitized)

        # 2. Redact user forbidden terms
        for term in self.forbidden_terms:
            if term:
                pattern = re.compile(re.escape(term), re.IGNORECASE)
                sanitized = pattern.sub("[REDACTED]", sanitized)

        # 3. Standard automated PII masking if enabled
        if self.mask_pii:
            # Mask emails
            sanitized = re.sub(
                r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
                "contact@company.internal",
                sanitized,
            )
            # Mask phone numbers
            sanitized = re.sub(
                r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
                "555-0199",
                sanitized,
            )
            # Mask IP addresses
            sanitized = re.sub(
                r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
                "10.0.0.1",
                sanitized,
            )

        return sanitized

    def get_prompt_instructions(self) -> str:
        """
        Returns structured guidance instructions to include in LLM prompts.
        """
        instructions = []
        if self.forbidden_terms:
            instructions.append(f"STRICTLY FORBIDDEN TERMS (NEVER USE): {', '.join(self.forbidden_terms)}")
        if self.custom_replacements:
            replacements_str = ", ".join([f"'{k}' -> '{v}'" for k, v in self.custom_replacements.items()])
            instructions.append(f"USE SAFE REPLACEMENTS: {replacements_str}")
        if self.additional_context:
            instructions.append(f"USER GUIDANCE: {self.additional_context}")

        return "\n".join(instructions)
