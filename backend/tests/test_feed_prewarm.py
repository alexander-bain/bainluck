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


def test_warm_shapes_match_the_first_paint_requests():
    """Warming a shape the clients don't request warms a key nobody reads."""
    shapes = {s["label"]: s for s in pcp.FEED_PREWARM_SHAPES}
    assert set(shapes) == {
        "discover",
        "sports",
        "discover_native",
        "sports_native",
        "sports_native_events",
    }

    assert shapes["discover"]["limit"] == 20
    assert shapes["discover"]["offset"] == 0
    assert shapes["discover"]["event_pct"] == 0.15
    assert shapes["discover"]["mode"] is None

    assert shapes["sports"]["limit"] == 20
    assert shapes["sports"]["offset"] == 0
    assert shapes["sports"]["mode"] == "sports"
    assert shapes["sports"]["event_pct"] is None

    # LAT-P089: the native Discover first paint. A different limit is a
    # different cache key, and this one had no warmer at all.
    assert shapes["discover_native"]["limit"] == 50
    assert shapes["discover_native"]["offset"] == 0
    assert shapes["discover_native"]["event_pct"] == 0.15
    assert shapes["discover_native"]["mode"] is None

    # LAT-P099: the native SPORTS first paint — the same defect, on the tab
    # LAT-P089 was not looking at. Measured 872 ms p50, `X-Feed-Cache: miss`
    # 3 of 3, against 57 ms `shared_hit` 3 of 3 for the Discover row directly
    # above it, same client, same release, same session.
    assert shapes["sports_native"]["limit"] == 50
    assert shapes["sports_native"]["offset"] == 0
    assert shapes["sports_native"]["event_pct"] is None
    assert shapes["sports_native"]["mode"] == "sports"

    # LAT-P100: the native Sports tab's events-only backfill. Not the request
    # that gates first paint — the one that fills Live Now / Upcoming behind it —
    # and it was UNWARMABLE rather than merely unwarmed: `include_futures` is in
    # the cache key and `_prewarm_feed_shape` hardcoded it to True, so no entry
    # in this tuple could have expressed the shape.
    assert shapes["sports_native_events"]["limit"] == 200
    assert shapes["sports_native_events"]["offset"] == 0
    assert shapes["sports_native_events"]["include_futures"] is False
    assert shapes["sports_native_events"]["include_events"] is True
    # No mode and no event_pct: the Discover-default guard (`routes/feed.py:1822`)
    # requires include_futures to be true, so it SKIPS this request and leaves
    # both as sent. A warmer that supplied either would key differently.
    assert shapes["sports_native_events"]["mode"] is None
    assert shapes["sports_native_events"]["event_pct"] is None


def test_every_shape_declares_its_include_flags_explicitly():
    """LAT-P100 / bar C3. A default here would rebuild the trap one level down.

    `_prewarm_feed_shape` used to hardcode `include_events=True,
    include_futures=True` in its `get_feed` call. Both are part of the response
    cache key, so that single pair of literals did not just omit a shape — it
    made an entire CLASS of shape unwarmable, and the Sports tab's backfill sat
    in that class from the day the warmer was written. Nothing failed, because
    nothing asked.

    Replacing the literals with `shape.get(..., True)` would move the same defect
    one indirection deeper: the next author to add a shape and forget the key
    would warm `True` silently, exactly as before. So the flags are REQUIRED, and
    this is the test that makes them required.
    """
    for shape in pcp.FEED_PREWARM_SHAPES:
        for flag in ("include_events", "include_futures"):
            assert flag in shape, (
                f"warm shape {shape['label']!r} does not declare {flag!r} — it is "
                "part of the cache key, so an undeclared value warms a key the "
                "client never asks for and the failure is silent"
            )
            assert isinstance(shape[flag], bool)

    # And the warmer must READ them rather than re-hardcoding them. The AST check
    # is the point: an assertion on the shapes cannot see a literal in the call.
    source = textwrap.dedent(inspect.getsource(pcp._prewarm_feed_shape))
    tree = ast.parse(source)
    call = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "get_feed"
    )
    for kw in call.keywords:
        if kw.arg in ("include_events", "include_futures"):
            assert not isinstance(kw.value, ast.Constant), (
                f"the warmer passes a literal {kw.arg}={ast.dump(kw.value)} to "
                "get_feed — every shape that needs the other value is "
                "unwarmable, which is the LAT-P100 defect exactly"
            )


