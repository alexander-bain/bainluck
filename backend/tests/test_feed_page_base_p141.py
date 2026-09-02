"""LAT-P141 — the page base: one build serves every page of the scroll.

WHAT THIS GUARDS, AND WHY IT IS NOT A LATENCY TEST.

``GET /api/feed`` builds the whole ranked list and then slices
``feed_items[offset : offset + limit]``. ``offset`` is not a build input — it
reaches the build at that one expression and nowhere else. The response cache
nevertheless keys on it, so every page after the first was a guaranteed cold
build of a list the server had already produced. Measured on production
2026-08-30, one fresh ``x-session-id`` per sample, native Discover shape:
offset=0 46 ms ``shared_hit``, offset=50 **1,329 ms** ``miss``, offset=100
**1,232 ms** ``miss``; web offset=20 1,033 ms, offset=40 1,164 ms, against
``total`` 105 — the entire feed is three native pages and two of them cost 28x
the first.

None of the guards below measure a millisecond. They pin the two things that
can go WRONG rather than slow:

* **Serving the wrong list.** The base is only sound because it is the
  ANONYMOUS build. The key therefore has no principal parameter at all and the
  route publishes/reads it only under LAT-P089's equality predicate. A build
  input added to the response key but forgotten here would serve page 2 of a
  different list, and no latency instrument on earth would notice.
* **Ending a scroll early.** ``has_more`` comes off ``total``. A truncated or
  half-written base that under-reports it would silently cut the feed short.
  ``render_feed_page_from_base`` fails CLOSED on that, and that refusal is
  guarded here in both directions.

The route-level tests at the bottom exist because of the plant-must-hit-the-
render rule: every helper below can be perfect while ``get_feed`` still folds
the base out of its own path, and only a test that drives the real route can
tell the difference.
"""

import inspect
import json
from importlib import import_module

import pytest

from app.routes.feed import get_feed
from app.utils import request_cache as _rc
from app.utils.feed_cache import (
    FEED_PAGE_BASE_BUILT_AT_FIELD,
    FEED_PAGE_BASE_CACHE_PREFIX,
    FEED_PAGE_BASE_ENV,
    FEED_RESPONSE_CACHE_PREFIX,
    feed_page_base_built_at,
    feed_page_base_cache_key,
    feed_page_base_enabled,
    feed_response_cache_key,
    render_feed_page_from_base,
)

feed_module = import_module("app.routes.feed")


def _base(n=105, **extra):
    """A well-formed page base of ``n`` items."""
    body = {
        "items": [{"type": "futures", "data": {"id": i}} for i in range(n)],
        "total": n,
        FEED_PAGE_BASE_BUILT_AT_FIELD: 1_700_000_000.0,
    }
    body.update(extra)
    return body


# ---------------------------------------------------------------------------
# A. The renderer — pure, no clock, no I/O (gotcha #44 cannot reach it)
# ---------------------------------------------------------------------------


def test_page_one_is_the_first_window():
    page = render_feed_page_from_base(_base(), limit=50, offset=0)
    assert [it["data"]["id"] for it in page["items"]] == list(range(0, 50))


def test_page_two_is_the_second_window_and_that_is_the_whole_point():
    page = render_feed_page_from_base(_base(), limit=50, offset=50)
    assert [it["data"]["id"] for it in page["items"]] == list(range(50, 100))


def test_the_last_partial_page_returns_only_what_is_left():
    page = render_feed_page_from_base(_base(), limit=50, offset=100)
    assert [it["data"]["id"] for it in page["items"]] == [100, 101, 102, 103, 104]


def test_an_offset_past_the_end_is_an_empty_page_not_an_error():
    page = render_feed_page_from_base(_base(), limit=50, offset=500)
    assert page["items"] == []
    assert page["has_more"] is False


def test_total_is_the_full_list_not_the_page():
    page = render_feed_page_from_base(_base(), limit=50, offset=50)
    assert page["total"] == 105
    assert len(page["items"]) == 50


