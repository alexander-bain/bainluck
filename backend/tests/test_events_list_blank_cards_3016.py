"""#3016 — a league page stops leading with cards that can say nothing.

THE SHIP: `/sports/soccer_other` stops opening on `Live & Paused 186` where all
186 cards are two club names and the words "No result reported". Measured on
production 2026-09-13 21:4xZ at 390px, that page is 21,792px tall and holds no
real content anywhere in it — no score, no probability, no kick-off time, on any
card. The oldest row is two days past its own kickoff.

## The change is a CALL SITE, not a rule

`not_a_blank_card` shipped for #4794 and `/api/events/search` has spent it since.
`list_events` — the endpoint that draws every `/sports/{key}` page — never
adopted it. So the predicate that made the search door readable has been sitting
one import away from the league door, in the same module, for three days. This
suite guards the adoption. The predicate itself is unchanged and is guarded by
`test_blank_event_cards_4794.py`; nothing here re-implements it.

The sibling belt on this same route (`not_a_proven_duplicate`, #5918) landed the
same way and its comment says the same thing: "this route was the last list
surface to be missing it".

## REACH AND THE ONE CONTROL THAT DECIDES IT

Over this route's own window and status set, production 2026-09-13 21:4xZ
(`sql_fingerprint` 2e7a5e91df29c41d, per-sport split c63c79322a1c0cd7):

    route serves                     2,628 rows
    suppressed                         932
    of those, carrying an
      `opening_home_probability`         0    <- the control
    with a `completed_at`                0
    with an `espn_id`                    0

`_has_no_probability_sources` reads the JSONB bag and nothing else, so a row
holding an EMPTY bag and a populated opening line renders a "Pre-match"
percentage and would still be suppressed. That is a real false-positive shape
and `TestTheKnownLimit` pins it rather than pretending the predicate handles it.
It is safe to spend here because production holds ZERO of them — a measurement
about today's rows, not a property of the predicate, which is why it is a
measured number in this docstring and a named test below rather than an
invariant anybody asserts.

## 🔴 THIS IS NOT THE `_EMPTY_SOURCE_BAGS` WIDENING, WHICH IS REFUTED

#3016's remainder splits. The other half is rows whose bag is NON-empty but
holds only `statpal_injuries`-style metadata; widening the emptiness test to
reach them blanks 452 of 462 rows that serve a real pre-match line (measured,
recorded on #3016 comment 5655941692). That fix stays unbuilt, this one does not
depend on it, and `test_a_metadata_only_bag_is_not_reached` is the control that
keeps the two apart — if a later session widens `_EMPTY_SOURCE_BAGS`, that test
goes red here and names the refutation.

## WHAT THIS DELIBERATELY DOES NOT REACH

A row still wearing `scheduled` hours past its own kickoff renders blank too,
and the frontend's `startedWithoutResult` files it under the very same
"Live & Paused" heading. `TERMINAL_STATUSES` excludes it on purpose — a
scheduled row may yet be played — so those rows stay and #3016 stays open for
them. `test_a_blank_scheduled_row_past_kickoff_survives` asserts the limit so
nobody reads this ship as bigger than it is.

## RED-FIRST

`TestTheDefectReproduces` runs the same corpus through the route with the belt
lifted and shows the blank rows served. Without it every assertion below could
be passing over a corpus the pre-fix route would also have cleaned, and the
suite would certify nothing. The controls in `TestWhatMustNotChange` are chosen
to be green in BOTH arms — a control that needs the fix proves the fix is
present, not that it is narrow.

🔴 REAL ROWS IN A REAL ENGINE. The predicate's probability arm is a
`cast(... AS String).in_(...)` over a JSONB column and its status arm is an
`IN`; a MagicMock answering every statement with the same rows would pass this
file while the WHERE clause did nothing. The harness is the one
`test_events_list_tag_fold_5918.py` uses, for that reason.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


# DDL shims so `create_all` can build the real schema on SQLite.
@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models.models import Base, Event, OddsSnapshot, Sport  # noqa: E402
from app.routes.events import list_events  # noqa: E402

S_OTHER = 1401
SPORT_KEY = "soccer_other"

#: The production specimens, by id and verbatim, read 2026-09-13 21:3xZ.
#: `15309432` and `15307903` are two of the 186 cards the page opens on; both
#: carry `status='suspended'`, a `{}` bag, no score and no opening line.
BLANK_A = 15309432  # CS 2 de Mayo v Libertad
BLANK_B = 15307903
#: The EPL row whose bag holds ONLY `statpal_injuries` — the refuted widening's
#: population, which this ship must not touch.
METADATA_ONLY = 15310639  # Liverpool v Fulham


def _fresh(value: float) -> dict:
    """A reading stamped now, so source-weight decay cannot move an assertion.

    Gotcha #44: offset from the clock, never a literal stamp.
    """
    return {"value": value, "updated_at": datetime.now(timezone.utc).isoformat()}


def _played(hours_ago=45):
    """A kick-off far enough back to clear `FINISHED_MARGIN` (6h).

    45 hours is the real gap the specimens wear: `15309432` commences
    2026-09-12 00:30Z and was still on the page at 21:3xZ on the 13th.
    """
    return datetime.now(timezone.utc) - timedelta(hours=hours_ago)


def _event(
    event_id,
    *,
    home,
    away,
    when=None,
    status="suspended",
    scores=(None, None),
    sources=None,
    opening=(None, None),
):
    when = _played() if when is None else when
    return Event(
        id=event_id,
        sport_id=S_OTHER,
        home_team_name=home,
        away_team_name=away,
        commence_time=when,
        completed_at=when + timedelta(hours=2) if status == "completed" else None,
        status=status,
        home_score=scores[0],
        away_score=scores[1],
        win_probability_sources=sources,
        event_tags=["provenance:unanchored"],
        opening_home_probability=opening[0],
        opening_away_probability=opening[1],
    )


def _blank(event_id, home="CS 2 de Mayo", away="Libertad", **kw):
    """A card that can render nothing: terminal, past, no score, empty bag."""
    kw.setdefault("sources", {})
    return _event(event_id, home=home, away=away, **kw)


def _engine(*events, sql_null_bag_for=()):
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=S_OTHER, key=SPORT_KEY, name="Other Soccer", group="Soccer"))
        for e in events:
            s.add(e)
        s.commit()
        # 🔴 The trap `blank_event_cards`' own docstring warns about:
        # `win_probability_sources=None` through the ORM does NOT produce a SQL
        # NULL — SQLAlchemy's JSON type writes the JSON TEXT 'null'. A fixture
        # built the obvious way exercises the `{}`/'null' arm and leaves the
        # `IS NULL` arm untested, so a mutation deleting it passes. Force the
        # real shape, then prove it took.
        for event_id in sql_null_bag_for:
            s.execute(
                text(
                    "UPDATE events SET win_probability_sources = NULL " "WHERE id = :i"
                ),
                {"i": event_id},
            )
            s.commit()
            kind = s.execute(
                text(
                    "SELECT typeof(win_probability_sources) FROM events "
                    "WHERE id = :i"
                ),
                {"i": event_id},
            ).scalar()
            assert kind == "null", (
                f"fixture {event_id} did not get a SQL NULL bag (typeof={kind!r}); "
                "the IS NULL arm would go untested"
            )
    return eng


class _Session:
    """A real engine behind the async surface `list_events` calls."""

    def __init__(self, session):
        self._s = session

    async def execute(self, statement, *args, **kwargs):
        return self._s.execute(statement, *args)


def _portable_odds_query(event_ids):
    """The odds enrichment read, in a form SQLite can parse.

    `latest_odds_per_bookmaker_query` is a recursive CTE joined `LATERAL`, a
    deliberate Postgres shape no other dialect executes; its own guards live in
    `tests/integration/test_search_odds_enrichment_equivalence.py` against real
    Postgres. No test here stores a snapshot, so the truthful answer is the
    empty one either way — this swaps which SQL is parsed, not what the page is
    told.
    """
    return select(OddsSnapshot).where(OddsSnapshot.event_id.in_(event_ids))


def _payload(*events, sql_null_bag_for=(), **params):
    """The served `GET /api/events` body, through the real route."""
    eng = _engine(*events, sql_null_bag_for=sql_null_bag_for)
    call = {"sport": SPORT_KEY, "status": None, "days": 14, "limit": 200, "offset": 0}
    call.update(params)
    with (
        patch(
            "app.routes.events._load_gei_percentiles", new=AsyncMock(return_value={})
        ),
        patch("app.routes.events._build_team_lookup", new=AsyncMock(return_value={})),
        patch(
            "app.routes.events.latest_odds_per_bookmaker_query",
            new=_portable_odds_query,
        ),
        Session(eng) as s,
    ):
        return asyncio.run(list_events(db=_Session(s), **call))


def _ids(payload) -> set:
    return {card["id"] for card in payload["events"]}


# ---------------------------------------------------------------------------
# red-first
# ---------------------------------------------------------------------------


class TestTheDefectReproduces:
    """The same corpus, with the belt lifted, serves the blank cards.

    This is the measurement that makes every assertion below mean something.
    `not_a_blank_card` is patched at the name the ROUTE resolves, so the route
    still runs its real query — one condition lighter, which is exactly the
    pre-fix endpoint.
    """

    @staticmethod
    def _without_the_belt(*events, **kw):
        from sqlalchemy import true

        with patch("app.routes.events.not_a_blank_card", new=lambda now: true()):
            return _payload(*events, **kw)

    def test_the_page_opened_on_cards_that_could_say_nothing(self):
        served = self._without_the_belt(
            _blank(BLANK_A), _blank(BLANK_B, home="A", away="B")
        )
        assert _ids(served) == {BLANK_A, BLANK_B}, (
            "the pre-fix route must serve both blank rows, or this suite is "
            "certifying a corpus the old code would also have cleaned"
        )

    def test_and_the_cards_really_do_render_nothing(self):
        """Not just present — present and empty, which is the reader's complaint."""
        served = self._without_the_belt(_blank(BLANK_A))
        card = served["events"][0]
        assert card["home_score"] is None and card["away_score"] is None
        assert not card.get("win_probability"), card.get("win_probability")
        assert not card.get("home_win_probability"), card.get("home_win_probability")


