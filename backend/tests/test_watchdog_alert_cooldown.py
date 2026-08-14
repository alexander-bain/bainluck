"""#1501 — the watchdog's Sentry emission cooldown.

Fingerprinting (#219E) collapsed many readings into one ISSUE, but Sentry bills
EVENTS, so a persistent stall still emitted one alarm per watchdog run. Measured
over the 2026-07-21 -> 07-29 cycle, culprit ``app.tasks.run_freshness_watchdog``:
**1,588 events — 24% of the entire 6,584-event cycle** — and it was TWO events
per reading:

* 805 from ``sentry_sdk.capture_message`` (fingerprinted, tagged);
* 774 from the ``logger.critical`` beside it, which the SDK's LoggingIntegration
  promotes to an event of its own (default ``event_level=logging.ERROR``).

A cooldown on only the first of those would have removed roughly half the volume
and looked like a fix. Both channels are behind one gate now.

The alert must not be lost — #1158 lists creation-stall and event-loop-block as
Sentry-ONLY classes with no board or cockpit equivalent — so the contract under
test is exactly: the FIRST occurrence always emits, repeats inside the window do
not, and a Redis failure fails OPEN.

Nothing here reads the wall clock (gotcha #44): the cooldown's expiry is asserted
through the TTL argument handed to Redis, never by advancing time.
"""

import logging

import pytest

from app.tasks import watchdog


class _FakeRedis:
    """Minimal SET NX EX behaviour."""

    def __init__(self):
        self.store = {}
        self.calls = []

    def set(self, key, value, nx=False, ex=None):
        self.calls.append({"key": key, "nx": nx, "ex": ex})
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


# --- the contract ------------------------------------------------------------

def test_first_alert_always_sends(fake_rc, sent):
    assert watchdog._alert("creation_stall", "kalshi", "stalled 7.3h") is True
    assert sent == ["stalled 7.3h"]


def test_repeat_inside_window_is_suppressed(fake_rc, sent):
    for i in range(10):
        watchdog._alert("creation_stall", "kalshi", f"stalled {i}h")
    assert len(sent) == 1, "only the first reading of one episode may bill quota"


def test_distinct_alert_classes_do_not_share_a_cooldown(fake_rc, sent):
    watchdog._alert("creation_stall", "kalshi", "a")
    watchdog._alert("phase_block", "kalshi", "b")
    assert len(sent) == 2


def test_distinct_providers_do_not_share_a_cooldown(fake_rc, sent):
    watchdog._alert("creation_stall", "kalshi", "a")
    watchdog._alert("creation_stall", "polymarket", "b")
    assert len(sent) == 2


def test_cooldown_fails_open_when_redis_is_down(monkeypatch, sent):
    """A telemetry-infra failure must never swallow an alarm."""

    def _boom():
        raise RuntimeError("redis unreachable")

    monkeypatch.setattr(watchdog, "_bounded_rc", _boom)
    watchdog._alert("creation_stall", "kalshi", "a")
    watchdog._alert("creation_stall", "kalshi", "b")
    assert len(sent) == 2, "must fail open, not suppress"


def test_cooldown_key_carries_a_ttl(fake_rc, sent):
    """Without an expiry the alert would fire once and then never again."""
    watchdog._alert("creation_stall", "kalshi", "a")
    assert fake_rc.calls[0]["ex"] == watchdog.ALERT_COOLDOWN_SECONDS
    assert fake_rc.calls[0]["ex"] > 0
    assert fake_rc.calls[0]["nx"] is True, "check-then-set would race between runs"


def test_cooldown_is_fleet_shared_not_per_process(fake_rc, sent):
    """The key lives in Redis, so a second dyno observing the same condition is
    suppressed too. This is the opposite trade-off from the before_send throttle
    (in-process, gotcha #39) and it is affordable here: this runs once per beat,
    not on every exception path."""
    watchdog._alert("creation_stall", "kalshi", "a")
    key = fake_rc.calls[0]["key"]
    assert key.startswith(watchdog._ALERT_COOLDOWN_PREFIX)
    assert "creation_stall" in key and "kalshi" in key


# --- the DUPLICATE-emission half of the fix ----------------------------------

