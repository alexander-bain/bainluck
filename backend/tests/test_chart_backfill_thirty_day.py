"""live/039 — guards for the one-time 30-day chart drain.

The defects worth guarding here are the ones that make a drain LOOK finished:
a keyset that steps over a tied cohort, a cursor that does not advance past
judged-but-thick rows, and a verdict that says `drained` on a page that merely
returned.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.tasks.chart_backfill_thirty_day import (
    THIRTY_DAY_THIN_POINTS,
    TIERS,
    DrainPage,
    _label,
    _verdict,
    is_us_open_sport_key,
    select_thirty_day_page,
)


# ---------------------------------------------------------------------------
# Tier membership
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        "tennis_atp_us_open",
        "tennis_wta_us_open",
        # 🔴 The split-pair half. 28 of 2026-09-01/02's US Open singles matches
        # exist as TWO event rows and the Kalshi-native one carries the PLAIN
        # tour key — including the specimen the whole rail was built for. A tier
        # that matched only the tournament keys would leave that half for last.
        "tennis_atp",
        "tennis_wta",
    ],
)
def test_us_open_tier_holds_both_spellings(key):
    assert is_us_open_sport_key(key) is True


@pytest.mark.parametrize(
    "key",
    [
        "soccer_other",
        "esports",
        "baseball_mlb",
        "tennis_other",
        None,
        "",
        # 🔴 Both of these are REAL rows in the sports table and both are matched
        # by the obvious `"us_open" in key`: `us_open` is a substring of
        # `aus_open`, and golf has a US Open too. Neither is Alex's cohort.
        "tennis_atp_aus_open_singles",
        "tennis_wta_aus_open_singles",
        "golf_us_open_winner",
    ],
)
def test_us_open_tier_excludes_everything_else(key):
    assert is_us_open_sport_key(key) is False


def test_tiers_are_ordered_ship_first():
    """The order IS the ship — 13,591 of the 19,646 candidates are the
    low-priority remainder, so a drain that walked them first would reach the US
    Open last."""
    assert [tier.name for tier in TIERS] == ["us_open", "reachable", "remainder"]


# ---------------------------------------------------------------------------
# Selection + the keyset
# ---------------------------------------------------------------------------


class _Row:
    def __init__(self, event_id, commence_time, point_count):
        self.event_id = event_id
        self.commence_time = commence_time
        self.point_count = point_count


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _Session:
    """Records the bound parameters so the keyset can be asserted on."""

    def __init__(self, rows):
        self._rows = rows
        self.params = None

    async def execute(self, _statement, params=None):
        self.params = params
        return _Result(self._rows)


BASE = datetime(2026, 9, 1, tzinfo=timezone.utc)


async def test_only_thin_events_are_selected():
    rows = [
        _Row(1, BASE, 0),
        _Row(2, BASE + timedelta(minutes=1), THIRTY_DAY_THIN_POINTS),      # thick
        _Row(3, BASE + timedelta(minutes=2), THIRTY_DAY_THIN_POINTS - 1),  # thin
    ]
    page = await select_thirty_day_page(_Session(rows), sport_ids=[7], limit=10)
    assert page.event_ids == [1, 3]


async def test_cursor_advances_past_judged_thick_rows():
    """A thick chart the cursor did not pass is re-counted on every re-trigger,
    which is how a drain spends every call re-reading the same head."""
    rows = [_Row(1, BASE, 0), _Row(2, BASE + timedelta(minutes=1), 999)]
    page = await select_thirty_day_page(_Session(rows), sport_ids=[7], limit=10)
    assert page.event_ids == [1]
    assert page.next_cursor == (BASE + timedelta(minutes=1), 2)


async def test_cursor_is_a_pair_not_a_bare_timestamp():
    """🔴 `commence_time` ties in BULK — a ticker-derived midnight is shared by
    every match on a card (438 events on one value, measured). Keyed on the
    timestamp alone, a tied cohort larger than one page loses its tail forever:
    the page reads the first N, the cursor lands ON the shared value, and the
    next page's strict `>` steps over the whole cohort including the part never
    looked at."""
    tied = [_Row(i, BASE, 0) for i in range(1, 6)]
    page = await select_thirty_day_page(_Session(tied), sport_ids=[7], limit=3)
    assert page.next_cursor is not None
    stamp, event_id = page.next_cursor
    assert stamp == BASE
    assert event_id == 3, "cursor must carry the id half to break the tie"


async def test_keyset_is_passed_to_the_query():
    session = _Session([])
    await select_thirty_day_page(
        session, sport_ids=[7], limit=5, after=(BASE, 42)
    )
    assert session.params["after_ts"] == BASE
    assert session.params["after_id"] == 42
    assert session.params["thin_points"] == THIRTY_DAY_THIN_POINTS


async def test_empty_tier_is_exhausted_not_an_error():
    """A tier with no sports selects nothing and says it is DONE, rather than
    falling through to an unfiltered `IN ()` (gotcha #53)."""
    page = await select_thirty_day_page(_Session([]), sport_ids=[], limit=10)
    assert page == DrainPage([], None, True, 0)


async def test_short_scan_reports_exhausted():
    rows = [_Row(1, BASE, 0)]
    page = await select_thirty_day_page(
        _Session(rows), sport_ids=[7], limit=10, scan_multiple=4
    )
    assert page.exhausted is True


async def test_full_scan_does_not_report_exhausted():
    """Bounded by BUDGET, not by work — and it must not claim otherwise."""
    rows = [_Row(i, BASE + timedelta(minutes=i), 0) for i in range(8)]
    page = await select_thirty_day_page(
        _Session(rows), sport_ids=[7], limit=2, scan_multiple=4
    )
    assert page.exhausted is False


# ---------------------------------------------------------------------------
# The verdict — "it returned" is not "it worked" (gotcha #53)
# ---------------------------------------------------------------------------


def test_verdict_is_drained_only_when_every_tier_says_so():
    summary = {
        "tiers": {
            "us_open": {"status": "drained"},
            "reachable": {"status": "drained"},
            "remainder": {"status": "in_progress"},
        }
    }
    assert _verdict(summary, only_tier=None) == "in_progress"


def test_verdict_drained_when_all_three_finish():
    summary = {
        "tiers": {
            "us_open": {"status": "drained"},
            "reachable": {"status": "already_drained"},
            "remainder": {"status": "drained"},
        }
    }
    assert _verdict(summary, only_tier=None) == "drained"


def test_a_tier_never_reached_is_not_drained():
    """The trap: two tiers finish, the budget runs out before the third is even
    scanned, and an `all()` over only the tiers PRESENT would report success."""
    summary = {"tiers": {"us_open": {"status": "drained"}}}
    assert _verdict(summary, only_tier=None) == "in_progress"


def test_only_tier_scopes_the_verdict():
    summary = {"tiers": {"us_open": {"status": "drained"}}}
    assert _verdict(summary, only_tier="us_open") == "drained"


def test_abort_beats_every_tier_status():
    summary = {
        "aborted": "consecutive_errors",
        "tiers": {t.name: {"status": "drained"} for t in TIERS},
    }
    assert _verdict(summary, only_tier=None) == "aborted"


def test_cursor_label_carries_both_halves_or_neither():
    assert _label(None) is None
    assert _label((BASE, 42)) == "2026-09-01T00:00:00+00:00|42"
