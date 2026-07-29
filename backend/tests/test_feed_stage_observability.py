"""Item 1 (Queue 273 / #1475): production-safe feed stage observability.

Ordinary slow /api/feed requests must self-report which stage consumed the
budget, the candidate/returned card-type coverage, and the cache/singleflight
outcome — without the admin ``debug=true`` path, which is unusable on a cold
build because it exceeds the 30s router cutoff. The export must be:

- identity-free (fixed stage names + integers + coarse cache status only),
- non-blocking (header build + at most one sampled log line, no Redis),
- always emitted for slow requests (never sampled away).
"""

import logging


from app.routes.feed import (
    FEED_STAGE_ALWAYS_LOG_MS,
    _emit_feed_stage_observability,
    _feed_stage_sample_rate,
    _summarize_feed_stages,
)


class _Resp:
    def __init__(self):
        self.headers = {}


_TIMINGS = [
    {"stage": "personalization", "ms": 12.0, "elapsed_ms": 12.0},
    {"stage": "events", "ms": 450.0, "elapsed_ms": 462.0},
    {
        "stage": "futures.pool_nonsports_editorial_recall",
        "ms": 8200.0,
        "elapsed_ms": 8662.0,
    },
    {"stage": "futures", "ms": 300.0, "elapsed_ms": 8962.0},
    {"stage": "ranking", "ms": 50.0, "elapsed_ms": 9012.0},
]

_COUNTS = {"type_event": 8, "type_futures": 10, "total": 18, "returned": 18}


def test_summarize_collapses_stage_ms():
    out = _summarize_feed_stages(_TIMINGS)
    assert out["events"] == 450.0
    assert out["futures.pool_nonsports_editorial_recall"] == 8200.0
    assert out["ranking"] == 50.0
    # None/empty timing list is safe.
    assert _summarize_feed_stages(None) == {}
    assert _summarize_feed_stages([]) == {}


def test_summarize_ignores_non_numeric_and_blank_stage():
    out = _summarize_feed_stages(
        [{"stage": "", "ms": 5.0}, {"stage": "x", "ms": "bad"}]
    )
    assert "" not in out
    assert out["x"] == 0.0


def test_headers_emitted_identity_free(monkeypatch):
    monkeypatch.setenv("FEED_STAGE_SAMPLE_RATE", "0")
    resp = _Resp()
    _emit_feed_stage_observability(
        resp,
        timings=_TIMINGS,
        cache_status="miss",
        singleflight="leader",
        counts=_COUNTS,
        started_at=__import__("time").perf_counter(),
    )
    stages = resp.headers["X-Feed-Stages"]
    counts = resp.headers["X-Feed-Counts"]
    assert "futures.pool_nonsports_editorial_recall=8200.0" in stages
    assert "events=450.0" in stages
    assert resp.headers["X-Feed-Singleflight"] == "leader"
    assert "total=18" in counts and "returned=18" in counts
    # Header values are bounded (router/proxy header-size safety).
    assert len(stages) <= 900
    assert len(counts) <= 400


def test_no_pii_in_headers():
    resp = _Resp()
    _emit_feed_stage_observability(
        resp,
        timings=_TIMINGS,
        cache_status="miss",
        singleflight="none",
        counts=_COUNTS,
        started_at=__import__("time").perf_counter(),
    )
    blob = resp.headers["X-Feed-Stages"] + resp.headers["X-Feed-Counts"]
    # Only fixed stage-name tokens + numbers appear; assert no market/user text.
    for banned in ("http", "@", "session", "user:", "u:", "s:", "?"):
        assert banned not in blob.lower()


def test_sampling_off_no_log(monkeypatch, caplog):
    monkeypatch.setenv("FEED_STAGE_SAMPLE_RATE", "0")
    assert _feed_stage_sample_rate() == 0.0
    resp = _Resp()
    import time as _t

    with caplog.at_level(logging.INFO, logger="app.routes.feed"):
        # Fast request (started just now → total well under the always-log floor).
        _emit_feed_stage_observability(
            resp,
            timings=_TIMINGS,
            cache_status="hit",
            singleflight="none",
            counts=_COUNTS,
            started_at=_t.perf_counter(),
        )
    assert not any(
        "feed_stage_observability" in r.message for r in caplog.records
    ), "sampling off + fast request must not log"
    # Headers still emit even with sampling off.
    assert "X-Feed-Stages" in resp.headers


def test_sampling_on_logs(monkeypatch, caplog):
    monkeypatch.setenv("FEED_STAGE_SAMPLE_RATE", "1")
    assert _feed_stage_sample_rate() == 1.0
    resp = _Resp()
    import time as _t

    with caplog.at_level(logging.INFO, logger="app.routes.feed"):
        _emit_feed_stage_observability(
            resp,
            timings=_TIMINGS,
            cache_status="miss",
            singleflight="leader",
            counts=_COUNTS,
            started_at=_t.perf_counter(),
        )
    assert any("feed_stage_observability" in r.message for r in caplog.records)


def test_slow_request_always_logs_even_when_sampling_off(monkeypatch, caplog):
    """A cold/degraded miss (the case we most need to see) must log regardless
    of the sample rate — it is never sampled away."""
    monkeypatch.setenv("FEED_STAGE_SAMPLE_RATE", "0")
    resp = _Resp()
    import time as _t

    # started_at far enough in the past that total_ms >= the always-log floor.
    slow_start = _t.perf_counter() - (FEED_STAGE_ALWAYS_LOG_MS / 1000.0) - 1.0
    with caplog.at_level(logging.INFO, logger="app.routes.feed"):
        _emit_feed_stage_observability(
            resp,
            timings=_TIMINGS,
            cache_status="miss",
            singleflight="leader",
            counts=_COUNTS,
            started_at=slow_start,
        )
    assert any("feed_stage_observability" in r.message for r in caplog.records)


def test_sample_rate_clamped_and_defaulted(monkeypatch):
    monkeypatch.setenv("FEED_STAGE_SAMPLE_RATE", "9")
    assert _feed_stage_sample_rate() == 1.0
    monkeypatch.setenv("FEED_STAGE_SAMPLE_RATE", "-3")
    assert _feed_stage_sample_rate() == 0.0
    monkeypatch.setenv("FEED_STAGE_SAMPLE_RATE", "notanumber")
    assert _feed_stage_sample_rate() == 0.02
    monkeypatch.delenv("FEED_STAGE_SAMPLE_RATE", raising=False)
    assert _feed_stage_sample_rate() == 0.02


def test_emit_never_raises_on_bad_input():
    """Observability must never break the feed, even on malformed timings."""
    resp = _Resp()
    _emit_feed_stage_observability(
        resp,
        timings=[{"stage": None}, {"nope": 1}],
        cache_status="miss",
        singleflight="none",
        counts={},
        started_at=None,  # forces an internal TypeError that must be swallowed
    )
    # Swallowed: no exception propagated (headers may or may not be set).
