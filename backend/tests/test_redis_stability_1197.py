"""#1197 (r246 option a + c) — Redis connection pool/recycle hardening.

Guards the pool/keepalive tuning that attacks the Heroku Redis TLS-handshake churn
(~294/24h that #233's bare keepalive didn't move) and the safety-net threshold
alarm. These are config-shape + pure-logic assertions — no live Redis needed."""

from app.tasks.config import socket_keepalive_options


class TestSocketKeepaliveOptions:
    def test_returns_dict_of_int_keys(self):
        opts = socket_keepalive_options()
        assert isinstance(opts, dict)
        # Every key is a resolved socket-option constant (int); values are the timers.
        for k, v in opts.items():
            assert isinstance(k, int)
            assert isinstance(v, int) and v > 0

    def test_platform_guarded_never_raises(self):
        # macOS CI lacks TCP_KEEPIDLE; the helper must degrade, not raise.
        socket_keepalive_options()  # no exception == pass


class TestCeleryRedisStabilityConfig:
    def test_broker_and_backend_carry_retry_and_keepalive(self):
        from app.tasks import celery_app

        c = celery_app.conf
        for opts in (c.broker_transport_options, c.result_backend_transport_options):
            assert opts.get("socket_keepalive") is True
            assert opts.get("retry_on_timeout") is True
            assert opts.get("health_check_interval") == 25
            assert "socket_keepalive_options" in opts
        assert c.broker_connection_retry_on_startup is True
        assert c.redis_retry_on_timeout is True


class TestRedisStateHelpersHardened:
    def test_sync_client_constructs_with_keepalive(self):
        # Construction must not connect; it just wires the pool kwargs.
        from app.tasks.redis_state import get_redis_client

        client = get_redis_client()
        assert client is not None

    def test_async_client_constructs(self):
        from app.tasks.redis_state import get_async_redis_client

        assert get_async_redis_client() is not None


class TestRedisChurnAlarm:
    def test_detects_connection_error_signatures(self):
        from app.tasks.sentry_snapshot import _is_redis_conn_error

        assert _is_redis_conn_error(
            {"title": "ConnectionError: Error 8 connecting to redis :10819", "culprit": ""}
        )
        assert _is_redis_conn_error(
            {"title": "Connection to Redis lost: Retry (15/20)", "culprit": ""}
        )
        assert _is_redis_conn_error(
            {"title": "redis [SSL: UNEXPECTED_EOF_WHILE_READING]", "culprit": "celery.backends.redis"}
        )

    def test_ignores_unrelated_issues(self):
        from app.tasks.sentry_snapshot import _is_redis_conn_error

        assert not _is_redis_conn_error({"title": "ValueError in feed", "culprit": "app.routes.feed"})
        assert not _is_redis_conn_error({"title": "Postgres timeout", "culprit": "db"})

    def test_threshold_is_above_current_churn(self):
        # r246 sets the safety net above the ~294/24h current level so it doesn't
        # page while option (a) is validated, but fires if the churn worsens.
        from app.tasks.sentry_snapshot import REDIS_ERROR_ALARM_THRESHOLD

        assert REDIS_ERROR_ALARM_THRESHOLD >= 294