# ---------------------------------------------------------------------------
# the ship
# ---------------------------------------------------------------------------


class TestTheLeaguePageStopsPrintingEmptyCards:
    def test_a_blank_suspended_row_is_gone(self):
        assert _ids(_payload(_blank(BLANK_A))) == set()

    def test_every_blank_row_is_gone_not_merely_the_first(self):
        served = _payload(
            _blank(BLANK_A),
            _blank(BLANK_B, home="Jaguares", away="Fortaleza"),
            _blank(15307902, home="LDU Quito", away="Cuenca"),
        )
        assert _ids(served) == set()

    def test_a_sql_null_bag_is_reached_too(self):
        """The `IS NULL` arm, on the shape the ORM cannot build.

        Production carries 61,730 SQL-NULL bags against 1,094 `{}` ones, so this
        is the MAJORITY shape, not an edge case.
        """
        served = _payload(_blank(BLANK_A), sql_null_bag_for=(BLANK_A,))
        assert _ids(served) == set()

    def test_the_count_reports_what_was_actually_served(self):
        """`count` is what the page prints beside "Live & Paused"."""
        served = _payload(
            _blank(BLANK_A),
            _event(
                15300001,
                home="Real",
                away="Racing",
                status="completed",
                scores=(2, 1),
            ),
        )
        assert served["count"] == len(served["events"]) == 1