def test_limit_and_offset_are_echoed_from_the_request_not_the_base():
    page = render_feed_page_from_base(_base(), limit=20, offset=40)
    assert page["limit"] == 20
    assert page["offset"] == 40


@pytest.mark.parametrize(
    "offset,limit,expected",
    [
        (0, 50, True),
        (50, 50, True),
        (100, 50, False),
        # The exact boundary: a page that ends ON total has no more.
        (55, 50, False),
        (54, 50, True),
    ],
)
def test_has_more_is_the_builds_own_expression(offset, limit, expected):
    """``(offset + limit) < total`` — the native client advances by the SERVER
    page boundary (``DiscoverViewModel.swift``), so any other expression walks
    it off the end of the list or strands the tail."""
    page = render_feed_page_from_base(_base(), limit=limit, offset=offset)
    assert page["has_more"] is expected


def test_the_bases_build_time_never_leaks_into_the_response_shape():
    page = render_feed_page_from_base(_base(), limit=50, offset=0)
    assert FEED_PAGE_BASE_BUILT_AT_FIELD not in page


def test_cache_metadata_is_per_serve_and_is_dropped():
    page = render_feed_page_from_base(
        _base(cache={"status": "miss"}), limit=50, offset=0
    )
    assert "cache" not in page


def test_envelope_fields_ride_along():
    """``build_quality`` and friends belong to the build, not the window."""
    page = render_feed_page_from_base(
        _base(build_quality="complete", personalized=False), limit=50, offset=50
    )
    assert page["build_quality"] == "complete"
    assert page["personalized"] is False


def test_rendering_does_not_mutate_the_base():
    base = _base()
    before = json.dumps(base, sort_keys=True)
    render_feed_page_from_base(base, limit=50, offset=50)
    render_feed_page_from_base(base, limit=50, offset=0)
    assert json.dumps(base, sort_keys=True) == before


def test_two_renders_of_the_same_base_agree():
    base = _base()
    a = render_feed_page_from_base(base, limit=50, offset=50)
    b = render_feed_page_from_base(base, limit=50, offset=50)
    assert a == b


# --- the fail-closed half ---------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "not a dict",
        [],
        42,
        {},
        {"items": "nope", "total": 3},
        {"items": None, "total": 0},
        {"items": [{"a": 1}]},  # no total at all
        {"items": [{"a": 1}], "total": "1"},  # total is not an int
        {"items": [{"a": 1}], "total": None},
    ],
)
def test_an_unusable_base_refuses_rather_than_guessing(bad):
    assert render_feed_page_from_base(bad, limit=50, offset=0) is None


def test_a_truncated_base_is_refused_because_it_would_end_the_scroll_early():
    """``total`` disagreeing with ``len(items)`` is the one failure that is
    invisible in the served page: 50 correct-looking cards and a ``has_more``
    computed off a number the list cannot support."""
    truncated = _base(n=105)
    truncated["items"] = truncated["items"][:40]
    assert render_feed_page_from_base(truncated, limit=50, offset=0) is None


def test_an_overlong_base_is_refused_in_the_same_direction():
    overlong = _base(n=105)
    overlong["total"] = 90
    assert render_feed_page_from_base(overlong, limit=50, offset=0) is None


# ---------------------------------------------------------------------------
# B. The key — where a wrong answer would come from
# ---------------------------------------------------------------------------


def _cache_shape_params() -> set[str]:
    """The build-input names ``get_feed`` puts in its response-cache shape.

    Read out of the route's own source rather than re-typed, so this test
    tracks the dict that actually exists.
    """
    src = inspect.getsource(get_feed)
    start = src.index("_cache_shape = dict(")
    body = src[start + len("_cache_shape = dict(") :]
    body = body[: body.index(")")]
    return {
        line.split("=", 1)[0].strip()
        for line in body.split(",")
        if "=" in line
    }


