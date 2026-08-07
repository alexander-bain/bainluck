"""LAT-P001 — guards for the Discover/Sports cold-response pre-warm.

Production measurement 2026-08-05: `/api/feed` is bimodal — 13–16ms on a cache
hit/stale_hit, a p50 of 10,981ms on a genuine miss. Nothing warmed the response
cache except a user request that had already paid the cold build. These tests
pin the properties that make the pre-warm actually work, because every one of
its failure modes is SILENT — a warmer that writes the wrong key, warms a shape
nobody requests, or short-circuits on the stale mirror instead of rebuilding all
look exactly like a warmer that is working.
"""

import ast
import hashlib
import inspect
import json
import re
import textwrap
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.utils.feed_cache import (
    FEED_PREWARM_KEY_SCOPE_KEY,
    FEED_PREWARM_SCOPE_KEY,
    FEED_RESPONSE_STALE_TTL_SECONDS,
    feed_response_cache_key,
    feed_response_cache_ttl,
)
# NOTE: `from app.tasks import precompute_category_pages` resolves to the Celery
# TASK of that name registered in app/tasks/__init__.py, not the module. Pull the
# module out of sys.modules explicitly.
from importlib import import_module

pcp = import_module("app.tasks.precompute_category_pages")


# --- The key must not drift ---------------------------------------------------


def _legacy_key(
    *,
    user_id=None,
    session_id=None,
    sport=None,
    limit,
    offset,
    include_events=True,
    include_futures=True,
    tags=None,
    event_pct=None,
    my_teams_only=False,
    mode=None,
):
    """The exact inline f-string `routes/feed.py` used before LAT-P001."""
    user_part = (
        f"u:{user_id}" if user_id is not None else f"s:{session_id}" if session_id else "anon"
    )
    parts = (
        f"feed:{user_part}:{sport or 'all'}:{limit}:{offset}:{include_events}:"
        f"{include_futures}:{tags or ''}:{event_pct or ''}:{my_teams_only}:{mode or 'discover'}"
    )
    return f"feed_cache:{hashlib.md5(parts.encode()).hexdigest()}"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"limit": 20, "offset": 0, "event_pct": 0.15},
        {"limit": 20, "offset": 0, "mode": "sports"},
        {"limit": 50, "offset": 0, "event_pct": 0.15, "mode": "discover"},
        {"limit": 20, "offset": 20, "event_pct": 0.15},
        {"limit": 20, "offset": 0, "session_id": "abc-123"},
        {"limit": 20, "offset": 0, "user_id": 42},
        {"limit": 20, "offset": 0, "my_teams_only": True},
        {"limit": 20, "offset": 0, "sport": "basketball", "tags": '["sport:basketball"]'},
        {"limit": 20, "offset": 0, "include_events": False, "include_futures": False},
    ],
)
def test_extracted_key_matches_the_legacy_inline_formula(kwargs):
    """Extracting the key builder must not change a single byte of any key.

    A changed key would silently invalidate every warm entry in production.
    """
    assert feed_response_cache_key(**kwargs) == _legacy_key(**kwargs)


def test_principal_segments_are_distinct():
    base = {"limit": 20, "offset": 0, "event_pct": 0.15}
    anon = feed_response_cache_key(**base)
    session = feed_response_cache_key(**base, session_id="s1")
    user = feed_response_cache_key(**base, user_id=7)
    assert len({anon, session, user}) == 3, "principals must never share a cache key"


def test_anon_ttl_is_the_longest_lived():
    """The anon key is the one a first-time visitor hits and the one we warm."""
    assert feed_response_cache_ttl() == 60
    assert feed_response_cache_ttl(identified=True) == 5
    assert feed_response_cache_ttl(my_teams_only=True) == 30
    # The warm cadence (every 2 min, hosted in the candidate-base beat) must stay
    # inside the stale window, or the mirror decays and cold misses return.
    assert FEED_RESPONSE_STALE_TTL_SECONDS > 120


# --- The warmer must call the route faithfully --------------------------------


def test_prewarm_passes_every_get_feed_parameter_explicitly():
    """Any `get_feed` param the warmer omits silently becomes a `Query` object.

    `get_feed` is a FastAPI route: called directly as a Python function, an
    omitted parameter does NOT get its documented default, it gets the
    `Query(...)` object itself. That object is truthy and stringifies into the
    cache key, so a single missed parameter warms a garbage key that no request
    will ever read — and the warmer still logs success. This test turns "someone
    added a param to get_feed" into a red test instead of a silent regression.
    """
    from app.routes.feed import get_feed

    expected = set(inspect.signature(get_feed).parameters)

    source = textwrap.dedent(inspect.getsource(pcp._prewarm_feed_shape))
    tree = ast.parse(source)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "get_feed"
    ]
    assert len(calls) == 1, "expected exactly one get_feed call in the warmer"

    passed = {kw.arg for kw in calls[0].keywords}
    assert not calls[0].args, "warmer must pass get_feed args by keyword only"
    missing = expected - passed
    assert not missing, (
        f"warmer omits get_feed parameter(s) {sorted(missing)} — each would be a "
        f"Query object at runtime and would poison the cache key"
    )
    assert not (passed - expected), f"warmer passes unknown params {sorted(passed - expected)}"


