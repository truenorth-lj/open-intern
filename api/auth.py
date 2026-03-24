"""Authentication — JWT-based auth for admin and user accounts."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.config import AppConfig
from core.database import get_session_factory
from core.exceptions import ConfigurationError
from memory.store import ApiKeyRecord, UserAgentAccess, UserRecord

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dashboard/auth", tags=["auth"])

_session_factory = None

# JWT settings (populated by init_auth)
JWT_SECRET = ""
JWT_EXPIRY_SECONDS = 60 * 60 * 24 * 7  # 7 days

# Admin credentials (populated by init_auth)
_admin_email = "admin@open-intern.local"
_admin_password_hash = ""  # PBKDF2 hash, never store plain-text


def init_auth(config: AppConfig) -> None:
    """Initialize auth with AppConfig (reads .env via pydantic-settings)."""
    global _session_factory, JWT_SECRET, _admin_email, _admin_password_hash
    _session_factory = get_session_factory(config.database_url)
    JWT_SECRET = config.auth_secret
    _admin_email = config.admin_email
    # Hash the admin password at init time so we never compare plain-text
    if config.dashboard_password:
        _admin_password_hash = _hash_password(config.dashboard_password)
    else:
        _admin_password_hash = ""
    if not JWT_SECRET:
        logger.warning(
            "AUTH_SECRET not set — authentication will fail. "
            "Set AUTH_SECRET environment variable before using the dashboard."
        )
    if not config.dashboard_password:
        logger.warning("DASHBOARD_PASSWORD not configured; admin login disabled")


def _get_session() -> Session:
    if _session_factory is None:
        raise ConfigurationError("Auth not initialized — call init_auth() first")
    return _session_factory()


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations=600_000)
    return f"{salt.hex()}:{h.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    if ":" not in stored:
        return False
    salt_hex, h_hex = stored.split(":", 1)
    salt = bytes.fromhex(salt_hex)
    expected = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations=600_000)
    return hmac.compare_digest(expected.hex(), h_hex)


def _generate_password() -> str:
    return secrets.token_urlsafe(12)


# Simple JWT implementation (no external dependency)
def _create_jwt(payload: dict) -> str:
    if not JWT_SECRET:
        raise RuntimeError("AUTH_SECRET not set")
    header = urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).rstrip(b"=")
    payload_bytes = urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=")
    message = header + b"." + payload_bytes
    sig = hmac.new(JWT_SECRET.encode(), message, hashlib.sha256).digest()
    sig_b64 = urlsafe_b64encode(sig).rstrip(b"=")
    return (message + b"." + sig_b64).decode()


def _decode_jwt(token: str) -> dict | None:
    if not JWT_SECRET:
        return None
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        message = (parts[0] + "." + parts[1]).encode()
        sig = urlsafe_b64decode(parts[2] + "==")
        expected = hmac.new(JWT_SECRET.encode(), message, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload_json = urlsafe_b64decode(parts[1] + "==")
        payload = json.loads(payload_json)
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def _hash_api_key(raw_key: str) -> str:
    """Hash an API key for storage/lookup using SHA-256."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _authenticate_api_key(raw_key: str) -> dict | None:
    """Validate an API key and return a user-like dict, or None."""
    key_hash = _hash_api_key(raw_key)
    with _get_session() as session:
        record = session.query(ApiKeyRecord).filter_by(key_hash=key_hash, is_active=True).first()
        if not record:
            return None
        # Check expiry
        if record.expires_at and record.expires_at < datetime.now(timezone.utc):
            return None
        # Update last_used_at
        record.last_used_at = datetime.now(timezone.utc)
        session.commit()
        return {
            "user_id": f"apikey:{record.id}",
            "email": f"apikey:{record.name or record.key_prefix}",
            "role": "apikey",
            "agent_id": record.agent_id,
            "api_key_id": record.id,
        }


