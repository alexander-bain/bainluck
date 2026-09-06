"""LAT-P107 / #1605 — every odds-enrichment site reads bookmakers, not history.

`row_number() OVER (... ORDER BY captured_at DESC)` to keep the latest snapshot per
bookmaker reads O(SNAPSHOT DEPTH) to return O(BOOKMAKERS). Tier-1 sports poll every
32 s, so depth is the part that grows: one measured Red Sox event carries **13,522
snapshots across 19 bookmakers**. LAT-P013 then LAT-P030 retired that shape from
`/api/events/search`, where it measured **6,724 ms -> 185 ms (36x), 78,800 rows read
-> 947, byte-identical output**, and lifted the replacement into the module-level
helper `latest_odds_per_bookmaker_query`.

Two sites were left behind and are fixed by this queue:

* `list_events`  (`GET /api/events`)          — the same window over a whole page.
* `get_event`    (`GET /api/events/{id}`)     — the same window over ONE event, plus
  a second round trip to re-fetch by id. Worst case for the anti-pattern, on the
  event page, which is product priority #3.

WHAT THIS FILE DOES AND DOES NOT PROVE
--------------------------------------
It asserts that each call site delegates to the SHARED helper. That is deliberately
all it asserts about shape, because `test_search_latency_contract.py` already pins
the helper's internals (loose index scan present, `LIMIT 1` present, strict `>`
advance, `id DESC` tiebreak, no `row_number()`, no `DISTINCT ON`) and
`tests/integration/test_search_odds_enrichment_equivalence.py` executes it against
real Postgres and diffs its rows against the very window shape being deleted here.
Duplicating those assertions per call site would fork the definition; asserting the
delegation makes both existing gates cover all three routes instead of one.

It does NOT prove the speedup on these two routes. The 36x is the SIBLING route's
production measurement; the shape is provably the same but the traffic is not, so
this queue's before/after on `/api/events` and `/api/events/{id}` is pre-registered
as a post-deploy check, not claimed here. A green suite is not a latency result.

No database: source-shape assertions only, following the sibling contract file.
"""

from __future__ import annotations

import inspect
import re

from app.routes import events as events_route


def _strip_comments(src: str) -> str:
    """Drop whole-line `#` comments.

    Mandatory here, not cosmetic: both call sites now carry long comments that QUOTE
    the anti-pattern they replaced, including the literal string `row_number()`. A
    naive substring check on raw source would match the explanation and pass while
    the live code did whatever it liked — which is the failure this file exists to
    prevent, so it must not be the failure this file commits.
    """
    return "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("#")
    )


def _code(fn) -> str:
    return _strip_comments(inspect.getsource(fn))


LIST_CODE = _code(events_route.list_events)
DETAIL_CODE = _code(events_route.get_event)
SEARCH_CODE = _code(events_route.search_events)
MODULE_CODE = _strip_comments(inspect.getsource(events_route))


# ---------------------------------------------------------------------------
# The two sites this queue converted
# ---------------------------------------------------------------------------


def test_list_events_delegates_to_the_shared_enrichment_query():
    """`GET /api/events`. If this stops calling the helper, the helper's shape
    guards and its real-Postgres equivalence test cover this route no longer —
    while still being green, because they cover the search route."""
    assert (
        "latest_odds_per_bookmaker_query(event_ids)" in LIST_CODE
    ), "list_events no longer builds its odds enrichment from the shared helper"


def test_event_detail_delegates_to_the_shared_enrichment_query():
    """`GET /api/events/{event_id}` — one event, so a one-element list."""
    assert (
        "latest_odds_per_bookmaker_query([event_id])" in DETAIL_CODE
    ), "get_event no longer builds its odds enrichment from the shared helper"


def test_no_call_site_reintroduces_the_window_scan():
    """The property, asserted per site rather than once for the module, so a
    failure names WHICH route regressed."""
    for name, code in (
        ("list_events", LIST_CODE),
        ("get_event", DETAIL_CODE),
        ("search_events", SEARCH_CODE),
    ):
        assert "row_number()" not in code, (
            f"{name} reintroduced the window scan over full snapshot history — it "
            f"reads every snapshot of every event on the page to keep one row per "
            f"bookmaker (measured 78,800 rows read to return 299)"
        )


