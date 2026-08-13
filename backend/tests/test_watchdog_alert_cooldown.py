"""#1501 — the watchdog's Sentry emission cooldown.

Fingerprinting collapsed many readings into one ISSUE but Sentry bills EVENTS,
so a persistent stall still sent one event per watchdog run: 1,212 events, ~20%
of a monthly quota, from one function in 8 days.

The alert must not be lost — #1158 lists these as Sentry-ONLY classes — so the
contract under test is precisely: the FIRST occurrence always sends, repeats
inside the window do not, and a Redis failure fails OPEN.
"""

import pytest

from app.tasks import watchdog


class _FakeRedis:
    """Minimal SET NX EX behaviour."""

    def __init__(self):
        self.store = {}

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True


@pytest.fixture
def fake_rc(monkeypatch):
    rc = _FakeRedis()
    monkeypatch.setattr(watchdog, "_bounded_rc", lambda: rc)
    return rc


@pytest.fixture
def sent(monkeypatch):
    """Capture Sentry sends without touching the SDK."""
    calls = []

    class _Scope:
        fingerprint = None

        def set_tag(self, *a):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(watchdog.sentry_sdk, "new_scope", lambda: _Scope())
    monkeypatch.setattr(
        watchdog.sentry_sdk, "capture_message", lambda msg, level=None: calls.append(msg)
    )
    return calls


def test_first_alert_always_sends(fake_rc, sent):
    watchdog._capture_fingerprinted("creation_stall", "kalshi", "stalled 7.3h")
    assert sent == ["stalled 7.3h"]


def test_repeat_inside_window_is_suppressed(fake_rc, sent):
    for i in range(10):
        watchdog._capture_fingerprinted("creation_stall", "kalshi", f"stalled {i}h")
    assert len(sent) == 1, "only the first reading of one episode may bill quota"


def test_distinct_alert_classes_do_not_share_a_cooldown(fake_rc, sent):
    watchdog._capture_fingerprinted("creation_stall", "kalshi", "a")
    watchdog._capture_fingerprinted("phase_block", "kalshi", "b")
    assert len(sent) == 2


def test_distinct_providers_do_not_share_a_cooldown(fake_rc, sent):
    watchdog._capture_fingerprinted("creation_stall", "kalshi", "a")
    watchdog._capture_fingerprinted("creation_stall", "polymarket", "b")
    assert len(sent) == 2


def test_cooldown_fails_open_when_redis_is_down(monkeypatch, sent):
    """A telemetry-infra failure must never swallow an alarm."""

    def _boom():
        raise RuntimeError("redis unreachable")

    monkeypatch.setattr(watchdog, "_bounded_rc", _boom)
    watchdog._capture_fingerprinted("creation_stall", "kalshi", "a")
    watchdog._capture_fingerprinted("creation_stall", "kalshi", "b")
    assert len(sent) == 2, "must fail open, not suppress"


def test_cooldown_key_carries_a_ttl(fake_rc, sent):
    """Without an expiry the alert would fire once and then never again."""
    captured = {}
    orig = fake_rc.set

    def _spy(key, value, nx=False, ex=None):
        captured["ex"] = ex
        return orig(key, value, nx=nx, ex=ex)

    fake_rc.set = _spy
    watchdog._capture_fingerprinted("creation_stall", "kalshi", "a")
    assert captured["ex"] == watchdog.ALERT_COOLDOWN_SECONDS
    assert captured["ex"] > 0


# --- provider normalization --------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("kalshi_settled:fetch:KXNASDAQ100U:p0", "kalshi_settled:fetch"),
        ("kalshi_settled:fetch:KXMLBHRR:p1", "kalshi_settled:fetch"),
        ("poll_kalshi:upsert_loop", "poll_kalshi:upsert_loop"),
        ("poll_kalshi:get_events:decode", "poll_kalshi:get_events:decode"),
    ],
)
def test_provider_normalization_drops_ticker_and_page_tokens(raw, expected):
    assert watchdog._normalize_provider(raw) == expected


def test_same_condition_on_two_tickers_shares_one_cooldown(fake_rc, sent):
    """The fragmentation that produced ~23 separate watchdog issues."""
    watchdog._capture_fingerprinted("phase_block", "kalshi_settled:fetch:KXNASDAQ100U:p0", "a")
    watchdog._capture_fingerprinted("phase_block", "kalshi_settled:fetch:KXMLBHRR:p1", "b")
    assert len(sent) == 1


def test_normalization_never_returns_empty(fake_rc):
    assert watchdog._normalize_provider("KXNASDAQ100U") != ""
