"""
PLM Enterprise Authentication & Authorization
Supabase JWT verification + API key validation + RBAC
"""

import os
import hashlib
import secrets
import time
import requests as _requests
from datetime import datetime
from typing import Optional, Dict, Any, List
from fastapi import HTTPException, Header, Depends, Request
from jose import jwt, jwk, JWTError
import logging

from enterprise.db.db_client import get_supabase_client, SupabaseClient

logger = logging.getLogger(__name__)

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")

if not SUPABASE_JWT_SECRET:
    logger.warning("SUPABASE_JWT_SECRET not set — HS256 JWT fallback will be disabled. Set this for production use.")
if not SUPABASE_URL:
    logger.warning("SUPABASE_URL not set — JWKS-based JWT verification will be disabled.")

# ---------------------------------------------------------------------------
# JWKS cache for ES256 verification (refreshes every 60 minutes)
# ---------------------------------------------------------------------------
_jwks_cache: Optional[Dict[str, Any]] = None
_jwks_cache_time: float = 0.0
_JWKS_TTL_SECONDS = 3600  # 1 hour


def _fetch_jwks(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Fetch and cache the JWKS from Supabase for ES256 token verification.

    Cache expires after _JWKS_TTL_SECONDS. Passing force_refresh=True
    bypasses the cache (used when a kid lookup miss suggests key rotation).
    """
    global _jwks_cache, _jwks_cache_time

    now = time.monotonic()
    if (
        not force_refresh
        and _jwks_cache is not None
        and (now - _jwks_cache_time) < _JWKS_TTL_SECONDS
    ):
        return _jwks_cache.get("keys", [])

    if not SUPABASE_URL:
        return []

    try:
        resp = _requests.get(
            f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json", timeout=10
        )
        resp.raise_for_status()
        _jwks_cache = resp.json()
        _jwks_cache_time = now
        logger.info("Fetched JWKS from Supabase for ES256 verification")
        return _jwks_cache.get("keys", [])
    except Exception as exc:
        logger.warning(f"Failed to fetch JWKS: {exc}")
        return []


def _get_signing_key(token: str):
    """Extract the signing key for the token from JWKS or fall back to HS256 secret."""
    try:
        headers = jwt.get_unverified_header(token)
    except JWTError:
        if not SUPABASE_JWT_SECRET:
            raise HTTPException(status_code=401, detail="JWT verification unavailable: no secret configured")
        return SUPABASE_JWT_SECRET, ["HS256"]

    alg = headers.get("alg", "HS256")
    kid = headers.get("kid")

    if alg == "HS256":
        if not SUPABASE_JWT_SECRET:
            raise HTTPException(status_code=401, detail="HS256 JWT verification unavailable: SUPABASE_JWT_SECRET not configured")
        return SUPABASE_JWT_SECRET, ["HS256"]

    # ES256 — look up in JWKS
    jwks_keys = _fetch_jwks()
    for key_data in jwks_keys:
        if kid and key_data.get("kid") != kid:
            continue
        if key_data.get("alg") == alg:
            public_key = jwk.construct(key_data)
            return public_key, [alg]

    # kid not found — keys may have rotated. Force a refresh and retry once.
    jwks_keys = _fetch_jwks(force_refresh=True)
    for key_data in jwks_keys:
        if kid and key_data.get("kid") != kid:
            continue
        if key_data.get("alg") == alg:
            public_key = jwk.construct(key_data)
            return public_key, [alg]

    # Fallback: try HS256 anyway
    if SUPABASE_JWT_SECRET:
        logger.warning(f"No matching JWKS key for alg={alg} kid={kid}, trying HS256 fallback")
        return SUPABASE_JWT_SECRET, ["HS256"]

    raise HTTPException(status_code=401, detail=f"No matching signing key found for alg={alg} kid={kid}")


class AuthContext:
    """Holds authenticated user context"""

    def __init__(
        self,
        user_id: Optional[str] = None,
        org_id: Optional[str] = None,
        email: Optional[str] = None,
        role: str = "member",
        auth_method: str = "none",
    ):
        self.user_id = user_id
        self.org_id = org_id
        self.email = email
        self.role = role
        self.auth_method = auth_method

    @property
    def is_authenticated(self) -> bool:
        return self.user_id is not None or self.auth_method == "api_key"

    def require_role(self, *roles: str):
        if self.role not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Requires role: {', '.join(roles)}. Your role: {self.role}",
            )

    def require_org(self, org_id: str):
        if self.org_id != org_id:
            raise HTTPException(
                status_code=403, detail="Access denied: organization mismatch"
            )


async def get_db() -> SupabaseClient:
    """Dependency: get Supabase client"""
    return get_supabase_client(use_service_role=True)


async def verify_jwt_token(token: str) -> Dict[str, Any]:
    """Verify Supabase JWT token and return payload.

    Supports both HS256 (legacy) and ES256 (current Supabase) algorithms
    by auto-detecting the algorithm from the token header and using
    the appropriate key (JWKS for ES256, shared secret for HS256).
    """
    try:
        key, algorithms = _get_signing_key(token)
        payload = jwt.decode(
            token,
            key,
            algorithms=algorithms,
            audience="authenticated",
        )
        return payload
    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def validate_api_key_hash(api_key: str, db: SupabaseClient) -> Dict[str, Any]:
    """Validate API key against database"""
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    prefix = api_key[:8]

    try:
        response = (
            db.client.table("api_keys")
            .select("*, organizations(*)")
            .eq("key_hash", key_hash)
            .eq("prefix", prefix)
            .eq("status", "active")
            .execute()
        )

        if not response.data:
            raise HTTPException(status_code=401, detail="Invalid API key")

        key_data = response.data[0]

        # Update last_used_at
        db.client.table("api_keys").update(
            {"last_used_at": datetime.utcnow().isoformat()}
        ).eq("id", key_data["id"]).execute()

        return key_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API key validation error: {e}")
        raise HTTPException(status_code=500, detail="Authentication error")


async def get_auth_context(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
) -> AuthContext:
    """
    Main auth dependency. Supports:
    1. Supabase JWT (Authorization: Bearer <token>)
    2. API Key (X-API-Key: <key>)
    3. Unauthenticated (public routes only)
    """
    db = get_supabase_client(use_service_role=True)

    # Try JWT auth first
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        payload = await verify_jwt_token(token)

        user_id = payload.get("sub")
        email = payload.get("email")

        # Look up user in our users table
        try:
            user_response = (
                db.client.table("users")
                .select("*")
                .eq("id", user_id)
                .execute()
            )

            if user_response.data:
                user = user_response.data[0]
                return AuthContext(
                    user_id=user_id,
                    org_id=user.get("organization_id"),
                    email=email,
                    role=user.get("role", "member"),
                    auth_method="jwt",
                )
            else:
                # User authenticated via Supabase but not in our users table yet
                return AuthContext(
                    user_id=user_id,
                    email=email,
                    role="member",
                    auth_method="jwt",
                )
        except Exception as e:
            logger.error(f"User lookup failed: {e}")
            return AuthContext(
                user_id=user_id, email=email, role="member", auth_method="jwt"
            )

    # Try API key auth
    if x_api_key:
        key_data = await validate_api_key_hash(x_api_key, db)
        return AuthContext(
            org_id=key_data.get("organization_id"),
            role="member",
            auth_method="api_key",
        )

    # No auth provided
    return AuthContext()


def require_auth(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
    """Dependency that requires authentication"""
    if not auth.is_authenticated:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Provide Bearer token or X-API-Key header.",
        )
    return auth


def require_admin(auth: AuthContext = Depends(require_auth)) -> AuthContext:
    """Dependency that requires admin or owner role"""
    auth.require_role("admin", "owner")
    return auth


def require_owner(auth: AuthContext = Depends(require_auth)) -> AuthContext:
    """Dependency that requires owner role"""
    auth.require_role("owner")
    return auth


# API Key management
def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key. Returns (full_key, key_hash, prefix)"""
    raw_key = f"plm_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    prefix = raw_key[:8]
    return raw_key, key_hash, prefix


async def create_api_key(
    org_id: str, name: str, db: SupabaseClient
) -> Dict[str, Any]:
    """Create a new API key for an organization"""
    raw_key, key_hash, prefix = generate_api_key()

    response = (
        db.client.table("api_keys")
        .insert(
            {
                "organization_id": org_id,
                "name": name,
                "key_hash": key_hash,
                "prefix": prefix,
                "status": "active",
            }
        )
        .execute()
    )

    if not response.data:
        raise HTTPException(status_code=500, detail="Failed to create API key")

    key_record = response.data[0]
    return {
        "id": key_record["id"],
        "key": raw_key,  # Only returned once at creation
        "prefix": prefix,
        "name": name,
        "created_at": key_record["created_at"],
    }


async def revoke_api_key(key_id: str, org_id: str, db: SupabaseClient) -> bool:
    """Revoke an API key"""
    response = (
        db.client.table("api_keys")
        .update({"status": "revoked", "revoked_at": datetime.utcnow().isoformat()})
        .eq("id", key_id)
        .eq("organization_id", org_id)
        .execute()
    )
    return len(response.data) > 0
