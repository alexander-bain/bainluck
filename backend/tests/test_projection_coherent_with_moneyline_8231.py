"""#8231 — a settled page's Score Differential stops ending on a mirrored projection.

THE SHIP, IN A READER'S WORDS: on `/events/15316869` (Red Sox 2 - 3 Guardians,
Final) the Win Probability chart ends at 0% Boston while the Score Differential
chart's projected margin spikes to Boston +1.5 on its last point. After this, the
projected line ends where the books that still made sense left it.

THE CAUSE, MEASURED ON PRODUCTION (`odds_snapshots`, event 15316869). The 01:42Z
bucket's only projection was betmgm's:

    01:40:45Z  betmgm  ML +675/-1200 (home 0.1226)  home +1.5 @ -10000  -> proj 2.0 - 3.5
    01:42:14Z  betmgm  ML +900/-2000 (home 0.0950)  home -1.5 @ +3300   -> proj 3.5 - 2.0

A run line is pinned at ±1.5, so late in a decided game a book can hang the -1.5
on the trailing side at long odds. `project_scores` reads the point and ignores
the price, so the same book that makes Boston a 9.5% moneyline shot "projects"
Boston by a run and a half. The refusal is keyed on that contradiction and
nothing else: a book whose projected leader is its own moneyline underdog gives
no projected score; every other field it wrote is served unchanged.

WHAT THIS IS NOT. It writes nothing. Stored rows keep their projection; the
refusal happens where the route serves them, so the specimen and every stored
row like it read correctly on the next page load with no backfill.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import app.routes.events as events_module
from app.utils.odds_math import (
    aggregate_bookmaker_odds,
    project_scores,
    projection_contradicts_moneyline,
    refuse_incoherent_projections,
)

from tests.test_history_one_vote_per_bookmaker_6771 import (
    _bucket,
    _live_event,
    _row,
    _serve,
)

UTC = timezone.utc


def _book(bookmaker, home_prob, home_spread, over_under, *, at=None):
    """An `odds_snapshots` row whose projection is derived exactly as the writer derives it."""
    row = _row(bookmaker, home_prob, **({"at": at} if at else {}))
    row.home_spread = home_spread
    row.over_under = over_under
    if home_spread is not None and over_under:
        row.projected_home_score, row.projected_away_score = project_scores(
            float(home_spread), float(over_under)
        )
    return row


# The two betmgm readings, verbatim from production.
_BETMGM_0140 = dict(home_prob=0.1226, home_spread=1.5, over_under=5.5)
_BETMGM_0142 = dict(home_prob=0.0950, home_spread=-1.5, over_under=5.5)


# ---------------------------------------------------------------------------
# The predicate
# ---------------------------------------------------------------------------


def test_the_specimen_reading_is_a_contradiction():
    home, away = project_scores(_BETMGM_0142["home_spread"], _BETMGM_0142["over_under"])
    assert (home, away) == (3.5, 2.0), "the writer's own projection for the specimen"
    assert projection_contradicts_moneyline(_BETMGM_0142["home_prob"], home, away)


def test_the_same_book_two_minutes_earlier_is_coherent():
    """The control: same book, same run line, sides the right way round."""
    home, away = project_scores(_BETMGM_0140["home_spread"], _BETMGM_0140["over_under"])
    assert (home, away) == (2.0, 3.5)
    assert not projection_contradicts_moneyline(_BETMGM_0140["home_prob"], home, away)


@pytest.mark.parametrize(
    "home_prob, home, away, expected",
    [
        (0.80, 4.0, 2.0, False),   # favourite projected ahead
        (0.20, 2.0, 4.0, False),   # underdog projected behind
        (0.80, 2.0, 4.0, True),    # favourite projected behind
        (0.20, 4.0, 2.0, True),    # underdog projected ahead
        (0.50, 4.0, 2.0, False),   # even moneyline crowns nobody
        (0.80, 3.0, 3.0, False),   # pick'em projection contradicts nobody
        (None, 4.0, 2.0, False),   # no moneyline is no evidence
        (0.80, None, 2.0, False),
        (0.80, 4.0, None, False),
    ],
)
def test_the_predicate_fires_only_on_opposite_signs(home_prob, home, away, expected):
    assert projection_contradicts_moneyline(home_prob, home, away) is expected


def test_decimal_inputs_are_read_as_numbers():
    """Stored columns arrive as `Decimal`; the predicate must not choke on them."""
    from decimal import Decimal

    assert projection_contradicts_moneyline(Decimal("0.0950"), Decimal("3.5"), Decimal("2.0"))
    assert not projection_contradicts_moneyline(Decimal("0.1226"), Decimal("2.0"), Decimal("3.5"))


# ---------------------------------------------------------------------------
# The consensus
# ---------------------------------------------------------------------------


def test_the_specimen_bucket_serves_no_projection():
    """01:42Z: betmgm was the bucket's only projection, so the bucket has none."""
    rows = [
        _book("fanduel", 0.1111, None, 5.5),
        _book("fanatics", 0.1060, None, 6.5),
        _book("betmgm", **_BETMGM_0142),
        _book("williamhill_us", 0.1570, None, 5.5),
    ]
    agg = aggregate_bookmaker_odds(rows)
    assert agg["projected_home_score"] is None
    assert agg["projected_away_score"] is None
    # Nothing else the book wrote is refused.
    assert agg["home_spread"] == -1.5
    assert agg["over_under"] == 5.8
    assert agg["bookmaker_count"] == 4


