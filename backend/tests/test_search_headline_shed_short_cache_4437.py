"""#4437 (b): a /search answer whose ONLY shed stage is the headline lane is cached, briefly.

THE SHIP. `chi` timed its headline lane out on every build (2,031-2,094 ms, Nov 7),
and a degraded answer was never cached, so every repeat of `chi` on the Search page
paid a full 3.3-3.4 s build. Such an answer still carries its teams, games and
futures. It is now written for `SEARCH_THIN_RESPONSE_TTL_SECONDS` (30 s) — never
the 180 s ceiling — and only when it has content, so a cut-short answer is never
served back as "No results". Every other shed stage stays uncached.
"""

import inspect

from app.utils.search_cache import (
    SEARCH_RESPONSE_TTL_SECONDS,
    SEARCH_THIN_RESPONSE_TTL_SECONDS,
    shed_answer_ttl_seconds,
)

FULL = {"results": [{"id": 1}], "futures": [], "teams": [], "event_concepts": []}


def _ttl(degraded, payload=FULL, debug_timing=False):
    return shed_answer_ttl_seconds(degraded, payload, debug_timing=debug_timing)


def test_a_headline_only_shed_with_content_lives_the_short_ttl():
    assert _ttl(["headline_contenders"]) == SEARCH_THIN_RESPONSE_TTL_SECONDS
    assert SEARCH_THIN_RESPONSE_TTL_SECONDS < SEARCH_RESPONSE_TTL_SECONDS


def test_any_other_shed_stage_is_still_never_written():
    for stages in (["futures"], ["teams"], ["event_count"], ["futures_refill"],
                   ["headline_contenders", "futures"], ["events"]):
        assert _ttl(stages) is None, stages


def test_an_empty_shed_answer_is_never_written():
    """It would be served back as a page with nothing on it."""
    empty = {"results": [], "futures": [], "teams": [], "event_concepts": []}
    assert _ttl(["headline_contenders"], empty) is None


def test_each_section_counts_as_content():
    for key in ("results", "futures", "teams", "event_concepts"):
        payload = {"results": [], "futures": [], "teams": [], "event_concepts": []}
        payload[key] = [{"x": 1}]
        assert _ttl(["headline_contenders"], payload) == SEARCH_THIN_RESPONSE_TTL_SECONDS, key


def test_a_complete_answer_is_not_this_helpers_business():
    assert _ttl([]) is None


def test_timing_requests_are_never_written():
    assert _ttl(["headline_contenders"], debug_timing=True) is None


def test_the_route_writes_through_the_helper_only_after_the_complete_answer_branch():
    from app.routes import events

    src = inspect.getsource(events.search_events)
    complete = src.index("if not degraded and not debug_timing:")
    shed = src.index("_shed_ttl := shed_answer_ttl_seconds(")
    assert complete < shed
    branch = src[shed: src.index("_record_search_query(_payload", shed)]
    assert "_publish_shed_search_answer(_search_cache_key, _payload, _shed_ttl)" in branch
    assert "_force_search_cache_rebuild" not in branch, "the warmer flag stays off write conditions"


def test_the_shed_write_respects_the_kill_switch_and_never_raises(monkeypatch):
    from app.routes import events

    writes = []

    class _RC:
        def setex(self, *a):
            writes.append(a)

    import app.tasks.redis_state as rs

    monkeypatch.setattr(rs, "get_redis_client", lambda *a, **k: _RC())
    monkeypatch.setattr(events, "search_response_cache_enabled", lambda: False)
    events._publish_shed_search_answer("k", {"results": [1]}, 30)
    assert writes == []
    monkeypatch.setattr(events, "search_response_cache_enabled", lambda: True)
    events._publish_shed_search_answer("k", {"results": [1]}, 30)
    assert writes and writes[0][:2] == ("k", 30)

    def _boom(*a, **k):
        raise RuntimeError("redis down")

    monkeypatch.setattr(rs, "get_redis_client", _boom)
    events._publish_shed_search_answer("k", {"results": [1]}, 30)  # must not raise
