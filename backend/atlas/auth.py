"""Verify Clerk session tokens and resolve the caller's workspace.

The web app sends the Clerk session token as `Authorization: Bearer <jwt>`.
We check its signature against Clerk's public keys, its issuer, expiry and
authorized party, then map the active Clerk organization to an Atlas
organization. A request without an active organization is refused: all data
belongs to a workspace.

For names and emails to appear in Atlas, add these claims to the Clerk
session token (Dashboard → Sessions → Customize session token):
    {"email": "{{user.primary_email_address}}", "name": "{{user.full_name}}", "org_name": "{{org.name}}"}
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import Request

from . import db
from .config import get_settings
from .errors import AtlasError

_jwks_client: jwt.PyJWKClient | None = None
_identity_cache: dict[tuple[str, str, str], tuple[float, "Identity"]] = {}
IDENTITY_TTL_SECONDS = 300


@dataclass(frozen=True)
class Identity:
    org_id: UUID
    user_id: UUID
    role: str


def _jwks() -> jwt.PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(get_settings().jwks_url, cache_keys=True, lifespan=3600)
    return _jwks_client


def verify_token(token: str) -> dict:
    settings = get_settings()
    try:
        key = _jwks().get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=settings.clerk_issuer.rstrip("/"),
            options={"require": ["exp", "iat", "sub", "iss"]},
            leeway=5,
        )
    except jwt.PyJWTError:
        raise AtlasError("unauthorized", status_code=401) from None
    azp = claims.get("azp")
    if azp is not None and azp not in settings.authorized_parties:
        raise AtlasError("unauthorized", status_code=401)
    return claims


def _org_claims(claims: dict) -> tuple[str | None, str | None, str]:
    """Supports Clerk session token v2 (`o` claim) and v1 (`org_*` claims)."""
    org = claims.get("o") or {}
    org_id = org.get("id") or claims.get("org_id")
    raw_role = str(org.get("rol") or claims.get("org_role") or "member")
    role = "admin" if raw_role.removeprefix("org:") == "admin" else "member"
    name = claims.get("org_name") or org.get("slg") or claims.get("org_slug") or org_id
    return org_id, name, role


def resolve_identity(claims: dict) -> Identity:
    clerk_user = claims["sub"]
    clerk_org, org_name, role = _org_claims(claims)
    if not clerk_org:
        raise AtlasError("no_workspace", status_code=403)

    cache_key = (clerk_org, clerk_user, role)
    cached = _identity_cache.get(cache_key)
    if cached and cached[0] > time.monotonic():
        return cached[1]

    with db.system() as conn:
        row = conn.execute(
            "SELECT org_id, user_id, role FROM ensure_identity(%s, %s, %s, %s, %s, %s)",
            (clerk_org, org_name, clerk_user, claims.get("email"), claims.get("name"), role),
        ).fetchone()
    identity = Identity(org_id=row["org_id"], user_id=row["user_id"], role=row["role"])
    _identity_cache[cache_key] = (time.monotonic() + IDENTITY_TTL_SECONDS, identity)
    return identity


def current_identity(request: Request) -> Identity:
    """FastAPI dependency for every tenant endpoint."""
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AtlasError("unauthorized", status_code=401)
    identity = resolve_identity(verify_token(token))
    request.state.org_id = str(identity.org_id)  # for request logs
    return identity
