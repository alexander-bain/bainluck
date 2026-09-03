"""The display collapse survives a provider clock disagreement (#2057).

WHAT BROKE
----------
``feed_event_candidates`` collapses duplicate game rows into one card, and it
partitioned on ``commence_time`` **exactly**.  Every duplicate it was built for
shared one — #2065's esports rows were byte-identical restatements, and #2213's
Red Sox pair was measured as "identical ``sport_id``, ``home_team_name``,
``away_team_name`` and ``commence_time``".

That stopped being true.  Measured on production 2026-08-31 across every
duplicate group in a five-day window: **three** groups at a 0s gap, **twelve**
at exactly 60s, one at 1,784s, and thirty-nine at 4.7h or more.  The twelve are
the entire MLB slate — a StatPal row and an Odds-API row for the same game, one
minute apart — so the exact key was inert against all of them.  Discover served
four of those pairs as eight cards.

WHAT THESE TESTS PIN
--------------------
The corpus below is the production pair, reproduced by its measured SIGNALS
rather than by its ids: both rows carry ``win_probability_sources``, neither
carries a score, and only the Odds-API row carries an opening probability.  That
shape matters — it is what makes ``has_opening`` the deciding key, and the
lowest-id tiebreak underneath it would pick the *poorer* StatPal row.

Every widening of a same-fixture rule is a doubleheader hazard, so the
doubleheader is asserted at the new boundary and not only far from it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, or_, select
from sqlalchemy.orm import Session

from app.models import Event, Sport
from app.utils.espn_candidate_selection import MAX_SAME_GAME_SECONDS
from app.utils.feed_event_candidates import (
    SAME_FIXTURE_SECONDS,
    deduplicated_event_ids,
    event_candidate_ids,
)

# Registered in the sibling module for the sqlite DDL shims those types need.
from tests.test_feed_event_candidates import _jsonb_on_sqlite  # noqa: F401

S_MLB = 1
S_SOCCER = 2

#: 2026-08-31 22:40Z — Cincinnati Reds v San Diego Padres, the StatPal row's
#: start.  The Odds-API row says 22:41Z.
FIRST_PITCH = datetime(2026, 8, 31, 22, 40, tzinfo=timezone.utc)

STATPAL_ROW = 15291401
ODDS_API_ROW = 15298070


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://")
    Base = Event.__base__
    Base.metadata.create_all(eng, tables=[Sport.__table__, Event.__table__])
    return eng


def _event(*, id, home, away, commence_time, sport_id=S_MLB, status="scheduled", **kw):
    return Event(
        id=id,
        sport_id=sport_id,
        home_team_name=home,
        away_team_name=away,
        commence_time=commence_time,
        status=status,
        win_probability_sources=kw.pop("sources", {"betting": {"value": 0.5}}),
        **kw,
    )


def _seed(session, rows):
    session.add(Sport(id=S_MLB, key="baseball_mlb", name="MLB"))
    session.add(Sport(id=S_SOCCER, key="soccer_other", name="Soccer"))
    for row in rows:
        session.add(row)
    session.commit()


def _conditions():
    return [or_(Event.status == "live", Event.status == "scheduled")]


def _admitted(session):
    return {r[0] for r in session.execute(event_candidate_ids(_conditions())).all()}


def _mystuff_admitted(session):
    return {r[0] for r in session.execute(deduplicated_event_ids(_conditions())).all()}


def _twin_pair():
    """The production specimen, by its measured signals.

    StatPal: sources, no score, NO opening probability, and the lower id.
    Odds-API: sources, no score, an opening probability, and the higher id.
    """
    return [
        _event(
            id=STATPAL_ROW,
            home="Cincinnati Reds",
            away="San Diego Padres",
            commence_time=FIRST_PITCH,
        ),
        _event(
            id=ODDS_API_ROW,
            home="Cincinnati Reds",
            away="San Diego Padres",
            commence_time=FIRST_PITCH + timedelta(seconds=60),
            opening_home_probability=0.4267,
        ),
    ]


# ---------------------------------------------------------------------------
# 1 — the defect itself
# ---------------------------------------------------------------------------


def test_a_sixty_second_clock_disagreement_is_one_card(engine):
    """The whole of #2057, on the pair that was live when it was written.

    Against the exact-``commence_time`` key this returns BOTH ids — that is the
    red-first state, and it is what production was serving.
    """
    with Session(engine) as s:
        _seed(s, _twin_pair())
        assert _admitted(s) == {ODDS_API_ROW}


def test_the_surviving_row_is_the_richer_one(engine):
    """Not merely "one card" — the RIGHT one.

    Both rows carry sources and neither carries a score, so the decision falls
    to ``has_opening``: the key #2213 added and CERT-407 repositioned.  The
    lowest-id tiebreak underneath it would keep the StatPal row, which on
    production carries 4 linked markets against the Odds-API row's 23 and no
    opening price at all.  Collapsing to that row would trade the duplicate for
    a worse card — CERT-407's exact finding, one surface along.
    """
    with Session(engine) as s:
        _seed(s, _twin_pair())
        survivor = _admitted(s)
        assert survivor == {ODDS_API_ROW}
        assert STATPAL_ROW not in survivor
        assert min(STATPAL_ROW, ODDS_API_ROW) == STATPAL_ROW, (
            "the specimen must keep the poorer row as the LOWER id, or this "
            "test stops proving that has_opening is what decides it"
        )


def test_my_stuff_and_discover_still_agree(engine):
    """One definition of "the same fixture", across both arms of the collapse."""
    with Session(engine) as s:
        _seed(s, _twin_pair())
        assert _mystuff_admitted(s) == _admitted(s)


def test_the_suppressed_row_is_still_a_row(engine):
    """A DISPLAY collapse, not a merge — ruling 048 is untouched.

    The StatPal row is hidden from the rail and remains fully addressable at
    ``/api/events/{id}``.  A future "cleanup" that turned this into a DELETE
    would pass every other test in this file.
    """
    with Session(engine) as s:
        _seed(s, _twin_pair())
        _admitted(s)
        still_there = {
            r[0]
            for r in s.execute(
                select(Event.id).where(Event.id.in_([STATPAL_ROW, ODDS_API_ROW]))
            ).all()
        }
        assert still_there == {STATPAL_ROW, ODDS_API_ROW}


# ---------------------------------------------------------------------------
# 2 — the doubleheader, asserted AT the boundary and not only far from it
# ---------------------------------------------------------------------------


def test_a_doubleheader_is_still_two_cards(engine):
    """ "Any matcher smart enough to join two same-game claims is provably dumb
    enough to destroy a doubleheader." Four hours apart, both must survive."""
    with Session(engine) as s:
        _seed(
            s,
            [
                _event(
                    id=1,
                    home="Miami Marlins",
                    away="Boston Red Sox",
                    commence_time=FIRST_PITCH,
                ),
                _event(
                    id=2,
                    home="Miami Marlins",
                    away="Boston Red Sox",
                    commence_time=FIRST_PITCH + timedelta(hours=4),
                ),
            ],
        )
        assert _admitted(s) == {1, 2}