def get_current_user(request: Request) -> dict:
    """Extract and validate user from JWT token, cookie, or X-API-Key header."""
    # 1. Check for API key auth
    api_key = request.headers.get("X-Agent-API-Key", "")
    if api_key:
        user = _authenticate_api_key(api_key)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid API key")
        return user

    # 2. Check JWT auth
    token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    if not token:
        token = request.cookies.get("oi_token", "")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = _decode_jwt(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# --- Auth endpoints ---


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user: dict


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest):
    # Check admin login (constant-time comparison for both email and password)
    is_admin = (
        secrets.compare_digest(body.email, _admin_email)
        and _admin_password_hash
        and _verify_password(body.password, _admin_password_hash)
    )
    if is_admin:
        payload = {
            "user_id": "admin",
            "email": _admin_email,
            "role": "admin",
            "exp": time.time() + JWT_EXPIRY_SECONDS,
        }
        token = _create_jwt(payload)
        return LoginResponse(
            token=token,
            user={"user_id": "admin", "email": _admin_email, "role": "admin"},
        )

    # Check user login
    with _get_session() as session:
        user = session.query(UserRecord).filter_by(email=body.email, is_active=True).first()
        if not user or not _verify_password(body.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        payload = {
            "user_id": user.id,
            "email": user.email,
            "role": user.role,
            "exp": time.time() + JWT_EXPIRY_SECONDS,
        }
        token = _create_jwt(payload)
        return LoginResponse(
            token=token,
            user={"user_id": user.id, "email": user.email, "role": user.role},
        )


@router.get("/me")
def get_me(user: dict = Depends(get_current_user)):
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "role": user["role"],
    }


# --- User management (admin only) ---


class UserCreate(BaseModel):
    email: str  # validated below
    role: str = "user"
    agent_ids: list[str] = []

    @staticmethod
    def _is_valid_email(v: str) -> bool:
        import re

        return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v))

    def model_post_init(self, __context: Any) -> None:
        if not self._is_valid_email(self.email):
            raise ValueError("Invalid email address")


class UserUpdate(BaseModel):
    email: str | None = None
    role: str | None = None
    is_active: bool | None = None


@router.get("/users")
def list_users(admin: dict = Depends(require_admin)):
    with _get_session() as session:
        users = session.query(UserRecord).order_by(UserRecord.created_at.desc()).all()
        result = []
        for u in users:
            agent_ids = [
                a.agent_id for a in session.query(UserAgentAccess).filter_by(user_id=u.id).all()
            ]
            result.append(
                {
                    "user_id": u.id,
                    "email": u.email,
                    "role": u.role,
                    "is_active": u.is_active,
                    "created_at": u.created_at.isoformat() if u.created_at else "",
                    "agent_ids": agent_ids,
                }
            )
        return {"users": result}


