"""
Unit Tests — FR04
Session expiry after 30 minutes of inactivity.
"""
import pytest
from datetime import timedelta
from unittest.mock import MagicMock
from freezegun import freeze_time

BASE_TIME   = "2025-01-01 12:00:00"
SAMPLE_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.sample"


@pytest.fixture
def redis_client():
    """Mock Redis client with simple dict-backed store."""
    store = {}

    client = MagicMock()
    client.get.side_effect    = lambda k: store.get(k)
    client.set.side_effect    = lambda k, v, ex=None: store.update({k: v})
    client.delete.side_effect = lambda k: store.pop(k, None)
    client._store = store
    return client


@pytest.fixture
def validate_token():
    from services.session_service import validate_token
    return validate_token


@pytest.fixture
def touch_session():
    from services.session_service import touch_session
    return touch_session


# ---------------------------------------------------------------------------
# TDP-M1-02 — Session Expiry Precision
# ---------------------------------------------------------------------------

class TestSessionExpiry:

    @freeze_time(BASE_TIME)
    def test_token_valid_at_1799_seconds(self, validate_token, redis_client):
        """
        PADLOCK P1 — Inactivity window is exact: 1800 s, not 'about 30 minutes'.
        Token must still be valid at t + 1799 s.
        """
        from datetime import datetime
        base = datetime.fromisoformat(BASE_TIME)

        with freeze_time(base + timedelta(seconds=1799)):
            result = validate_token(SAMPLE_TOKEN, redis_client)
            assert result.valid is True  # P1

    @freeze_time(BASE_TIME)
    def test_token_invalid_at_1800_seconds(self, validate_token, redis_client):
        """
        PADLOCK P1 — Token must be invalid at exactly t + 1800 s.
        PADLOCK P2 — Server-side invalidation is mandatory; Redis key must be deleted.
        PADLOCK P4 — Error message is exact.
        """
        from datetime import datetime
        base = datetime.fromisoformat(BASE_TIME)

        with freeze_time(base + timedelta(seconds=1800)):
            result = validate_token(SAMPLE_TOKEN, redis_client)
            assert result.valid is False                                      # P1
            assert result.http_status == 401                                  # Gherkin
            assert result.message == "Session expired. Please log in again."  # P4
            # P2 — token removed from Redis
            assert redis_client.get(f"session:{SAMPLE_TOKEN}") is None        # P2

    @freeze_time(BASE_TIME)
    def test_activity_resets_inactivity_clock(self, validate_token, touch_session, redis_client):
        """
        PADLOCK P3 — Clock is inactivity-based, not issuance-based:
          Activity resets the countdown; window is from last_active, not token creation.
        """
        from datetime import datetime
        base = datetime.fromisoformat(BASE_TIME)

        # Activity event at t + 1000 s
        with freeze_time(base + timedelta(seconds=1000)):
            touch_session(SAMPLE_TOKEN, redis_client)

        # Still valid at t + 2799 s (1000 + 1800 - 1 = 2799)
        with freeze_time(base + timedelta(seconds=2799)):
            result = validate_token(SAMPLE_TOKEN, redis_client)
            assert result.valid is True   # P3

        # Invalid at t + 2800 s (1000 + 1800 = 2800)
        with freeze_time(base + timedelta(seconds=2800)):
            result = validate_token(SAMPLE_TOKEN, redis_client)
            assert result.valid is False  # P3

    def test_expired_token_is_removed_from_redis(self, validate_token, redis_client):
        """
        PADLOCK P2 — Server-side invalidation:
          Client-side JWT expiry alone is insufficient.
          The token key must be explicitly deleted from the Redis store.
        """
        with freeze_time("2025-01-01 12:30:01"):
            validate_token(SAMPLE_TOKEN, redis_client)
            redis_client.delete.assert_called()
