"""#5853 — a league card may not lose the number the row it suppressed held.

## What a reader saw

`https://bainluck.com/sport/soccer/bundesliga`, Saturday's slate. Eight finished
cards printed a pre-match percentage; the ninth printed nothing at all::

    TSG Hoffenheim 56% / VfB Stuttgart 44%   Pre-match · sportsbooks
    Mainz          --  / Eintracht Frankfurt --

Measured on production 2026-09-13 09:5xZ, `GET /api/leagues/soccer_germany_bundesliga`,
`recent_results`::

    15310934  Mainz          @ Eintracht Frankfurt  home_win_probability: null
                                                    no `opening_odds`, no `current_odds`
    15297872  TSG Hoffenheim @ VfB Stuttgart        opening_odds 0.5551 / 0.445

## Why, and why neither existing fold reaches it

The blank card has a twin the reader cannot see. `db-query`, same morning::

    15310934  "Mainz"         espn       tags [provenance:source:espn]
                              wps {statpal_injuries…}          opening NULL
    15297803  "FSV Mainz 05"  odds_api   tags […, provenance:duplicate-of:15310934]
                              wps {kalshi, betting, polymarket} opening 0.6937 / 0.3063

`reconcile_shared_fixture_ids` tagged `15297803` as the duplicate — correctly:
both rows carry StatPal fixture `9543399`, and `twin_identity_rank` elects the
ESPN-born row because an anchored row is the one the event page, the chart and
the settlement path can all reach. The tag then suppresses the loser at every
rail, and the loser was the only row holding a number.

The serve-time fold (`fold_twin_events`, #4100/#5496/#5746) would have carried
those numbers across — `_elect` unions the loser's venues onto the survivor —
but it can never see this pair twice over: `not_a_proven_duplicate()` has
already removed the tagged row from the rails' SQL, and even in one list
`_squash("Mainz")` is `mainz` while `_squash("FSV Mainz 05")` is `fsvmainz05`,
so its name key would not group them.

**So the two mechanisms are not redundant: the tag hides pairs the name fold
cannot group, and only the name fold carries data forward.** The id-keyed
carry exists (`folded_probability_sources_batch`, #3937) and was wired into
the event page, the events list, the team page and tournaments — never into
`/api/leagues/{sport_key}`. This file is that surface's turn, plus the half no
surface had.

## The half no surface had: the SETTLED card's number is not in the bag

`folded_probability_sources_batch` folds `win_probability_sources`, and on a
live card that bag IS the number. On a finished card it is not. The card prints
"Pre-match · sportsbooks" from `opening_odds`, which is served from the
`Event.opening_*` COLUMNS. Wiring only the existing fold here would have moved
`home_win_probability` on this row and left the printed percentage blank — a
green test over a live bug. `merge_opening_line` is the missing half, and
`test_the_sources_fold_alone_would_have_left_the_card_blank` is that sentence
as a test.

## Reach, measured over the whole tagged population

Production 2026-09-13, all 191 rows carrying a `provenance:duplicate-of:` tag,
counting only real probability speakers (keys in `SOURCE_WEIGHTS`)::

    canonical holds FEWER speakers than the row it suppresses     11
    canonical holds NONE while the suppressed row held some        6
    canonical has NO opening line while the suppressed row does    1   <- this card

Small and bounded, and the one is the one on a league rail tonight.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


# DDL shims so `create_all` can build the real schema on SQLite — the same pair
# `test_team_page_twin_fold_5487.py` declares, for the same reason: the
# duplicate-tag predicate's Postgres arm is a `@>` operator, so the portable arm
# has to be exercised against a real engine rather than a mock.
@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models.models import Base, Event, Sport  # noqa: E402
from app.routes import league_futures as route  # noqa: E402
from app.services.anchor_channel import duplicate_tag  # noqa: E402
from app.utils.proven_duplicates import (  # noqa: E402
    folded_card_numbers_batch,
    folded_probability_sources_batch,
    merge_opening_line,
)

#: The production pair, verbatim (`db-query`, 2026-09-13 09:4xZ).
CANONICAL = 15310934  # "Mainz", ESPN-born, no speakers, no opening line
SUPPRESSED = 15297803  # "FSV Mainz 05", tagged duplicate, 3 speakers, opened .6937
S_BUNDESLIGA = 1305
SPORT_KEY = "soccer_germany_bundesliga"

CANON_HOME = "Mainz"
DUP_HOME = "FSV Mainz 05"
AWAY = "Eintracht Frankfurt"

OPEN_HOME = 0.6937
OPEN_AWAY = 0.3063


def _fresh(value: float) -> dict:
    """A reading stamped now, so source-weight decay cannot move an assertion.

    Gotcha #44: offset from the clock, never a literal stamp — a frozen one
    makes these assertions drift with the calendar.
    """
    return {"value": value, "updated_at": datetime.now(timezone.utc).isoformat()}


def _floats(pair: tuple) -> tuple:
    """A `(home, away)` pair as floats — `Event.opening_*` is NUMERIC."""
    return tuple(None if v is None else float(v) for v in pair)


def _played(hours_ago=20):
    return datetime.now(timezone.utc) - timedelta(hours=hours_ago)


def _event(
    event_id,
    *,
    home,
    when=None,
    away=AWAY,
    sources=None,
    tags=None,
    opening=(None, None),
    status="completed",
    scores=(1, 3),
):
    return Event(
        id=event_id,
        sport_id=S_BUNDESLIGA,
        home_team_name=home,
        away_team_name=away,
        commence_time=when or _played(),
        completed_at=(when or _played()) + timedelta(hours=2),
        status=status,
        home_score=scores[0],
        away_score=scores[1],
        win_probability_sources=sources,
        event_tags=tags if tags is not None else ["provenance:unanchored"],
        opening_home_probability=opening[0],
        opening_away_probability=opening[1],
    )


def _the_production_pair(**canonical_overrides):
    """The two rows exactly as production holds them, canonical first."""
    when = _played()
    canonical = _event(CANONICAL, home=CANON_HOME, when=when, **canonical_overrides)
    suppressed = _event(
        SUPPRESSED,
        home=DUP_HOME,
        when=when,
        sources={
            "kalshi": _fresh(0.01),
            "betting": _fresh(0.0028),
            "polymarket": _fresh(0.555),
        },
        tags=["provenance:source:odds_api", duplicate_tag(CANONICAL)],
        opening=(OPEN_HOME, OPEN_AWAY),
    )
    return canonical, suppressed


def _engine(*events):
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=S_BUNDESLIGA, key=SPORT_KEY, name="Bundesliga"))
        for e in events:
            s.add(e)
        s.commit()
    return eng


class _Session:
    """A real engine behind the async surface `build_league` calls."""

    def __init__(self, session):
        self._s = session

    async def execute(self, statement, *args, **kwargs):
        return self._s.execute(statement)


def _fold(*events, canonicals=None):
    """`folded_card_numbers_batch` against a real engine, over real rows.

    The canonicals are RE-READ from the fold's own session rather than reused
    from the fixture builder: the rows the route hands the fold came out of the
    rails' own query, and a detached instance would answer from a stale
    identity map — or raise — instead of from the database.
    """
    ids = list(canonicals) if canonicals is not None else [e.id for e in events]
    eng = _engine(*events)
    with Session(eng) as s:
        rows = [s.get(Event, i) for i in ids]
        return asyncio.run(folded_card_numbers_batch(_Session(s), rows))


def _results_rail(*events):
    """The served `recent_results` rail, through the real route."""
    eng = _engine(*events)
    with Session(eng) as s:
        payload = asyncio.run(route.build_league(SPORT_KEY, _Session(s)))
    return {card["id"]: card for card in payload["recent_results"]}


# ---------------------------------------------------------------------------
# the ship
# ---------------------------------------------------------------------------


class TestTheBundesligaCard:
    def test_the_card_prints_the_pre_match_percentage_again(self):
        """🔴 THE SHIP. The blank card on Alex's league page gets its number back.

        Binary, and stated as the production value rather than derived: without
        the fold this card carries no `opening_odds` key at all, with it the key
        is the pair the suppressed row has held all along.
        """
        card = _results_rail(*_the_production_pair())[CANONICAL]

        assert card.get("opening_odds") == {
            "home_probability": OPEN_HOME,
            "away_probability": OPEN_AWAY,
        }, (
            "the surviving card was served with no pre-match line while the "
            "row it suppressed holds one — this is the production bug "
            f"(got {card.get('opening_odds')!r})"
        )

    def test_the_suppressed_row_is_still_not_a_second_card(self):
        """The fold reads the hidden row; it never un-hides it.

        `not_a_proven_duplicate()` is the belt this rides behind, and a repair
        that printed the number by printing the row again would be #2263
        reopened — two cards for one game, which is the worse bug.
        """
        rail = _results_rail(*_the_production_pair())

        assert SUPPRESSED not in rail, (
            "the tagged duplicate came back as its own card: " f"{sorted(rail)}"
        )
        assert CANONICAL in rail

    def test_the_live_number_comes_across_too(self):
        """The bag half, on the same row: the canonical held no speaker at all.

        `betting` is the only one of the three that survives a completed game
        (the blend drops Kalshi and Polymarket once a game is over), so this is
        the settled sportsbook price and the assertion names it outright.
        """
        card = _results_rail(*_the_production_pair())[CANONICAL]

        assert card["home_win_probability"] == pytest.approx(0.0028), (
            "the card's blend is still empty while three venues sit on the row "
            f"it suppressed (got {card['home_win_probability']!r})"
        )

    def test_the_sources_fold_alone_would_have_left_the_card_blank(self):
        """🔴 READ THIS ONE FIRST — it fails on the DESIGN, not the code.

        Wiring only the fold that already existed (`folded_probability_sources_batch`,
        #3937) into this page is the obvious repair, and on this specimen it
        does not fix what a reader sees: the printed "Pre-match · sportsbooks"
        percentage is served from `opening_odds`, which comes from the
        `Event.opening_*` COLUMNS and has never been in the JSONB bag. This
        asserts the gap directly, so a future edit that drops `merge_opening_line`
        and keeps the sources fold reddens here rather than on production.
        """
        canonical, suppressed = _the_production_pair()
        eng = _engine(canonical, suppressed)
        with Session(eng) as s:
            sources_only = asyncio.run(
                folded_probability_sources_batch(_Session(s), [s.get(Event, CANONICAL)])
            )

        folded_bag = sources_only[CANONICAL]

        assert "betting" in folded_bag, "the sources fold stopped folding sources"
        assert not any(key.startswith("opening") for key in folded_bag), (
            "the opening line turned up inside `win_probability_sources` — if "
            "that is now true, this ship's second half is redundant and should "
            "be deleted rather than left as a second writer of one number"
        )


# ---------------------------------------------------------------------------
# the rule: gap-fill, a pair at a time
# ---------------------------------------------------------------------------


class TestMergeOpeningLine:
    def test_a_canonical_with_its_own_line_keeps_it(self):
        """Strictly additive: a page printing a correct pair today never moves.

        The twin here holds a DIFFERENT line, so a rule that preferred the twin
        — or the richer row, or the later one — would show up as 0.11.
        """
        assert merge_opening_line(0.42, 0.58, [(SUPPRESSED, 0.11, 0.89)]) == (
            0.42,
            0.58,
        )

    def test_half_a_canonical_line_is_still_the_canonical_s(self):
        """A canonical holding EITHER half is left alone.

        Stricter than the formatter's own gate, which reads the away half only
        when the home half is set. The strictness is what makes the fold
        provably additive: with either value present the return is the row's own
        two values, so no assertion anywhere else has to reason about a mixed
        line.
        """
        assert merge_opening_line(None, 0.58, [(SUPPRESSED, 0.11, 0.89)]) == (
            None,
            0.58,
        )

    def test_the_twin_supplies_both_halves_or_neither(self):
        """A pair travels as a pair.

        Taking the home from one row and the away from another states two
        openings as one line. They are medians taken at different moments over
        different sportsbooks (#1841) and need not sum to 1, so the mixture is a
        number no venue ever quoted.
        """
        assert merge_opening_line(None, None, [(SUPPRESSED, 0.11, None)]) == (
            0.11,
            None,
        )

    def test_two_half_lines_are_not_assembled_into_one(self):
        """🔴 THE MUTATION THIS RULE EXISTS FOR, and the only arrangement that
        can see it.

        A rule that filled each half from whichever twin happened to hold it
        would answer `(0.11, 0.89)` here — a home probability from one row and
        an away probability from another, summing to 1.00 by coincidence and
        quoted by nobody. Only the pair the SECOND twin actually holds is a real
        line, and a twin whose home half is missing supplies nothing.

        The single-twin case cannot catch this: the canonical's own away half is
        necessarily `None` whenever the fold fires at all, so the mixed answer
        and the correct one are the same tuple.
        """
        assert merge_opening_line(
            None, None, [(SUPPRESSED, None, 0.89), (SUPPRESSED + 5, 0.11, None)]
        ) == (0.11, None)

    def test_a_twin_with_no_line_supplies_nothing(self):
        assert merge_opening_line(None, None, [(SUPPRESSED, None, 0.89)]) == (
            None,
            None,
        )

    def test_two_twins_are_consumed_lowest_id_first(self):
        """A card may not flicker between two twins across two requests.

        Fed in the WRONG order deliberately: a rule that took the first row the
        database happened to return would pass on a list that arrived sorted.
        """
        assert merge_opening_line(
            None, None, [(SUPPRESSED + 5, 0.30, 0.70), (SUPPRESSED, 0.11, 0.89)]
        ) == (0.11, 0.89)

    def test_no_twins_is_the_canonical_s_own_answer(self):
        assert merge_opening_line(None, None, []) == (None, None)


# ---------------------------------------------------------------------------
# what the fold may NOT do
# ---------------------------------------------------------------------------


class TestTheFoldRefuses:
    def test_an_inverted_twin_supplies_neither_number(self):
        """🔴 THE ONE THAT MATTERS MOST IF IT EVER FIRES.

        An opening line is a HOME probability, a number whose meaning comes
        from its own row's `home_team_name`. Folding one from a row that
        disagrees about which side is home prints one team's number under the
        other's name — a single confident percentage with no curve shape for a
        reader to notice is wrong.
        """
        when = _played()
        canonical = _event(CANONICAL, home=CANON_HOME, when=when)
        inverted = _event(
            SUPPRESSED,
            home=AWAY,
            away=DUP_HOME,
            when=when,
            sources={"betting": _fresh(0.0028)},
            tags=[duplicate_tag(CANONICAL)],
            opening=(OPEN_HOME, OPEN_AWAY),
        )

        folded = _fold(canonical, inverted)[CANONICAL]

        assert folded.opening == (None, None)
        assert "betting" not in (folded.win_probability_sources or {})

    def test_a_twin_tagged_against_another_canonical_does_not_leak(self):
        """The `OR` of tag arms says a row matched SOME arm, never which.

        Both canonicals are on this page, so a fold that attributed by "it came
        back from the query" rather than by reading the row's own tag would put
        another match's opening line on this card.
        """
        when = _played()
        canonical = _event(CANONICAL, home=CANON_HOME, when=when)
        other_canonical = _event(CANONICAL + 1, home="Werder Bremen", when=when)
        someone_elses_twin = _event(
            SUPPRESSED,
            home="Werder Bremen",
            when=when,
            tags=[duplicate_tag(CANONICAL + 1)],
            opening=(OPEN_HOME, OPEN_AWAY),
        )

        folded = _fold(canonical, other_canonical, someone_elses_twin)

        assert folded[CANONICAL].opening == (None, None)
        # `float()` because the column is NUMERIC and SQLAlchemy hands back a
        # `Decimal`; the fold passes the row's own value through untouched, and
        # the formatter is the layer that casts (it always has).
        assert _floats(folded[CANONICAL + 1].opening) == (OPEN_HOME, OPEN_AWAY)

    def test_an_untwinned_row_is_returned_untouched(self):
        """Every event gets an entry, folded or not, so a caller indexes
        unconditionally and a page with no duplicates compiles the answer it
        has today."""
        lone = _event(
            CANONICAL,
            home=CANON_HOME,
            sources={"betting": _fresh(0.61)},
            opening=(0.55, 0.45),
        )

        folded = _fold(lone)[CANONICAL]

        assert _floats(folded.opening) == (0.55, 0.45)
        assert set(folded.win_probability_sources) == {"betting"}


# ---------------------------------------------------------------------------
# the rail keeps working when the fold does not
# ---------------------------------------------------------------------------


class TestTheRailDegrades:
    def test_a_failing_fold_costs_the_number_and_never_the_page(self):
        """Gotcha #42 at the stage boundary. The fold improves the rail; it is
        never a precondition for having one. A raise here would cost all three
        rails — sixteen games — for the sake of one card's percentage."""
        assert asyncio.run(route._tag_folded_rows(_Exploding(), [object()])) == {}

    def test_the_route_serves_its_rails_when_the_fold_raises(self, monkeypatch):
        """The same thing proved through the route rather than the helper: the
        cards are still there, and they carry their own unfolded numbers."""

        async def _boom(*_args, **_kwargs):
            raise RuntimeError("index unavailable")

        monkeypatch.setattr(route, "folded_card_numbers_batch", _boom)

        canonical, suppressed = _the_production_pair()
        rail = _results_rail(canonical, suppressed)

        assert CANONICAL in rail
        assert rail[CANONICAL].get("opening_odds") is None


class _Exploding:
    async def execute(self, *_args, **_kwargs):
        raise RuntimeError("index unavailable")