def test_every_native_first_paint_shape_is_warmed():
    """The set, not the members — this is the test that would have caught it.

    `test_warm_shapes_match_the_first_paint_requests` above asserts each shape
    it KNOWS about, which is exactly why it stayed green for the whole time the
    native Sports tab was paying a cold build: nobody had written the missing
    member down, so nothing could notice it was missing. Asserting over a
    declared NAMED set moves the failure from "someone remembers" to "the set
    is short".
    """
    labels = {s["label"] for s in pcp.FEED_PREWARM_SHAPES}
    missing = pcp.FEED_PREWARM_NATIVE_LABELS - labels
    assert not missing, (
        f"native first-paint shape(s) {sorted(missing)} are declared but not "
        "warmed — the tab pays a full cold build on every open, and the "
        "inert-principal share has no anonymous entry to route to"
    )
    assert not (pcp.FEED_PREWARM_NATIVE_LABELS & pcp.FEED_PREWARM_WEB_LABELS)


#: What each NATIVE client actually puts on the wire, transcribed once. The
#: numbers and strings in here are not trusted on their own — the two tests
#: below this dict pin `limit` and `mode` against the Swift sources — but the
#: SHAPE (which params are present, and what the route's Discover-default guard
#: leaves them as) has to be written down somewhere to be checkable at all.
#:
#: `mode` is the subtle one. Native Discover sends none, and the guard at
#: `routes/feed.py:1822` rewrites it to "discover"; native Sports sends
#: "sports" and the guard skips it, leaving `event_pct` as None. Both then key
#: through `{mode or 'discover'}`, which is why the warmer's `mode: None` and
#: the route's rewritten `"discover"` land on the same string.
NATIVE_CLIENT_REQUEST_SHAPES: dict[str, dict] = {
    "discover_native": dict(
        sport=None,
        limit=50,
        offset=0,
        include_events=True,
        include_futures=True,
        tags=None,
        event_pct=0.15,
        my_teams_only=False,
        mode="discover",  # the guard's rewrite of an absent mode
    ),
    "sports_native": dict(
        sport=None,
        limit=50,
        offset=0,
        include_events=True,
        include_futures=True,
        tags=None,
        event_pct=None,  # the guard SKIPS mode=sports, so this stays None
        my_teams_only=False,
        mode="sports",
    ),
    # LAT-P100. `APIClient.fetchSportsEventBackfill` -> `fetchFeed(limit: 200,
    # includeFutures: false)`, which sends no mode and no event_pct. The
    # Discover-default guard requires `include_futures` to be TRUE, so it does
    # not fire and neither value is rewritten — unlike `discover_native` above,
    # where the same absent mode IS rewritten to "discover". Both end up keying
    # through `{mode or 'discover'}`, which is why the two rows look
    # inconsistent and are not.
    "sports_native_events": dict(
        sport=None,
        limit=200,
        offset=0,
        include_events=True,
        include_futures=False,
        tags=None,
        event_pct=None,
        my_teams_only=False,
        mode=None,
    ),
}


