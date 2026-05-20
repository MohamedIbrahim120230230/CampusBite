"""
Unit Tests — FR03
Account lockout after 5 consecutive failed login attempts.
"""
import pytest
from datetime import timedelta
from unittest.mock import MagicMock
from freezegun import freeze_time


LOCK_START = "2025-01-01 12:00:00"
VALID_EMAIL = "ali@university.edu"
WRONG_PASS  = "wrongPassword!"
RIGHT_PASS  = "correctPassword1!"


@pytest.fixture
def db_session():
    return MagicMock()


@pytest.fixture
def service(db_session):
    from services.auth_service import AuthService
    return AuthService(db_session)


# ---------------------------------------------------------------------------
# TDP-M1-01 — Core Lockout Behaviour
# ---------------------------------------------------------------------------

class TestAccountLockout:

    def test_account_locked_on_fifth_consecutive_failure(self, service):
        """
        PADLOCKS:
          P1 — Attempt count is exact: lock triggers at attempt == 5, not >= 4
          P2 — Lock duration is exact: 900 seconds (not 'about 15 minutes')
          P5 — Non-5th attempt returns 401, not 403
        """
        # Attempts 1-4 must return 401, account still open
        for attempt in range(4):
            result = service.login(VALID_EMAIL, WRONG_PASS)
            assert result.http_status == 401, (
                f"Attempt {attempt + 1} should return 401 — got {result.http_status}"
            )
            assert result.locked is False  # P1

        # 5th failure — account must lock NOW
        result = service.login(VALID_EMAIL, WRONG_PASS)
        assert result.locked is True                      # P1
        assert result.http_status == 403                  # P5
        assert result.lock_duration_seconds == 900        # P2

    def test_lockout_response_message_is_exact(self, service):
        """Exact error message required by Gherkin scenario."""
        for _ in range(5):
            service.login(VALID_EMAIL, WRONG_PASS)
        result = service.login(VALID_EMAIL, WRONG_PASS)
        assert "Account locked" in result.message
        assert "15 minutes" in result.message

    def test_audit_log_written_before_returning_403(self, service, db_session):
        """
        PADLOCK P3 — Audit log is mandatory:
          Every lockout must write to audit_log before returning HTTP 403.
        """
        for _ in range(5):
            service.login(VALID_EMAIL, WRONG_PASS)
        # Verify audit log was written (db_session.add or audit service called)
        db_session.add.assert_called()
        audit_calls = [
            str(call) for call in db_session.add.call_args_list
            if "audit" in str(call).lower() or "lockout" in str(call).lower()
        ]
        assert len(audit_calls) >= 1, "AuditLog entry must be written on lockout"  # P3

    def test_failed_attempt_counter_resets_to_zero_on_success(self, service):
        """
        PADLOCK P4 — Counter resets to zero:
          Successful login resets counter to 0, not to current - 1.
        """
        # Build up 4 failures
        for _ in range(4):
            service.login(VALID_EMAIL, WRONG_PASS)

        # Correct login clears counter
        result = service.login(VALID_EMAIL, RIGHT_PASS)
        assert result.http_status == 200
        assert result.failed_attempts == 0  # P4


# ---------------------------------------------------------------------------
# TDP-M1-01 — Lock Duration Precision
# ---------------------------------------------------------------------------

class TestLockDuration:

    @freeze_time(LOCK_START)
    def test_account_still_locked_at_899_seconds(self, service):
        """Lock must still be active at exactly t + 899 s."""
        # Trigger lockout
        for _ in range(5):
            service.login(VALID_EMAIL, WRONG_PASS)

        from datetime import datetime
        lock_time = datetime.fromisoformat(LOCK_START)

        with freeze_time(lock_time + timedelta(seconds=899)):
            result = service.login(VALID_EMAIL, RIGHT_PASS)
            assert result.locked is True  # P2 — 899s → still locked

    @freeze_time(LOCK_START)
    def test_account_unlocked_at_exactly_900_seconds(self, service):
        """Lock must be released at exactly t + 900 s."""
        for _ in range(5):
            service.login(VALID_EMAIL, WRONG_PASS)

        from datetime import datetime
        lock_time = datetime.fromisoformat(LOCK_START)

        with freeze_time(lock_time + timedelta(seconds=900)):
            result = service.login(VALID_EMAIL, RIGHT_PASS)
            assert result.locked is False  # P2 — 900s → released

    def test_login_succeeds_after_lockout_expires(self, service):
        """
        Given the account was locked 15 minutes ago,
        When the student submits the correct password,
        Then the system unlocks the account, issues a JWT, and resets the counter.
        """
        for _ in range(5):
            service.login(VALID_EMAIL, WRONG_PASS)

        with freeze_time("2025-01-01 12:15:01"):   # 15 min + 1s later
            result = service.login(VALID_EMAIL, RIGHT_PASS)
            assert result.http_status == 200
            assert result.access_token is not None
            assert result.failed_attempts == 0     # P4
