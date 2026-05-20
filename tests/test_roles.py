"""
Unit Tests — FR06 / FR07
Password reset (time-limited, single-use) & role assignment.
"""
import pytest
from datetime import timedelta
from unittest.mock import MagicMock
from freezegun import freeze_time

BASE_TIME    = "2025-01-01 12:00:00"
RESET_TOKEN  = "secure-reset-token-xyz-abc"


@pytest.fixture
def db_session():
    return MagicMock()


# ---------------------------------------------------------------------------
# TDP-M1-03 — FR06 Password Reset Link (15-Minute TTL, Single-Use)
# ---------------------------------------------------------------------------

class TestPasswordReset:

    @freeze_time(BASE_TIME)
    def test_reset_link_valid_at_899_seconds(self, db_session):
        """
        PADLOCK P1 — TTL is exactly 900 seconds: 899 s → valid.
        """
        from services.auth_service import consume_reset_token
        from datetime import datetime
        base = datetime.fromisoformat(BASE_TIME)

        with freeze_time(base + timedelta(seconds=899)):
            result = consume_reset_token(RESET_TOKEN, db=db_session)
            assert result.valid is True  # P1

    @freeze_time(BASE_TIME)
    def test_reset_link_expired_at_900_seconds(self, db_session):
        """
        PADLOCK P1 — TTL is exactly 900 seconds: 900 s → expired.
        PADLOCK P3 — Expired token must not change password (no side-effects).
        PADLOCK P4 — Distinct error code: LINK_EXPIRED.
        """
        from services.auth_service import consume_reset_token
        from datetime import datetime
        base = datetime.fromisoformat(BASE_TIME)

        with freeze_time(base + timedelta(seconds=900)):
            result = consume_reset_token(RESET_TOKEN, db=db_session)
            assert result.valid is False           # P1
            assert result.error == "LINK_EXPIRED"  # P4
            # P3 — no password change attempted on expiry
            db_session.query.assert_not_called()   # implementation must not query for update

    def test_reset_link_is_single_use(self, db_session):
        """
        PADLOCK P2 — Single-use enforced atomically:
          Token marked used=True in the same transaction as the password update.
        PADLOCK P4 — LINK_ALREADY_USED ≠ LINK_EXPIRED.
        """
        from services.auth_service import consume_reset_token

        first = consume_reset_token(RESET_TOKEN, new_password="NewPass1!", db=db_session)
        assert first.valid is True

        second = consume_reset_token(RESET_TOKEN, new_password="AnotherPass1!", db=db_session)
        assert second.valid is False
        assert second.error == "LINK_ALREADY_USED"  # P4

    def test_expired_error_differs_from_used_error(self, db_session):
        """PADLOCK P4 — Two distinct error codes for two distinct failure modes."""
        from services.auth_service import consume_reset_token

        # Mark first use (single-use)
        consume_reset_token(RESET_TOKEN, new_password="Pass1!", db=db_session)
        second = consume_reset_token(RESET_TOKEN, new_password="Pass2!", db=db_session)

        # Simulate expiry scenario separately
        with freeze_time("2025-01-01 12:16:00"):
            expired_result = consume_reset_token("other-token", db=db_session)

        assert second.error != expired_result.error  # P4 — codes must differ


# ---------------------------------------------------------------------------
# FR07 — Role Assignment by Admin
# ---------------------------------------------------------------------------

class TestRoleAssignment:

    def test_admin_can_assign_student_role(self, db_session):
        """Administrator can assign STUDENT role to a user."""
        from services.user_service import UserService
        svc = UserService(db_session)
        result = svc.assign_role(
            admin_actor="admin@university.edu",
            target_user="new@university.edu",
            role="STUDENT"
        )
        assert result.http_status == 200
        assert result.assigned_role == "STUDENT"

    def test_admin_can_assign_staff_role(self, db_session):
        """Administrator can assign STAFF role to a user."""
        from services.user_service import UserService
        svc = UserService(db_session)
        result = svc.assign_role(
            admin_actor="admin@university.edu",
            target_user="staff@university.edu",
            role="STAFF"
        )
        assert result.http_status == 200
        assert result.assigned_role == "STAFF"

    def test_non_admin_cannot_assign_roles(self, db_session):
        """Only ADMIN role can assign roles — STUDENT or STAFF must be rejected."""
        from services.user_service import UserService
        svc = UserService(db_session)
        result = svc.assign_role(
            admin_actor="student@university.edu",
            target_user="other@university.edu",
            role="STAFF"
        )
        assert result.http_status == 403

    def test_staff_permissions_do_not_overlap_admin(self, db_session):
        """Staff and Admin have non-overlapping permission sets (NFR14)."""
        from services.rbac_service import RBACService
        rbac = RBACService()
        staff_perms = rbac.get_permissions("STAFF")
        admin_perms = rbac.get_permissions("ADMIN")
        # Admin-only actions must not be in staff permissions
        admin_only = {"MANAGE_USERS", "SYSTEM_CONFIG", "EXPORT_REPORTS"}
        overlap = admin_only & staff_perms
        assert overlap == set(), f"Staff should not have admin-only permissions: {overlap}"
