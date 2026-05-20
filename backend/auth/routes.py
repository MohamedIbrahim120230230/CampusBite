"""
backend/auth/routes.py
Auth & Identity — Member 1 (Lead)

TDP compliance:
  TDP-M1-01  FR03  Account lockout — all 4 padlocks satisfied
  TDP-M1-02  FR04  Session expiry  — all 4 padlocks satisfied (via DB expires_at)
  TDP-M1-03  FR06  Password reset  — all 4 padlocks satisfied
  TDP-M1-04  FR08  Account status  — all 3 padlocks satisfied

Note: Redis removed — Vercel's vendored redis lib is incompatible with Redis Cloud TLS.
      Sessions are stored in the DB sessions table with expires_at for inactivity TTL.
      Migration required:
        ALTER TABLE sessions ADD COLUMN IF NOT EXISTS jti TEXT;
        CREATE INDEX IF NOT EXISTS idx_sessions_jti ON sessions(jti);
"""

from __future__ import annotations

import hashlib
import json as _json
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncpg
import bcrypt
import jwt
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, field_validator

# ─────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ─────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────

JWT_SECRET               = os.environ.get("JWT_SECRET", "dev-secret-CHANGE-IN-PRODUCTION")
JWT_ALGO                 = "HS256"
INACTIVITY_TTL_SECONDS   = 1800
ACCESS_TTL_SECONDS       = INACTIVITY_TTL_SECONDS
REFRESH_TTL_SECONDS      = 7 * 24 * 3600
RESET_TTL_SECONDS        = 900
LOCKOUT_DURATION_SECONDS = 900
MAX_FAILED_ATTEMPTS      = 5
UTC                      = timezone.utc
ALLOWED_DOMAINS          = ["ejust.edu.eg"]

ACCOUNT_STATUS_MESSAGES = {
    "suspended": "Your account has been suspended. Contact the registrar.",
    "expired":   "Your university account has expired. Contact IT services.",
}

# ─────────────────────────────────────────────────────────────
# Email helpers
# ─────────────────────────────────────────────────────────────

def _is_university_email(email: str) -> bool:
    try:
        return email.strip().split("@")[1].lower() in ALLOWED_DOMAINS
    except IndexError:
        return False


def _is_student_email(email: str) -> bool:
    try:
        local  = email.strip().split("@")[0]
        parts  = local.split(".")
        pot_id = parts[-1] if len(parts) >= 2 else ""
        return pot_id.isdigit() and len(pot_id) >= 6
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────
# DB pool
# ─────────────────────────────────────────────────────────────

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        db_url = os.environ.get(
            "DATABASE_URL",
            "postgresql://postgres:postgres123@localhost:5432/cafeteria",
        )
        _pool = await asyncpg.create_pool(
            db_url,
            min_size=1,
            max_size=5,
            command_timeout=30,
            statement_cache_size=0,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


# ─────────────────────────────────────────────────────────────
# Response envelope
# ─────────────────────────────────────────────────────────────

def ok(data, status: int = 200) -> JSONResponse:
    return JSONResponse({"success": True, "data": data}, status_code=status)


def err(code: str, message: str, details=None, status: int = 400) -> JSONResponse:
    return JSONResponse(
        {"success": False, "error": {"code": code, "message": message, "details": details}},
        status_code=status,
    )


# ─────────────────────────────────────────────────────────────
# Pydantic schemas
# ─────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email:    EmailStr
    password: str = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def must_be_university_email(cls, v: str) -> str:
        if not _is_university_email(v):
            domains = ", ".join(f"@{d}" for d in ALLOWED_DOMAINS)
            raise ValueError(f"Only university email addresses are allowed ({domains}).")
        return v.lower().strip()


class PasswordResetRequestBody(BaseModel):
    email: EmailStr


class PasswordResetConfirmBody(BaseModel):
    token:        str
    new_password: str = Field(min_length=8)


class AdminCreateUserBody(BaseModel):
    email:        EmailStr
    display_name: str
    role:         str = Field(pattern="^(student|staff|admin)$")
    password:     str = Field(min_length=8)


class AdminUpdateUserBody(BaseModel):
    status:       Optional[str] = Field(None, pattern="^(active|suspended|expired)$")
    role:         Optional[str] = Field(None, pattern="^(student|staff|admin)$")
    display_name: Optional[str] = None


# ─────────────────────────────────────────────────────────────
# JWT & crypto helpers
# ─────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(UTC)


def _create_access_token(user_id: str, role: str, email: str) -> str:
    return jwt.encode(
        {
            "sub":     user_id,
            "user_id": user_id,
            "role":    role,
            "email":   email,
            "iat":     _now(),
            "exp":     _now() + timedelta(seconds=ACCESS_TTL_SECONDS),
            "jti":     str(uuid.uuid4()),
        },
        JWT_SECRET,
        algorithm=JWT_ALGO,
    )


def _create_token_pair() -> tuple[str, str]:
    raw    = secrets.token_urlsafe(48)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


def _decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])


