"""#4794 — the blank-card scope predicate, both directions, on a real engine.

THE DEFECT, measured on production 2026-09-10 13:35Z from the search endpoint's
own payload. `GET /api/events/search?q=Galatasaray&limit=60` returns 16 game
rows and **10 of them render nothing at all** — league name, the words "No
result reported" where the date belongs, two team names, and no date, no score,
no percentage:

    the 6 that render     4 carry a score; every one carries a `betting` or
                          `kalshi` entry in win_probability_sources
    the 10 that are blank none carries a score; 8 carry `{}` — an EMPTY bag —
                          and 2 carry `polymarket` alone

WHAT THIS SUITE PINS. The ship is "searching a club stops returning cards that
show nothing", and a guard that only asserted the suppression would pass just as
happily on a predicate that suppressed EVERYTHING. So every test is a PAIR: the
blank row is gone AND the row it must never touch is still there.

The four conditions are tested one at a time by RELAXING exactly one of them on
an otherwise-blank row. That shape is what pins the AND — a predicate that
dropped any single condition would still suppress the fully-blank specimen and
would only fail on its own relaxed sibling.

Executed against a real engine rather than asserted on compiled SQL, for the
reason `test_proven_duplicate_2263` Part C gives one column over: the trap here
is NULL semantics, and NULL semantics are a property of the database, not of the
string SQLAlchemy emits.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models import Event, Sport  # noqa: E402
from app.models.models import Base  # noqa: E402
from app.utils.blank_event_cards import (  # noqa: E402
    FINISHED_MARGIN,
    TERMINAL_STATUSES,
    has_nothing_to_render,
    not_a_blank_card,
)
from app.utils.event_completion import EVENT_SUSPENDED  # noqa: E402

# Gotcha #44: a fixed instant with no branch in it. Every row below is placed by
# an OFFSET from this, so the suite reads the same at any wall clock.
NOW = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)

#: Comfortably past `FINISHED_MARGIN`, so "no score" means "never will".
LONG_OVER = NOW - FINISHED_MARGIN - timedelta(hours=12)

S_SOCCER = 900

# The specimen ids. Each is one field away from BLANK, named for the field.
BLANK = 1
SCORED = 2
UPCOMING = 3
LIVE = 4
JUST_FINISHED = 5
PRICED = 6
EMPTY_BAG = 7
SCHEDULED_NULL_BAG = 8
JSON_NULL_BAG = 9

#: Rows whose bag must reach the database as a genuine SQL NULL.
#:
#: 🔴 THIS LIST EXISTS BECAUSE `win_probability_sources=None` DOES NOT PRODUCE
#: ONE. SQLAlchemy's JSON type serialises Python `None` to the JSON text
#: `'null'` rather than to SQL NULL (`typeof()` reads `text`, not `null`), so a
#: fixture built the obvious way tests a shape production almost never holds and
#: leaves the `IS NULL` arm of `_has_no_probability_sources` completely
#: unexercised — a mutation that deletes that arm passes the whole suite.
#:
#: Measured on production 2026-09-10 13:5xZ over the past-terminal-no-score
#: population: **61,730 SQL NULL, 0 JSON null, 1,094 `{}`**. SQL NULL is 98% of
#: the population, so it is the shape these tests have to carry.
_FORCE_SQL_NULL = (BLANK, SCORED, UPCOMING, LIVE, JUST_FINISHED, SCHEDULED_NULL_BAG)


def _row(
    id,
    *,
    commence_time=LONG_OVER,
    status="closed",
    home_score=None,
    away_score=None,
    sources=None,
    home="Galatasaray SK",
    away="Trabzonspor",
):
    """A blank card by default; each caller relaxes exactly one field."""
    return Event(
        id=id,
        sport_id=S_SOCCER,
        home_team_name=home,
        away_team_name=away,
        commence_time=commence_time,
        status=status,
        home_score=home_score,
        away_score=away_score,
        win_probability_sources=sources,
    )


@pytest.fixture
def engine():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=S_SOCCER, key="soccer_turkey_super_league", name="Super Lig"))

        # The defect itself.
        s.add(_row(BLANK))

        # Condition 3 relaxed: the score arrived.
        s.add(
            _row(SCORED, home_score=3, away_score=2, home="Galatasaray", away="Goztepe")
        )

        # Condition 1 relaxed: next week's fixture, no odds yet.
        s.add(_row(UPCOMING, commence_time=NOW + timedelta(days=7), status="scheduled"))

        # Condition 2 relaxed, two ways: the status, and the margin behind it.
        s.add(_row(LIVE, commence_time=NOW - timedelta(minutes=20), status="live"))
        s.add(
            _row(
                JUST_FINISHED,
                commence_time=NOW - timedelta(minutes=20),
                status="closed",
                home="Besiktas",
            )
        )

        # Condition 4 relaxed: pre-match odds, still no score.
        s.add(_row(PRICED, sources={"betting": {"value": 0.62}}))

        # The other emptiness: `{}` rather than SQL NULL.
        s.add(_row(EMPTY_BAG, sources={}, home="Kocaelispor"))

        # The NULL-safety specimen: a NULL bag on a row that must survive.
        s.add(
            _row(
                SCHEDULED_NULL_BAG,
                commence_time=NOW + timedelta(days=2),
                status="scheduled",
                sources=None,
                home="Fenerbahce",
            )
        )

        # The JSON-`null` shape. Zero rows on production today, but
        # `_EMPTY_SOURCE_BAGS` names it, and an unexercised member of a constant
        # is a claim nobody has checked.
        s.add(_row(JSON_NULL_BAG, sources=None, home="Antalyaspor"))
        s.commit()

        # Production's actual shape, which the ORM cannot express — see
        # `_FORCE_SQL_NULL`. Written last so it overwrites what `sources=None`
        # serialised, and deliberately NOT applied to JSON_NULL_BAG.
        s.execute(
            text(
                "UPDATE events SET win_probability_sources = NULL "
                f"WHERE id IN ({', '.join(str(i) for i in _FORCE_SQL_NULL)})"
            )
        )
        s.commit()
    return eng


def test_the_fixture_really_holds_the_two_shapes_it_claims(engine):
    """The fixture's own gate, because everything below rests on it.

    If `_FORCE_SQL_NULL` silently stopped working — a renamed column, a driver
    that coerces — every NULL-safety assertion in this file would keep passing
    while testing the JSON-text shape instead. Assert the storage, not the
    intent (gotcha #53: a value that reads back is not proof of its type).
    """
    with Session(engine) as s:
        kinds = dict(
            s.execute(
                text("SELECT id, typeof(win_probability_sources) FROM events")
            ).all()
        )

    assert kinds[BLANK] == "null", "BLANK must carry a genuine SQL NULL"
    assert kinds[JSON_NULL_BAG] == "text", "JSON_NULL_BAG must carry the text 'null'"
    assert kinds[EMPTY_BAG] == "text", "EMPTY_BAG must carry the text '{}'"


def _admitted(eng):
    """The ids the scope predicate admits — i.e. what search would still print."""
    with Session(eng) as s:
        return sorted(
            s.execute(select(Event.id).where(not_a_blank_card(NOW))).scalars().all()
        )


class TestTheBlankCardGoes:
    def test_the_blank_card_is_suppressed(self, engine):
        assert BLANK not in _admitted(engine)

    def test_an_empty_bag_is_the_same_emptiness_as_a_null_one(self, engine):
        """8 of the 10 specimen rows carried `{}`, not SQL NULL.

        A predicate that only tested `IS NULL` would leave every one of them on
        the page while passing the test above.
        """
        assert EMPTY_BAG not in _admitted(engine)

    def test_a_json_null_bag_is_the_same_emptiness_too(self, engine):
        """`'null'` is the third member of `_EMPTY_SOURCE_BAGS`.

        0 rows on production today, so this is the one shape here that is not
        load-bearing — but a constant listing a value nothing exercises is a
        claim nobody has checked.
        """
        assert JSON_NULL_BAG not in _admitted(engine)

    def test_every_terminal_status_suppresses_including_suspended(self, engine):
        """`suspended` is the disposition the #4242 re-date leaves behind.

        Six of the ten specimen rows wear it, so a `TERMINAL_STATUSES` that
        quietly lost it would leave most of the reported page exactly as it is.
        Driven off the constant, so a future edit to it is what this reads.
        """
        assert EVENT_SUSPENDED in TERMINAL_STATUSES

        with Session(engine) as s:
            for i, status in enumerate(TERMINAL_STATUSES):
                s.add(_row(500 + i, status=status, home=f"Club {i}"))
            s.commit()

        admitted = _admitted(engine)
        assert not [
            i for i in range(500, 500 + len(TERMINAL_STATUSES)) if i in admitted
        ]


class TestTheRealCardsStay:
    """THE TRAP. Every assertion above is satisfied by a predicate that admits
    nothing at all, so each condition gets a row that isolates it."""

    def test_a_finished_game_with_a_score_is_still_returned(self, engine):
        assert SCORED in _admitted(engine)

    def test_an_upcoming_fixture_with_no_odds_yet_is_still_returned(self, engine):
        """Condition 1 — the front door's whole job.

        This row differs from BLANK in `commence_time` and status ALONE: no
        score, no sources. Suppressing it would empty the page while cleaning it.
        """
        assert UPCOMING in _admitted(engine)

    def test_a_game_in_progress_is_never_suppressed(self, engine):
        assert LIVE in _admitted(engine)

    def test_a_game_that_just_kicked_off_survives_a_terminal_status(self, engine):
        """The case `FINISHED_MARGIN` exists for: a scoreboard still settling."""
        assert JUST_FINISHED in _admitted(engine)

    def test_a_past_game_with_pre_match_odds_and_no_score_is_still_returned(
        self, engine
    ):
        """Condition 4 — the one carrying most of the safety.

        This card is not blank: it shows percentages and a "Pre-match ·
        sportsbooks" line. A real fixture we tracked has pre-match odds, so this
        is what keeps a genuinely-played game whose score never backfilled.
        """
        assert PRICED in _admitted(engine)

    def test_a_null_bag_row_is_not_dropped_by_the_not(self, engine):
        """The trap the module is a function to avoid.

        `NOT (… AND cast(sources) IN ('{}'))` evaluates to NULL — and therefore
        drops the row — for every row with a NULL bag, which is most of them.
        This row can only survive if the `IS NULL` arm made the inner AND
        two-valued.
        """
        assert SCHEDULED_NULL_BAG in _admitted(engine)


class TestThePartition:
    def test_the_two_predicates_are_exact_complements(self, engine):
        """No row in neither, no row in both.

        They are written as a predicate and its `not_()`, so this is cheap — and
        it is precisely the invariant a future edit that added an arm to one and
        not the other would break silently. It is also a second, independent
        reading of the null-safety property: a row evaluating to NULL on either
        side would fall out of both sets.
        """
        with Session(engine) as s:
            all_ids = set(s.execute(select(Event.id)).scalars().all())
            blank = set(
                s.execute(select(Event.id).where(has_nothing_to_render(NOW)))
                .scalars()
                .all()
            )
        kept = set(_admitted(engine))

        assert blank | kept == all_ids
        assert not (blank & kept)


class TestTheSurfacesCarryIt:
    """#2263's Part D, for the same reason: a predicate in a utils module that
    no route imports is a no-op that every unit test passes."""

    def test_both_search_paths_carry_the_predicate(self):
        """The primary scope list AND the fuzzy-corrected fallback.

        The fallback replaces `query` wholesale and builds its own condition
        list — the file says so in its own comment — so a clause carried only by
        `event_scope_conditions` is silently dropped for exactly the MISSPELLED
        queries, which are the ones a person types.
        """
        from pathlib import Path

        source = Path("app/routes/events.py").read_text()
        head, _, tail = source.partition("fuzzy_conditions = [")
        assert tail, "the fuzzy fallback's condition list has moved or been renamed"

        assert (
            "not_a_blank_card(now)" in head
        ), "the primary event_scope_conditions no longer carries not_a_blank_card"
        assert "not_a_blank_card(now)" in tail.split("]")[0], (
            "the fuzzy-corrected fallback no longer carries not_a_blank_card — "
            "misspelled queries would still return blank cards"
        )