# The response-key inputs that are NOT build inputs, and so are deliberately
# absent from the base key. Every name here is a claim that the field SELECTS
# from the built list and never changes it:
#
#   offset     — a window onto the list (LAT-P141).
#   live_only  — a filter on the list (UX-1035 / #2709): the "Live Now" rail is
#                the live part of the SAME ranking the page below it shows.
#
# Adding a third name is a real decision, not a formality: it says one stored
# base may serve two different responses, and it is only true while the field is
# applied downstream of the build. `test_the_live_projection_is_applied_at_the_
# slice_not_in_the_pools` and its sibling below pin that for `live_only`.
_PROJECTIONS_NOT_BUILD_INPUTS = {"offset", "live_only"}


def test_the_base_key_covers_every_build_input_the_response_key_covers():
    """🔴 THE DRIFT GUARD. Add a build input to ``_cache_shape`` and forget it
    here and page 2 comes off a list built under different inputs. That is a
    WRONG page, served fast, with nothing measuring it."""
    shape = _cache_shape_params()
    keyed = set(inspect.signature(feed_page_base_cache_key).parameters)
    expected = shape - _PROJECTIONS_NOT_BUILD_INPUTS
    assert expected == keyed, (
        "feed_page_base_cache_key must key on exactly _cache_shape minus "
        f"{sorted(_PROJECTIONS_NOT_BUILD_INPUTS)}; "
        f"missing={expected - keyed} extra={keyed - expected}"
    )


def test_offset_is_not_a_parameter_at_all_not_merely_defaulted():
    """Structural, not conventional: a caller cannot pass an offset it does not
    accept, so no future edit can key a base per page by accident."""
    assert "offset" not in inspect.signature(feed_page_base_cache_key).parameters


def test_no_principal_can_be_keyed_into_a_base():
    """The base is ALWAYS the anonymous build. There is no argument by which a
    personalized list could be stored under one."""
    params = set(inspect.signature(feed_page_base_cache_key).parameters)
    assert "user_id" not in params
    assert "session_id" not in params


def test_the_same_shape_gives_the_same_key():
    a = feed_page_base_cache_key(limit=50, event_pct=0.15)
    b = feed_page_base_cache_key(limit=50, event_pct=0.15)
    assert a == b


@pytest.mark.parametrize(
    "kwargs",
    [
        {"limit": 20},
        {"limit": 50, "sport": "basketball"},
        {"limit": 50, "include_events": False},
        {"limit": 50, "include_futures": False},
        {"limit": 50, "tags": '["sport:basketball"]'},
        {"limit": 50, "my_teams_only": True},
        {"limit": 50, "mode": "sports"},
        {"limit": 50, "event_pct": 0.5},
    ],
)
def test_every_build_input_changes_the_key(kwargs):
    baseline = feed_page_base_cache_key(limit=50)
    assert feed_page_base_cache_key(**kwargs) != baseline


def test_limit_is_a_build_input_and_native_and_web_get_their_own_base():
    """``apply_discover_display_chain`` sizes several windows from ``limit``, so
    50 and 20 are two different LISTS, not two windows on one."""
    assert feed_page_base_cache_key(limit=50, event_pct=0.15) != (
        feed_page_base_cache_key(limit=20, event_pct=0.15)
    )


def test_the_base_key_is_not_the_response_key():
    assert feed_page_base_cache_key(limit=50, event_pct=0.15) != (
        feed_response_cache_key(limit=50, offset=0, event_pct=0.15)
    )


def test_the_base_lives_under_the_prefix_feed_invalidation_scans():
    """``invalidate_feed_response_cache`` deletes ``feed_cache:*``. A base
    outside that namespace would survive an invalidation and re-serve the
    pre-invalidation list on the very next scroll."""
    assert FEED_PAGE_BASE_CACHE_PREFIX.startswith(f"{FEED_RESPONSE_CACHE_PREFIX}:")
    assert feed_page_base_cache_key(limit=50).startswith(
        f"{FEED_RESPONSE_CACHE_PREFIX}:"
    )


# ---------------------------------------------------------------------------
# C. The kill switch and the provenance field
# ---------------------------------------------------------------------------


def test_unset_means_enabled(monkeypatch):
    monkeypatch.delenv(FEED_PAGE_BASE_ENV, raising=False)
    assert feed_page_base_enabled() is True