# ---------------------------------------------------------------------------
# controls — green on BOTH arms
# ---------------------------------------------------------------------------


class TestWhatMustNotChange:
    """Every row a reader could get something from is still served.

    These route only through symbols that predate this change, so they pass
    with the belt present and with it deleted. That is what makes them controls
    rather than a second copy of the ship.
    """

    def test_a_finished_game_with_a_score_survives(self):
        row = _event(
            15300002, home="Gremio", away="Vasco", status="completed", scores=(3, 1)
        )
        assert _ids(_payload(row)) == {15300002}

    def test_a_suspended_match_with_a_score_is_still_reachable_cert_786(self):
        """CERT-786's whole point, and the reason that suite exists.

        live/048 stopped writing a false Final onto a rain-delayed match and
        wrote `suspended`; the readers dropped the word and the match rendered
        NOWHERE. A belt that suppressed a suspended row carrying a scoreline
        would re-open exactly that hole, so this is the control that matters
        most: the predicate reaches EMPTY rows, never suspended ones.
        """
        row = _event(15300003, home="Alcaraz", away="Sinner", scores=(1, 2))
        assert _ids(_payload(row)) == {15300003}

    def test_a_suspended_row_with_a_real_probability_survives(self):
        row = _event(
            15300004,
            home="Flamengo",
            away="Palmeiras",
            sources={"betting": _fresh(0.61)},
        )
        assert _ids(_payload(row)) == {15300004}

    def test_a_metadata_only_bag_is_not_reached(self):
        """The refuted widening's population, held apart on purpose.

        `15310639` (Liverpool v Fulham) carries a bag holding only
        `statpal_injuries`. Widening `_EMPTY_SOURCE_BAGS` to call that "empty"
        blanks 452 of 462 rows that serve a real pre-match line (#3016 comment
        5655941692). If a later session widens it anyway, this test goes red and
        points at the refutation.
        """
        row = _event(
            METADATA_ONLY,
            home="Liverpool",
            away="Fulham",
            sources={
                "statpal_injuries": [{"player": "C. Bradley", "status": "Out"}],
                "statpal_injuries_updated": datetime.now(timezone.utc).isoformat(),
            },
        )
        assert _ids(_payload(row)) == {METADATA_ONLY}

    def test_an_upcoming_fixture_with_nothing_yet_survives(self):
        """No score and no odds is the NORMAL state of a fixture days out.

        Suppressing it would empty the front door instead of cleaning it.
        """
        row = _event(
            15300005,
            home="Boca",
            away="River",
            when=datetime.now(timezone.utc) + timedelta(days=3),
            status="scheduled",
        )
        assert _ids(_payload(row)) == {15300005}

    def test_a_game_in_progress_with_no_score_yet_survives(self):
        row = _event(
            15300006,
            home="Cusco",
            away="Melgar",
            when=datetime.now(timezone.utc) - timedelta(minutes=20),
            status="live",
        )
        assert _ids(_payload(row)) == {15300006}

    def test_a_scoreless_draw_is_a_result_and_survives(self):
        """0-0 is a score. `home_score IS NULL` is the test, never falsiness."""
        row = _event(
            15300007,
            home="Cancun",
            away="Correcaminos",
            status="completed",
            scores=(0, 0),
        )
        assert _ids(_payload(row)) == {15300007}

    def test_a_blank_row_inside_the_settling_margin_survives(self):
        """`FINISHED_MARGIN` is 6h: just-final rows have not backfilled yet."""
        row = _blank(15300008, when=datetime.now(timezone.utc) - timedelta(hours=2))
        assert _ids(_payload(row)) == {15300008}


