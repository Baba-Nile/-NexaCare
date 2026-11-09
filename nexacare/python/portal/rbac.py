"""Roles and permissions. Enforcement is server-side only; hiding a link is never treated as protection."""
from functools import wraps
from urllib.parse import quote
from flask import abort, g, redirect, request, url_for
from .audit import audit

ROLE_PERMS = {
    # System administrators run the platform; they have NO access to patient or clinical records.
    "system_admin": {"staff.manage", "audit.read"},
    "hospital_admin": {"staff.manage", "audit.read", "patients.read", "patients.write", "portal.manage", "appointments.manage", "visits.manage", "careplans.read", "billing.read", "enquiries.read"},
    "receptionist": {"patients.read", "patients.write", "portal.manage", "appointments.manage", "enquiries.read"},
    "homecare_coordinator": {"patients.read", "visits.manage", "careplans.read", "careplans.write", "enquiries.read"},
    "nurse": {"patients.read", "careplans.read", "careplans.write", "clinical.read", "clinical.write", "visits.own", "appointments.view"},
    "doctor": {"patients.read", "careplans.read", "careplans.write", "clinical.read", "clinical.write", "meds.order", "appointments.view"},
    "caregiver": {"visits.own"},
    "billing_clerk": {"patients.read", "billing.read", "billing.write"},
}
ROLE_LABELS = {"system_admin": "System administrator", "hospital_admin": "Hospital administrator", "receptionist": "Receptionist", "homecare_coordinator": "Homecare coordinator",
               "nurse": "Nurse", "doctor": "Doctor", "caregiver": "Homecare caregiver", "billing_clerk": "Billing clerk"}
# Which roles each admin may create or modify (hospital admins cannot create administrators).
ASSIGNABLE = {"system_admin": set(ROLE_PERMS), "hospital_admin": set(ROLE_PERMS) - {"system_admin", "hospital_admin"}}

def can(perm): return bool(getattr(g, "staff", None)) and perm in ROLE_PERMS.get(g.staff["role"], set())

def staff_required(*perms):
    """Require a logged-in, active staff member holding ALL listed permissions."""
    def deco(f):
        @wraps(f)
        def wrapper(*a, **k):
            if not g.staff: return redirect(url_for("staff.login", next=request.path))
            if g.staff["must_change_password"] and request.endpoint not in ("staff.password", "staff.logout"): return redirect(url_for("staff.password"))
            missing = [p for p in perms if not can(p)]
            if missing:
                audit("access.denied", detail={"path": request.path, "needs": missing}, outcome="denied"); abort(403)
            return f(*a, **k)
        return wrapper
    return deco

def account_required(f):
    @wraps(f)
    def wrapper(*a, **k):
        if not g.account: return redirect(url_for("patient.login"))
        return f(*a, **k)
    return wrapper
