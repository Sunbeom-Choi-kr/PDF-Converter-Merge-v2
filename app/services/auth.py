from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from fastapi import Header, HTTPException, Request

from app.services.env_config import get_env


@dataclass
class AuthUser:
    user_id: str
    email: str | None
    role: str | None
    is_admin: bool

def _admin_emails() -> set[str]:
    raw = get_env("ADMIN_EMAILS")
    return {email.strip().lower() for email in raw.split(",") if email.strip()}


def get_public_auth_config() -> dict[str, Any]:
    supabase_url = get_env("SUPABASE_URL").rstrip("/")
    supabase_anon_key = get_env("SUPABASE_ANON_KEY")
    return {
        "enabled": bool(supabase_url and supabase_anon_key),
        "supabase_url": supabase_url,
        "supabase_anon_key": supabase_anon_key,
    }


def _issuer() -> str:
    supabase_url = get_env("SUPABASE_URL").rstrip("/")
    if not supabase_url:
        raise HTTPException(status_code=500, detail="SUPABASE_URL is not configured")
    return f"{supabase_url}/auth/v1"


def _audience() -> str:
    return get_env("SUPABASE_JWT_AUDIENCE") or "authenticated"


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2:
        return None
    scheme, token = parts
    if scheme.lower() != "bearer":
        return None
    return token.strip() or None


def _fetch_supabase_user(token: str) -> dict[str, Any]:
    supabase_anon_key = get_env("SUPABASE_ANON_KEY")
    if not supabase_anon_key:
        raise HTTPException(status_code=500, detail="SUPABASE_ANON_KEY is not configured")

    request = urllib.request.Request(
        url=f"{_issuer()}/user",
        headers={
            "Authorization": f"Bearer {token}",
            "apikey": supabase_anon_key,
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = "Invalid access token"
        try:
            payload = json.loads(error.read().decode("utf-8"))
            detail = payload.get("msg") or payload.get("error_description") or payload.get("error") or detail
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(status_code=401, detail=detail) from error
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Failed to validate token with Supabase: {error}") from error


def _payload_to_user(payload: dict[str, Any]) -> AuthUser:
    user_id = payload.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token subject is missing")
    email = payload.get("email")
    normalized_email = (email or "").strip().lower()
    return AuthUser(
        user_id=user_id,
        email=email,
        role=payload.get("role") or _audience(),
        is_admin=normalized_email in _admin_emails(),
    )


def get_current_user(authorization: str | None = Header(default=None)) -> AuthUser:
    token = _extract_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return _payload_to_user(_fetch_supabase_user(token))


def get_current_user_or_query_token(
    request: Request,
    authorization: str | None = Header(default=None),
) -> AuthUser:
    token = _extract_bearer_token(authorization) or request.query_params.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Missing access token")
    return _payload_to_user(_fetch_supabase_user(token))