# ---------------------------------------------------------------------------
# the limits, stated rather than discovered
# ---------------------------------------------------------------------------


class TestTheKnownLimit:
    def test_a_blank_scheduled_row_past_kickoff_survives(self):
        """The half of #3016 this ship does NOT close, pinned so nobody misreads it.

        A row still wearing `scheduled` hours past its own kickoff renders just
        as blank, and the frontend files it under the SAME "Live & Paused"
        heading (`startedWithoutResult`). `TERMINAL_STATUSES` excludes it
        deliberately — such a row may yet be played — so it stays on the page
        and #3016 stays open for it.
        """
        row = _blank(
            15300009,
            when=datetime.now(timezone.utc) - timedelta(hours=20),
            status="scheduled",
        )
        assert _ids(_payload(row)) == {15300009}

    def test_an_empty_bag_with_an_opening_line_is_suppressed_and_that_is_the_risk(self):
        """The false-positive shape, asserted as the behaviour it actually is.

        `_has_no_probability_sources` reads the bag and nothing else, so a row
        with an empty bag AND an opening line would render a "Pre-match"
        percentage and is suppressed anyway. This is a LIMIT, not a feature.

        It is safe to spend on this route because production holds ZERO such
        rows inside the route's own window and status set (measured
        2026-09-13 21:4xZ, `sql_fingerprint` 2e7a5e91df29c41d: 932 suppressed,
        0 with `opening_home_probability IS NOT NULL`). That is a fact about
        today's data. If this test ever becomes the thing that hurts, the fix is
        to add an opening-line arm to `has_nothing_to_render` — which would be a
        change to the PREDICATE, guarded next door in
        `test_blank_event_cards_4794.py`, and not to this call site.
        """
        row = _blank(15300010, opening=(0.7528, 0.2472))
        assert _ids(_payload(row)) == set()


# ---------------------------------------------------------------------------
# the belt is on THIS route, not merely importable
# ---------------------------------------------------------------------------


class TestTheRouteItselfCarriesIt:
    def test_the_two_belts_are_independent(self):
        """Deleting either one leaves the other standing.

        The duplicate belt (#5918) and the blank belt (#3016) answer different
        questions — "is this row a second copy" and "can this row say anything"
        — and a row can be either, both or neither. If a later edit collapses
        them into one condition this goes red.
        """
        from sqlalchemy import true

        blank_row = _blank(BLANK_A)
        with patch("app.routes.events.not_a_proven_duplicate", new=lambda: true()):
            assert (
                _ids(_payload(blank_row)) == set()
            ), "the blank belt must not depend on the duplicate belt"

    @pytest.mark.parametrize("status_filter", ["suspended", "completed"])
    def test_an_explicit_status_filter_does_not_reopen_the_hole(self, status_filter):
        """`?status=suspended` takes a different branch of the condition builder.

        That branch replaces the default status set, and a belt appended after
        the `if/else` applies to both. A belt written INSIDE the `else` would
        pass every other test in this file and leak here.
        """
        served = _payload(
            _blank(BLANK_A, status=status_filter),
            status=status_filter,
        )
        assert _ids(served) == set()
