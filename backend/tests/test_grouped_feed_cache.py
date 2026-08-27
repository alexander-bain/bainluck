"""LAT-P100 — the grouped-feed response cache, and the key both writers share.

`GET /api/futures/grouped-feed` is the Sports tab's THIRD request, on both
surfaces, and it had no server cache of any kind while costing 1,034.5 ms p50
(native shape, max 1,308) and 683.0 ms p50 (web shape) on production slug
`7833da68` — paid by every person on every open.

The failure mode this suite exists for is not "the cache is slow". It is the one
LAT-P001 closed for the feed and LAT-P099 then hit anyway from the other
direction: **a warmer that publishes a key nobody reads runs, succeeds, logs
success, and changes nothing.** A broken warmer and a working one produce
identical logs, so the equality has to be asserted rather than observed.
"""

import ast
import inspect
import textwrap
from importlib import import_module

import pytest

from app.utils.grouped_feed_cache import (
    GROUPED_FEED_PREWARM_SCOPE_KEY,
    GROUPED_FEED_STALE_TTL_SECONDS,
    GROUPED_FEED_TTL_SECONDS,
    grouped_feed_cache_key,
)

pcp = import_module("app.tasks.precompute_category_pages")


# --- The key contract ---------------------------------------------------------


def test_the_key_covers_every_parameter_the_route_branches_on():
    """Derived from the route's own signature, not from a copy of its params.

    A param that changes the response but not the key serves the wrong body to
    the next caller; a param that changes the key but not the response fragments
    the cache into entries nothing ever reuses. Reading the signature means
    adding a filter to the route without adding it here is a red test rather
    than a silent bug.
    """
    from app.routes.futures import grouped_feed

    route_params = set(inspect.signature(grouped_feed).parameters)
    # `request`/`response`/`db` are plumbing, not selectors.
    selectors = route_params - {"request", "response", "db"}
    key_params = set(inspect.signature(grouped_feed_cache_key).parameters)

    missing = selectors - key_params
    assert not missing, (
        f"the route selects on {sorted(missing)} but the cache key does not — "
        "two different responses would share one entry"
    )
    assert not (key_params - selectors), (
        f"the key uses {sorted(key_params - selectors)}, which the route does "
        "not select on — that fragments the cache for no benefit"
    )


@pytest.mark.parametrize(
    "a,b",
    [
        (dict(limit=20), dict(limit=50)),
        (dict(limit=20), dict(limit=20, sports_only=True)),
        (dict(limit=20), dict(limit=20, category="sports")),
        (dict(limit=20), dict(limit=20, sport="basketball_nba")),
        (
            dict(limit=20, sports_only=True),
            dict(limit=20, sports_only=False),
        ),
    ],
)
def test_different_shapes_get_different_keys(a, b):
    assert grouped_feed_cache_key(**a) != grouped_feed_cache_key(**b)


def test_the_same_shape_gets_the_same_key_however_it_is_spelled():
    """`sports_only` arrives as a real bool and `limit` as an int; pin both."""
    assert grouped_feed_cache_key(
        category=None, sport=None, sports_only=False, limit=20
    ) == grouped_feed_cache_key(limit=20)
    # A truthy non-bool must not key differently from True — FastAPI coerces, but
    # the warmer calls the function directly and is not coerced for it.
    assert grouped_feed_cache_key(limit=20, sports_only=1) == grouped_feed_cache_key(
        limit=20, sports_only=True
    )
    assert grouped_feed_cache_key(limit="20") == grouped_feed_cache_key(limit=20)


def test_the_key_is_not_principal_scoped_and_must_not_become_so():
    """One entry per shape serves everybody, and that is a correctness claim.

    The route reads no user, no session and no personalization context — its
    response is a pure function of four query params. That is what makes a single
    shared entry safe. If a principal ever enters this route, this key becomes a
    cross-user leak, so the absence is asserted rather than assumed.
    """
    from app.routes.futures import grouped_feed

    source = inspect.getsource(grouped_feed)
    for forbidden in ("current_user", "get_current_user", "x-session-id", "user_id"):
        assert forbidden not in source, (
            f"{forbidden!r} appeared in grouped_feed — the cache key has no "
            "principal segment, so this is a cross-user leak, not a slowdown"
        )


# --- The TTLs are chosen against the warm cadence, not by taste ---------------