def test_one_second_past_the_window_stays_two_cards(engine):
    """The boundary itself, from the outside.

    A test that only drives 60s and 4h passes with the tolerance set to
    anything between them, including a value wide enough to eat a short
    doubleheader.  This pins where the edge actually is.
    """
    with Session(engine) as s:
        _seed(
            s,
            [
                _event(
                    id=1,
                    home="Miami Marlins",
                    away="Boston Red Sox",
                    commence_time=FIRST_PITCH,
                ),
                _event(
                    id=2,
                    home="Miami Marlins",
                    away="Boston Red Sox",
                    commence_time=FIRST_PITCH
                    + timedelta(seconds=SAME_FIXTURE_SECONDS + 1),
                ),
            ],
        )
        assert _admitted(s) == {1, 2}


def test_exactly_at_the_window_is_one_card(engine):
    """And from the inside, so the comparison cannot silently become strict."""
    with Session(engine) as s:
        _seed(
            s,
            [
                _event(
                    id=1,
                    home="Miami Marlins",
                    away="Boston Red Sox",
                    commence_time=FIRST_PITCH,
                ),
                _event(
                    id=2,
                    home="Miami Marlins",
                    away="Boston Red Sox",
                    commence_time=FIRST_PITCH + timedelta(seconds=SAME_FIXTURE_SECONDS),
                    opening_home_probability=0.5,
                ),
            ],
        )
        assert _admitted(s) == {2}


def test_the_window_cannot_reach_a_doubleheader(engine):
    """A bound on the CONSTANT, not on one corpus.

    Every specimen above fixes a distance.  This fixes the rule: the display
    window stays far below the repository's own measured identity bound, so no
    future widening can quietly grow it into doubleheader range without
    failing here.
    """
    assert SAME_FIXTURE_SECONDS < MAX_SAME_GAME_SECONDS
    assert SAME_FIXTURE_SECONDS <= 15 * 60, (
        "the display window is deliberately the smallest number that covers "
        "the measured 60s provider skew; widening it hides real games"
    )


# ---------------------------------------------------------------------------
# 3 — what must NOT collapse
# ---------------------------------------------------------------------------


def test_different_teams_at_the_same_minute_are_two_cards(engine):
    """The window is scoped by the fixture keys, not applied to the clock alone."""
    with Session(engine) as s:
        _seed(
            s,
            [
                _event(
                    id=1,
                    home="Cincinnati Reds",
                    away="San Diego Padres",
                    commence_time=FIRST_PITCH,
                ),
                _event(
                    id=2,
                    home="Tampa Bay Rays",
                    away="New York Mets",
                    commence_time=FIRST_PITCH + timedelta(seconds=60),
                ),
            ],
        )
        assert _admitted(s) == {1, 2}