@pytest.mark.parametrize("label", sorted(NATIVE_CLIENT_REQUEST_SHAPES))
def test_the_warmed_anon_key_is_the_key_the_inert_share_reads(label):
    """The whole fix in one assertion, provable without a deploy.

    A native client is the `s:<uuid>` principal, so it can never hit the key the
    warmer publishes directly. LAT-P089's inert-principal share
    (`routes/feed.py:2224`) is what saves it: when the personalization context
    equals a default-constructed one, the request re-derives the ANONYMOUS key
    of its own shape and reads that instead of building.

    So a warmed native shape helps only if the anonymous key the warmer
    publishes is byte-identical to the anonymous key the share computes. If the
    two strings differ the warmer warms a key nobody reads — which fails
    EXACTLY as silently as warming nothing, and is the failure mode LAT-P099
    was repairing when it found the Sports tab paying 872 ms a cold build with
    `X-Feed-Cache: miss` on 3 of 3 samples.

    Asserting it here rather than predicting it is the point: the alternative is
    shipping and finding out, and this class of defect does not announce itself
    — a broken warmer and a working one produce the same logs.
    """
    shape = next(
        s for s in pcp.FEED_PREWARM_SHAPES if s["label"] == label
    )
    # What the warmer publishes: `_prewarm_feed_shape` calls the route with an
    # anonymous synthetic request and no sport/tags/my_teams, passing the
    # shape's OWN include flags (LAT-P100 — they used to be literals here and in
    # the warmer, which is what made a whole class of shape unwarmable).
    warmed_key = feed_response_cache_key(
        user_id=None,
        session_id=None,
        sport=None,
        limit=shape["limit"],
        offset=shape["offset"],
        include_events=shape["include_events"],
        include_futures=shape["include_futures"],
        tags=None,
        event_pct=shape["event_pct"],
        my_teams_only=False,
        mode=shape["mode"],
    )
    # What the share reads: `feed_response_cache_key(user_id=None,
    # session_id=None, **_cache_shape)` over the CLIENT's request shape.
    client_shape = NATIVE_CLIENT_REQUEST_SHAPES[label]
    shared_key = feed_response_cache_key(
        user_id=None, session_id=None, **client_shape
    )
    assert warmed_key == shared_key, (
        f"{label}: the warmer publishes {warmed_key} but the inert-principal "
        f"share reads {shared_key} — the tab pays a full cold build on every "
        "open and nothing in the logs says so"
    )
    # And the private key must still be its own, or the share would be pointless.
    private_key = feed_response_cache_key(
        user_id=None, session_id="a-native-install-uuid", **client_shape
    )
    assert private_key != shared_key


def _sports_fetch_arguments(source: str) -> str:
    """Return the argument text of `FeedViewModel`'s `fetchFeed(mode: "sports")`.

    Scanning to the balanced close paren instead of pinning the whole literal
    keeps the guard honest when an argument that does NOT change the request
    shape is added — native/006 added a `trace:` closure and reddened master
    on a call that still asks mode=sports at the default limit. Callers assert
    on the returned text; an unfindable call returns "" so the guard fails
    closed rather than passing vacuously.
    """
    start = source.find('fetchFeed(mode: "sports"')
    if start < 0:
        return ""
    open_paren = source.index("(", start)
    depth = 0
    for i in range(open_paren, len(source)):
        if source[i] in "([{":
            depth += 1
        elif source[i] in ")]}":
            depth -= 1
            if depth == 0:
                return source[open_paren + 1 : i]
    return ""