def test_the_fresh_ttl_outlives_the_warm_cadence():
    """A fresh TTL below the beat interval hands cold builds to the gap.

    This is the number that is easy to get wrong in a way that reads as "the
    cache does not seem to help": warm every 120 s behind a 60 s TTL and the
    entry is missing for half of every cycle. Asserted against the schedule
    rather than against a literal, so re-timing the beat fails here instead of
    quietly reintroducing the gap.
    """
    from app.tasks import celery_app

    entry = celery_app.conf.beat_schedule.get("precompute-discover-candidate-base")
    assert entry, "the beat hosting the grouped-feed pre-warm is gone"
    minutes = sorted(entry["schedule"].minute)
    gaps = [b - a for a, b in zip(minutes, minutes[1:])]
    gaps.append(60 - minutes[-1] + minutes[0])
    max_gap_s = max(gaps) * 60

    assert GROUPED_FEED_TTL_SECONDS > max_gap_s, (
        f"the entry expires after {GROUPED_FEED_TTL_SECONDS}s but the beat can go "
        f"{max_gap_s}s between fires — whoever arrives in the gap pays the build"
    )
    assert (
        GROUPED_FEED_STALE_TTL_SECONDS > GROUPED_FEED_TTL_SECONDS
    ), "the stale mirror must outlive the fresh entry or it can never be read"


# --- The warmer must reach the key the route reads ----------------------------


def test_prewarm_passes_every_grouped_feed_parameter_explicitly():
    """An omitted param is a `Query` object, and it stringifies into the key.

    `grouped_feed` is a FastAPI route: called directly as a Python function, an
    omitted parameter does not get its documented default, it gets the
    `Query(...)` object itself. That object is truthy, so a single missed
    parameter changes the route's own key derivation and the warmer warms
    something no request will ever read — while still logging success.
    """
    from app.routes.futures import grouped_feed

    expected = set(inspect.signature(grouped_feed).parameters)
    source = textwrap.dedent(inspect.getsource(pcp._prewarm_grouped_feed_shape))
    calls = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "grouped_feed"
    ]
    assert len(calls) == 1, "expected exactly one grouped_feed call in the warmer"
    assert not calls[0].args, "warmer must pass grouped_feed args by keyword only"

    passed = {kw.arg for kw in calls[0].keywords}
    missing = expected - passed
    assert not missing, (
        f"warmer omits grouped_feed parameter(s) {sorted(missing)} — each would "
        "be a Query object at runtime and would poison the cache key"
    )
    assert not (passed - expected)


@pytest.mark.parametrize(
    "label", sorted(s["label"] for s in pcp.GROUPED_FEED_PREWARM_SHAPES)
)
def test_the_warmed_key_is_the_key_the_client_request_reads(label):
    """Bar C1 — the whole fix in one assertion, provable without a deploy.

    The route is the single writer: the warmer calls it with the pre-warm marker
    and the ROUTE publishes under the key it derived itself. So the equality that
    has to hold is between the warm SHAPE and what the client puts on the wire —
    and that is checkable here, offline, instead of after a deploy.
    """
    shape = next(s for s in pcp.GROUPED_FEED_PREWARM_SHAPES if s["label"] == label)
    warmed = grouped_feed_cache_key(
        category=shape["category"],
        sport=shape["sport"],
        sports_only=shape["sports_only"],
        limit=shape["limit"],
    )
    client_shape = CLIENT_GROUPED_REQUEST_SHAPES[label]
    read = grouped_feed_cache_key(**client_shape)
    assert warmed == read, (
        f"{label}: the warmer publishes {warmed} but the client reads {read} — "
        "the tab pays the full build on every open and nothing in the logs says so"
    )


#: What each client actually puts on the wire. The native tab sends NO
#: `sports_only`; the web page sends `sports_only=true`. That single difference
#: is a different key and therefore a different entry — the same "one row below
#: the line being edited" shape difference that cost the Sports tab 872 ms for
#: two days in LAT-P099.
CLIENT_GROUPED_REQUEST_SHAPES: dict[str, dict] = {
    "grouped_native": dict(category=None, sport=None, sports_only=False, limit=20),
    "grouped_web": dict(category=None, sport=None, sports_only=True, limit=20),
}


def test_both_real_client_shapes_are_warmed():
    """The set, not the members — the test that catches a missing member."""
    labels = {s["label"] for s in pcp.GROUPED_FEED_PREWARM_SHAPES}
    assert labels == set(CLIENT_GROUPED_REQUEST_SHAPES), (
        "a real grouped-feed client shape is declared but not warmed — that "
        "surface pays the full build on every open"
    )