def test_event_detail_no_longer_re_fetches_the_snapshots_by_id():
    """The window form needed two round trips: rank-and-project ids, then select
    the rows those ids name. The helper returns the rows. If the second query
    comes back, the first one is almost certainly back with it."""
    assert "OddsSnapshot.id.in_(latest_ids)" not in DETAIL_CODE, (
        "get_event is re-fetching snapshots by id again — the helper already "
        "returns OddsSnapshot rows, so a second round trip means the id-projection "
        "window is back"
    )


def test_all_three_sites_share_one_definition():
    """The point of the helper (LAT-P030) is that CI executes the REAL statement.
    Three copies of a correct query is three places for the next edit to fork."""
    assert MODULE_CODE.count("def latest_odds_per_bookmaker_query(") == 1


# ---------------------------------------------------------------------------
# The census — a NEW window scan must not be able to appear quietly
# ---------------------------------------------------------------------------

#: 🔴 **ZERO SINCE #2286, AND THE SURVEYED WINDOW WAS REMOVED RATHER THAN REWRITTEN.**
#:
#: This constant was 1. LAT-P107 surveyed the `/search-suggestions` window and
#: deliberately left it: it partitions by `event_id` alone under a fixed
#: `bookmaker == "aggregate"`, so `latest_odds_per_bookmaker_query` — whose entire
#: mechanism is enumerating the distinct bookmakers — did not fit and could not be
#: reused. The note said it was "a separate, smaller ship … [that] needs its own
#: equivalence proof", and this test's own failure message asks whoever changes it
#: to cite one. THE EQUIVALENCE PROOF IS THAT THERE IS NOTHING TO BE EQUIVALENT TO:
#:
#: `bookmaker == "aggregate"` matches nothing and never did. Measured on production
#: before the change: 18 real books wrote `odds_snapshots` in the preceding two
#: hours and `aggregate` is not among them, and independently every `bookmaker=`
#: write site in `app/` emits a real book key, `polymarket`, `kalshi` or
#: `datagolf_model`. `EXPLAIN (ANALYZE, BUFFERS)` on the corrected query measured
#: **799.8 ms and 46,012 shared buffer hits to return `Actual Rows: 0`** on every
#: uncached build. So the window was not a slow way of getting the right answer; it
#: was a slow way of getting no answer, and LAT-P107's caution was protecting a
#: query with no output to preserve.
#:
#: A replacement is therefore not owed, and one is not there: section 1 now reads
#: `compute_aggregate_probability` over `win_probability_sources`, already loaded on
#: the `Event` rows it just fetched, at ZERO additional round trips — and coverage
#: went 0/69 live events to 55/69 because of it. #2286.
EXPECTED_REMAINING_ODDS_WINDOWS = 0


def test_the_remaining_window_count_is_pinned_in_both_directions():
    """Still two-directional, and at zero only one direction is reachable.

    UP is the regression, and it is now the whole job: a fourth site appears, or a
    converted one reverts, and the per-site tests above miss it because the new
    code is in a helper or a route nobody thought to list. At a floor of zero this
    guard has become a plain "no window scan in this file", which is stronger than
    what it pinned before — there is no longer a surveyed exception for a new one
    to hide behind.

    DOWN is unreachable at zero and the constant stays a constant anyway: the
    equality is what makes UP fail, and rewriting it as `<= 0` would say the count
    is a budget rather than a fact. If a window is ever legitimately re-added, this
    goes back to 1 WITH the reason, exactly as it came down to 0 with one.
    """
    windows = len(re.findall(r"func\.row_number\(\)", MODULE_CODE))
    assert windows == EXPECTED_REMAINING_ODDS_WINDOWS, (
        f"routes/events.py has {windows} `row_number()` windows, expected "
        f"{EXPECTED_REMAINING_ODDS_WINDOWS} — the surveyed /search-suggestions one "
        f"was REMOVED by #2286 (it filtered on a bookmaker nothing writes and cost "
        f"799.8 ms to return 0 rows; see the constant's note). If you added a site, "
        f"use `latest_odds_per_bookmaker_query`. If you re-added a window on "
        f"purpose, update the constant here and say why."
    )
