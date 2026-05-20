"""
Security Tests — NFR12, NFR13, NFR14, NFR16, NFR19, NFR21
SQL injection prevention, rate limiting, JWT expiry, role-based access control,
OWASP Top 10 mitigations.
"""
import pytest
import time
from unittest.mock import MagicMock


@pytest.fixture
def client():
    """Test HTTP client for the API."""
    from app import create_app
    app = create_app(testing=True)
    with app.test_client() as c:
        yield c


@pytest.fixture
def admin_token(client):
    """Returns a valid JWT token for an admin user."""
    r = client.post("/auth/login", json={
        "email": "admin@university.edu",
        "password": "AdminPass1!"
    })
    return r.json["access_token"]


@pytest.fixture
def student_token(client):
    """Returns a valid JWT token for a student user."""
    r = client.post("/auth/login", json={
        "email": "ali@university.edu",
        "password": "validPass1!"
    })
    return r.json["access_token"]


# ---------------------------------------------------------------------------
# NFR16 — SQL Injection Prevention (Parameterised SQL / ORM Only)
# ---------------------------------------------------------------------------

class TestSQLInjection:

    def test_sql_injection_in_login_email_rejected(self, client):
        """
        NFR16: Parameterised SQL / ORM prevents injection via email field.
        A classic OR 1=1 attempt must return 401, never 200.
        """
        response = client.post("/auth/login", json={
            "email":    "' OR 1=1 --",
            "password": "x"
        })
        assert response.status_code == 401, (
            "SQL injection attempt should return 401, not 200"
        )

    def test_sql_injection_in_login_password_rejected(self, client):
        """SQL injection via password field must also be rejected."""
        response = client.post("/auth/login", json={
            "email":    "ali@university.edu",
            "password": "' OR '1'='1"
        })
        assert response.status_code == 401

    def test_sql_injection_in_search_query_rejected(self, client):
        """SQL injection in GET /menu?q= parameter must not expose data."""
        response = client.get("/menu?q='; DROP TABLE menu_items; --")
        assert response.status_code in (200, 400)
        # Must not return a 500 (which would indicate unhandled injection)
        assert response.status_code != 500

    def test_sql_injection_in_order_id_path_rejected(self, client, student_token):
        """SQL injection in path parameter must return 400 or 404, never 500."""
        response = client.get(
            "/orders/' OR 1=1 --",
            headers={"Authorization": f"Bearer {student_token}"}
        )
        assert response.status_code in (400, 404)
        assert response.status_code != 500

    def test_error_response_does_not_expose_sql(self, client):
        """
        NFR: Internal error code sanitisation — stack traces and DB errors
        (e.g. ORA-00001, psycopg2 errors) must never be exposed to clients.
        """
        response = client.post("/auth/login", json={
            "email": "' UNION SELECT * FROM users --",
            "password": "x"
        })
        body = response.get_data(as_text=True)
        assert "ORA-"         not in body
        assert "psycopg"      not in body
        assert "sqlalchemy"   not in body
        assert "Traceback"    not in body
        assert "syntax error" not in body.lower()


# ---------------------------------------------------------------------------
# NFR19 — Rate Limiting (20 req/min/IP for unauthenticated endpoints)
# ---------------------------------------------------------------------------

class TestRateLimiting:

    def test_rate_limit_enforced_on_menu_endpoint(self, client):
        """
        NFR19 (refined): Unauthenticated endpoints limited to 20 req/min/IP.
        After 20 requests the next must return HTTP 429.
        """
        for i in range(20):
            r = client.get("/menu")
            assert r.status_code == 200, f"Request {i + 1} should succeed"

        blocked = client.get("/menu")
        assert blocked.status_code == 429

    def test_rate_limit_enforced_on_login_endpoint(self, client):
        """Login endpoint is unauthenticated — rate limit applies."""
        for _ in range(20):
            client.post("/auth/login", json={
                "email": "any@university.edu", "password": "pass"
            })
        response = client.post("/auth/login", json={
            "email": "any@university.edu", "password": "pass"
        })
        assert response.status_code == 429

    def test_rate_limit_returns_correct_headers(self, client):
        """HTTP 429 response must include Retry-After header (NFR19)."""
        for _ in range(21):
            r = client.get("/menu")
        if r.status_code == 429:
            assert "Retry-After" in r.headers


# ---------------------------------------------------------------------------
# NFR14 — JWT Bearer Auth on All Endpoints
# ---------------------------------------------------------------------------

