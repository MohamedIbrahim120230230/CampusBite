"""
Unit Tests — FR01, FR02, FR08
Login with university credentials & account status rejection.
"""
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session():
    """Lightweight in-memory mock for DB session."""
    return MagicMock()


@pytest.fixture
def auth_service(db_session):
    from services.auth_service import AuthService
    return AuthService(db_session)


# ---------------------------------------------------------------------------
# FR01 — Successful Login
# ---------------------------------------------------------------------------

class TestSuccessfulLogin:
    def test_valid_credentials_return_access_and_refresh_tokens(self, auth_service):
        """
        Given valid email + password,
        When login is called,
        Then access_token and refresh_token are issued and http_status is 200.
        """
        result = auth_service.login("ali@university.edu", "validPass1!")
        assert result.http_status == 200
        assert result.access_token is not None
        assert result.refresh_token is not None
        assert result.token_type == "Bearer"

    def test_access_token_ttl_is_1800_seconds(self, auth_service):
        """JWT access token must expire in exactly 1800 seconds (30 min)."""
        result = auth_service.login("ali@university.edu", "validPass1!")
        assert result.expires_in == 1800

    def test_refresh_token_ttl_is_604800_seconds(self, auth_service):
        """JWT refresh token must expire in exactly 604800 seconds (7 days)."""
        result = auth_service.login("ali@university.edu", "validPass1!")
        assert result.refresh_token_expires_in == 604800

    def test_successful_login_redirects_to_menu(self, auth_service):
        """After successful login the redirect target is the menu home page."""
        result = auth_service.login("ali@university.edu", "validPass1!")
        assert result.redirect == "/menu"


# ---------------------------------------------------------------------------
# FR01 — Invalid Credentials (Scenario Outline)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("email,password,reason", [
    ("unknown@ext.com",       "anyPass1!",   "Unregistered email"),
    ("ali@university.edu",    "wrongPass!",  "Wrong password"),
    ("expired@university.edu","validPass1!", "Expired account"),
])
def test_login_rejected_for_invalid_credentials(auth_service, email, password, reason):
    """
    Given credentials that are invalid for various reasons,
    When login is submitted,
    Then HTTP 401 is returned with 'Invalid credentials' body.
    """
    result = auth_service.login(email, password)
    assert result.http_status == 401, f"Expected 401 for: {reason}"
    assert "Invalid credentials" in result.message


# ---------------------------------------------------------------------------
# FR08 — Suspended / Expired / Not-Found Account Rejection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status,expected_message", [
    ("SUSPENDED", "Your account has been suspended. Contact the registrar."),
    ("EXPIRED",   "Your university account has expired. Contact IT services."),
    ("NOT_FOUND", "No account found for this email address."),
])
def test_rejected_account_statuses_return_403(db_session, status, expected_message):
    """
    Given an account in a non-active status,
    When login is attempted with a correct password,
    Then HTTP 403 is returned with the status-specific message and no tokens are issued.

    PADLOCKS:
      P1 — No token on rejection: access_token and refresh_token are None
      P2 — Messages are status-specific: each status has a unique message
      P3 — HTTP 403, not 401 (authorization failure, not authentication failure)
    """
    from services.auth_service import AuthService
    service = AuthService(db_session)
    result = service.login("ali@university.edu", "validPass1!")

    assert result.http_status == 403                          # P3
    assert result.message == expected_message                 # P2
    assert result.access_token is None                        # P1
    assert result.refresh_token is None                       # P1
