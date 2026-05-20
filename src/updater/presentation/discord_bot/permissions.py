from __future__ import annotations

from typing import Any


def has_admin_role(member: Any, *, admin_role_id: int) -> bool:
    roles = getattr(member, "roles", None)
    if not roles:
        return False
    return any(getattr(role, "id", None) == admin_role_id for role in roles)