def test_warm_shapes_match_the_web_first_paint_requests():
    """Warming a shape the clients don't request warms a key nobody reads."""
    shapes = {s["label"]: s for s in pcp.FEED_PREWARM_SHAPES}
    assert set(shapes) == {"discover", "sports"}

    assert shapes["discover"]["limit"] == 20
    assert shapes["discover"]["offset"] == 0
    assert shapes["discover"]["event_pct"] == 0.15
    assert shapes["discover"]["mode"] is None

    assert shapes["sports"]["limit"] == 20
    assert shapes["sports"]["offset"] == 0
    assert shapes["sports"]["mode"] == "sports"
    assert shapes["sports"]["event_pct"] is None


def test_warm_limit_tracks_the_frontend_page_limit():
    """Pin against the frontend's own constant, not a copy of the number."""
    paging = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "lib"
        / "discover"
        / "feedPaging.ts"
    )
    if not paging.exists():  # frontend not present in this checkout
        pytest.skip("frontend/lib/discover/feedPaging.ts not available")
    match = re.search(r"FEED_PAGE_LIMIT\s*=\s*(\d+)", paging.read_text())
    assert match, "could not read FEED_PAGE_LIMIT from feedPaging.ts"
    frontend_limit = int(match.group(1))
    for shape in pcp.FEED_PREWARM_SHAPES:
        assert shape["limit"] == frontend_limit, (
            f"warm shape {shape['label']} warms limit={shape['limit']} but the web "
            f"first paint requests limit={frontend_limit} — different cache key"
        )
        assert shape["offset"] == 0, "first paint is always offset 0"


# --- The warmer must publish only good payloads, under the resolved key -------


def _run_warm(payload, *, rc=None, resolved_key="feed_cache:deadbeef"):
    """Drive `_prewarm_feed_shape` with a stubbed `get_feed`."""
    rc = rc or MagicMock()
    captured = {}

    async def fake_get_feed(**kwargs):
        captured.update(kwargs)
        request = kwargs["request"]
        assert request.scope.get(FEED_PREWARM_SCOPE_KEY) is True, (
            "warmer must mark the request so the route skips the cache READ"
        )
        if resolved_key is not None:
            request.scope[FEED_PREWARM_KEY_SCOPE_KEY] = resolved_key
        return payload

    @asynccontextmanager
    async def fake_session():
        yield MagicMock()

    import asyncio

    with patch("app.routes.feed.get_feed", fake_get_feed), patch(
        "app.tasks.base.get_task_session", fake_session
    ):
        result = asyncio.run(
            pcp._prewarm_feed_shape(dict(pcp.FEED_PREWARM_SHAPES[0]), rc)
        )
    return result, rc, captured


def test_warmer_publishes_under_the_key_the_route_resolved():
    payload = {"items": [{"id": "a"}, {"id": "b"}], "total": 2}
    result, rc, captured = _run_warm(payload, resolved_key="feed_cache:abc123")

    assert result["outcome"] == "ok"
    assert result["items"] == 2

    written = {call.args[0]: call.args for call in rc.setex.call_args_list}
    assert "feed_cache:abc123" in written, "fresh key not published"
    assert "feed_cache:abc123:stale" in written, "stale mirror not published"
    assert written["feed_cache:abc123"][1] == 60
    assert written["feed_cache:abc123:stale"][1] == FEED_RESPONSE_STALE_TTL_SECONDS
    # Both mirrors hold the same body, and it is the built payload.
    assert json.loads(written["feed_cache:abc123"][2])["total"] == 2
    assert written["feed_cache:abc123"][2] == written["feed_cache:abc123:stale"][2]

    # The warmer must build ANONYMOUSLY — that is the whole point of one shared key.
    assert captured["user"] is None
    assert captured["request"].headers.get("x-session-id") is None
    assert captured["debug"] is False and captured["exclude_reviewed"] is False


def test_warmer_refuses_to_publish_a_degraded_build():
    """A partial build must never replace a good cached payload (C80 contract)."""
    payload = {
        "items": [{"id": "a"}],
        "build_quality": "degraded",
        "degraded_reason": "futures_timeout",
    }
    result, rc, _ = _run_warm(payload)
    assert result["outcome"] == "degraded"
    rc.setex.assert_not_called()


def test_warmer_refuses_to_publish_an_empty_feed():
    result, rc, _ = _run_warm({"items": [], "total": 0})
    assert result["outcome"] == "empty"
    rc.setex.assert_not_called()


def test_warmer_publishes_nothing_when_the_route_resolved_no_key():
    """No resolved key means the route did not take the cacheable path."""
    result, rc, _ = _run_warm({"items": [{"id": "a"}]}, resolved_key=None)
    assert result["outcome"] == "no_key"
    rc.setex.assert_not_called()


