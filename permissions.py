"""What each person may do.

Every role comes with a default set of permissions; the MD can switch individual ones on or off
for a person. Steps in the approval chain (department head approval, MD PA routing, MD approval)
stay tied to roles, so the chain itself cannot be skipped by a permission.
"""

import json

# Shown to the MD in this order.
CAPABILITIES = {
    "register_incoming": ("Register incoming letters", "Record letters received, with their scans."),
    "create_outgoing": ("Create outgoing letters", "Start letters to be sent."),
    "route_letters": ("Route letters to another department", "Send a new letter to a different department."),
    "assign_letters": ("Assign letters to staff", "Choose who handles a letter in their department."),
    "all_letters": ("Work on letters in every department", "See every letter, update status, respond and assign anywhere."),
    "edit_register_details": ("Correct locked letter details", "Fix details typed when a letter was registered."),
    "dispatch_letters": ("Dispatch letters and record delivery", "Mark approved letters as sent and delivered."),
    "sign_letters": ("Sign letters", "Upload a signature and be chosen to sign letters."),
    "view_reports": ("See reports", "Company-wide figures and overdue letters."),
    "manage_users": ("Manage users and departments", "Add users, reset passwords, add departments."),
}

ROLE_DEFAULTS = {
    "front_desk": {"register_incoming", "create_outgoing", "route_letters", "dispatch_letters"},
    "department_head": {"create_outgoing", "assign_letters", "sign_letters"},
    "team_member": {"create_outgoing"},
    "md_pa": {"create_outgoing", "route_letters", "assign_letters", "all_letters", "edit_register_details",
              "dispatch_letters", "view_reports", "manage_users"},
    "md": {"create_outgoing", "all_letters", "edit_register_details", "dispatch_letters", "sign_letters",
           "view_reports", "manage_users"},
}

# The MD always keeps these, so the company cannot be locked out of its own system.
MD_ALWAYS = {"manage_users", "all_letters"}


def overrides(user) -> dict:
    """The switches the MD has changed for this person: {capability: True/False}."""
    try:
        raw = json.loads(user["permissions"] or "{}")
    except (KeyError, IndexError, TypeError, ValueError):
        return {}
    return {key: bool(value) for key, value in raw.items() if key in CAPABILITIES}


def capabilities(user) -> set:
    granted = set(ROLE_DEFAULTS.get(user["role"], set()))
    for key, allowed in overrides(user).items():
        (granted.add if allowed else granted.discard)(key)
    if user["role"] == "md":
        granted |= MD_ALWAYS
    return granted


def can(user, capability: str) -> bool:
    return capability in capabilities(user)


def clean_overrides(role: str, requested: dict) -> str | None:
    """Store only the switches that differ from the role's defaults, as JSON (None when there are none)."""
    defaults = ROLE_DEFAULTS.get(role, set())
    changed = {
        key: bool(value) for key, value in (requested or {}).items()
        if key in CAPABILITIES and bool(value) != (key in defaults)
    }
    return json.dumps(changed, sort_keys=True) if changed else None
