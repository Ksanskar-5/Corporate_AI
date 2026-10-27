"""
sanitizer.py — Entity-Preserving Semantic Anonymization & Persona Rewriter
Preserves true corporate procedural steps, decisions, and business rules,
while deterministically replacing vulnerable PII, executive names (POIs), and dollar thresholds.
"""

import re

# Comprehensive mapping of Enron POIs / real executives to professional corporate roles
PERSONA_REPLACEMENTS = {
    r"\bkenneth\s+lay\b": "Chief Executive Officer",
    r"\bken\s+lay\b": "Chief Executive Officer",
    r"\bjeffrey\s+skilling\b": "President & Chief Operating Officer",
    r"\bjeff\s+skilling\b": "President & Chief Operating Officer",
    r"\bandrew\s+fastow\b": "Chief Financial Officer",
    r"\bandy\s+fastow\b": "Chief Financial Officer",
    r"\brichard\s+causey\b": "Chief Accounting Officer",
    r"\brick\s+causey\b": "Chief Accounting Officer",
    r"\bmichael\s+kopper\b": "Managing Director of Special Finance",
    r"\bmark\s+frevert\b": "Chairman of Global Operations",
    r"\bsteven\s+kean\b": "Chief of Staff & VP Regulatory Affairs",
    r"\bsteve\s+kean\b": "Chief of Staff & VP Regulatory Affairs",
    r"\bvince\s+kaminski\b": "Director of Quantitative Research",
    r"\bkaminski\b": "Quantitative Research Lead",
    r"\blou\s+pai\b": "Energy Services Division CEO",
    r"\bjames\s+derrick\b": "General Counsel & Legal Director",
    r"\bjim\s+derrick\b": "General Counsel & Legal Director",
    r"\bdelainey\b": "Commercial Trading Lead",
    r"\bskilling\b": "Chief Operating Officer",
    r"\bfastow\b": "Chief Financial Officer",
    r"\blay\b": "Executive Board Lead",
    r"\bkopper\b": "Structured Finance Director",
    r"\bglisan\b": "Treasury Director",
    r"\bcausey\b": "Senior Accounting Director",
    r"\bhannon\b": "Commercial Operations Manager",
    r"\benron\b": "ApexGlobal",
    r"\benrononline\b": "ApexTrader Platform",
    r"\beol\b": "Internal Trading Desk",
}

# Regex to detect raw Enron internal email strings
EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@enron\.com", re.IGNORECASE)

# Regex to detect real phone numbers
PHONE_REGEX = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")

# Regex to detect SSN formats
SSN_REGEX = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

# Dollar amount normalization (e.g. $15,000,000 -> Capital Tier 1 Allocation)
LARGE_DOLLAR_REGEX = re.compile(r"\$\s?\d{1,3}(?:,\d{3}){2,}(?:\.\d{2})?")
MID_DOLLAR_REGEX = re.compile(r"\$\s?\d{1,3}(?:,\d{3})(?:\.\d{2})?")


def sanitize_enterprise_text(
    text: str,
    forbidden_terms: list[str] = None,
    custom_replacements: dict = None,
    normalize_financials: bool = True,
) -> str:
    """
    Applies entity-preserving semantic anonymization to enterprise text:
    - Retains workflow instructions, regulatory rules, and procedural context.
    - Replaces real executive/POI names with department leadership personas.
    - Anonymizes email addresses to internal corporate format.
    - Standardizes phone numbers and SSNs.
    - Buckets large financial sums into normalized capital allocation tiers.
    """
    if not text:
        return ""

    sanitized = text

    # 1. Custom user-provided replacements
    if custom_replacements:
        for secret, alias in custom_replacements.items():
            if secret:
                pat = rf"\b{re.escape(secret)}\b" if secret.isalnum() else re.escape(secret)
                sanitized = re.sub(pat, alias, sanitized, flags=re.IGNORECASE)

    # 2. Executive Personas and Entity Mapping
    for pattern, persona in PERSONA_REPLACEMENTS.items():
        sanitized = re.sub(pattern, persona, sanitized, flags=re.IGNORECASE)

    # 3. Clean raw emails and contact details
    sanitized = EMAIL_REGEX.sub("corporate.lead@company.internal", sanitized)
    sanitized = PHONE_REGEX.sub("555-0199", sanitized)
    sanitized = SSN_REGEX.sub("[ID-CONFIDENTIAL]", sanitized)

    # 4. Normalize financial sums to preserve scale without exact transaction leakage
    if normalize_financials:
        sanitized = LARGE_DOLLAR_REGEX.sub("[High-Value Capital Allocation Tier 1]", sanitized)
        sanitized = MID_DOLLAR_REGEX.sub("[Standard Operational Expenditure Tier 2]", sanitized)

    # 5. Redact any explicit user forbidden terms
    if forbidden_terms:
        for term in forbidden_terms:
            if term:
                pat = rf"\b{re.escape(term)}\b" if term.isalnum() else re.escape(term)
                sanitized = re.sub(pat, "[REDACTED]", sanitized, flags=re.IGNORECASE)

    return sanitized.strip()
