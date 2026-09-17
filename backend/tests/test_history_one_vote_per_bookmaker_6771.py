"""#6771 route half — one sportsbook, one vote, inside a chart minute.

THE SHIP, IN A READER'S WORDS: a live match page stops telling you thirteen
sportsbooks are behind the number when six of them wrote it, and the chart stops
stepping four points on a minute where no book changed its price.

WHAT A READER SAW. `/api/events/15305827/history?hours=48` — the window
`detailBoot.ts` actually boots the event page with — measured against the bytes
production served 2026-09-17 18:57Z, replayed by
`artifacts/live-356/replay_bucket_dedupe.py` (positive control: 718 of 718
buckets rebuilt point-for-point from the served payload before either arm ran):

    buckets in the reader's own window            718
    buckets carrying a book that wrote twice      535   (74%)
    sportsbooks reported across them            1,336
    sportsbooks that actually wrote                732   <- an 82% overstatement
    buckets whose probability changes                66, three of them by >= 3pp

The count is not internal bookkeeping. `lib/eventKeyStats.ts` reads the newest
bucket's `bookmaker_count` and prints `Live · N sportsbooks` beside the
probability; 35 of that page's last 60 buckets would have printed an overstated
N. The three worst probability minutes, drawn today vs. one vote per book:

    17:33Z   67.48%  ->  63.91%     5 rows / 4 books
    17:51Z   65.15%  ->  69.60%     3 rows / 2 books
    17:52Z   77.44%  ->  81.68%     6 rows / 5 books

WHAT THESE ASSERT, AND WHY EACH CLAUSE IS HERE.

* The three production minutes are replayed through the REAL
  `aggregate_bookmaker_odds` and `detect_reversed_bookmakers`, not through a
  restatement of them. A test that re-derives the average agrees with itself.
* The route is driven end to end for the same reason, against a session stub
  that answers the odds rail — a helper that is right and a route that never
  calls it would pass a helper-only file.
* THE COST IS A TEST, NOT A FOOTNOTE. `detect_reversed_bookmakers` needs three
  ENTRIES and counts rows, so buckets that only reached three by counting one
  book twice stop being reversal-checked. Authority measured 224 of 854 armed
  buckets in that state, 7 of them a single book compared against a median built
  from its own duplicates. `test_a_bucket_armed_only_by_a_duplicate_is_honestly_disarmed`
  asserts that loss deliberately, and the control beside it asserts a bucket with
  three genuinely distinct books is still checked — without that pair, "the
  detector went quiet" and "the detector is dead" look identical.
* Determinism is asserted on both tie-break keys. No per-book pick exists today,
  so this change CREATES the tie; two rows a book wrote in the same microsecond
  must resolve the same way on every request or the chart flickers between page
  loads.

WHAT THIS IS NOT. It reads `captured_at`, `bookmaker` and `id` and never
`valid_until`, so no point this route has already served can be revised by a
later write — that is why it is extractable while codex's Brief-14 hold stands on
interval reconstruction. And it is not the whole defect: #6771's other half
(`_snapshots_are_equal` in `tasks/odds_polling.py`, another owner) is the cause of
611 of 816 double-counted buckets, and is forward-only — it stops new duplicates
and repairs nothing already stored. This half is what the reader gets on the rows
that already exist, on the next page load, with no backfill.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.routes.events import (
    get_event_odds_history,
    one_row_per_bookmaker_in_bucket,
)
from app.utils.odds_math import aggregate_bookmaker_odds, detect_reversed_bookmakers

from tests.test_history_window_stale_open_event import _DispatchingSession, _Result

UTC = timezone.utc

#: The production specimen every number in this module was measured on.
_SPECIMEN_ID = 15305827

_T0 = datetime(2026, 9, 17, 17, 33, tzinfo=UTC)


def _row(bookmaker, home_prob, *, at=_T0, row_id=None, event_id=_SPECIMEN_ID):
    """One `odds_snapshots` row, carrying only the fields this rail reads."""
    return SimpleNamespace(
        id=row_id if row_id is not None else _row.next_id(),
        event_id=event_id,
        bookmaker=bookmaker,
        captured_at=at,
        valid_until=None,
        home_win_probability=home_prob,
        away_win_probability=(
            None if home_prob is None else round(1.0 - home_prob, 4)
        ),
        over_under=None,
        home_spread=None,
        projected_home_score=None,
        projected_away_score=None,
    )


def _ids():
    n = 1000
    while True:
        n += 1
        yield n


_row.next_id = lambda _gen=_ids(): next(_gen)


def _aggregate(rows):
    """The bucket exactly as the route composes it, through the real helpers."""
    reversed_bks = detect_reversed_bookmakers(rows)
    kept = [r for r in rows if r.bookmaker not in reversed_bks] if reversed_bks else rows
    return aggregate_bookmaker_odds(kept if kept else rows)


# ---------------------------------------------------------------------------
# The three production minutes, through the real aggregation
# ---------------------------------------------------------------------------

#: Exactly the rows `bookmaker_history` exposed for these three minutes in the
#: served payload, in the order the route's `ORDER BY captured_at` produced them.
_SERVED_MINUTES = {
    "17:33Z": (
        [
            ("betmgm", 0.5647),
            ("bovada", 0.8174),
            ("bovada", 0.8174),
            ("draftkings", 0.5927),
            ("fanduel", 0.5816),
        ],
        0.6748,  # what production drew
        0.6391,  # one vote per book
        5,       # sportsbooks production reported
        4,       # sportsbooks that wrote
    ),
    "17:51Z": (
        [("bovada", 0.5625), ("bovada", 0.5625), ("draftkings", 0.8295)],
        0.6515,
        0.6960,
        3,
        2,
    ),
    "17:52Z": (
        [
            ("betmgm", 0.809),
            ("bovada", 0.5625),
            ("bovada", 0.8097),
            ("draftkings", 0.8021),
            ("fanatics", 0.8326),
            ("fanduel", 0.8306),
        ],
        0.7744,
        0.8168,
        6,
        5,
    ),
}


def _minute_rows(pairs):
    """The rows of one served minute, one second apart so `captured_at` orders
    them the way the query did — the duplicate that arrived second is the later
    observation, which is the one a bucket for that minute should carry."""
    return [
        _row(bk, prob, at=_T0 + timedelta(seconds=i))
        for i, (bk, prob) in enumerate(pairs)
    ]


def test_the_three_production_minutes_are_drawn_wrong_today():
    """The BEFORE arm. Without this, the AFTER arm below proves only arithmetic."""
    for label, (pairs, served, _after, served_count, _books) in _SERVED_MINUTES.items():
        aggregated = _aggregate(_minute_rows(pairs))
        assert aggregated["home_probability"] == served, (
            f"{label}: the rig no longer reproduces what production drew"
        )
        assert aggregated["bookmaker_count"] == served_count, label


def test_one_vote_per_book_repairs_all_three_production_minutes():
    for label, (pairs, _served, after, _c, books) in _SERVED_MINUTES.items():
        aggregated = _aggregate(one_row_per_bookmaker_in_bucket(_minute_rows(pairs)))
        assert aggregated["home_probability"] == after, (
            f"{label}: expected {after}, got {aggregated['home_probability']}"
        )
        assert aggregated["bookmaker_count"] == books, (
            f"{label}: the page would still print "
            f"'{aggregated['bookmaker_count']} sportsbooks'"
        )


def test_the_reported_sportsbook_count_stops_overstating():
    """The label clause, stated on its own so a probability-only fix cannot pass.

    17:52Z is the sharp one: six rows, five books, and the two bovada rows are 25
    points apart in price.
    """
    pairs, _served, _after, served_count, books = _SERVED_MINUTES["17:52Z"]
    rows = _minute_rows(pairs)
    assert _aggregate(rows)["bookmaker_count"] == served_count == 6
    assert _aggregate(one_row_per_bookmaker_in_bucket(rows))["bookmaker_count"] == books == 5


# ---------------------------------------------------------------------------
# The rule: the LAST row, and nothing merged
# ---------------------------------------------------------------------------


def test_the_books_last_row_in_the_minute_is_the_one_that_counts():
    """Not the first, and not an average of the two.

    A book that genuinely moved inside the minute is one opinion observed twice;
    the later observation is what was true at the end of the minute. Averaging
    would keep a superseded price alive in the number, and taking the first would
    make the bucket lag its own timestamp.
    """
    rows = [
        _row("bovada", 0.40, at=_T0),
        _row("bovada", 0.80, at=_T0 + timedelta(seconds=30)),
    ]
    kept = one_row_per_bookmaker_in_bucket(rows)
    assert [r.home_win_probability for r in kept] == [0.80]
    assert _aggregate(kept)["home_probability"] == 0.80, (
        "the bucket averaged the book against its own superseded price"
    )


def test_two_books_each_writing_twice_both_survive_once():
    rows = [
        _row("bovada", 0.40, at=_T0),
        _row("fanduel", 0.60, at=_T0 + timedelta(seconds=1)),
        _row("bovada", 0.44, at=_T0 + timedelta(seconds=2)),
        _row("fanduel", 0.66, at=_T0 + timedelta(seconds=3)),
    ]
    kept = one_row_per_bookmaker_in_bucket(rows)
    assert sorted((r.bookmaker, r.home_win_probability) for r in kept) == [
        ("bovada", 0.44),
        ("fanduel", 0.66),
    ]


def test_a_bucket_with_no_duplicate_is_passed_through_untouched():
    """The control that bounds the blast radius: 183 of the specimen's 718
    buckets are this shape, and their payload must be unchanged by identity, not
    by equivalence."""
    rows = [
        _row("bovada", 0.40, at=_T0),
        _row("fanduel", 0.60, at=_T0 + timedelta(seconds=1)),
        _row("betmgm", 0.50, at=_T0 + timedelta(seconds=2)),
    ]
    kept = one_row_per_bookmaker_in_bucket(rows)
    assert [id(r) for r in kept] == [id(r) for r in rows], (
        "a clean bucket was reordered or its rows replaced"
    )


def test_the_input_bucket_is_not_mutated():
    """`snapshots_by_time` is read again below this loop by the per-book rail."""
    rows = [_row("bovada", 0.40, at=_T0), _row("bovada", 0.80, at=_T0)]
    before = list(rows)
    one_row_per_bookmaker_in_bucket(rows)
    assert rows == before and len(rows) == 2


def test_an_empty_bucket_is_empty():
    assert one_row_per_bookmaker_in_bucket([]) == []


# ---------------------------------------------------------------------------
# Determinism — this change CREATES the tie, so it must also settle it
# ---------------------------------------------------------------------------


def test_rows_sharing_a_microsecond_resolve_by_id_not_by_arrival():
    """Two rows the same book wrote in the same microsecond. `id` is the writer's
    own order, so the higher id is the later row however the query returns them."""
    low = _row("bovada", 0.40, at=_T0, row_id=10)
    high = _row("bovada", 0.80, at=_T0, row_id=11)
    assert one_row_per_bookmaker_in_bucket([low, high])[0].home_win_probability == 0.80
    assert one_row_per_bookmaker_in_bucket([high, low])[0].home_win_probability == 0.80


def test_rows_identical_in_time_and_id_resolve_by_input_position():
    """The last key. It can only fire on rows that are indistinguishable by the
    two real ones, and it exists so the answer is still a function of the input
    rather than of dict iteration order."""
    first = _row("bovada", 0.40, at=_T0, row_id=7)
    second = _row("bovada", 0.80, at=_T0, row_id=7)
    assert one_row_per_bookmaker_in_bucket([first, second])[0] is second
    assert one_row_per_bookmaker_in_bucket([second, first])[0] is first


def test_a_row_with_no_id_never_raises():
    """An unflushed row has `id is None`, and `(datetime, None, int)` is not
    orderable against `(datetime, int, int)` — a TypeError here would be a 500 on
    the chart, not a wrong number."""
    unflushed = _row("bovada", 0.40, at=_T0, row_id=9)
    unflushed.id = None  # `row_id=None` means "mint one"; this means what it says.
    kept = one_row_per_bookmaker_in_bucket(
        [unflushed, _row("bovada", 0.80, at=_T0, row_id=9)]
    )
    assert [r.home_win_probability for r in kept] == [0.80]


# ---------------------------------------------------------------------------
# The measured cost, asserted rather than hidden
# ---------------------------------------------------------------------------


def test_a_bucket_armed_only_by_a_duplicate_is_honestly_disarmed():
    """THE DELIBERATE LOSS. `detect_reversed_bookmakers` needs three ENTRIES and
    counts rows. This bucket reaches three only because bovada wrote twice, so
    today the detector runs and compares bovada against a median two thirds built
    from bovada's own rows. After the dedupe it declines to judge two books.

    Authority measured this over 3h / 300 events: 224 of 854 armed buckets were
    armed on fewer than three distinct books, 7 on a single book. Honestly
    unarmed beats vacuously armed — but it is a loss, and it is asserted here so
    nobody has to discover it in production.
    """
    rows = [
        _row("bovada", 0.80, at=_T0),
        _row("bovada", 0.80, at=_T0 + timedelta(seconds=1)),
        _row("fanduel", 0.18, at=_T0 + timedelta(seconds=2)),
    ]
    assert detect_reversed_bookmakers(rows) == {"fanduel"}, (
        "the BEFORE arm is gone: this bucket is no longer armed today either"
    )
    assert detect_reversed_bookmakers(one_row_per_bookmaker_in_bucket(rows)) == set()


def test_a_bucket_with_three_real_books_is_still_reversal_checked():
    """The control without which the test above reads as 'the detector is dead'."""
    rows = [
        _row("bovada", 0.80, at=_T0),
        _row("betmgm", 0.82, at=_T0 + timedelta(seconds=1)),
        _row("fanduel", 0.18, at=_T0 + timedelta(seconds=2)),
    ]
    assert detect_reversed_bookmakers(one_row_per_bookmaker_in_bucket(rows)) == {
        "fanduel"
    }


def test_a_single_book_no_longer_compares_itself_to_its_own_duplicates():
    """Seven buckets were measured in exactly this state. One book, three rows,
    one of them stale enough to look reversed against the median of the other
    two — and it is the same book being convicted and excluded."""
    rows = [
        _row("bovada", 0.85, at=_T0),
        _row("bovada", 0.86, at=_T0 + timedelta(seconds=1)),
        _row("bovada", 0.14, at=_T0 + timedelta(seconds=2)),
    ]
    assert detect_reversed_bookmakers(rows) == {"bovada"}
    assert detect_reversed_bookmakers(one_row_per_bookmaker_in_bucket(rows)) == set()
    # And the bucket then carries bovada's newest price rather than falling back
    # to all three rows because the exclusion emptied the list.
    assert _aggregate(one_row_per_bookmaker_in_bucket(rows))["home_probability"] == 0.14


# ---------------------------------------------------------------------------
# The route, end to end
# ---------------------------------------------------------------------------


class _OddsSession(_DispatchingSession):
    """The stale-open rig, plus the odds rail it leaves empty.

    Subclassed rather than copied so the five other reads this route makes — the
    series fold, the blend fold, the Kalshi-silence question, the entity lookup —
    keep answering the way every other history test's rig answers them.
    """

    def __init__(self, event, odds_rows):
        super().__init__(event, [])
        self.odds_rows = odds_rows

    async def execute(self, statement, *a, **kw):
        if "odds_snapshots" in str(statement):
            return _Result(self.odds_rows)
        return await super().execute(statement, *a, **kw)


def _live_event(now):
    return SimpleNamespace(
        id=_SPECIMEN_ID,
        status="live",
        commence_time=now - timedelta(hours=1),
        completed_at=None,
        home_team_name="St Gallen",
        away_team_name="Sion",
        home_score=None,
        away_score=None,
        sport=SimpleNamespace(key="soccer_switzerland_superleague"),
        sport_id=1,
        box_score_data=None,
        win_probability_sources={},
    )


async def _serve(event, odds_rows, hours=48):
    session = _OddsSession(event, odds_rows)
    payload = await get_event_odds_history(
        event_id=event.id, hours=hours, response=MagicMock(headers={}), db=session
    )
    return payload


def _bucket(payload, minute):
    for row in payload["history"]:
        if row["timestamp"].startswith(minute):
            return row
    raise AssertionError(f"no bucket at {minute} in {[r['timestamp'] for r in payload['history']]}")


async def test_the_route_serves_the_deduped_value_and_the_honest_count():
    """The clause that makes this a ship rather than a helper. Same six rows as
    the 17:52Z production minute, served through the real route."""
    now = datetime.now(UTC)
    minute = now.replace(second=0, microsecond=0) - timedelta(minutes=5)
    pairs, _served, after, _c, books = _SERVED_MINUTES["17:52Z"]
    rows = [
        _row(bk, prob, at=minute + timedelta(seconds=i))
        for i, (bk, prob) in enumerate(pairs)
    ]

    served = _bucket(await _serve(_live_event(now), rows), minute.isoformat()[:16])
    assert served["home_probability"] == after
    assert served["bookmaker_count"] == books


async def test_the_route_leaves_a_duplicate_free_page_point_for_point_identical():
    """The blast-radius control, taken through the route rather than the helper:
    a page whose books each wrote once must serve the bytes it served before."""
    now = datetime.now(UTC)
    minute = now.replace(second=0, microsecond=0) - timedelta(minutes=5)
    rows = [
        _row("bovada", 0.61, at=minute),
        _row("fanduel", 0.63, at=minute + timedelta(seconds=1)),
        _row("betmgm", 0.62, at=minute + timedelta(seconds=2)),
    ]

    served = _bucket(await _serve(_live_event(now), rows), minute.isoformat()[:16])
    assert served["bookmaker_count"] == 3
    assert served["home_probability"] == 0.62
    assert served["probability_range"] == {"min": 0.61, "max": 0.63}


async def test_the_probability_range_narrows_to_the_books_that_wrote():
    """`probability_range` is `min/max` over the same list, so a duplicated
    outlier widens the band the page draws around the number as well as moving
    it. 17:52Z again: bovada's superseded 0.5625 is the minimum."""
    now = datetime.now(UTC)
    minute = now.replace(second=0, microsecond=0) - timedelta(minutes=5)
    pairs = _SERVED_MINUTES["17:52Z"][0]
    rows = [
        _row(bk, prob, at=minute + timedelta(seconds=i))
        for i, (bk, prob) in enumerate(pairs)
    ]

    served = _bucket(await _serve(_live_event(now), rows), minute.isoformat()[:16])
    assert served["probability_range"]["min"] == 0.8021, (
        "the band still opens at a price bovada had already replaced"
    )