@router.post("/users")
def create_user(body: UserCreate, admin: dict = Depends(require_admin)):
    with _get_session() as session:
        existing = session.query(UserRecord).filter_by(email=body.email).first()
        if existing:
            raise HTTPException(status_code=409, detail="Email already exists")

        password = _generate_password()
        now = datetime.now(timezone.utc)
        user = UserRecord(
            id=str(uuid4()),
            email=body.email,
            password_hash=_hash_password(password),
            role=body.role,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add(user)

        # Set agent access
        for agent_id in body.agent_ids:
            session.add(UserAgentAccess(user_id=user.id, agent_id=agent_id))

        session.commit()
        return {
            "user_id": user.id,
            "email": user.email,
            "role": user.role,
            "password": password,  # shown once to admin
            "agent_ids": body.agent_ids,
        }


@router.put("/users/{user_id}")
def update_user(user_id: str, body: UserUpdate, admin: dict = Depends(require_admin)):
    with _get_session() as session:
        user = session.query(UserRecord).filter_by(id=user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if body.email is not None:
            dup = session.query(UserRecord).filter_by(email=body.email).first()
            if dup and dup.id != user_id:
                raise HTTPException(status_code=409, detail="Email already in use")
            user.email = body.email
        if body.role is not None:
            user.role = body.role
        if body.is_active is not None:
            user.is_active = body.is_active
        user.updated_at = datetime.now(timezone.utc)
        session.commit()
        return {"ok": True, "user_id": user_id}


@router.delete("/users/{user_id}")
def delete_user(user_id: str, admin: dict = Depends(require_admin)):
    with _get_session() as session:
        user = session.query(UserRecord).filter_by(id=user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.is_active = False
        user.updated_at = datetime.now(timezone.utc)
        session.commit()
        return {"ok": True}


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: str, admin: dict = Depends(require_admin)):
    with _get_session() as session:
        user = session.query(UserRecord).filter_by(id=user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        password = _generate_password()
        user.password_hash = _hash_password(password)
        user.updated_at = datetime.now(timezone.utc)
        session.commit()
        return {"ok": True, "password": password}  # shown once to admin


@router.get("/users/{user_id}/agents")
def get_user_agents(user_id: str, admin: dict = Depends(require_admin)):
    with _get_session() as session:
        agent_ids = [
            a.agent_id for a in session.query(UserAgentAccess).filter_by(user_id=user_id).all()
        ]
        return {"agent_ids": agent_ids}


class AgentAccessUpdate(BaseModel):
    agent_ids: list[str]


@router.put("/users/{user_id}/agents")
def set_user_agents(user_id: str, body: AgentAccessUpdate, admin: dict = Depends(require_admin)):
    with _get_session() as session:
        user = session.query(UserRecord).filter_by(id=user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        # Clear existing
        session.query(UserAgentAccess).filter_by(user_id=user_id).delete()
        # Set new
        for agent_id in body.agent_ids:
            session.add(UserAgentAccess(user_id=user_id, agent_id=agent_id))
        session.commit()
        return {"ok": True, "agent_ids": body.agent_ids}


def get_user_accessible_agents(user: dict) -> list[str] | None:
    """Return list of agent_ids the user can access, or None if admin (all access)."""
    if user.get("role") == "admin":
        return None  # admin sees everything
    if user.get("role") == "apikey":
        # API keys are scoped to a single agent
        return [user["agent_id"]]
    user_id = user.get("user_id", "")
    with _get_session() as session:
        return [a.agent_id for a in session.query(UserAgentAccess).filter_by(user_id=user_id).all()]


# --- API Key Management (admin only) ---


class ApiKeyCreate(BaseModel):
    name: str = ""
    expires_in_days: int | None = None  # None = never expires


@router.post("/agents/{agent_id}/api-keys")
def create_api_key(agent_id: str, body: ApiKeyCreate, admin: dict = Depends(require_admin)):
    """Create a new API key scoped to a specific agent. Returns the raw key once."""
    from memory.store import AgentRecord

    # Verify agent exists
    with _get_session() as session:
        agent = session.query(AgentRecord).filter_by(agent_id=agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    raw_key = f"oi_{secrets.token_urlsafe(32)}"
    key_hash = _hash_api_key(raw_key)
    key_prefix = raw_key[:11]  # "oi_" + first 8 chars
    now = datetime.now(timezone.utc)

    expires_at = None
    if body.expires_in_days is not None:
        expires_at = now + timedelta(days=body.expires_in_days)

    record_id = str(uuid4())
    record = ApiKeyRecord(
        id=record_id,
        key_prefix=key_prefix,
        key_hash=key_hash,
        agent_id=agent_id,
        name=body.name,
        created_by=admin.get("user_id", ""),
        is_active=True,
        expires_at=expires_at,
        created_at=now,
    )
    try:
        with _get_session() as session:
            session.add(record)
            session.commit()
    except Exception as e:
        logger.error("Failed to create API key for agent %s: %s", agent_id, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to create API key. "
            "Ensure the database migration has been run (alembic upgrade head).",
        )
    logger.info("API key created for agent %s by %s", agent_id, admin.get("user_id", ""))

    return {
        "id": record_id,
        "key": raw_key,  # shown once
        "key_prefix": key_prefix,
        "agent_id": agent_id,
        "name": body.name,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "created_at": now.isoformat(),
    }


@router.get("/agents/{agent_id}/api-keys")
def list_api_keys(agent_id: str, user: dict = Depends(get_current_user)):
    """List API keys for an agent (key values are never shown)."""
    # Allow admin or users with access to this agent
    accessible = get_user_accessible_agents(user)
    if accessible is not None and agent_id not in accessible:
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        session = _get_session()
    except Exception:
        return {"api_keys": []}
    with session:
        try:
            records = (
                session.query(ApiKeyRecord)
                .filter_by(agent_id=agent_id)
                .order_by(ApiKeyRecord.created_at.desc())
                .all()
            )
        except Exception:
            return {"api_keys": []}
        return {
            "api_keys": [
                {
                    "id": r.id,
                    "key_prefix": r.key_prefix,
                    "agent_id": r.agent_id,
                    "name": r.name,
                    "created_by": r.created_by,
                    "is_active": r.is_active,
                    "expires_at": (
                        r.expires_at.isoformat() if getattr(r, "expires_at", None) else None
                    ),
                    "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
                    "created_at": r.created_at.isoformat() if r.created_at else "",
                }
                for r in records
            ]
        }


@router.delete("/agents/{agent_id}/api-keys/{key_id}")
def revoke_api_key(agent_id: str, key_id: str, admin: dict = Depends(require_admin)):
    """Revoke (deactivate) an API key."""
    with _get_session() as session:
        record = session.query(ApiKeyRecord).filter_by(id=key_id, agent_id=agent_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="API key not found")
        record.is_active = False
        session.commit()
    logger.info("API key %s revoked for agent %s by %s", key_id, agent_id, admin.get("user_id", ""))
    return {"ok": True, "id": key_id, "is_active": False}