def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=12)).decode()


def _verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


# ─────────────────────────────────────────────────────────────
# TDP-M1-02: DB-only session management
# Inactivity window = INACTIVITY_TTL_SECONDS, enforced via expires_at.
# touch_session() resets expires_at on every authenticated request.
# ─────────────────────────────────────────────────────────────

async def touch_session(jti: str) -> None:
    pool = await get_pool()
    new_expiry = _now() + timedelta(seconds=INACTIVITY_TTL_SECONDS)
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE sessions SET expires_at = $1 WHERE jti = $2 AND revoked_at IS NULL",
            new_expiry, jti,
        )


async def validate_session(jti: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT expires_at FROM sessions WHERE jti = $1 AND revoked_at IS NULL",
            jti,
        )
    if not row:
        return False
    expires_at = row["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return _now() < expires_at


async def revoke_session(jti: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE sessions SET revoked_at = NOW() WHERE jti = $1",
            jti,
        )


async def revoke_all_sessions_for_user(user_id: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE sessions SET revoked_at = NOW() WHERE user_id = $1 AND revoked_at IS NULL",
            uuid.UUID(user_id),
        )


async def _revoke_all_sessions_for_user_conn(user_id: str, conn) -> None:
    await conn.execute(
        "UPDATE sessions SET revoked_at = NOW() WHERE user_id = $1 AND revoked_at IS NULL",
        uuid.UUID(user_id),
    )


# ─────────────────────────────────────────────────────────────
# Auth guard
# ─────────────────────────────────────────────────────────────

async def _require_role(request: Request, *roles: str):
    header = request.headers.get("Authorization", "")
    token  = header.removeprefix("Bearer ").strip()
    if not token:
        return None, err("TOKEN_INVALID", "Authentication required.", status=401)

    try:
        payload = _decode_token(token)
    except jwt.ExpiredSignatureError:
        return None, err("TOKEN_EXPIRED", "Session expired. Please log in again.", status=401)
    except jwt.InvalidTokenError:
        return None, err("TOKEN_INVALID", "Invalid token.", status=401)

    jti = payload.get("jti", "")
    if not await validate_session(jti):
        return None, err("TOKEN_EXPIRED", "Session expired. Please log in again.", status=401)

    await touch_session(jti)

    if roles and payload.get("role") not in roles:
        return None, err("FORBIDDEN", "You do not have permission for this action.", status=403)

    return payload, None


# ─────────────────────────────────────────────────────────────
# Audit helper
# ─────────────────────────────────────────────────────────────

async def _audit(
    event_type: str,
    actor_id,
    target_id,
    ip: Optional[str],
    payload: Optional[dict] = None,
    *,
    raise_on_failure: bool = False,
) -> None:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO audit_log (event_type, actor_id, target_id, ip_address, payload)
                   VALUES ($1, $2, $3, $4::inet, $5::jsonb)""",
                event_type,
                uuid.UUID(actor_id)  if actor_id  else None,
                uuid.UUID(target_id) if target_id else None,
                ip,
                _json.dumps(payload or {}),
            )
    except Exception as exc:
        if raise_on_failure:
            raise RuntimeError(f"Audit write failed for {event_type}: {exc}") from exc
        logger.error("[AUDIT ERROR] event=%s error=%s", event_type, exc)


# ─────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/v1/auth", tags=["Auth & Identity"])


@router.post("/login")
async def login(body: LoginRequest, request: Request):
    ip   = request.client.host if request.client else None
    pool = await get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT id::text, email, display_name, password_hash,
                      role, status::text, failed_attempts, locked_until,
                      wallet_balance, meal_plan_balance
               FROM users WHERE email = $1""",
            body.email,
        )

        if not row:
            await _audit("LOGIN_FAILED_UNKNOWN", None, None, ip, {"email": body.email})
            return err("INVALID_CREDENTIALS", "No account found for this email address.", status=403)

        user = dict(row)

        if user["locked_until"]:
            lu = user["locked_until"]
            if lu.tzinfo is None:
                lu = lu.replace(tzinfo=UTC)
            if lu > _now():
                secs = int((lu - _now()).total_seconds())
                return err(
                    "ACCOUNT_LOCKED",
                    f"Account locked. Try again in {max(1, secs // 60)} minute(s).",
                    details={
                        "unlocks_at":            lu.isoformat(),
                        "retry_after_seconds":   secs,
                        "lock_duration_seconds": LOCKOUT_DURATION_SECONDS,
                    },
                    status=403,
                )

        status = user["status"]
        if status != "active":
            await _audit("LOGIN_REJECTED_INACTIVE", None, user["id"], ip, {"status": status})
            message = ACCOUNT_STATUS_MESSAGES.get(
                status, "Your account is not active. Contact the university helpdesk."
            )
            return err(
                "ACCOUNT_SUSPENDED" if status == "suspended" else "ACCOUNT_EXPIRED",
                message,
                details={"access_token": None, "refresh_token": None},
                status=403,
            )

        if not _verify_password(body.password, user["password_hash"]):
            new_count = await conn.fetchval(
                "UPDATE users SET failed_attempts = failed_attempts + 1 WHERE email = $1 RETURNING failed_attempts",
                body.email,
            )

            if new_count < MAX_FAILED_ATTEMPTS:
                remaining = MAX_FAILED_ATTEMPTS - new_count
                await _audit("LOGIN_FAILED_BAD_PW", None, user["id"], ip, {"attempt": new_count})
                return err(
                    "INVALID_CREDENTIALS",
                    f"Invalid credentials. {remaining} attempt(s) remaining before lockout.",
                    status=401,
                )

            lock_until = _now() + timedelta(seconds=LOCKOUT_DURATION_SECONDS)
            await conn.execute(
                "UPDATE users SET locked_until = $1 WHERE email = $2",
                lock_until, body.email,
            )
            await _audit(
                "ACCOUNT_LOCKED", None, user["id"], ip,
                {"locked_until": lock_until.isoformat(), "lock_duration_seconds": LOCKOUT_DURATION_SECONDS, "ip_address": ip},
                raise_on_failure=True,
            )
            return err(
                "ACCOUNT_LOCKED",
                "Account locked. Try again in 15 minutes.",
                details={
                    "unlocks_at":            lock_until.isoformat(),
                    "lock_duration_seconds": LOCKOUT_DURATION_SECONDS,
                    "retry_after_seconds":   LOCKOUT_DURATION_SECONDS,
                },
                status=403,
            )

        # Success — reset counter
        await conn.execute(
            "UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = $1",
            uuid.UUID(user["id"]),
        )

        access_token          = _create_access_token(user["id"], user["role"], user["email"])
        raw_refresh, ref_hash = _create_token_pair()
        refresh_expires       = _now() + timedelta(seconds=REFRESH_TTL_SECONDS)
        decoded               = _decode_token(access_token)
        jti                   = decoded["jti"]

        # Store session with jti and initial inactivity expiry
        session_expires = _now() + timedelta(seconds=INACTIVITY_TTL_SECONDS)
        await conn.execute(
            "INSERT INTO sessions (user_id, token_hash, jti, expires_at) VALUES ($1, $2, $3, $4)",
            uuid.UUID(user["id"]), ref_hash, jti, session_expires,
        )

    await _audit("LOGIN_SUCCESS", user["id"], user["id"], ip, {"role": user["role"]})

    return ok({
        "access_token":  access_token,
        "refresh_token": raw_refresh,
        "token_type":    "bearer",
        "expires_in":    ACCESS_TTL_SECONDS,
        "user": {
            "id":           user["id"],
            "email":        user["email"],
            "display_name": user["display_name"],
            "role":         user["role"],
            "is_student":   _is_student_email(user["email"]),
        },
    })