def test_the_native_grouped_shape_tracks_the_ios_client():
    """Pin against the Swift source, not a copy of the number."""
    from pathlib import Path

    client = (
        Path(__file__).resolve().parents[2]
        / "ios"
        / "Bain Luck"
        / "Bain Luck"
        / "Services"
        / "APIClient.swift"
    )
    view_model = (
        Path(__file__).resolve().parents[2]
        / "ios"
        / "Bain Luck"
        / "Bain Luck"
        / "ViewModels"
        / "FeedViewModel.swift"
    )
    if not (client.exists() and view_model.exists()):
        pytest.skip("ios sources not available")

    import re

    match = re.search(r"groupedFeedLimit\s*=\s*(\d+)", view_model.read_text())
    assert match, "could not read FeedViewModel.groupedFeedLimit"
    native_limit = int(match.group(1))

    shape = next(
        s for s in pcp.GROUPED_FEED_PREWARM_SHAPES if s["label"] == "grouped_native"
    )
    assert shape["limit"] == native_limit, (
        f"warming limit={shape['limit']} but the native tab asks for "
        f"limit={native_limit} — a different key, so nothing is warmed"
    )
    # The native call site passes ONLY a limit; if it starts sending
    # `sports_only` the warm shape has to follow it or go stale silently.
    assert "sports_only" not in client.read_text().split("grouped-feed")[1][:200]
    assert shape["sports_only"] is False


def test_the_web_grouped_shape_tracks_the_sports_page():
    """Pin against the page's own call, not a copy of it."""
    from pathlib import Path

    page = (
        Path(__file__).resolve().parents[2] / "frontend" / "app" / "sports" / "page.tsx"
    )
    if not page.exists():
        pytest.skip("frontend/app/sports/page.tsx not available")
    source = page.read_text()
    assert "fetchGroupedFeed({ limit: 20, sportsOnly: true })" in source, (
        "the web Sports page no longer requests grouped-feed at limit=20 with "
        "sportsOnly — re-derive the grouped_web warm shape from what it asks now"
    )
    shape = next(
        s for s in pcp.GROUPED_FEED_PREWARM_SHAPES if s["label"] == "grouped_web"
    )
    assert shape["limit"] == 20
    assert shape["sports_only"] is True


# --- The pre-warm marker must be unreachable from HTTP ------------------------


def test_the_prewarm_marker_is_scope_only_never_a_client_input():
    """If a client could set this, it would be a free lever to force cold builds."""
    from app.routes.futures import grouped_feed

    params = inspect.signature(grouped_feed).parameters
    assert GROUPED_FEED_PREWARM_SCOPE_KEY not in params
    assert "prewarm" not in " ".join(params).lower()

    source = inspect.getsource(grouped_feed)
    assert "request.scope.get(GROUPED_FEED_PREWARM_SCOPE_KEY)" in source
    assert f'headers.get("{GROUPED_FEED_PREWARM_SCOPE_KEY}")' not in source
    assert "Query" not in source.split("_prewarm_rebuild")[1][:200]


def test_the_prewarm_marker_suppresses_the_read_but_not_the_write():
    """A warmer that went through the cache read would never refresh anything.

    It would return the ageing entry, report success, and re-publish nothing —
    indistinguishable from working, until the payload is an hour old. The marker
    therefore has to skip the READ only; the write is unconditional (modulo the
    empty guard), which is also what lets a plain request-path miss populate the
    cache when the beat is broken.
    """
    from app.routes.futures import grouped_feed

    source = inspect.getsource(grouped_feed)
    assert (
        "if not _prewarm_rebuild:" in source
    ), "the cache READ must be skipped when pre-warming"
    # The publish must NOT be inside a `not _prewarm_rebuild` branch.
    publish_line = next(
        line
        for line in source.splitlines()
        if "_publish_grouped_feed_cache" in line and "await" in line
    )
    indent = len(publish_line) - len(publish_line.lstrip())
    assert indent <= 8, (
        "the publish is nested deeper than the empty-feed guard — check it is "
        "not gated on the pre-warm marker, or the warmer writes nothing"
    )


def test_an_empty_feed_is_never_published():
    """An empty read must not become shared truth for three minutes.

    Publishing a transient empty response is strictly worse than the build it
    replaced: everybody gets the empty one until it expires. Same contract the
    feed pre-warm enforces (Queue 283 / C80).
    """
    from app.routes.futures import grouped_feed

    source = inspect.getsource(grouped_feed)
    assert (
        'if payload["feed"]:' in source
    ), "the publish is not guarded on a non-empty feed"
