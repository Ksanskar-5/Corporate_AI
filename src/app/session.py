"""
session.py - Application Session & Current User State Management
Tracks the currently authenticated user, clearance levels, and role permissions.
"""

class UserSession:
    """Singleton session container tracking logged-in user credentials and privileges."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(UserSession, cls).__new__(cls)
            cls._instance.user = None
        return cls._instance

    def login(self, user_dict: dict):
        """Sets the active user session."""
        self.user = user_dict

    def logout(self):
        """Clears the active session."""
        self.user = None

    @property
    def is_authenticated(self) -> bool:
        return self.user is not None

    @property
    def username(self) -> str:
        return self.user.get("username", "guest") if self.user else "guest"

    @property
    def full_name(self) -> str:
        return self.user.get("full_name", "Guest User") if self.user else "Guest User"

    @property
    def role(self) -> str:
        return self.user.get("role", "Employee") if self.user else "Employee"

    @property
    def department(self) -> str:
        return self.user.get("department", "Corporate Operations") if self.user else "Corporate Operations"

    @property
    def clearance_description(self) -> str:
        """Returns readable clearance privileges based on user role."""
        if self.role == "Admin":
            return "Clearance: RESTRICTED (Full C-Suite Access)"
        if self.role == "Analyst":
            return "Clearance: AUDIT & CONFIDENTIAL (Global Analytics)"
        if self.role == "Manager":
            return "Clearance: CONFIDENTIAL (Departmental Scope)"
        return "Clearance: INTERNAL (Standard Operations)"

    @property
    def can_access_pipeline(self) -> bool:
        """Managers, Analysts, and Admins can trigger data ingestion and synthesis."""
        return self.role in ["Admin", "Manager", "Analyst"]

    @property
    def can_upload(self) -> bool:
        """Only Admins and Managers may add files (mirrors WRITE_ROLES)."""
        return self.role in ["Admin", "Manager"]


# Global session instance
session = UserSession()
