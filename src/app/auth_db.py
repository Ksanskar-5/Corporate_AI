"""
auth_db.py - SQLite Authentication & Role-Based Access Control (RBAC) User Store
Manages user accounts, salted password hashes, departments, and pre-seeded test accounts.

Roles (general corporate hierarchy):
  Admin    - Full system access: assistant, database (view/edit/delete), file upload
  Manager  - Department access: assistant, database (view + upload new files)
  Analyst  - Read-only data access: assistant, database view only
  Employee - Basic: assistant only
"""

import os
import sqlite3
import hashlib
import secrets

DEFAULT_AUTH_DB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data",
    "app_auth.db",
)

# Ordered: least → most privileged
SUPPORTED_ROLES = [
    "Employee",
    "Analyst",
    "Manager",
    "Admin",
]

# DB-access roles (can see the Database view)
DB_ACCESS_ROLES = {"Admin", "Manager", "Analyst", "Employee"}

# Write-access roles (can upload files)
WRITE_ROLES = {"Admin", "Manager"}

# Full-control roles (can edit and delete records)
ADMIN_ROLES = {"Admin"}

PRESEEDED_ACCOUNTS = [
    {
        "username": "employee",
        "password": "pass123",
        "full_name": "Aarav Sharma",
        "role": "Employee",
        "department": "Operations",
    },
    {
        "username": "analyst",
        "password": "pass123",
        "full_name": "Ananya Iyer",
        "role": "Analyst",
        "department": "Finance",
    },
    {
        "username": "manager",
        "password": "pass123",
        "full_name": "Rohan Verma",
        "role": "Manager",
        "department": "Sales",
    },
    {
        "username": "admin",
        "password": "pass123",
        "full_name": "Aditya Rao",
        "role": "Admin",
        "department": "Executive",
    },
]


def _hash_password(password: str, salt: str = None) -> tuple[str, str]:
    """Generates a secure SHA-256 salted hash."""
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return hashed, salt


def get_auth_connection(db_path: str = DEFAULT_AUTH_DB) -> sqlite3.Connection:
    """Connects to the SQLite auth DB and initializes the users table."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL,
            department TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    return conn


def init_auth_db(db_path: str = DEFAULT_AUTH_DB):
    """Ensures database is initialized and seeds default accounts if missing."""
    conn = get_auth_connection(db_path)
    try:
        cur = conn.cursor()
        for acc in PRESEEDED_ACCOUNTS:
            cur.execute("SELECT id FROM users WHERE username = ?;", (acc["username"],))
            if not cur.fetchone():
                pwd_hash, salt = _hash_password(acc["password"])
                cur.execute("""
                    INSERT INTO users (username, password_hash, salt, full_name, role, department)
                    VALUES (?, ?, ?, ?, ?, ?);
                """, (
                    acc["username"],
                    pwd_hash,
                    salt,
                    acc["full_name"],
                    acc["role"],
                    acc["department"],
                ))
        conn.commit()
    finally:
        conn.close()


def authenticate_user(username: str, password: str, db_path: str = DEFAULT_AUTH_DB) -> dict | None:
    """Verifies credentials and returns user dict if valid, else None."""
    init_auth_db(db_path)
    conn = get_auth_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = ?;", (username.strip().lower(),))
        row = cur.fetchone()
        if not row:
            return None
        expected_hash, _ = _hash_password(password, row["salt"])
        if expected_hash == row["password_hash"]:
            return {
                "id": row["id"],
                "username": row["username"],
                "full_name": row["full_name"],
                "role": row["role"],
                "department": row["department"],
            }
        return None
    finally:
        conn.close()


def register_user(
    username: str,
    password: str,
    full_name: str,
    role: str = "Employee",
    department: str = "Operations",
    db_path: str = DEFAULT_AUTH_DB,
) -> tuple[bool, str]:
    """Registers a new user into the SQLite store."""
    if role not in SUPPORTED_ROLES:
        return False, f"Invalid role: {role}"
    if len(password) < 4:
        return False, "Password must be at least 4 characters long."

    init_auth_db(db_path)
    conn = get_auth_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username = ?;", (username.strip().lower(),))
        if cur.fetchone():
            return False, "Username already exists."
        pwd_hash, salt = _hash_password(password)
        cur.execute("""
            INSERT INTO users (username, password_hash, salt, full_name, role, department)
            VALUES (?, ?, ?, ?, ?, ?);
        """, (username.strip().lower(), pwd_hash, salt, full_name.strip(), role, department.strip()))
        conn.commit()
        return True, "User registered successfully."
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()


def get_all_users(db_path: str = DEFAULT_AUTH_DB) -> list[dict]:
    """Returns all users list (without credentials)."""
    init_auth_db(db_path)
    conn = get_auth_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, username, full_name, role, department, created_at FROM users ORDER BY id;")
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