def test_native_sports_warm_shape_tracks_the_ios_client():
    """Pin against the Swift constants, not a copy of the numbers.

    Two constants have to agree for this shape to warm anything: the mode
    string `FeedViewModel` sends, and the DEFAULT limit `APIClient.fetchFeed`
    applies when it is not given one. The second is the one that broke —
    nothing in `FeedViewModel` mentions 50, so a reader of the Sports call site
    cannot see which limit it asks for, and a warmer author reading only that
    file would write the web's 20.
    """
    view_model = (
        Path(__file__).resolve().parents[2]
        / "ios"
        / "Bain Luck"
        / "Bain Luck"
        / "ViewModels"
        / "FeedViewModel.swift"
    )
    client = (
        Path(__file__).resolve().parents[2]
        / "ios"
        / "Bain Luck"
        / "Bain Luck"
        / "Services"
        / "APIClient.swift"
    )
    if not (view_model.exists() and client.exists()):
        pytest.skip("ios sources not available")

    arguments = _sports_fetch_arguments(view_model.read_text())
    assert arguments, (
        "FeedViewModel no longer requests mode=sports at the default limit — "
        "re-derive the sports_native warm shape from whatever it asks now"
    )
    assert "limit:" not in arguments, (
        "the Sports call now passes an explicit limit — the warm shape below "
        "keys off APIClient's DEFAULT limit and would warm nothing"
    )
    limit_match = re.search(
        r"func fetchFeed\((?:[^)]*?)limit:\s*Int\s*=\s*(\d+)",
        client.read_text(),
        re.S,
    )
    assert limit_match, "could not read APIClient.fetchFeed's default limit"
    native_limit = int(limit_match.group(1))

    shape = next(
        s for s in pcp.FEED_PREWARM_SHAPES if s["label"] == "sports_native"
    )
    assert shape["limit"] == native_limit, (
        f"warmer warms limit={shape['limit']} but the native Sports first "
        f"paint requests limit={native_limit} — a different cache key, so "
        "nothing is warmed and the failure is silent"
    )
    assert shape["mode"] == "sports"
    assert shape["offset"] == 0
    # The Discover-default guard at routes/feed.py:1822 skips mode=sports, so
    # event_pct stays None on the request path. A warmer that supplied 0.15
    # here would key differently from the request and warm nothing.
    assert shape["event_pct"] is None


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
    web = [
        s for s in pcp.FEED_PREWARM_SHAPES if s["label"] in pcp.FEED_PREWARM_WEB_LABELS
    ]
    assert web, "the web first-paint shapes must not vanish from the warm set"
    for shape in web:
        assert shape["limit"] == frontend_limit, (
            f"warm shape {shape['label']} warms limit={shape['limit']} but the web "
            f"first paint requests limit={frontend_limit} — different cache key"
        )
    for shape in pcp.FEED_PREWARM_SHAPES:
        assert shape["offset"] == 0, "first paint is always offset 0"


def test_native_warm_shape_tracks_the_ios_first_page_limit():
    """Pin against the Swift constant, not a copy of the number.

    LAT-P089. The native shape is enrolled precisely BECAUSE its limit differs
    from the web's; a stale copy of that number here warms a key the app never
    asks for, which fails exactly as silently as warming nothing.
    """
    view_model = (
        Path(__file__).resolve().parents[2]
        / "ios"
        / "Bain Luck"
        / "Bain Luck"
        / "ViewModels"
        / "DiscoverViewModel.swift"
    )
    if not view_model.exists():  # iOS sources not present in this checkout
        pytest.skip("ios DiscoverViewModel.swift not available")
    source = view_model.read_text()

    limit_match = re.search(r"firstPageLimit\s*=\s*(\d+)", source)
    assert limit_match, "could not read firstPageLimit from DiscoverViewModel.swift"
    native_limit = int(limit_match.group(1))

    # The first-paint call site passes eventPct explicitly; read it rather than
    # trusting that it still matches the web's 0.15.
    pct_match = re.search(
        r"fetchDiscoverFeedResolvingPrincipal\(\s*\n?\s*limit:\s*Self\.firstPageLimit,"
        r"\s*offset:\s*0,\s*eventPct:\s*([0-9.]+)",
        source,
    )
    assert pct_match, "could not read the native first-paint eventPct"
    native_event_pct = float(pct_match.group(1))

    native = next(s for s in pcp.FEED_PREWARM_SHAPES if s["label"] == "discover_native")
    assert native["limit"] == native_limit, (
        f"warmer warms limit={native['limit']} but the native first paint requests "
        f"limit={native_limit} — different cache key, so nothing is warmed"
    )
    assert native["event_pct"] == native_event_pct
    assert native["offset"] == 0
    assert native["mode"] is None


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
    """The warm must never run unbounded inside the 2-minute beat.

    LAT-P100 replaced the per-shape deadline with ONE pass budget, so this is no
    longer a product that grows with the target count: the worst case is now a
    CONSTANT, and adding a target costs coverage inside the bound instead of
    pushing the bound toward `soft_time_limit`. The previous form fired at the
    moment of the addition rather than at the moment of the mistake, and each new
    shape had to buy its room by cutting everyone else's deadline.
    """
    worst_case = 20 + pcp.FEED_PREWARM_PASS_BUDGET_S
    assert worst_case < 120, (
        f"worst-case warm pass {worst_case}s exceeds soft_time_limit — this is "
        "now a constant, so if it fails someone raised the pass budget"
    )
    # And it must stay a constant. A budget re-derived from the target count is
    # the old defect wearing the new name.
    source = textwrap.dedent(inspect.getsource(pcp._prewarm_discover_feed_responses))
    assert "FEED_PREWARM_PASS_BUDGET_S" in source
    assert "* len(" not in source, (
        "the pass budget must not be multiplied by a target count — that is the "
        "per-item form this replaced"
    )


