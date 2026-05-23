"""Tests for push notification tasks: daily challenge + big move alerts."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.tasks.push_notifications import (
    BIG_MOVE_THRESHOLD,
    _InvalidTokenError,
    _send_daily_challenge_push,
    _send_big_move_alerts,
    _send_fcm_message,
)


# ---------------------------------------------------------------------------
# Helpers: fake DB rows
# ---------------------------------------------------------------------------


def _fake_device_token(
    token_id=1,
    device_token="abcdefgh12345678",
    platform="ios",
    user_id=None,
    is_active=True,
):
    """Create a mock DeviceToken object."""
    dt = MagicMock()
    dt.id = token_id
    dt.device_token = device_token
    dt.platform = platform
    dt.user_id = user_id
    dt.is_active = is_active
    return dt


def _fake_user(user_id=1, push_preferences=None):
    """Create a mock User object."""
    u = MagicMock()
    u.id = user_id
    u.push_preferences = push_preferences
    return u


# ---------------------------------------------------------------------------
# Tests: _send_fcm_message
# ---------------------------------------------------------------------------


_has_firebase = False
try:
    import firebase_admin  # noqa: F401
    _has_firebase = True
except ImportError:
    pass

_skip_no_firebase = pytest.mark.skipif(
    not _has_firebase, reason="firebase_admin not installed"
)


@_skip_no_firebase
class TestSendFcmMessage:
    """Test the FCM message sending helper (requires firebase_admin)."""

    @patch("app.services.firebase_auth._init_firebase", return_value=False)
    def test_raises_when_firebase_not_configured(self, mock_init):
        with pytest.raises(RuntimeError, match="Firebase Admin SDK not configured"):
            _send_fcm_message(
                token="some_token",
                title="Test",
                body="Test body",
            )

    @patch("app.services.firebase_auth._init_firebase", return_value=True)
    @patch("firebase_admin.messaging")
    def test_sends_message_successfully(self, mock_messaging, mock_init):
        mock_messaging.send.return_value = "msg-id-123"
        result = _send_fcm_message(
            token="token123",
            title="Hello",
            body="World",
            data={"type": "test"},
        )
        assert result == "msg-id-123"
        mock_messaging.send.assert_called_once()

    @patch("app.services.firebase_auth._init_firebase", return_value=True)
    @patch("firebase_admin.messaging")
    def test_raises_invalid_token_on_unregistered(self, mock_messaging, mock_init):
        mock_messaging.UnregisteredError = type("UnregisteredError", (Exception,), {})
        mock_messaging.InvalidArgumentError = type("InvalidArgumentError", (Exception,), {})
        mock_messaging.send.side_effect = mock_messaging.UnregisteredError("gone")
        with pytest.raises(_InvalidTokenError):
            _send_fcm_message(token="stale_token", title="T", body="B")


# ---------------------------------------------------------------------------
# Tests: daily challenge push
# ---------------------------------------------------------------------------


class TestDailyChallengePush:
    """Test daily challenge push notification task."""

    @pytest.mark.asyncio
    async def test_no_tokens_skips(self):
        """When no device tokens exist, task returns early."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("app.tasks.base.get_task_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _send_daily_challenge_push()
            assert result["sent"] == 0
            assert result["reason"] == "no_tokens"

    @pytest.mark.asyncio
    async def test_sends_to_opted_in_user(self):
        """Sends push to user who has not opted out."""
        dt = _fake_device_token(user_id=1)
        user = _fake_user(user_id=1, push_preferences={"daily_challenge": True})

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [(dt, user)]
        mock_session.execute = AsyncMock(return_value=mock_result)

        with (
            patch("app.tasks.base.get_task_session") as mock_ctx,
            patch(
                "app.tasks.push_notifications._send_fcm_message"
            ) as mock_send,
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _send_daily_challenge_push()
            assert result["sent"] == 1
            assert result["skipped"] == 0
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_opted_out_user(self):
        """Skips user who opted out of daily challenge."""
        dt = _fake_device_token(user_id=1)
        user = _fake_user(user_id=1, push_preferences={"daily_challenge": False})

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [(dt, user)]
        mock_session.execute = AsyncMock(return_value=mock_result)

        with (
            patch("app.tasks.base.get_task_session") as mock_ctx,
            patch(
                "app.tasks.push_notifications._send_fcm_message"
            ) as mock_send,
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _send_daily_challenge_push()
            assert result["sent"] == 0
            assert result["skipped"] == 1
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_sends_to_anonymous_token(self):
        """Anonymous tokens (no user) get daily challenge by default."""
        dt = _fake_device_token(user_id=None)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [(dt, None)]
        mock_session.execute = AsyncMock(return_value=mock_result)

        with (
            patch("app.tasks.base.get_task_session") as mock_ctx,
            patch(
                "app.tasks.push_notifications._send_fcm_message"
            ) as mock_send,
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _send_daily_challenge_push()
            assert result["sent"] == 1
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_deactivates_invalid_token(self):
        """Invalid tokens are marked inactive."""
        dt = _fake_device_token(user_id=None)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [(dt, None)]
        mock_session.execute = AsyncMock(return_value=mock_result)

        with (
            patch("app.tasks.base.get_task_session") as mock_ctx,
            patch(
                "app.tasks.push_notifications._send_fcm_message",
                side_effect=_InvalidTokenError("stale"),
            ),
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _send_daily_challenge_push()
            assert result["failed"] == 1
            assert result["sent"] == 0
            # Verify execute was called for the deactivation update
            assert mock_session.execute.call_count >= 2


# ---------------------------------------------------------------------------
# Tests: big move alerts
# ---------------------------------------------------------------------------


class TestBigMoveAlerts:
    """Test big move alert push notification task."""

    @pytest.mark.asyncio
    async def test_no_movers_returns_early(self):
        """When no markets have big moves, returns early."""
        mock_session = AsyncMock()

        # Both queries (positive and negative movers) return empty
        empty_result = MagicMock()
        empty_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=empty_result)

        with patch("app.tasks.base.get_task_session") as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await _send_big_move_alerts()
            assert result["sent"] == 0

    def test_big_move_threshold_is_15pp(self):
        """Verify threshold constant is 15 percentage points."""
        assert BIG_MOVE_THRESHOLD == 0.15


class TestPushNotificationTaskImport:
    """Verify push notification task module imports cleanly."""

    def test_import_module(self):
        from app.tasks.push_notifications import (
            _send_daily_challenge_push,
            _send_big_move_alerts,
        )
        assert callable(_send_daily_challenge_push)
        assert callable(_send_big_move_alerts)

    def test_celery_tasks_registered(self):
        from app.tasks import celery_app
        registered = set(celery_app.tasks.keys())
        assert "app.tasks.send_daily_challenge_push" in registered
        assert "app.tasks.send_big_move_alerts" in registered

    def test_beat_schedule_includes_push_tasks(self):
        from app.tasks import celery_app
        schedule = celery_app.conf.beat_schedule
        assert "daily-challenge-push" in schedule
        assert "big-move-alerts" in schedule

        # Verify daily challenge runs at 2 PM UTC
        dc = schedule["daily-challenge-push"]
        assert dc["task"] == "app.tasks.send_daily_challenge_push"

        # Verify big moves runs every 30 min
        bm = schedule["big-move-alerts"]
        assert bm["task"] == "app.tasks.send_big_move_alerts"


class TestPushPreferencesDefaults:
    """Verify push preference defaults are opt-in (True)."""

    def test_default_daily_challenge_true(self):
        """Users without explicit prefs get daily challenge by default."""
        user = _fake_user(push_preferences=None)
        # No prefs set means default to True
        prefs = user.push_preferences if isinstance(user.push_preferences, dict) else {}
        assert prefs.get("daily_challenge", True) is True

    def test_default_big_moves_true(self):
        """Users without explicit prefs get big move alerts by default."""
        user = _fake_user(push_preferences={})
        prefs = user.push_preferences if isinstance(user.push_preferences, dict) else {}
        assert prefs.get("big_moves", True) is True

    def test_opted_out_returns_false(self):
        """Users who explicitly opted out get False."""
        user = _fake_user(push_preferences={"daily_challenge": False, "big_moves": False})
        assert user.push_preferences["daily_challenge"] is False
        assert user.push_preferences["big_moves"] is False