def test_a_contradicting_book_leaves_the_coherent_mean_as_a_pair():
    """Refusing one side only would average a home figure over a different set of
    books than the away figure it is subtracted from."""
    rows = [
        _book("betmgm", **_BETMGM_0142),                # 3.5 - 2.0, refused
        _book("draftkings", 0.15, 1.5, 6.5),            # 2.5 - 4.0
        _book("fanduel", 0.14, 1.5, 7.5),               # 3.0 - 4.5
    ]
    agg = aggregate_bookmaker_odds(rows)
    assert (agg["projected_home_score"], agg["projected_away_score"]) == (2.8, 4.2)


def test_a_coherent_bucket_is_unchanged():
    """Blast-radius control: nothing contradicts, nothing moves."""
    rows = [
        _book("betmgm", **_BETMGM_0140),     # 2.0 - 3.5
        _book("draftkings", 0.15, 1.5, 6.5),  # 2.5 - 4.0
    ]
    agg = aggregate_bookmaker_odds(rows)
    assert (agg["projected_home_score"], agg["projected_away_score"]) == (2.2, 3.8)


# ---------------------------------------------------------------------------
# The per-book rows
# ---------------------------------------------------------------------------


def test_per_book_rows_are_refused_and_their_other_fields_kept():
    rows = [
        {"bookmaker": "betmgm", "home_probability": 0.095, "spread": -1.5,
         "projected_home_score": 3.5, "projected_away_score": 2.0},
        {"bookmaker": "draftkings", "home_probability": 0.15, "spread": 1.5,
         "projected_home_score": 2.5, "projected_away_score": 4.0},
    ]
    out = refuse_incoherent_projections(rows)
    assert out is rows
    assert rows[0] == {"bookmaker": "betmgm", "home_probability": 0.095, "spread": -1.5,
                       "projected_home_score": None, "projected_away_score": None}
    assert rows[1]["projected_home_score"] == 2.5
    assert rows[1]["projected_away_score"] == 4.0


def test_a_reversed_book_is_judged_after_its_sides_are_swapped_back():
    """The table swaps a reversed book's legs before serving; a raw-orientation
    judgement would refuse the correct row and keep the mirrored one."""
    swapped = {"home_probability": 0.80, "projected_home_score": 4.0, "projected_away_score": 2.0}
    refuse_incoherent_projections([swapped])
    assert swapped["projected_home_score"] == 4.0


def test_every_served_per_book_site_calls_the_refusal():
    """Two `bookmaker_odds` tables and the history's per-book lines. A route that
    stopped calling the helper would pass every helper test above."""
    import inspect

    src = inspect.getsource(events_module)
    assert src.count('response["bookmaker_odds"] = refuse_incoherent_projections(bookmaker_odds_list)') == 2
    assert "refuse_incoherent_projections([point_data])" in src
    assert 'response["bookmaker_odds"] = bookmaker_odds_list\n' not in src


# ---------------------------------------------------------------------------
# Through the route
# ---------------------------------------------------------------------------


async def test_the_route_ends_on_the_last_coherent_projection():
    """The specimen's last two minutes, through the real `/history` route: the
    01:40-shaped bucket keeps its projection, the 01:42-shaped one carries none,
    so the chart's projected line ends on Boston -1.5, not +1.5."""
    now = datetime.now(UTC)
    t1 = now.replace(second=0, microsecond=0) - timedelta(minutes=6)
    t2 = t1 + timedelta(minutes=2)
    rows = [
        _book("betmgm", **_BETMGM_0140, at=t1),
        _book("betmgm", **_BETMGM_0142, at=t2),
    ]
    payload = await _serve(_live_event(now), rows)

    before = _bucket(payload, t1.isoformat()[:16])
    after = _bucket(payload, t2.isoformat()[:16])
    assert (before["projected_home_score"], before["projected_away_score"]) == (2.0, 3.5)
    assert after["projected_home_score"] is None
    assert after["projected_away_score"] is None
    assert after["home_probability"] == 0.095, "the moneyline reading is served untouched"

    points = payload["bookmaker_history"]["betmgm"]
    by_minute = {p["timestamp"][:16]: p for p in points}
    assert by_minute[t2.isoformat()[:16]]["projected_home_score"] is None
    assert by_minute[t1.isoformat()[:16]]["projected_home_score"] == 2.0