def test_no_target_can_be_starved_by_the_ones_ahead_of_it():
    """LAT-P100 / bar B8 — gotcha #34, executed rather than commented.

    A shared budget consumed in loop order starves whatever is last: give the
    pass 80 s and let each target take what it wants, and one slow first target
    spends the lot while the ones behind it get nothing. The failure is
    invisible — a starved warmer logs exactly what a healthy one logs, and the
    only symptom is users paying cold builds on the tabs that happen to sort
    late.

    `_prewarm_target_deadline` divides the REMAINING budget by the REMAINING
    targets, which makes the floor arithmetic instead of aspirational. This test
    runs the adversarial case: every target consumes its entire allowance, which
    is the exact scenario that starves a naive shared budget.
    """
    budget = pcp.FEED_PREWARM_PASS_BUDGET_S
    n = len(pcp._prewarm_targets())
    assert n >= 2

    floor = budget / n
    left = budget
    spent = 0.0
    for index in range(n):
        deadline = pcp._prewarm_target_deadline(left, n - index)
        assert deadline >= floor - 1e-9, (
            f"target {index} of {n} is allowed only {deadline:.3f}s against a "
            f"floor of {floor:.3f}s — the targets ahead of it starved it"
        )
        # The adversarial case: this target burns everything it was given.
        left = max(0.0, left - deadline)
        spent += deadline

    assert spent <= budget + 1e-9, (
        f"the pass can spend {spent:.3f}s against a budget of {budget}s"
    )

    # The upside the division buys: a target that finishes early hands its
    # unspent time to everyone behind it, so the common case (fast shapes) leaves
    # the LAST target with far more than its floor rather than exactly its floor.
    left = budget
    for index in range(n - 1):
        left = max(0.0, left - 0.5)  # every earlier target warms in 0.5s
    assert pcp._prewarm_target_deadline(left, 1) > floor

    # Degenerate inputs must not produce a negative or infinite deadline.
    assert pcp._prewarm_target_deadline(-5.0, 3) == 0.0
    assert pcp._prewarm_target_deadline(10.0, 0) == 0.0


def test_every_warm_target_is_in_the_budgeted_pass():
    """A budget that only bounds SOME of the work it shares a beat with is not one.

    Both shape families warm different routes through different writers, but they
    compete for the same two minutes. Enumerating them into one list is what lets
    a single budget cover them; this asserts nobody adds a family that quietly
    runs outside it.
    """
    labels = [label for label, _ in pcp._prewarm_targets()]
    assert len(labels) == len(set(labels)), f"duplicate warm target labels: {labels}"
    expected = {s["label"] for s in pcp.FEED_PREWARM_SHAPES} | {
        s["label"] for s in pcp.GROUPED_FEED_PREWARM_SHAPES
    }
    assert set(labels) == expected


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
