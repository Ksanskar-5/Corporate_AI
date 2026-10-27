"""Focused regression tests: JSON profile parsing and grounded fallback synthesis.

Run with:  .venv/bin/python tests/test_zephyra_grounding.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ingestion.parsers import parse_json
from src.synthesis.engine import (
    _generate_fallback_records,
    _normalize_fidelity,
    FIDELITY_LEVELS,
)

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "raw", "zephyra_loopworks",
)
PROFILE_JSON = os.path.join(DATA_DIR, "zephyra_company_profile.json")
TICKETS_JSON = os.path.join(DATA_DIR, "zephyra_support_tickets.json")


def test_profile_body_contains_staff_facts():
    docs = parse_json(PROFILE_JSON)
    assert len(docs) == 1, f"expected 1 profile doc, got {len(docs)}"
    body = docs[0]["body_text"]
    assert len(body.split()) > 20, f"profile body too thin: {body!r}"
    assert "Meera Nair" in body, "staff name missing from profile body"
    assert "Launch Program Manager" in body, "staff role missing from profile body"


def test_ticket_body_and_type_unchanged():
    docs = parse_json(TICKETS_JSON)
    assert len(docs) == 8, f"expected 8 ticket docs, got {len(docs)}"
    assert docs[0]["data_type"] == "support_ticket"
    assert "pairing" in docs[0]["body_text"].lower()


def test_fallback_records_grounded_in_reference():
    ref = [{
        "doc_id": "test_1",
        "title": "LoopTag Orion B-114 antenna swap",
        "body_text": "Move the LoopTag within 2 metres of the router and retry pairing.",
        "data_type": "support_ticket",
        "attributes": {"resolution": "Free swap to lot B-115 unit."},
    }]
    recs = _generate_fallback_records(ref, "support_ticket", 1)
    assert len(recs) == 1
    content = recs[0]["content"]
    assert "2 metres" in content, f"reference fact missing: {content!r}"
    assert "B-115" in content, f"reference attribute fact missing: {content!r}"


def test_fidelity_levels_known_and_invalid_rejected():
    assert set(FIDELITY_LEVELS) == {"full", "balanced", "minimal"}
    assert _normalize_fidelity("Full") == "full"
    assert _normalize_fidelity(None) == "balanced"
    try:
        _normalize_fidelity("everything")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid fidelity accepted")


def test_full_keeps_more_than_minimal():
    ref = {
        "doc_id": "test_1",
        "title": "LoopTag Orion B-114 antenna swap",
        "body_text": (
            "Move the LoopTag within 2 metres of the router and retry pairing. "
            "If the app still shows Pairing timed out after 60 seconds on Android, "
            "offer a free B-115 replacement and file support ticket ZL-1041. "
            "Warehouse lot B-115 stock arrives October 5 for the October 15 launch."
        ),
        "data_type": "support_ticket",
        "department": "Corporate Operations",
        "attributes": {"resolution": "Free swap to lot B-115 unit.", "status": "Resolved", "ticket_id": "ZL-1041"},
    }
    full = _generate_fallback_records([ref], "support_ticket", 1, fidelity="full")[0]
    mini = _generate_fallback_records([ref], "support_ticket", 1, fidelity="minimal")[0]
    assert "ZL-1041" in full["content"], "full fidelity dropped the ticket id"
    assert "B-115" in full["content"]
    assert full["department"] == "Corporate Operations", "full fidelity must keep department"
    assert len(full["content"]) > len(mini["content"]), "full must keep more than minimal"
    assert "October 15" in full["content"], "full fidelity dropped a late-body fact"
    assert "October 15" not in mini["content"], "minimal fidelity kept more than a short summary"


def test_vector_details_render_resolution_skip_noise():
    from src.agent.vector_store import _render_attribute_details
    details = _render_attribute_details({
        "resolution": "Free swap to lot B-115 unit.",
        "Message-ID": "<abc123>",
    })
    assert "Free swap to lot B-115 unit." in details
    assert "Message-ID" not in details


if __name__ == "__main__":
    test_profile_body_contains_staff_facts()
    test_ticket_body_and_type_unchanged()
    test_fallback_records_grounded_in_reference()
    test_vector_details_render_resolution_skip_noise()
    test_fidelity_levels_known_and_invalid_rejected()
    test_full_keeps_more_than_minimal()
    print("All grounding regression tests passed.")