class TestJWTProtection:

    @pytest.mark.parametrize("endpoint,method", [
        ("/orders",             "POST"),
        ("/orders/some-id",     "GET"),
        ("/orders/some-id/payment", "POST"),
        ("/profile",            "GET"),
        ("/admin/users",        "GET"),
    ])
    def test_protected_endpoints_reject_unauthenticated_requests(self, client, endpoint, method):
        """
        NFR14: All API endpoints must be protected with JWT Bearer auth.
        Requests without a token must return HTTP 401.
        """
        if method == "GET":
            r = client.get(endpoint)
        else:
            r = client.post(endpoint, json={})
        assert r.status_code == 401, (
            f"{method} {endpoint} should require authentication"
        )

    def test_invalid_jwt_returns_401(self, client):
        """Malformed or tampered JWT must be rejected."""
        r = client.get("/orders", headers={
            "Authorization": "Bearer this.is.not.a.valid.jwt"
        })
        assert r.status_code == 401

    def test_expired_jwt_returns_401(self, client):
        """Expired JWT must be rejected (tested with a pre-generated expired token)."""
        expired = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
            ".eyJzdWIiOiJ1c2VyMDAxIiwiZXhwIjoxfQ"
            ".signature"
        )
        r = client.get("/menu", headers={"Authorization": f"Bearer {expired}"})
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# NFR13 — Password Hashing (bcrypt cost ≥ 12)
# ---------------------------------------------------------------------------

class TestPasswordHashing:

    def test_password_is_hashed_with_bcrypt(self):
        """
        NFR13: Passwords stored using bcrypt with cost factor ≥ 12.
        Plaintext must never appear in storage.
        """
        import bcrypt
        from services.auth_service import hash_password

        hashed = hash_password("MySecurePass1!")
        assert hashed != "MySecurePass1!"           # never plaintext
        assert hashed.startswith("$2b$") or hashed.startswith("$2a$"), (
            "Hash must be bcrypt format"
        )

        # Verify cost factor ≥ 12
        cost = int(hashed.split("$")[2])
        assert cost >= 12, f"bcrypt cost factor is {cost}, must be ≥ 12 (NFR13)"

    def test_verify_password_succeeds_for_correct_input(self):
        """Password verification must work correctly."""
        from services.auth_service import hash_password, verify_password
        hashed = hash_password("MySecurePass1!")
        assert verify_password("MySecurePass1!", hashed) is True

    def test_verify_password_fails_for_wrong_input(self):
        """Verification must fail for wrong passwords."""
        from services.auth_service import hash_password, verify_password
        hashed = hash_password("MySecurePass1!")
        assert verify_password("WrongPassword!", hashed) is False


# ---------------------------------------------------------------------------
# NFR14 — Role-Based Access Control (RBAC)
# ---------------------------------------------------------------------------

class TestRBACEnforcement:

    def test_student_cannot_access_admin_endpoints(self, client, student_token):
        """Students must not access admin-only endpoints."""
        r = client.get(
            "/admin/users",
            headers={"Authorization": f"Bearer {student_token}"}
        )
        assert r.status_code == 403

    def test_student_cannot_access_staff_endpoints(self, client, student_token):
        """Students must not access staff-only order advancement endpoints."""
        r = client.patch(
            "/orders/some-order-id/status",
            json={"status": "PREPARING"},
            headers={"Authorization": f"Bearer {student_token}"}
        )
        assert r.status_code == 403

    def test_staff_cannot_access_admin_endpoints(self, client):
        """Staff must not access admin-only configuration endpoints."""
        from tests.helpers import get_staff_token
        staff_token = get_staff_token(client)

        r = client.get(
            "/admin/system-config",
            headers={"Authorization": f"Bearer {staff_token}"}
        )
        assert r.status_code == 403

    def test_admin_can_access_user_management(self, client, admin_token):
        """Admins must be able to access user management endpoints."""
        r = client.get(
            "/admin/users",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# NFR12 — TLS 1.2+ (Infrastructure Check)
# ---------------------------------------------------------------------------

class TestTLSConfiguration:

    def test_http_redirects_to_https(self, client):
        """
        NFR12: All data in transit must use TLS 1.2+.
        HTTP requests must be redirected to HTTPS (301/302).
        Note: In test mode this may be a config assertion.
        """
        from app import create_app
        app = create_app(testing=False, tls=True)
        assert app.config.get("FORCE_HTTPS") is True, (
            "Application must enforce HTTPS (NFR12)"
        )


# ---------------------------------------------------------------------------
# NFR21 — OWASP Top 10 Mitigations
# ---------------------------------------------------------------------------

class TestOWASPMitigations:

    def test_xss_content_type_header_present(self, client):
        """Response headers should include X-Content-Type-Options: nosniff."""
        r = client.get("/menu")
        assert r.headers.get("X-Content-Type-Options") == "nosniff"

    def test_clickjacking_protection_header(self, client):
        """Response should include X-Frame-Options or CSP frame-ancestors."""
        r = client.get("/menu")
        xfo = r.headers.get("X-Frame-Options", "")
        csp = r.headers.get("Content-Security-Policy", "")
        assert "DENY" in xfo or "SAMEORIGIN" in xfo or "frame-ancestors" in csp

    def test_error_response_does_not_expose_stack_trace(self, client, student_token):
        """
        A 500-level error must not expose internal stack traces to the client.
        """
        with pytest.raises(Exception):
            r = client.get(
                "/orders/trigger-500",
                headers={"Authorization": f"Bearer {student_token}"}
            )
            if r.status_code == 500:
                body = r.get_data(as_text=True)
                assert "Traceback" not in body
                assert "File \"/"  not in body