@pytest.mark.parametrize("value", ["0", "false", "FALSE", "no", "off", " Off "])
def test_the_operator_can_turn_it_off_without_a_deploy(monkeypatch, value):
    monkeypatch.setenv(FEED_PAGE_BASE_ENV, value)
    assert feed_page_base_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "banana", ""])
def test_an_unrecognised_value_stays_enabled(monkeypatch, value):
    """A typo must not silently switch a latency fix off and leave the cold
    builds back with nobody knowing why."""
    monkeypatch.setenv(FEED_PAGE_BASE_ENV, value)
    assert feed_page_base_enabled() is True


def test_it_is_a_separate_lever_from_the_inert_principal_share(monkeypatch):
    monkeypatch.setenv("FEED_INERT_PRINCIPAL_SHARE", "0")
    monkeypatch.delenv(FEED_PAGE_BASE_ENV, raising=False)
    assert feed_page_base_enabled() is True


def test_built_at_is_read_off_the_base():
    assert feed_page_base_built_at(_base()) == 1_700_000_000.0


@pytest.mark.parametrize(
    "bad", [None, "x", {}, {FEED_PAGE_BASE_BUILT_AT_FIELD: "soon"}]
)
def test_a_base_with_no_usable_build_time_reports_unknown_not_now(bad):
    """CERT-409: ``None`` degrades to read-time, which is the pre-fix behaviour.
    Minting a fresh timestamp here would restart the live ceiling's clock at
    every hop — the exact defect that ruling exists for."""
    assert feed_page_base_built_at(bad) is None


# ---------------------------------------------------------------------------
# D. The route — the base must reach the RENDER, not merely exist
# ---------------------------------------------------------------------------


def test_the_scrub_runs_over_the_whole_list_not_just_the_page():
    """The internal-key strip used to iterate ``paginated``. Publishing the base
    off a list scrubbed only in its first window would ship ``_rank_score``,
    ``_quality_story_key`` and the rest to every reader of page 2 — and the
    public-item-contract test, which only ever sees page 1, would stay green."""
    src = inspect.getsource(get_feed)
    marker = "# Remove internal sort/debug keys"
    tail = src[src.index(marker) :]
    loop = next(l for l in tail.splitlines() if l.strip().startswith("for item in"))
    assert loop.strip() == "for item in feed_items:"


def test_the_route_refuses_the_base_for_a_personalized_reader():
    """The soundness argument is LAT-P089's equality argument and nothing else.
    If this clause goes, identified users start reading the anonymous list."""
    src = inspect.getsource(get_feed)
    block = src[src.index("_page_base_key = None") :]
    block = block[: block.index("_page_base_key = feed_page_base_cache_key")]
    assert "ctx == PersonalizationContext()" in block
    assert "not my_teams_only" in block
    assert "feed_page_base_enabled()" in block


def test_the_warmer_never_reads_the_base():
    """LAT-P001's rule, one tier down: a warmer served from any cache refreshes
    nothing and reports success. The base is the tier the warmer exists to
    fill."""
    src = inspect.getsource(get_feed)
    block = src[src.index("_page_base_key = feed_page_base_cache_key") :]
    block = block[: block.index("_base_body =")]
    assert "_prewarm_rebuild" in block


def test_the_warmer_still_publishes_the_base():
    """The other half of the rule above: it must skip the READ and keep the
    WRITE, or the whole scroll stays cold for everyone."""
    src = inspect.getsource(get_feed)
    publish = src[src.index("if _page_base_key:") :]
    assert "_prewarm_rebuild" not in publish[: publish.index("schedule_background")]


def test_the_base_shape_is_derived_from_the_cache_shape_by_exclusion():
    """Re-typing the field list is how the drift in
    ``test_the_base_key_covers_every_build_input...`` would be introduced. This
    pins the mechanism, not just the outcome."""
    src = inspect.getsource(get_feed)
    assert (
        'k: v\n                for k, v in _cache_shape.items()\n'
        '                if k not in ("offset", "live_only")'
    ) in src


