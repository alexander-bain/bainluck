"""Ruling 137's cold-path charter, pinned against the clients it describes.

The instrument (`backend/scripts/cold_path_snapshot.py`) claims to measure "the
request each tab issues on first appear". That claim decays silently: a client
changes a limit, adds a call, or starts fetching on a tab that used to fetch
nothing, and the instrument keeps returning a confident number about a shape
nobody asks for any more. That is LAT-P089's failure exactly — the warmer warmed
`limit=20` while native asked `limit=50`, and warming a key nobody reads fails
identically to warming nothing.

So every path in the table is pinned to the client constant it came from, the
same way `test_feed_prewarm.py` pins the warmed shapes. The tests skip (not
fail) when a client's sources are absent from the checkout, because the backend
suite runs in places the iOS tree does not exist.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
IOS = REPO / "ios" / "Bain Luck" / "Bain Luck"
FRONTEND = REPO / "frontend"


def _load_instrument():
    path = REPO / "backend" / "scripts" / "cold_path_snapshot.py"
    spec = importlib.util.spec_from_file_location("cold_path_snapshot", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cps():
    return _load_instrument()


def _path_by_key(cps, key: str):
    return next(p for p in cps.PATHS if p.key == key)


# --------------------------------------------------------------------------
# The load-bearing claim: Browse costs nothing, and it is a SOURCE fact
# --------------------------------------------------------------------------


def test_browse_issues_no_network_request_on_appear():
    """Ruling 137: a surface that issues no request is NO SERVER DEPENDENCY.

    Reported as such rather than as "0 ms measured" — but the claim is only
    honest while it is true, and it is exactly the kind of thing that changes
    without anyone re-reading the report that depends on it. If Browse ever
    starts fetching, this test fails and the charter's Browse row has to be
    re-derived instead of silently continuing to say zero.
    """
    view = IOS / "Views" / "LeaguesView.swift"
    if not view.exists():
        pytest.skip("ios LeaguesView.swift not available")
    source = view.read_text()

    # Anything that could reach the network from this view. `AnalyticsService`
    # is deliberately NOT in this list: it is fire-and-forget telemetry, not
    # something first paint waits on.
    forbidden = ("APIClient", "URLSession", "await fetch", "try await api")
    hits = [token for token in forbidden if token in source]
    assert not hits, (
        f"LeaguesView.swift now references {hits} — the Browse tab has grown a "
        "network dependency. Ruling 137's Browse row reports NO SERVER "
        "DEPENDENCY on the strength of this file issuing nothing on appear; "
        "re-derive that row (and add the request to cold_path_snapshot.PATHS) "
        "rather than leaving the charter claiming a zero it can no longer back."
    )


def test_browse_has_no_blocking_path_in_the_instrument(cps):
    """And the instrument agrees with the source fact, in both directions."""
    assert "Browse" in cps.TABS, "Browse must still be reported, as an empty row"
    assert not [p for p in cps.PATHS if p.tab == "Browse"], (
        "Browse must have NO entry in PATHS. An empty row printed from an "
        "absent path is the honest shape; a probed 0 ms is not."
    )


# --------------------------------------------------------------------------
# Every measured shape is the client's shape
# --------------------------------------------------------------------------


def test_discover_native_shape_tracks_the_ios_first_page_limit(cps):
    vm = IOS / "ViewModels" / "DiscoverViewModel.swift"
    if not vm.exists():
        pytest.skip("ios DiscoverViewModel.swift not available")
    match = re.search(r"firstPageLimit\s*=\s*(\d+)", vm.read_text())
    assert match, "could not read firstPageLimit from DiscoverViewModel.swift"
    limit = int(match.group(1))
    path = _path_by_key(cps, "discover_native").path
    assert f"limit={limit}" in path, (
        f"the instrument measures {path} but native Discover asks for "
        f"limit={limit} — a different cache key, so the number describes a "
        "request the app never makes"
    )


def test_sports_native_shape_tracks_the_ios_client(cps):
    """Sports asks `mode=sports` at APIClient's DEFAULT limit, which is 50."""
    vm = IOS / "ViewModels" / "FeedViewModel.swift"
    client = IOS / "Services" / "APIClient.swift"
    if not (vm.exists() and client.exists()):
        pytest.skip("ios sources not available")
    assert (
        'fetchFeed(mode: "sports")' in vm.read_text()
    ), "FeedViewModel no longer requests mode=sports — re-derive the Sports row"
    match = re.search(
        r"func fetchFeed\((?:[^)]*?)limit:\s*Int\s*=\s*(\d+)",
        client.read_text(),
        re.S,
    )
    assert match, "could not read APIClient.fetchFeed's default limit"
    limit = int(match.group(1))
    path = _path_by_key(cps, "sports_native").path
    assert f"limit={limit}" in path and "mode=sports" in path, (
        f"the instrument measures {path} but native Sports asks limit={limit}"
        " with mode=sports"
    )


def test_web_shapes_track_the_frontend_page_limit(cps):
    paging = FRONTEND / "lib" / "discover" / "feedPaging.ts"
    if not paging.exists():
        pytest.skip("frontend/lib/discover/feedPaging.ts not available")
    match = re.search(r"FEED_PAGE_LIMIT\s*=\s*(\d+)", paging.read_text())
    assert match, "could not read FEED_PAGE_LIMIT from feedPaging.ts"
    limit = int(match.group(1))
    for key in ("discover_web", "sports_web"):
        path = _path_by_key(cps, key).path
        assert (
            f"limit={limit}" in path
        ), f"{key} measures {path} but the web first paint asks limit={limit}"


