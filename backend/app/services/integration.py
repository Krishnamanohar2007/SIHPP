"""API-key service accounts for integrating external land-acquisition systems.

Government land-record systems cannot log in interactively, so integration uses a
long-lived key presented in the ``X-API-Key`` header. Keys are shown once at
creation and stored only as a bcrypt hash, with a searchable non-secret prefix.
Every key carries explicit scopes plus optional state/district limits that are
applied to queries the same way a user's role scope is.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

import bcrypt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ApiClient, Project


KEY_PREFIX_LENGTH = 12
SCOPES = {
    "projects.read": "Read projects and predictions",
    "projects.write": "Create or update projects",
    "analytics.read": "Read portfolio analytics",
    "alerts.read": "Read risk alerts",
}


def generate_key() -> tuple[str, str, str]:
    """Return (full key shown once, stored prefix, bcrypt hash)."""
    secret = secrets.token_urlsafe(32)
    prefix = f"lar_{secrets.token_hex(4)}"
    full = f"{prefix}.{secret}"
    digest = bcrypt.hashpw(secret.encode(), bcrypt.gensalt()).decode()
    return full, prefix, digest


def verify_key(candidate: str, digest: str) -> bool:
    try:
        return bcrypt.checkpw(candidate.encode(), digest.encode())
    except ValueError:
        return False


def resolve_client(api_key: str, db: Session) -> ApiClient:
    """Look a key up by its prefix, then verify the secret half."""
    if "." not in api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Malformed API key")
    prefix, secret = api_key.split(".", 1)
    client = db.scalar(select(ApiClient).where(ApiClient.key_prefix == prefix))
    if client is None or client.status != "ACTIVE" or not verify_key(secret, client.key_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
    client.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return client


def current_client(x_api_key: str = Header(..., alias="X-API-Key"), db: Session = Depends(get_db)) -> ApiClient:
    return resolve_client(x_api_key, db)


def require_scope(scope: str):
    """Dependency factory enforcing one scope on an integration endpoint."""

    def guard(client: ApiClient = Depends(current_client)) -> ApiClient:
        if scope not in (client.scopes or []):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"API key is missing scope '{scope}'")
        return client

    return guard


def scoped_for_client(statement: Select, client: ApiClient) -> Select:
    """Apply the key's geographic limits, mirroring the user role scoping."""
    if client.state:
        statement = statement.where(Project.state == client.state)
    if client.district:
        statement = statement.where(Project.district == client.district)
    return statement