def test_the_live_projection_never_rebinds_the_list_the_base_is_published_from():
    """🔴 THE TRAP UX-1035 HAD TO STEP AROUND, PINNED.

    The page base is published hundreds of lines below the filter, from
    ``feed_items`` and ``total``. Filtering either one IN PLACE would store a
    ``live_only`` request's 14-item sub-list as the ANONYMOUS base — every
    subsequent reader on the site served a feed of live games only. Worse, the
    near-miss is silent in the other direction: the base's integrity check is
    ``len(items) == total``, so rebinding one name and not the other makes
    ``render_feed_page_from_base`` fail closed and disables the page base
    site-wide, which reads as a latency regression with no wrong answer to
    trace it back to.

    So the projection must land in NEW names. This asserts the mechanism,
    because the outcome — a poisoned shared cache under a rare query param —
    is exactly the kind no unit test naturally reaches.
    """
    src = inspect.getsource(get_feed)
    assert (
        "_page_items = filter_live_items(feed_items) if live_only else feed_items"
        in src
    )
    assert "feed_items = filter_live_items" not in src
    assert "total = len(filter_live_items" not in src
    # And the base still publishes the WHOLE list under the WHOLE count.
    publish = src[src.index("if _page_base_key:") :]
    publish = publish[: publish.index("schedule_background")]
    assert '_page_base_body["items"] = feed_items' in publish
    assert '_page_base_body["total"] = total' in publish


def test_the_live_projection_is_applied_at_the_slice_not_in_the_pools():
    """``live_only`` is licensed to skip the base key ONLY because it selects
    from the built list. If it ever reaches the pools or the display chain it
    becomes a build input, one base would serve two different lists, and the
    exclusion in ``_PROJECTIONS_NOT_BUILD_INPUTS`` becomes a wrong answer."""
    src = inspect.getsource(get_feed)
    chain_at = src.index("feed_items, _chain_meta = apply_discover_display_chain(")
    slice_at = src.index("_page_items = filter_live_items(")
    assert slice_at > chain_at, "the live filter must run AFTER the display chain"
    # Nothing between the route signature and the chain may branch on it: the
    # only earlier mentions allowed are the parameter itself and the two cache
    # shapes, none of which change what gets built.
    head = src[:chain_at]
    # An EXACT allow-list, not a substring sniff. Every line above the build
    # that names `live_only` is here, and each one is either the parameter, a
    # cache key, or the base-hit SERVE — which is the projection applied to a
    # list that was already built, the very thing being licensed. A new line
    # has to be added here consciously, and adding one is the moment to ask
    # whether it is still a projection.
    allowed = {
        "live_only: bool = Query(",
        "live_only=live_only,",
        'if k not in ("offset", "live_only")',
        "_base_body, limit=limit, offset=offset, live_only=live_only",
    }
    for raw in head.splitlines():
        # Comments and the docstring cannot reach the build path; only code can.
        line = raw.split("#", 1)[0].strip()
        if "live_only" not in line:
            continue
        assert line in allowed, (
            "live_only reached the build path at: " + line
        )


def test_the_base_is_stored_with_the_anonymous_ttl_not_the_builders():
    """``_live_ttls`` asks ``identified=bool(feed_user or feed_session_id)`` —
    a statement about the READER. A fresh session that happens to build the base
    must not stamp its 5 s lifetime on the anonymous list, or the entry expires
    before the next scroll and this fix measures as noise."""
    src = inspect.getsource(get_feed)
    publish = src[src.index("if _page_base_key:") :]
    publish = publish[: publish.index("schedule_background")]
    assert "identified=False" in publish
    assert "_live_ttls(" not in publish


def test_a_degraded_build_never_becomes_the_base():
    """A partial build is handed to its own caller and to coalesced waiters, and
    is never shared truth. The base is shared truth by definition."""
    src = inspect.getsource(get_feed)
    guard = src.index("if _cache_key and not _is_degraded_build and _shared_redis")
    assert src.index("if _page_base_key:") > guard
    # ...and inside it: the next dedent to that guard's own level must come
    # after the publish block.
    tail = src[guard:]
    assert tail.index("if _page_base_key:") < tail.index("\n        # Item 1 (Queue")