def test_suppressed_path_logs_below_the_sentry_event_threshold(fake_rc, sent, caplog):
    """774 of the 1,588 events were the logger.critical twin. On the suppressed
    path the line must still reach the dyno logs, but BELOW logging.ERROR — the
    LoggingIntegration's default event_level — or the cooldown saves nothing."""
    watchdog._alert("creation_stall", "kalshi", "first")
    with caplog.at_level(logging.DEBUG, logger="app.tasks.watchdog"):
        watchdog._alert("creation_stall", "kalshi", "second reading")
    records = [r for r in caplog.records if "second reading" in r.getMessage()]
    assert records, "the suppressed alarm must still be logged"
    assert all(r.levelno < logging.ERROR for r in records), (
        "an ERROR-level log record is itself a billable Sentry event"
    )


def test_emitted_path_still_logs_critical(fake_rc, sent, caplog):
    """The other direction: a real first alarm stays loud in the logs."""
    with caplog.at_level(logging.DEBUG, logger="app.tasks.watchdog"):
        watchdog._alert("creation_stall", "kalshi", "the alarm")
    records = [r for r in caplog.records if "the alarm" in r.getMessage()]
    assert records and any(r.levelno == logging.CRITICAL for r in records)


def test_the_watchdog_logger_is_declared_a_duplicate_source():
    """And the SDK is told to ignore it, so the critical line costs no quota."""
    from app.utils.sentry_filter import DUPLICATE_EVENT_LOGGERS

    assert watchdog.logger.name in DUPLICATE_EVENT_LOGGERS


# --- provider normalization ---------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("kalshi_settled:fetch:KXNASDAQ100U:p0", "kalshi_settled:fetch"),
        ("kalshi_settled:fetch:KXMLBHRR:p1", "kalshi_settled:fetch"),
        ("kalshi_settled:sql:KXMLBHIT:p2", "kalshi_settled:sql"),
        ("poll_kalshi:upsert_loop", "poll_kalshi:upsert_loop"),
        ("poll_kalshi:get_events:decode", "poll_kalshi:get_events:decode"),
        # counter-shaped tokens, all observed in the real census
        ("poll_kalshi:fetch:unfiltered:p35:recv50", "poll_kalshi:fetch:unfiltered"),
        ("poll_kalshi:fetch:markets_backfill:155", "poll_kalshi:fetch:markets_backfill"),
        ("poll_kalshi:get_events:req:a0", "poll_kalshi:get_events:req"),
        ("poll_kalshi:fetch:supp:KXNBAGAME", "poll_kalshi:fetch:supp"),
    ],
)
def test_provider_normalization_drops_ticker_and_counter_tokens(raw, expected):
    assert watchdog._normalize_provider(raw) == expected


def test_same_condition_on_two_tickers_shares_one_cooldown(fake_rc, sent):
    """The fragmentation that produced ~23 separate watchdog issues."""
    watchdog._alert("phase_block", "kalshi_settled:fetch:KXNASDAQ100U:p0", "a")
    watchdog._alert("phase_block", "kalshi_settled:fetch:KXMLBHRR:p1", "b")
    assert len(sent) == 1


def test_same_phase_on_two_pages_shares_one_cooldown(fake_rc, sent):
    watchdog._alert("phase_block", "poll_kalshi:fetch:unfiltered:p17", "a")
    watchdog._alert("phase_block", "poll_kalshi:fetch:unfiltered:p66", "b")
    assert len(sent) == 1


def test_normalization_never_returns_empty(fake_rc):
    """A provider that normalizes away entirely must keep its raw form rather
    than collide with every other one."""
    assert watchdog._normalize_provider("KXNASDAQ100U") == "KXNASDAQ100U"
    assert watchdog._normalize_provider("p0") == "p0"


def test_genuinely_different_phases_still_alert_separately(fake_rc, sent):
    """Gotcha #43's other direction: normalization must not over-collapse."""
    watchdog._alert("phase_block", "poll_kalshi:upsert_loop", "a")
    watchdog._alert("phase_block", "poll_kalshi:orphan_cleanup", "b")
    watchdog._alert("phase_block", "kalshi_settled:sql:KXMLBHRR:p1", "c")
    assert len(sent) == 3


# --- the call sites must go through the gate ---------------------------------

def test_no_call_site_bypasses_the_cooldown():
    """A future caller reaching for _capture_fingerprinted directly would
    reintroduce the uncapped emission, and nothing would notice."""
    import inspect

    src = inspect.getsource(watchdog)
    # Exactly two textual occurrences: the `def`, and the single call inside
    # `_alert`. A third means a call site went around the cooldown.
    assert src.count("_capture_fingerprinted(") == 2, (
        "watchdog call sites must alert through _alert(), not _capture_fingerprinted()"
    )
    assert src.count("_alert(\"") + src.count("_alert(alert_class") >= 2
