"""#5105 — a page built under opening seating cannot be read back as a legacy page.

Seating reorders the whole Discover deck, so a seated build and an unseated one
are two different lists. Both cache tiers that hold a list — the per-page
response entry and the shared whole-deck base — therefore take an opt-in
``opening_seating`` discriminator. This file pins the contract the future route
wiring will rely on:

* ``False`` (the default, and what every caller passes today) hashes the
  byte-identical legacy key — pinned as literals computed on ``ca8362c6e8``
  BEFORE the parameter existed, so "unchanged" is measured, not self-consistent.
* ``True`` separates the response key, the base key AND the edition policy
  fingerprint together, for every principal and every category/collections
  shape, while staying under the prefixes ``invalidate_feed_response_cache``
  scans.
* The route derives the value from ONE internal served switch that is
  ``False`` (``routes/feed.py::_DISCOVER_OPENING_SEATING_SERVED``); no warmer,
  env var or query parameter can turn it on.

Pure: no Redis, no DB, no network.
"""

from __future__ import annotations

import inspect
import pathlib

import pytest

from app.routes import feed as feed_route
from app.utils import feed_cache
from app.utils.feed_cache import (
    FEED_OPENING_SEATING_KEY_MARKER,
    FEED_PAGE_BASE_CACHE_PREFIX,
    FEED_RESPONSE_CACHE_PREFIX,
    feed_page_base_cache_key,
    feed_response_cache_key,
)
from app.utils.feed_editions import (
    _OPENING_SEATING_POLICY_MARKER,
    edition_policy_fingerprint,
)