def test_warm_pass_is_decoupled_from_the_candidate_base():
    """A candidate-base failure must not stop the feed from being warmed.

    The base has three early-return paths (kill switch, deadline, empty build).
    If the pre-warm hung off its success path, a base hiccup would silently
    reintroduce the 5–11s cold miss with no signal.
    """
    import asyncio

    async def boom():
        raise RuntimeError("base build exploded")

    warmed = []

    async def fake_prewarm():
        warmed.append(True)
        return 2

    with patch.object(pcp, "_publish_discover_candidate_base", boom), patch.object(
        pcp, "_prewarm_discover_feed_responses", fake_prewarm
    ):
        result = asyncio.run(pcp._precompute_discover_candidate_base())

    assert warmed == [True], "feed pre-warm must run even when the base build fails"
    assert result["candidate_base"] == "error"
    assert result["feed_prewarm"] == 2


def test_prewarm_is_kill_switchable():
    import asyncio

    rc = MagicMock()
    rc.get.return_value = b"0"
    with patch("app.tasks.redis_state.get_redis_client", return_value=rc):
        result = asyncio.run(pcp._prewarm_discover_feed_responses())
    assert result == "disabled"
    rc.setex.assert_not_called()


def test_warm_cadence_stays_inside_the_stale_window():
    """The regression guard for the win itself.

    The pre-warm is hosted in the `precompute-discover-candidate-base` beat. The
    entire fix rests on that beat firing more often than the 300s `:stale` mirror
    expires — that is what makes the WORST case a visitor can see a ~15ms
    stale_hit instead of a 5–11s cold build. Reschedule the beat slower than the
    stale window and the cold misses come straight back, with nothing failing and
    no alert. This test is what makes that a red build.
    """
    from app.tasks import celery_app

    entry = celery_app.conf.beat_schedule.get("precompute-discover-candidate-base")
    assert entry, "the beat hosting the feed pre-warm is gone"

    sched = entry["schedule"]
    # Must fire every hour of every day — a windowed schedule would leave the
    # cache cold for the hours it skips.
    assert set(sched.hour) == set(range(24)), "warm beat must run every hour"
    assert len(sched.day_of_week) == 7, "warm beat must run every day"

    minutes = sorted(sched.minute)
    assert minutes, "warm beat has no minute schedule"
    gaps = [b - a for a, b in zip(minutes, minutes[1:])]
    gaps.append(60 - minutes[-1] + minutes[0])  # wrap across the hour boundary
    max_gap_s = max(gaps) * 60

    assert max_gap_s < FEED_RESPONSE_STALE_TTL_SECONDS, (
        f"warm beat can go {max_gap_s}s between fires but the stale mirror expires "
        f"after {FEED_RESPONSE_STALE_TTL_SECONDS}s — first visitors would pay the "
        f"full cold build again"
    )


def test_prewarm_is_bounded():
    """The warm must never run unbounded inside the 2-minute beat."""
    assert pcp.FEED_PREWARM_DEADLINE_S <= 30
    # Worst case: base deadline (20s) + one deadline per shape, under the task's
    # soft_time_limit of 120s.
    worst_case = 20 + pcp.FEED_PREWARM_DEADLINE_S * len(pcp.FEED_PREWARM_SHAPES)
    assert worst_case < 120, f"worst-case warm pass {worst_case}s exceeds soft_time_limit"


# --- The internal rebuild marker must be unreachable from HTTP ----------------


def test_prewarm_marker_is_scope_only_never_a_client_input():
    """If a client could set this, it would be a free DoS on our slowest endpoint."""
    from app.routes.feed import get_feed

    params = inspect.signature(get_feed).parameters
    assert FEED_PREWARM_SCOPE_KEY not in params
    assert "prewarm" not in " ".join(params).lower()

    source = inspect.getsource(get_feed)
    # The marker is read from the ASGI scope, never from headers or query params.
    assert f'request.scope.get(FEED_PREWARM_SCOPE_KEY)' in source or (
        "FEED_PREWARM_SCOPE_KEY" in source and "request.scope" in source
    )
    assert f'headers.get("{FEED_PREWARM_SCOPE_KEY}")' not in source


def test_prewarm_skips_the_cache_read_so_it_actually_rebuilds():
    """The route must skip the fresh AND stale reads when pre-warming.

    Reading the 300s stale mirror would return without rebuilding, so the warmer
    would re-publish the same ageing payload forever and never refresh it.
    """
    from app.routes.feed import get_feed

    source = inspect.getsource(get_feed)
    # Both reads are guarded by the marker.
    for target in ["_fresh = (", "_stale = ("]:
        assert target in source, f"expected guarded read {target!r}"
    guarded = source.count("if _prewarm_rebuild\n") + source.count("if _prewarm_rebuild")
    assert guarded >= 2, "both the fresh and stale reads must be pre-warm guarded"
