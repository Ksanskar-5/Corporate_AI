"""Focused regression tests: upload permission gating and account names.

Run with:  .venv/bin/python tests/test_rbac_upload.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.app.session import UserSession
from src.app.auth_db import PRESEEDED_ACCOUNTS, WRITE_ROLES
from src.agent.vector_store import effective_source_scope

EXPECTED_NAMES = {
    "employee": "Aarav Sharma",
    "analyst": "Ananya Iyer",
    "manager": "Rohan Verma",
    "admin": "Aditya Rao",
}


def _role_can_upload(role: str) -> bool:
    s = UserSession()
    try:
        s.login({"username": "probe", "full_name": "Probe", "role": role, "department": "Ops"})
        return s.can_upload
    finally:
        s.logout()


def test_upload_restricted_to_writers():
    assert WRITE_ROLES == {"Admin", "Manager"}
    assert _role_can_upload("Admin") is True
    assert _role_can_upload("Manager") is True
    assert _role_can_upload("Analyst") is False
    assert _role_can_upload("Employee") is False


def test_pipeline_view_stays_open_for_analyst():
    s = UserSession()
    try:
        s.login({"username": "probe", "full_name": "Probe", "role": "Analyst", "department": "Ops"})
        assert s.can_access_pipeline is True
        assert s.can_upload is False
    finally:
        s.logout()


def test_only_admin_sees_vault_data():
    assert effective_source_scope("Admin", "all") == "all"
    assert effective_source_scope("Admin", "vault") == "vault"
    assert effective_source_scope("Admin", "synthetic") == "synthetic"
    for role in ("Employee", "Analyst", "Manager"):
        for requested in ("all", "synthetic", "vault"):
            assert effective_source_scope(role, requested) == "synthetic", (role, requested)
    assert effective_source_scope("Intruder", "vault") == "synthetic"


def test_preseeded_accounts_use_indian_names():
    assert len(PRESEEDED_ACCOUNTS) == 4
    for acc in PRESEEDED_ACCOUNTS:
        assert acc["full_name"] == EXPECTED_NAMES[acc["username"]], acc


if __name__ == "__main__":
    test_upload_restricted_to_writers()
    test_pipeline_view_stays_open_for_analyst()
    test_only_admin_sees_vault_data()
    test_preseeded_accounts_use_indian_names()
    print("All RBAC upload tests passed.")