_APP = pathlib.Path(feed_cache.__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# A. Legacy keys are byte-identical — literals from the pre-change tree
# ---------------------------------------------------------------------------

#: (kwargs, key) computed on ca8362c6e8 before ``opening_seating`` existed.
_LEGACY_RESPONSE = [
    (dict(limit=50, offset=0, event_pct=0.15), "feed_cache:9a5e7d22943a58feb0a5932ad9d84fee"),
    (
        dict(
            user_id=42,
            limit=20,
            offset=20,
            category="economics",
            edition="abcd1234",
            collections="hub:1:r3",
            mode="discover",
            event_pct=0.15,
        ),
        "feed_cache:882531e58990a1100276f36ad3b126fd",
    ),
    (
        dict(
            session_id="sess-x",
            limit=50,
            offset=0,
            sport="basketball",
            tags='["sport:basketball"]',
            mode="sports",
        ),
        "feed_cache:06e22020e75a15484d4c379cd64e8db3",
    ),
]

_LEGACY_BASE = [
    (dict(limit=50, event_pct=0.15), "feed_cache:pagebase:9abfad6b35b47fb5aadebdb1fd3e5ac3"),
    (
        dict(limit=20, category="economics", collections="hub:1:r3", event_pct=0.15),
        "feed_cache:pagebase:39a61be8c4bcbd7dff135746181bc08c",
    ),
    (
        dict(limit=50, sport="basketball", mode="sports", include_futures=False),
        "feed_cache:pagebase:22fe2db81a68db7a84d40277d8210dcc",
    ),
]


@pytest.mark.parametrize("kwargs,expected", _LEGACY_RESPONSE)
def test_a_legacy_response_key_is_the_literal_it_was_before(kwargs, expected):
    assert feed_response_cache_key(**kwargs) == expected
    assert feed_response_cache_key(**kwargs, opening_seating=False) == expected


@pytest.mark.parametrize("kwargs,expected", _LEGACY_BASE)
def test_a_legacy_base_key_is_the_literal_it_was_before(kwargs, expected):
    assert feed_page_base_cache_key(**kwargs) == expected
    assert feed_page_base_cache_key(**kwargs, opening_seating=False) == expected


def test_the_parameter_defaults_to_false_on_both_helpers():
    for fn in (feed_response_cache_key, feed_page_base_cache_key):
        param = inspect.signature(fn).parameters["opening_seating"]
        assert param.kind is inspect.Parameter.KEYWORD_ONLY
        assert param.default is False


# ---------------------------------------------------------------------------
# B. True separates response, base and edition policy — together
# ---------------------------------------------------------------------------

_PRINCIPALS = [
    pytest.param({}, None, id="anon"),
    pytest.param({"user_id": 42}, "u:42", id="auth"),
    pytest.param({"session_id": "sess-x"}, "s:sess-x", id="session"),
]

_BUILD_SHAPES = [
    pytest.param(dict(limit=50, event_pct=0.15), id="discover-native"),
    pytest.param(dict(limit=20, event_pct=0.15), id="discover-web"),
    pytest.param(dict(limit=50, category="economics"), id="category"),
    pytest.param(dict(limit=50, event_pct=0.15, collections="hub:1:r3"), id="collections"),
    pytest.param(
        dict(limit=20, category="economics", collections="hub:1:r3"),
        id="category+collections",
    ),
    pytest.param(dict(limit=50, sport="basketball", mode="sports"), id="sports"),
]


@pytest.mark.parametrize("principal,principal_str", _PRINCIPALS)
@pytest.mark.parametrize("shape", _BUILD_SHAPES)
def test_true_separates_all_three_identities_for_every_shape(principal, principal_str, shape):
    resp = lambda **kw: feed_response_cache_key(**principal, **shape, offset=0, **kw)  # noqa: E731
    base_shape = {k: v for k, v in shape.items() if k != "collections"}
    policy = lambda **kw: edition_policy_fingerprint(  # noqa: E731
        **base_shape, principal=principal_str, **kw
    )

    assert resp(opening_seating=True) != resp(opening_seating=False)
    assert feed_page_base_cache_key(**shape, opening_seating=True) != (
        feed_page_base_cache_key(**shape, opening_seating=False)
    )
    assert policy(opening_seating=True) != policy(opening_seating=False)


@pytest.mark.parametrize("shape", _BUILD_SHAPES)
def test_true_keys_stay_under_the_prefixes_invalidation_scans(shape):
    """``invalidate_feed_response_cache`` deletes ``feed_cache:*``. A seated
    entry outside that namespace would outlive an invalidation."""
    assert feed_response_cache_key(**shape, offset=0, opening_seating=True).startswith(
        f"{FEED_RESPONSE_CACHE_PREFIX}:"
    )
    assert feed_page_base_cache_key(**shape, opening_seating=True).startswith(
        f"{FEED_PAGE_BASE_CACHE_PREFIX}:"
    )


def test_true_keys_are_stable_across_calls():
    shape = dict(limit=50, event_pct=0.15, category="economics", collections="hub:1:r3")
    assert feed_response_cache_key(**shape, offset=0, opening_seating=True) == (
        feed_response_cache_key(**shape, offset=0, opening_seating=True)
    )
    assert feed_page_base_cache_key(**shape, opening_seating=True) == (
        feed_page_base_cache_key(**shape, opening_seating=True)
    )


def test_seated_principals_still_get_their_own_response_keys():
    """Seating is one more build input, not a replacement for the principal."""
    keys = {
        feed_response_cache_key(**p.values[0], limit=50, offset=0, opening_seating=True)
        for p in _PRINCIPALS
    }
    assert len(keys) == 3


def test_the_cache_marker_is_the_edition_policys_marker():
    """One policy, one name: the cache entry and the edition minted from it
    must mean the same seating rule. A version bump in one place and not the
    other would let a v2 page be pinned by a v1 edition."""
    assert FEED_OPENING_SEATING_KEY_MARKER == _OPENING_SEATING_POLICY_MARKER
    assert FEED_OPENING_SEATING_KEY_MARKER.endswith("-v1")


# ---------------------------------------------------------------------------
# C. Window/order dimensions stay where they were
# ---------------------------------------------------------------------------


def test_a_seated_response_key_still_separates_offsets():
    a = feed_response_cache_key(limit=20, offset=0, opening_seating=True)
    b = feed_response_cache_key(limit=20, offset=20, opening_seating=True)
    assert a != b


def test_a_seated_response_key_still_separates_requested_editions():
    a = feed_response_cache_key(limit=20, offset=20, opening_seating=True)
    b = feed_response_cache_key(limit=20, offset=20, edition="abcd1234", opening_seating=True)
    c = feed_response_cache_key(limit=20, offset=20, edition="ffff0000", opening_seating=True)
    assert len({a, b, c}) == 3


def test_the_base_takes_no_offset_edition_or_boundary():
    """Offset and requested edition are windows/orders over a build; the
    continuation boundary is the edition's layout. None is a base build input,
    so none may be a base key parameter — seated or not."""
    params = set(inspect.signature(feed_page_base_cache_key).parameters)
    for absent in ("offset", "edition", "continuation_start", "boundary", "user_id", "session_id"):
        assert absent not in params


# ---------------------------------------------------------------------------
# D. Nothing in production can turn it on yet
# ---------------------------------------------------------------------------


def test_the_route_keys_on_the_one_policy_and_its_switch_is_off():
    # The seated serving path is commissioned default-OFF (#5105 server
    # connection): `_cache_shape` and the edition fingerprint both read the one
    # `_opening_seating` value, which is False unless the single internal
    # switch is flipped. Route behaviour is pinned in
    # `tests/integration/test_route_feed_opening_seating_5105.py`.
    src = inspect.getsource(feed_route.get_feed)
    shape = src[src.index("_cache_shape = dict(") :]
    shape = shape[: shape.index("\n        )\n")]
    assert "opening_seating=_opening_seating," in shape
    assert feed_route._DISCOVER_OPENING_SEATING_SERVED is False
    assert not feed_route._feed_opening_seating_policy(
        mode=None,
        sport=None,
        category=None,
        tags=None,
        my_teams_only=False,
        include_events=True,
        include_futures=True,
    )


def test_no_query_parameter_can_select_seating():
    assert "opening_seating" not in inspect.signature(feed_route.get_feed).parameters


def test_no_warmer_task_or_env_switch_mentions_seating():
    for path in sorted((_APP / "tasks").glob("*.py")):
        assert "opening_seating" not in path.read_text(), path.name
    cache_src = inspect.getsource(feed_cache)
    assert "OPENING_SEATING_ENV" not in cache_src
    assert "environ" not in inspect.getsource(feed_cache.feed_response_cache_key)
    assert "environ" not in inspect.getsource(feed_cache.feed_page_base_cache_key)
