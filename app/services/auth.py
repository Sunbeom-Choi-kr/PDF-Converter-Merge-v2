from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Header, HTTPException, Request


@dataclass
class AuthUser:
    user_id: str
    email: str | None
    role: str | None
    is_admin: bool


_JWKS_CACHE: dict[str, Any] = {"keys": {}, "fetched_at": 0.0}
_JWKS_LOCK = threading.Lock()
_JWKS_TTL_SECONDS = 300


def get_public_auth_config() -> dict[str, Any]:
    supabase_url = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    supabase_anon_key = (os.getenv("SUPABASE_ANON_KEY") or "").strip()
    return {
        "enabled": bool(supabase_url and supabase_anon_key),
        "supabase_url": supabase_url,
        "supabase_anon_key": supabase_anon_key,
    }


def _issuer() -> str:
    supabase_url = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    if not supabase_url:
        raise HTTPException(status_code=500, detail="SUPABASE_URL is not configured")
    return f"{supabase_url}/auth/v1"


def _audience() -> str:
    return (os.getenv("SUPABASE_JWT_AUDIENCE") or "authenticated").strip()


def _jwks_url() -> str:
    return f"{_issuer()}/.well-known/jwks.json"


def _fetch_jwks() -> dict[str, Any]:
    with urllib.request.urlopen(_jwks_url(), timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_cached_jwks() -> dict[str, Any]:
    now = time.time()
    with _JWKS_LOCK:
        if _JWKS_CACHE["keys"] and now - _JWKS_CACHE["fetched_at"] < _JWKS_TTL_SECONDS:
            return _JWKS_CACHE["keys"]
        fresh = _fetch_jwks()
        _JWKS_CACHE["keys"] = fresh
        _JWKS_CACHE["fetched_at"] = now
        return fresh


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


def _decode_token(token: str) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(token)
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=401, detail=f"Invalid token header: {error}") from error

    kid = header.get("kid")
    if not kid:
        raise HTTPException(status_code=401, detail="Token is missing kid")

    jwks = _get_cached_jwks()
    keys = jwks.get("keys", [])
    jwk = next((k for k in keys if k.get("kid") == kid), None)
    if not jwk:
        raise HTTPException(status_code=401, detail="No matching JWKS key for token")

    public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
    try:
        payload = jwt.decode(
            token,
            key=public_key,
            algorithms=["RS256"],
            audience=_audience(),
            issuer=_issuer(),
        )
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=401, detail=f"Invalid token: {error}") from error
    return payload


def _payload_to_user(payload: dict[str, Any]) -> AuthUser:
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token subject is missing")
    email = payload.get("email")
    return AuthUser(
        user_id=user_id,
        email=email,
        role=payload.get("role"),
        is_admin=(email or "").strip().lower() == "admin@admin",
    )


def get_current_user(authorization: str | None = Header(default=None)) -> AuthUser:
    token = _extract_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return _payload_to_user(_decode_token(token))


def get_current_user_or_query_token(
    request: Request,
    authorization: str | None = Header(default=None),
) -> AuthUser:
    token = _extract_bearer_token(authorization) or request.query_params.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Missing access token")
    return _payload_to_user(_decode_token(token))