def test_only_the_away_team_differing_is_still_two_cards(engine):
    """One team in common is not one fixture.

    ADDED BY A SURVIVING MUTATION.  The corpus above varies BOTH names, so
    deleting ``away_team_name`` from the collapse partition left every test in
    this file green — the inner ``lag()`` window still carried the full key, so
    ``prev_commence_time`` stayed correctly scoped and nothing downstream
    noticed.  A specimen has to vary exactly one name for that key to be load-
    bearing.
    """
    with Session(engine) as s:
        _seed(
            s,
            [
                _event(
                    id=1,
                    home="Cincinnati Reds",
                    away="San Diego Padres",
                    commence_time=FIRST_PITCH,
                ),
                _event(
                    id=2,
                    home="Cincinnati Reds",
                    away="Chicago Cubs",
                    commence_time=FIRST_PITCH,
                ),
            ],
        )
        assert _admitted(s) == {1, 2}


def test_only_the_home_team_differing_is_still_two_cards(engine):
    """The symmetric specimen, so neither name can be dropped unnoticed."""
    with Session(engine) as s:
        _seed(
            s,
            [
                _event(
                    id=1,
                    home="Cincinnati Reds",
                    away="San Diego Padres",
                    commence_time=FIRST_PITCH,
                ),
                _event(
                    id=2,
                    home="Chicago Cubs",
                    away="San Diego Padres",
                    commence_time=FIRST_PITCH,
                ),
            ],
        )
        assert _admitted(s) == {1, 2}


def test_the_same_teams_in_different_sports_are_two_cards(engine):
    """``sport_id`` stays in the fixture key."""
    with Session(engine) as s:
        _seed(
            s,
            [
                _event(
                    id=1,
                    home="Kataller Toyama",
                    away="Tochigi City FC",
                    commence_time=FIRST_PITCH,
                ),
                _event(
                    id=2,
                    sport_id=S_SOCCER,
                    home="Kataller Toyama",
                    away="Tochigi City FC",
                    commence_time=FIRST_PITCH + timedelta(seconds=60),
                ),
            ],
        )
        assert _admitted(s) == {1, 2}


def test_the_census_outlier_stays_uncollapsed(engine):
    """The control the measurement itself supplies.

    One group in the 2026-08-31 census sat at 1,784s — a lone ``soccer_other``
    pair, far outside the window.  It is left alone deliberately: the fail-safe
    direction is an extra card, and nothing measured says those two rows are
    one fixture.
    """
    with Session(engine) as s:
        _seed(
            s,
            [
                _event(
                    id=1,
                    sport_id=S_SOCCER,
                    home="Kataller Toyama",
                    away="Tochigi City FC",
                    commence_time=FIRST_PITCH,
                ),
                _event(
                    id=2,
                    sport_id=S_SOCCER,
                    home="Kataller Toyama",
                    away="Tochigi City FC",
                    commence_time=FIRST_PITCH + timedelta(seconds=1784),
                ),
            ],
        )
        assert _admitted(s) == {1, 2}


# ---------------------------------------------------------------------------
# 4 — the documented chain behaviour, pinned so it cannot drift silently
# ---------------------------------------------------------------------------


def test_a_chain_fails_safe_rather_than_transitively_fusing(engine):
    """Three rows four minutes apart do NOT become one card.

    ``lag()`` compares each row with its predecessor, so row 3 adopts row 2's
    start and not row 1's.  The result is two cards, not one and not three.
    This is the documented, deliberate fail-safe direction — an extra card
    never hides a game — and no such chain exists in the measured data.  Pinned
    because a "fix" that made it transitive would be a real widening.
    """
    with Session(engine) as s:
        _seed(
            s,
            [
                _event(
                    id=1,
                    home="Miami Marlins",
                    away="Boston Red Sox",
                    commence_time=FIRST_PITCH,
                ),
                _event(
                    id=2,
                    home="Miami Marlins",
                    away="Boston Red Sox",
                    commence_time=FIRST_PITCH + timedelta(minutes=4),
                ),
                _event(
                    id=3,
                    home="Miami Marlins",
                    away="Boston Red Sox",
                    commence_time=FIRST_PITCH + timedelta(minutes=8),
                ),
            ],
        )
        assert _admitted(s) == {1, 3}


# ---------------------------------------------------------------------------
# 5 — the whole measured slate, end to end
# ---------------------------------------------------------------------------


def test_the_measured_slate_halves(engine):
    """Twelve twin pairs in, twelve cards out.

    The census shape rather than one pair: this is what the MLB slate looked
    like on 2026-08-31, and it is the number a production re-read should match.
    """
    rows = []
    for i in range(12):
        base = FIRST_PITCH + timedelta(minutes=5 * i)
        rows.append(
            _event(
                id=100 + i * 2,
                home=f"Home {i}",
                away=f"Away {i}",
                commence_time=base,
            )
        )
        rows.append(
            _event(
                id=101 + i * 2,
                home=f"Home {i}",
                away=f"Away {i}",
                commence_time=base + timedelta(seconds=60),
                opening_home_probability=0.5,
            )
        )
    with Session(engine) as s:
        _seed(s, rows)
        admitted = _admitted(s)
        assert len(admitted) == 12
        assert admitted == {101 + i * 2 for i in range(12)}