def test_my_stuff_blocking_request_is_the_one_that_fires_signed_out(cps):
    """The signed-out person's wait is the measurable one, and it is the row.

    `/api/predictions/stats` fires from `MyStuffView`'s `.task` regardless of
    auth; the team feed only exists in the authenticated branch and is not
    measurable from a sandbox holding an admin secret rather than a user JWT.
    """
    view = IOS / "Views" / "MyStuffView.swift"
    if not view.exists():
        pytest.skip("ios MyStuffView.swift not available")
    blocking = [p for p in cps.PATHS if p.tab == "My Stuff" and p.blocking]
    assert [p.path for p in blocking] == ["/api/predictions/stats"]
    feed = _path_by_key(cps, "my_stuff_feed_requires_auth")
    assert not feed.barred, (
        "the anonymous my_teams_only probe must never vote on the verdict — it "
        "hits the requires_auth early return, not the real path"
    )


def test_every_tab_has_exactly_one_blocking_path_per_surface(cps):
    """A tab whose headline is ambiguous has no headline.

    Two blocking rows for one (tab, surface) means the report cannot say what
    gates first paint, which is the whole quantity ruling 137 names.
    """
    seen: dict[tuple[str, str], int] = {}
    for p in cps.PATHS:
        if p.blocking:
            seen[(p.tab, p.surface)] = seen.get((p.tab, p.surface), 0) + 1
    duplicates = {k: v for k, v in seen.items() if v > 1}
    assert not duplicates, f"ambiguous headline for {duplicates}"


# --------------------------------------------------------------------------
# The bars are the pre-registered ones, and a cycle cannot soften them
# --------------------------------------------------------------------------


def test_the_bars_are_the_ones_pre_registered_before_measurement(cps):
    """Frozen in `docs/audits/latency/lat-p099-cold-path-charter.md` §3.

    Not a tautology test: the pre-registration doc is committed BEFORE any
    number exists, and this is the mechanism that stops a later cycle from
    editing a constant it is about to fail. If a bar genuinely needs to move,
    the doc and the ruling move with it, in the open.
    """
    assert cps.TAB_FIRST_LOAD_BAR_MS == 1000.0
    assert cps.SEARCH_COLD_BAR_MS == 1000.0
    assert cps.TYPEAHEAD_COLD_BAR_MS == 500.0
    assert cps.CLIENT_DEADLINE_MS == 6000.0

    charter = REPO / "docs" / "audits" / "latency" / "lat-p099-cold-path-charter.md"
    assert charter.exists(), "the pre-registration record must not be deleted"
    text = charter.read_text()
    for token in ("≤ 1,000 ms", "≤ 500 ms", "≤ 6,000 ms"):
        assert token in text, f"the charter no longer states the bar {token}"


def test_the_hard_ceiling_is_the_clients_own_deadline(cps):
    """6,000 ms is not a taste — it is `DiscoverViewModel.retryBudget`."""
    vm = IOS / "ViewModels" / "DiscoverViewModel.swift"
    if not vm.exists():
        pytest.skip("ios DiscoverViewModel.swift not available")
    match = re.search(r"retryBudget:\s*TimeInterval\s*=\s*([0-9.]+)", vm.read_text())
    assert match, "could not read retryBudget from DiscoverViewModel.swift"
    assert cps.CLIENT_DEADLINE_MS == float(match.group(1)) * 1000, (
        "the hard ceiling has drifted from the client deadline it is supposed "
        "to be. A ceiling above the client's budget grades a give-up as a pass."
    )


# --------------------------------------------------------------------------
# The classifier must not silently absorb a status it has never seen
# --------------------------------------------------------------------------


def test_every_cache_status_the_route_can_emit_is_classified(cps):
    """An unclassified status must land in `unknown`, never in warm or cold.

    The route grew `shared_hit` after LAT-P089 and could grow another. A
    classifier written as "not hit means cold" would have counted every new
    status as a miss and reported a cold-share regression that never happened.
    """
    route = REPO / "backend" / "app" / "routes" / "feed.py"
    emitted = set(re.findall(r'cache_status="([a-z_]+)"', route.read_text()))
    # `n/a` is the placeholder the observability call uses when no status was set.
    emitted -= {"n/a"}
    known = cps.COLD_STATUSES | cps.WARM_STATUSES | {"shared_hit", "shared_stale_hit"}
    unknown = emitted - known
    assert not unknown, (
        f"routes/feed.py can emit {sorted(unknown)} and the instrument does not "
        "classify it. Add it to COLD_STATUSES or WARM_STATUSES deliberately — "
        "leaving it to fall through means a real cache state is reported as "
        "`unknown` and drops out of the cold share."
    )
    assert not (cps.COLD_STATUSES & cps.WARM_STATUSES)


def test_an_unknown_status_is_not_counted_as_warm_or_cold(cps):
    assert cps._classify({"feed_cache": "some_future_status"}) == "unknown"
    assert cps._classify({"feed_cache": "miss"}) == "cold"
    assert cps._classify({"feed_cache": "shared_hit"}) == "warm"
    # No feed header at all: fall back to the query count, the same
    # discriminator done_bar_snapshot.py uses for /typeahead.
    assert cps._classify({"feed_cache": None, "queries": 0}) == "warm"
    assert cps._classify({"feed_cache": None, "queries": 7}) == "cold"
    assert cps._classify({"feed_cache": None, "queries": None}) == "unknown"


def test_the_term_sets_are_imported_not_copied(cps):
    """One term list for the whole program — a copy drifts on its first edit."""
    from done_bar_snapshot import TERM_SETS  # noqa: PLC0415

    assert cps.TERM_SETS is TERM_SETS