@router.get("/me")
async def get_me(request: Request):
    payload, guard = await _require_role(request, "student", "staff", "admin")
    if guard:
        return guard

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT id::text, email, display_name, role, status::text,
                      wallet_balance, meal_plan_balance
               FROM users WHERE id = $1""",
            uuid.UUID(payload["user_id"]),
        )

    if not row:
        return err("TOKEN_INVALID", "User not found.", status=401)

    u = dict(row)
    return ok({
        "id":                u["id"],
        "email":             u["email"],
        "display_name":      u["display_name"],
        "role":              u["role"],
        "status":            u["status"],
        "wallet_balance":    float(u["wallet_balance"]),
        "meal_plan_balance": float(u["meal_plan_balance"]),
        "is_student":        _is_student_email(u["email"]),
    })


@router.post("/logout")
async def logout(request: Request):
    payload, guard = await _require_role(request, "student", "staff", "admin")
    if guard:
        return guard

    await revoke_all_sessions_for_user(payload["user_id"])
    await _audit("LOGOUT", payload["user_id"], payload["user_id"], None, {})
    return ok({"logged_out": True})


@router.post("/password-reset/request")
async def password_reset_request(body: PasswordResetRequestBody, request: Request):
    ip   = request.client.host if request.client else None
    pool = await get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id::text FROM users WHERE email = $1 AND status = 'active'",
            str(body.email).lower().strip(),
        )
        if row:
            raw_token, token_hash = _create_token_pair()
            expires_at = _now() + timedelta(seconds=RESET_TTL_SECONDS)
            await conn.execute(
                "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) VALUES ($1, $2, $3)",
                uuid.UUID(row["id"]), token_hash, expires_at,
            )
            await _audit("PASSWORD_RESET_REQUESTED", row["id"], row["id"], ip, {})

    return JSONResponse(
        {"success": True, "data": {"message": "If this email is registered, a reset link has been sent."}},
        status_code=202,
    )


@router.post("/password-reset/confirm")
async def password_reset_confirm(body: PasswordResetConfirmBody, request: Request):
    ip         = request.client.host if request.client else None
    token_hash = _sha256(body.token)
    pool       = await get_pool()

    async with pool.acquire() as conn:
        token_row = await conn.fetchrow(
            "SELECT user_id::text, used_at, expires_at FROM password_reset_tokens WHERE token_hash = $1",
            token_hash,
        )

        if not token_row:
            return err("INVALID_TOKEN", "Reset link is invalid or has expired.", status=422)

        if token_row["used_at"] is not None:
            return err("LINK_ALREADY_USED", "This reset link has already been used. Please request a new one.", status=422)

        expires_at = token_row["expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)

        if _now() >= expires_at:
            return err("LINK_EXPIRED", "This reset link has expired. Please request a new one.", status=422)

        await conn.execute(
            "UPDATE password_reset_tokens SET used_at = NOW() WHERE token_hash = $1",
            token_hash,
        )
        await conn.execute(
            "UPDATE users SET password_hash = $1 WHERE id = $2",
            _hash_password(body.new_password),
            uuid.UUID(token_row["user_id"]),
        )
        await _revoke_all_sessions_for_user_conn(token_row["user_id"], conn)
        await _audit("PASSWORD_RESET_COMPLETED", token_row["user_id"], token_row["user_id"], ip, {})

    return ok({"message": "Password updated. Please log in with your new password."})


@router.get("/admin/users")
async def list_users(request: Request, page: int = 1, per_page: int = 20):
    payload, guard = await _require_role(request, "admin")
    if guard:
        return guard

    offset = (page - 1) * per_page
    pool   = await get_pool()
    async with pool.acquire() as conn:
        rows  = await conn.fetch(
            """SELECT id::text, email, display_name, role, status::text, created_at
               FROM users ORDER BY created_at DESC LIMIT $1 OFFSET $2""",
            per_page, offset,
        )
        total = await conn.fetchval("SELECT COUNT(*) FROM users")

    return ok({"users": [dict(r) for r in rows], "total": total, "page": page, "per_page": per_page})


@router.get("/admin/users/{user_id}")
async def get_user(user_id: str, request: Request):
    payload, guard = await _require_role(request, "admin", "staff")
    if guard:
        return guard

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id::text, email, display_name, role, status::text, created_at FROM users WHERE id = $1",
            uuid.UUID(user_id),
        )
    if not row:
        return err("USER_NOT_FOUND", "User not found.", status=404)
    return ok(dict(row))


@router.post("/admin/users")
async def create_user(body: AdminCreateUserBody, request: Request):
    payload, guard = await _require_role(request, "admin")
    if guard:
        return guard

    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                """INSERT INTO users (email, display_name, password_hash, role)
                   VALUES ($1, $2, $3, $4)
                   RETURNING id::text, email, display_name, role, status::text, created_at""",
                str(body.email).lower().strip(),
                body.display_name,
                _hash_password(body.password),
                body.role,
            )
        except asyncpg.UniqueViolationError:
            return err("EMAIL_TAKEN", "A user with this email already exists.", status=409)

    await _audit("USER_CREATED", payload["user_id"], row["id"], None, {"role": body.role})
    return ok(dict(row), status=201)


@router.patch("/admin/users/{user_id}")
async def update_user(user_id: str, body: AdminUpdateUserBody, request: Request):
    payload, guard = await _require_role(request, "admin")
    if guard:
        return guard

    fields = body.model_dump(exclude_none=True)
    if not fields:
        return err("NO_FIELDS", "No fields provided to update.", status=422)

    parts, vals, idx = [], [], 1
    if "display_name" in fields:
        parts.append(f"display_name = ${idx}");        vals.append(fields["display_name"]); idx += 1
    if "role"   in fields:
        parts.append(f"role = ${idx}::user_role");     vals.append(fields["role"]);         idx += 1
    if "status" in fields:
        parts.append(f"status = ${idx}::user_status"); vals.append(fields["status"]);       idx += 1

    vals.append(uuid.UUID(user_id))
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"UPDATE users SET {', '.join(parts)} WHERE id = ${idx} "
            f"RETURNING id::text, email, display_name, role, status::text",
            *vals,
        )

    if not row:
        return err("USER_NOT_FOUND", "User not found.", status=404)
    await _audit("USER_UPDATED", payload["user_id"], user_id, None, fields)
    return ok(dict(row))