"""Shared audit-trail helper.

Every state-changing endpoint records one row here, so the audit log covers
project edits, outcome entry, alert workflow, model activation and integration
keys, not only account administration.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog, User


def record(
    db: Session,
    actor: User | None,
    action: str,
    target_type: str,
    target_id: Any,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    """Stage one audit row. The caller commits it with its own transaction."""
    entry = AuditLog(
        actor_id=actor.id if actor is not None else None,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        details=details or {},
    )
    db.add(entry)
    return entry


def changed_fields(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Return a compact before/after diff suitable for the audit details column."""
    diff: dict[str, Any] = {}
    for key, new_value in after.items():
        old_value = before.get(key)
        if str(old_value) != str(new_value):
            diff[key] = {"from": _plain(old_value), "to": _plain(new_value)}
    return diff


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
