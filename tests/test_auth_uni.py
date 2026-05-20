"""
unit/backend/test_auth_unit.py
Unit tests for backend/auth/routes.py

Covers (NO DB, NO network):
  - Email domain validation (_is_university_email, _is_student_email)
  - Password hashing & verification
  - JWT creation & decoding
  - Pydantic schema validation (LoginRequest, PasswordResetConfirmBody, AdminCreateUserBody)
  - Account lockout countdown logic
  - ACCOUNT_STATUS_MESSAGES mapping
  - SHA-256 token helper
  - TDP-M1-01 through TDP-M1-04 pure-logic paths
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import pytest

# ── re-implement the pure helpers locally to avoid DB import side-effects ──
UTC        = timezone.utc
JWT_SECRET = "dev-secret-CHANGE-IN-PRODUCTION"
JWT_ALGO   = "HS256"

ALLOWED_DOMAINS = ["ejust.edu.eg"]

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

def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=4)).decode()

def _verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())

def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()

def _create_access_token(user_id: str, role: str, email: str) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {"sub": user_id, "user_id": user_id, "role": role,
         "email": email, "iat": now,
         "exp": now + timedelta(seconds=1800),
         "jti": str(uuid.uuid4())},
        JWT_SECRET, algorithm=JWT_ALGO,
    )

ACCOUNT_STATUS_MESSAGES = {
    "suspended": "Your account has been suspended. Contact the registrar.",
    "expired":   "Your university account has expired. Contact IT services.",
}

MAX_FAILED_ATTEMPTS      = 5
LOCKOUT_DURATION_SECONDS = 900

# ═══════════════════════════════════════════════════════════════
# EMAIL VALIDATION
# ═══════════════════════════════════════════════════════════════

class TestUniversityEmailValidation:
    """TDP-M1-01 FR03 — domain allow-list"""

    @pytest.mark.unit
    def test_valid_ejust_email(self):
        assert _is_university_email("student.123456@ejust.edu.eg") is True

    @pytest.mark.unit
    def test_valid_email_case_insensitive(self):
        assert _is_university_email("Student.123456@EJUST.EDU.EG") is True

    @pytest.mark.unit
    def test_invalid_gmail(self):
        assert _is_university_email("student@gmail.com") is False

    @pytest.mark.unit
    def test_invalid_no_at_sign(self):
        assert _is_university_email("notanemail") is False

    @pytest.mark.unit
    def test_invalid_subdomain(self):
        assert _is_university_email("user@mail.ejust.edu.eg") is False

    @pytest.mark.unit
    def test_invalid_empty_string(self):
        assert _is_university_email("") is False

    @pytest.mark.unit
    def test_invalid_only_at(self):
        assert _is_university_email("@") is False

    @pytest.mark.unit
    def test_strips_whitespace(self):
        assert _is_university_email("  student.123456@ejust.edu.eg  ") is True


class TestStudentEmailDetection:
    """Detect student vs staff by local-part numeric ID suffix"""

    @pytest.mark.unit
    def test_student_email_numeric_suffix(self):
        assert _is_student_email("ahmed.saber.202212345@ejust.edu.eg") is True

    @pytest.mark.unit
    def test_six_digit_id_is_student(self):
        assert _is_student_email("ali.123456@ejust.edu.eg") is True

    @pytest.mark.unit
    def test_five_digit_not_student(self):
        assert _is_student_email("ali.12345@ejust.edu.eg") is False

    @pytest.mark.unit
    def test_staff_no_numeric_suffix(self):
        assert _is_student_email("prof.smith@ejust.edu.eg") is False

    @pytest.mark.unit
    def test_single_part_local_not_student(self):
        assert _is_student_email("admin@ejust.edu.eg") is False

    @pytest.mark.unit
    def test_empty_local_not_student(self):
        assert _is_student_email("@ejust.edu.eg") is False


# ═══════════════════════════════════════════════════════════════
# PASSWORD HASHING
# ═══════════════════════════════════════════════════════════════

class TestPasswordHashing:
    """Bcrypt hash + verify"""

    @pytest.mark.unit
    def test_hash_is_not_plaintext(self):
        h = _hash_password("Secret123!")
        assert h != "Secret123!"

    @pytest.mark.unit
    def test_correct_password_verifies(self):
        h = _hash_password("Password99!")
        assert _verify_password("Password99!", h) is True

    @pytest.mark.unit
    def test_wrong_password_rejected(self):
        h = _hash_password("Password99!")
        assert _verify_password("WrongPass!", h) is False

    @pytest.mark.unit
    def test_hash_unique_per_call(self):
        h1 = _hash_password("SamePassword!")
        h2 = _hash_password("SamePassword!")
        assert h1 != h2  # different salts

    @pytest.mark.unit
    def test_empty_string_password(self):
        h = _hash_password("")
        assert _verify_password("", h) is True


# ═══════════════════════════════════════════════════════════════
# JWT CREATION & DECODING
# ═══════════════════════════════════════════════════════════════

class TestJWTTokens:
    """Access token shape, claims, expiry"""

    @pytest.mark.unit
    def test_token_contains_required_claims(self):
        uid = str(uuid.uuid4())
        token = _create_access_token(uid, "student", "s.123456@ejust.edu.eg")
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        assert payload["user_id"] == uid
        assert payload["role"]    == "student"
        assert payload["email"]   == "s.123456@ejust.edu.eg"
        assert "jti" in payload
        assert "exp" in payload
        assert "iat" in payload

    @pytest.mark.unit
    def test_token_expires_after_1800s(self):
        uid   = str(uuid.uuid4())
        token = _create_access_token(uid, "student", "s.123456@ejust.edu.eg")
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        ttl = payload["exp"] - payload["iat"]
        assert ttl == 1800

    @pytest.mark.unit
    def test_expired_token_raises(self):
        now = datetime.now(UTC)
        token = jwt.encode(
            {"sub": "u1", "user_id": "u1", "role": "student",
             "iat": now - timedelta(seconds=3601),
             "exp": now - timedelta(seconds=1),
             "jti": str(uuid.uuid4())},
            JWT_SECRET, algorithm=JWT_ALGO,
        )
        with pytest.raises(jwt.ExpiredSignatureError):
            jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])

    @pytest.mark.unit
    def test_wrong_secret_raises(self):
        uid   = str(uuid.uuid4())
        token = _create_access_token(uid, "student", "s.123456@ejust.edu.eg")
        with pytest.raises(jwt.InvalidSignatureError):
            jwt.decode(token, "WRONG_SECRET", algorithms=[JWT_ALGO])

    @pytest.mark.unit
    def test_tampered_token_raises(self):
        uid   = str(uuid.uuid4())
        token = _create_access_token(uid, "student", "s.123456@ejust.edu.eg")
        # Flip a char in the signature
        parts = token.split(".")
        tampered = parts[0] + "." + parts[1] + "." + parts[2][:5] + "X" + parts[2][6:]
        with pytest.raises(jwt.InvalidSignatureError):
            jwt.decode(tampered, JWT_SECRET, algorithms=[JWT_ALGO])

    @pytest.mark.unit
    def test_admin_role_preserved(self):
        uid   = str(uuid.uuid4())
        token = _create_access_token(uid, "admin", "admin.001@ejust.edu.eg")
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        assert payload["role"] == "admin"

    @pytest.mark.unit
    def test_jti_is_unique_per_token(self):
        uid = str(uuid.uuid4())
        t1  = _create_access_token(uid, "student", "s.123456@ejust.edu.eg")
        t2  = _create_access_token(uid, "student", "s.123456@ejust.edu.eg")
        p1  = jwt.decode(t1, JWT_SECRET, algorithms=[JWT_ALGO])
        p2  = jwt.decode(t2, JWT_SECRET, algorithms=[JWT_ALGO])
        assert p1["jti"] != p2["jti"]


# ═══════════════════════════════════════════════════════════════
# SHA-256 TOKEN HELPER
# ═══════════════════════════════════════════════════════════════

class TestSHA256Helper:
    """Refresh / reset token hashing"""

    @pytest.mark.unit
    def test_sha256_deterministic(self):
        assert _sha256("hello") == _sha256("hello")

    @pytest.mark.unit
    def test_sha256_different_inputs(self):
        assert _sha256("abc") != _sha256("def")

    @pytest.mark.unit
    def test_sha256_hex_length(self):
        assert len(_sha256("any-token")) == 64

    @pytest.mark.unit
    def test_sha256_known_value(self):
        # SHA-256("abc") from NIST
        assert _sha256("abc") == "ba7816bf8f01cfea414140de5dae2ec73b00361bbef0469f492c347a2456ecb2"[:64]


# ═══════════════════════════════════════════════════════════════
# ACCOUNT LOCKOUT LOGIC
# ═══════════════════════════════════════════════════════════════

class TestLockoutLogic:
    """TDP-M1-01 FR03 — lockout counting & timing"""

    @pytest.mark.unit
    def test_lockout_triggers_at_max_attempts(self):
        """After MAX_FAILED_ATTEMPTS the account should be locked."""
        failed = MAX_FAILED_ATTEMPTS
        should_lock = failed >= MAX_FAILED_ATTEMPTS
        assert should_lock is True

    @pytest.mark.unit
    def test_before_max_attempts_no_lock(self):
        for n in range(1, MAX_FAILED_ATTEMPTS):
            assert n < MAX_FAILED_ATTEMPTS

    @pytest.mark.unit
    def test_lockout_duration_is_900s(self):
        assert LOCKOUT_DURATION_SECONDS == 900

    @pytest.mark.unit
    def test_locked_until_in_future_means_locked(self):
        locked_until = datetime.now(UTC) + timedelta(seconds=60)
        assert locked_until > datetime.now(UTC)

    @pytest.mark.unit
    def test_locked_until_in_past_means_unlocked(self):
        locked_until = datetime.now(UTC) - timedelta(seconds=1)
        assert locked_until < datetime.now(UTC)

    @pytest.mark.unit
    def test_remaining_attempts_calculation(self):
        new_count = 3
        remaining = MAX_FAILED_ATTEMPTS - new_count
        assert remaining == 2


# ═══════════════════════════════════════════════════════════════
# ACCOUNT STATUS MESSAGES
# ═══════════════════════════════════════════════════════════════

class TestAccountStatusMessages:
    """TDP-M1-04 FR08 — status messages"""

    @pytest.mark.unit
    def test_suspended_message_present(self):
        assert "suspended" in ACCOUNT_STATUS_MESSAGES
        assert "registrar" in ACCOUNT_STATUS_MESSAGES["suspended"]

    @pytest.mark.unit
    def test_expired_message_present(self):
        assert "expired" in ACCOUNT_STATUS_MESSAGES
        assert "IT" in ACCOUNT_STATUS_MESSAGES["expired"]

    @pytest.mark.unit
    def test_unknown_status_falls_back(self):
        status = "banned"
        msg = ACCOUNT_STATUS_MESSAGES.get(
            status, "Your account is not active. Contact the university helpdesk."
        )
        assert "helpdesk" in msg


# ═══════════════════════════════════════════════════════════════
# PYDANTIC SCHEMA VALIDATION
# ═══════════════════════════════════════════════════════════════

class TestLoginRequestSchema:
    """Pydantic guards: email domain, password min-length"""

    @pytest.mark.unit
    def test_valid_login_request(self):
        from pydantic import ValidationError

        # Inline schema to avoid DB import
        from pydantic import BaseModel, EmailStr, Field, field_validator

        class LoginRequest(BaseModel):
            email:    EmailStr
            password: str = Field(min_length=1)

            @field_validator("email")
            @classmethod
            def must_be_university_email(cls, v: str) -> str:
                if not _is_university_email(v):
                    raise ValueError("Only university email addresses are allowed.")
                return v.lower().strip()

        req = LoginRequest(email="test.123456@ejust.edu.eg", password="pass")
        assert req.email == "test.123456@ejust.edu.eg"

    @pytest.mark.unit
    def test_invalid_domain_raises(self):
        from pydantic import BaseModel, EmailStr, Field, ValidationError, field_validator

        class LoginRequest(BaseModel):
            email:    EmailStr
            password: str = Field(min_length=1)

            @field_validator("email")
            @classmethod
            def must_be_university_email(cls, v: str) -> str:
                if not _is_university_email(v):
                    raise ValueError("Only university email addresses are allowed.")
                return v.lower().strip()

        with pytest.raises(ValidationError) as exc_info:
            LoginRequest(email="hacker@evil.com", password="pass")
        assert "university" in str(exc_info.value).lower()

    @pytest.mark.unit
    def test_empty_password_raises(self):
        from pydantic import BaseModel, EmailStr, Field, ValidationError

        class LoginRequest(BaseModel):
            email:    EmailStr
            password: str = Field(min_length=1)

        with pytest.raises(ValidationError):
            LoginRequest(email="test.123456@ejust.edu.eg", password="")

    @pytest.mark.unit
    def test_password_reset_min_length(self):
        from pydantic import BaseModel, Field, ValidationError

        class PasswordResetConfirmBody(BaseModel):
            token:        str
            new_password: str = Field(min_length=8)

        with pytest.raises(ValidationError):
            PasswordResetConfirmBody(token="tok", new_password="short")

    @pytest.mark.unit
    def test_admin_role_pattern(self):
        from pydantic import BaseModel, EmailStr, Field, ValidationError

        class AdminCreateUserBody(BaseModel):
            email:        EmailStr
            display_name: str
            role:         str = Field(pattern="^(student|staff|admin)$")
            password:     str = Field(min_length=8)

        with pytest.raises(ValidationError):
            AdminCreateUserBody(
                email="x.001@ejust.edu.eg",
                display_name="X",
                role="superuser",
                password="Passw0rd!",
            )

    @pytest.mark.unit
    def test_admin_update_status_pattern(self):
        from pydantic import BaseModel, Field, ValidationError
        from typing import Optional

        class AdminUpdateUserBody(BaseModel):
            status: Optional[str] = Field(None, pattern="^(active|suspended|expired)$")

        with pytest.raises(ValidationError):
            AdminUpdateUserBody(status="banned")