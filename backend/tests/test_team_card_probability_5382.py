"""A team page's game cards must show the blended probability (#5382).

## Why this file exists

`teams.py::_format_event_brief` read `win_probability_sources["aggregate"]` for
its whole life. **That key has never existed.** The column's schema is
`{source: {value, updated_at, …}}` — the blend is COMPUTED by
`utils/aggregation.compute_aggregate_probability`, not stored — so `wp` was
`None` on every row of every team page. Measured on production 2026-09-11:

    SELECT count(*), count(*) FILTER (WHERE win_probability_sources ? 'aggregate')
    FROM events WHERE win_probability_sources IS NOT NULL;
    -- 52975, 0

The sharpest specimen was the live Cubs–Pirates game (event 15310077) sitting on
the Cubs page with `win_probability: null` while its own event page hero read
99% off five sources.

This is **#1776 in a second file**. `league_futures.py::_event_probability`
carried the identical read, was fixed there, and the team page did not get the
same fix — so `tests/test_league_games_rail_probability.py` is this file's
sibling and its shape is deliberately mirrored.

## The shape of the guard

Both directions, per gotcha #43: a game WITH sources must render a number, and a
payload carrying ONLY the old assumed shape must still render `None` — the pair
localises a regression instead of merely detecting it.

The fixtures are REAL production payloads, not invented shapes. The whole bug was
a mismatch between an assumed shape and the real one, so a hand-drawn fixture
would reproduce the assumption instead of the data.

Two riders specific to the team page, both pinned below:

1. The brief is **team-relative** ("we had them at 72%") while the blend states
   the HOME side, so an away row is the complement. `test_the_away_row_is_the_
   complement_of_the_home_row` uses a fixture whose blend is far from 0.5, so an
   orientation slip cannot pass by symmetry.
2. The `isinstance` guard must survive: a throw inside a per-item formatter does
   not blank one row, it empties the whole rail (gotcha #42).

## PART TWO — the half the first presentation missed (CERT-2662)

Reading the canonical blend fixes every row that OWNS readings. It cannot fix a
row that owns none, and the team rails are exactly where that row is common:
both queries carry `not_a_proven_duplicate()`, so the SURVIVOR is printed and
its suppressed twin is not — and when the venue price landed on the twin, the
card had nothing to blend. The event page has folded that twin since #3810.
Same fixture, two answers, one of them blank.

Measured on production 2026-09-11 (read-only `db-query`), the specimen this file
now carries verbatim:

    canonical 15310026  Aryna Sabalenka v Elena Rybakina, 2026-09-12 20:00Z
                        win_probability_sources IS NULL      <- the blank card
    twin      15309964  tagged provenance:duplicate-of:15310026
                        kalshi 0.575, polymarket 0.555       <- the hero's number

`TestTheTwinFoldReachesTheTeamCard` runs the REAL `get_team` against a real
engine — its real `select()`s, its real fold call — rather than injecting a
blend map below the seam (the CERT-2235 lesson). Delete the
`folded_probability_sources_batch` call from `_folded_briefs` and every test in
that class goes back to `None`.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.routes.teams import _format_event_brief
from app.utils.aggregation import compute_aggregate_probability


#: Verbatim from production event 15189168 (Pirates @ Marlins, live MLB).
#: Chosen for the settled-language test because its model and market sources
#: DISAGREE — mlb/espn/stat_model cluster ~0.65-0.72 while kalshi/polymarket sit
#: at 0.485/0.285. A fixture whose sources agree cannot tell whether the
#: completed-status exclusion fired.
PRODUCTION_SOURCES_DISAGREEING = {
    "mlb": {"value": 0.693, "display_name": "MLB Model", "type": "model", "color": "#06b6d4"},
    "espn": {"value": 0.642, "display_name": "ESPN", "type": "model", "color": "#f97316"},
    "kalshi": {"value": 0.485, "display_name": "Kalshi", "type": "market", "color": "#22c55e"},
    "polymarket": {"value": 0.285, "display_name": "Polymarket", "type": "market", "color": "#3b82f6"},
    "stat_model": {"value": 0.7186, "display_name": "Bain Luck Model", "type": "model", "color": "#8b5cf6"},
}

#: Verbatim from production event 15310077 — the Cubs–Pirates game named in
#: #5382, the row that served `win_probability: null` beside a 99% hero. Note
#: `betting_book_count`, a non-source scalar living in the same column: it is
#: not in SOURCE_WEIGHTS and must be skipped, not parsed as a reading.
PRODUCTION_SOURCES_SPECIMEN = {
    "mlb": {"value": 0.999, "updated_at": "2026-09-11T21:02:39.657938+00:00"},
    "espn": {"value": 1.0, "updated_at": "2026-09-11T21:02:48.947009+00:00"},
    "kalshi": {"value": 0.99, "updated_at": "2026-09-11T22:51:47.396163+00:00"},
    "polymarket": {"value": 0.9965, "updated_at": "2026-09-11T20:42:20.315515+00:00"},
    "stat_model": {"value": 0.999, "updated_at": "2026-09-11T21:02:48.985231+00:00"},
    "betting_book_count": 1,
}


class FakeSport:
    key = "baseball_mlb"


class FakeTeam:
    def __init__(self, *, id: int, name: str):
        self.id = id
        self.name = name


class FakeEvent:
    """Duck-typed Event carrying exactly what `_format_event_brief` reads.

    Deliberately as wide as the formatter's reads, not as wide as the model: a
    fixture narrower than the row is how a formatter comes to depend on an
    attribute nothing in the suite has.
    """

    def __init__(
        self,
        *,
        sources=None,
        status="live",
        espn=None,
        opening=None,
        opening_away=None,
        home_team_id=1,
        scores=(None, None),
    ):
        self.id = 15310077
        self.sport = FakeSport()
        self.home_team_id = home_team_id
        self.home_team_name = "Chicago Cubs"
        self.away_team_name = "Pittsburgh Pirates"
        self.commence_time = datetime(2026, 9, 11, 17, 40, tzinfo=timezone.utc)
        self.completed_at = None
        self.status = status
        self.home_score, self.away_score = scores
        self.win_probability_sources = sources
        self.espn_win_prob_home = espn
        self.opening_home_probability = opening
        self.opening_away_probability = opening_away


HOME_TEAM = FakeTeam(id=1, name="Chicago Cubs")
AWAY_TEAM = FakeTeam(id=2, name="Pittsburgh Pirates")


class TestTheRegression:
    def test_a_game_with_sources_renders_a_probability(self):
        """The headline. This was None for every row of every team page."""
        card = _format_event_brief(
            FakeEvent(sources=PRODUCTION_SOURCES_SPECIMEN, status="live"), HOME_TEAM
        )
        assert card["win_probability"] is not None, (
            "the team page game cards are blank again — _format_event_brief is "
            "not reading the canonical blend"
        )
        assert 0.0 <= card["win_probability"] <= 1.0

    def test_the_nonexistent_aggregate_key_is_not_what_we_read(self):
        """Pins the ACTUAL defect, not just its symptom.

        A payload carrying the old assumed shape and nothing else must resolve to
        None — proving we no longer depend on `aggregate`. Reintroduce the old
        read and this passes while the test above fails; hardcode a constant and
        this one fails. The pair localises the regression.
        """
        only_aggregate = {"aggregate": {"home": 0.77, "away": 0.23}}
        card = _format_event_brief(
            FakeEvent(sources=only_aggregate, status="live"), HOME_TEAM
        )
        assert card["win_probability"] is None

    def test_a_game_with_no_sources_stays_null_rather_than_fabricating_50(self):
        """The other direction of gotcha #43.

        Null must never be drawn as a claim, and a formatter that answers 0.5 when
        it knows nothing is worse than one that answers nothing.
        """
        card = _format_event_brief(
            FakeEvent(sources=None, status="scheduled"), HOME_TEAM
        )
        assert card["win_probability"] is None


class TestTheCardIsTheHero:
    def test_the_card_serves_exactly_the_canonical_blend(self):
        """One number per question: card == hero == chart.

        Asserts against the blend the hero calls, not against a literal — a
        literal here would be this formatter's second opinion of the blend, which
        is the class of defect the shared function exists to prevent.
        """
        event = FakeEvent(sources=PRODUCTION_SOURCES_DISAGREEING, status="live")
        expected = compute_aggregate_probability(event)
        assert expected is not None  # fixture sanity: the test below is not vacuous

        card = _format_event_brief(event, HOME_TEAM)
        assert card["win_probability"] == pytest.approx(round(expected, 3))

    def test_the_away_row_is_the_complement_of_the_home_row(self):
        """Rider 1 — orientation.

        The blend states the HOME side; this brief is team-relative. The fixture's
        blend is far from 0.5 on purpose, so an orientation slip cannot pass by
        symmetry — that is the whole reason this asserts home != away first.
        """
        event = FakeEvent(sources=PRODUCTION_SOURCES_DISAGREEING, status="live")
        home_card = _format_event_brief(event, HOME_TEAM)
        away_card = _format_event_brief(event, AWAY_TEAM)

        assert home_card["is_home"] is True
        assert away_card["is_home"] is False

        home_p = home_card["win_probability"]
        away_p = away_card["win_probability"]
        assert home_p is not None and away_p is not None

        assert home_p != away_p, (
            "home and away read the same number — the fixture drifted to a coin "
            "flip and this test can no longer catch an orientation slip"
        )
        assert away_p == pytest.approx(1.0 - home_p, abs=1e-9)

    def test_the_away_row_is_not_silently_the_home_number(self):
        """The mutation this file exists to kill.

        Delete the `1 - p` and the complement assertion above fails; delete the
        `not is_home` condition and BOTH sides get complemented, which this pins
        by naming which side must exceed 0.5 for this fixture.
        """
        event = FakeEvent(sources=PRODUCTION_SOURCES_DISAGREEING, status="live")
        home_p = _format_event_brief(event, HOME_TEAM)["win_probability"]
        away_p = _format_event_brief(event, AWAY_TEAM)["win_probability"]

        # The fixture's models favour the HOME side (mlb .693, espn .642,
        # stat_model .7186 against kalshi .485 / polymarket .285).
        assert home_p > 0.5, f"home should be favoured on this fixture, got {home_p}"
        assert away_p < 0.5, f"away should be the underdog on this fixture, got {away_p}"


class TestSettledMeansSettled:
    def test_a_completed_game_drops_the_prediction_market_sources(self):
        """Acceptance clause 2, and it must not be vacuous.

        `status` travels on the event, so the completed-exclusion happens inside
        `_tier1_readings` without this formatter re-deriving a rule of its own.
        Proven by DIFFERENCE: the same sources under `live` and under `completed`
        must produce different numbers, or the exclusion did not fire and this
        test is watching nothing.
        """
        live = _format_event_brief(
            FakeEvent(sources=PRODUCTION_SOURCES_DISAGREEING, status="live"), HOME_TEAM
        )["win_probability"]
        completed = _format_event_brief(
            FakeEvent(
                sources=PRODUCTION_SOURCES_DISAGREEING,
                status="completed",
                scores=(5, 2),
            ),
            HOME_TEAM,
        )["win_probability"]

        assert live is not None and completed is not None
        assert completed != live, (
            "the completed-status exclusion did not change the number — either "
            "kalshi/polymarket are no longer dropped, or this fixture's sources "
            "stopped disagreeing and the test is vacuous"
        )
        # Dropping the two low market readings must move the blend UP toward the
        # models, never down.
        assert completed > live


class TestTheRailSurvivesBadData:
    @pytest.mark.parametrize(
        "poisoned",
        [
            pytest.param(["mlb", 0.69], id="list"),
            pytest.param("kalshi=0.485", id="bare-string"),
            pytest.param(12345, id="int"),
        ],
    )
    def test_a_truthy_non_dict_returns_none_instead_of_emptying_the_rail(self, poisoned):
        """Rider 2 — gotcha #42.

        `compute_aggregate_probability` does `.items()` on the column, so a truthy
        NON-dict raises AttributeError. This runs in a per-item formatter: a throw
        does not blank one row, it empties the entire rail. The `isinstance` guard
        is load-bearing, not dead weight inherited from the broken read.
        """
        event = FakeEvent(sources=poisoned, status="live")
        card = _format_event_brief(event, HOME_TEAM)  # must not raise
        assert card["win_probability"] is None
        # The rest of the card still renders — the row degrades, the rail lives.
        assert card["id"] == 15310077
        assert card["opponent"] == "Pittsburgh Pirates"


class TestTheRestOfTheCardIsUnchanged:
    def test_pregame_and_completed_fields_still_travel(self):
        """#5382 touches one field. A neighbour that regresses is this file's
        business too, because the recents grammar ("we had them at 72%") reads
        `pregame_win_probability` from the columns beside it."""
        event = FakeEvent(
            sources=PRODUCTION_SOURCES_DISAGREEING,
            status="live",
            opening=0.6333,
            opening_away=0.3668,
        )
        home_card = _format_event_brief(event, HOME_TEAM)
        away_card = _format_event_brief(event, AWAY_TEAM)

        assert home_card["pregame_win_probability"] == pytest.approx(0.633)
        assert away_card["pregame_win_probability"] == pytest.approx(0.367)
        assert home_card["home_team"] == "Chicago Cubs"
        assert away_card["opponent"] == "Chicago Cubs"

    def test_the_served_number_is_rounded_to_three_places(self):
        event = FakeEvent(sources=PRODUCTION_SOURCES_DISAGREEING, status="live")
        wp = _format_event_brief(event, HOME_TEAM)["win_probability"]
        assert wp == round(wp, 3)


# ════════════════════════════════════════════════════════════════════════════
# PART TWO — the twin fold reaches the card (the CERT-2662 repair)
# ════════════════════════════════════════════════════════════════════════════
#
# 🔴 Everything above runs the FORMATTER. None of it would fail if the route
# never folded, because the formatter is handed whatever sources the row owns.
# What follows runs the REAL `get_team` against a real engine.


# DDL shims so `create_all` can build the real schema on SQLite — the same pair
# `test_hub_folds_the_twin_3937` and `test_blend_fold_3810` declare, for the same
# reason: the fold's Postgres arm is an `@>` operator, so the portable arm has to
# be exercised against a real engine rather than a mock.
@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models.models import Base, Event, Sport, Team  # noqa: E402
from app.routes import teams as route  # noqa: E402
from app.services.anchor_channel import duplicate_tag  # noqa: E402

#: The production pair, verbatim (read 2026-09-11, `db-query`). The canonical is
#: what a team page prints; the twin is where the venues landed.
CANON_ID = 15310026
TWIN_ID = 15309964
HOME_TEAM_ID = 18513  # Aryna Sabalenka
AWAY_TEAM_ID = 18852  # Elena Rybakina
S_WTA = 356530

#: Measured on the twin row, verbatim. Blends to 0.555 — `betting` is absent, so
#: the two market readings carry equal weight and the weighted median is the
#: lower of them. The number is asserted against the blend rather than hardcoded
#: wherever this pair is used, for the reason `TestTheCardIsTheHero` gives.
TWIN_SOURCES = {
    "kalshi": {"value": 0.575, "updated_at": "2026-09-11T22:50:48.622500+00:00"},
    "polymarket": {"value": 0.555, "updated_at": "2026-09-11T14:15:44.450247+00:00"},
}

#: The bus's named repair case: ONE source, held only by the twin. A single
#: reading IS its own blend, so this fixture states the expected card outright —
#: 0.61 for the home side, 0.39 for the away side — with no arithmetic between
#: the fixture and the assertion for a reader to have to trust.
TWIN_ONLY_SOURCE = {"kalshi": {"value": 0.61, "updated_at": "2026-09-11T22:50:48+00:00"}}


class _CountingSession:
    """Runs real Core statements, and counts the FOLD's separately.

    The fold is dispatched on the labels the statement itself asked for
    (`event_tags` is selected by nothing else on this page), so a change to the
    fold's `select()` shows up here rather than being absorbed by a fake that was
    told what to expect.
    """

    def __init__(self, session):
        self._session = session
        self.executed = 0
        self.fold_lookups = 0

    async def execute(self, statement):
        self.executed += 1
        try:
            labels = [desc["name"] for desc in statement.column_descriptions]
        except Exception:  # pragma: no cover - non-ORM statement
            labels = []
        if "event_tags" in labels:
            self.fold_lookups += 1
        return self._session.execute(statement)


def _event(event_id, *, home, away, sources=None, tags=None, when=None, status="scheduled",
           home_team_id=None, away_team_id=None, scores=(None, None)):
    return Event(
        id=event_id,
        sport_id=S_WTA,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home_team_name=home,
        away_team_name=away,
        commence_time=when,
        status=status,
        home_score=scores[0],
        away_score=scores[1],
        win_probability_sources=sources,
        event_tags=tags,
    )


def _engine(*events, teams=()):
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=S_WTA, key="tennis_wta", name="WTA"))
        for team_id, name, slug in teams:
            s.add(Team(id=team_id, sport_id=S_WTA, name=name, slug=slug))
        for e in events:
            s.add(e)
        s.commit()
    return eng


def _page(eng, slug):
    """`get_team` for real, plus the session so a test can read the query counts."""
    with Session(eng) as s:
        db = _CountingSession(s)
        return asyncio.run(route.get_team(slug, db=db)), db


TEAMS = (
    (HOME_TEAM_ID, "Aryna Sabalenka", "aryna-sabalenka"),
    (AWAY_TEAM_ID, "Elena Rybakina", "elena-rybakina"),
)


def _standard_page(twin_sources=TWIN_SOURCES, twin_home="Sabalenka", twin_away="Rybakina",
                   twin_tags=None, canon_sources=None):
    """The production pair: a blank canonical on the rail, its twin holding the price."""
    soon = datetime.now(timezone.utc) + timedelta(hours=6)
    return _engine(
        _event(
            CANON_ID,
            home="Aryna Sabalenka",
            away="Elena Rybakina",
            home_team_id=HOME_TEAM_ID,
            away_team_id=AWAY_TEAM_ID,
            sources=canon_sources,
            when=soon,
        ),
        _event(
            TWIN_ID,
            home=twin_home,
            away=twin_away,
            sources=twin_sources,
            tags=[duplicate_tag(CANON_ID)] if twin_tags is None else twin_tags,
            when=soon,
        ),
        teams=TEAMS,
    )


def _card(page, rail="upcoming_events", event_id=CANON_ID):
    cards = [c for c in page[rail] if c["id"] == event_id]
    assert len(cards) == 1, f"expected exactly one card for {event_id}, got {cards}"
    return cards[0]


class TestTheTwinFoldReachesTheTeamCard:
    def test_team_page_folds_suppressed_twin_probability_sources_5382(self):
        """🔴 THE REPAIR. A card whose only reading lives on a suppressed twin.

        The canonical owns NOTHING — `win_probability_sources IS NULL`, exactly
        the production row — so the fix that reads the canonical blend leaves it
        blank. The twin holds one reading at 0.61, and a single reading is its
        own blend, so the home card must read 0.61 and the away card 0.39.

        This is the number the event page has already been printing. Delete the
        `folded_probability_sources_batch` call from `_folded_briefs` and both
        assertions go back to `None` — which is what shipped, and what the team
        page served beside a hero that disagreed with it.
        """
        eng = _standard_page(twin_sources=TWIN_ONLY_SOURCE)

        home_card = _card(_page(eng, "aryna-sabalenka")[0])
        away_card = _card(_page(eng, "elena-rybakina")[0])

        assert home_card["is_home"] is True
        assert away_card["is_home"] is False
        assert home_card["win_probability"] == pytest.approx(0.61)
        assert away_card["win_probability"] == pytest.approx(0.39)

    def test_the_production_specimen_stops_serving_null(self):
        """The same repair on the pair as measured, values and all.

        Asserted against the blend the hero calls rather than a literal — a
        literal here would be this test's second opinion of the blend, the class
        of defect the shared function exists to prevent. The sanity line above it
        is what stops the comparison passing on `None == None`.
        """
        expected = compute_aggregate_probability(
            FakeEvent(sources=TWIN_SOURCES, status="scheduled")
        )
        assert expected is not None, "fixture drifted: the twin's readings no longer blend"

        card = _card(_page(_standard_page(), "aryna-sabalenka")[0])
        assert card["win_probability"] == pytest.approx(round(expected, 3))
        # The literal BESIDE the computed assertion, so a change to the blend's
        # weighting shows up here as a decision rather than sliding through on a
        # comparison that can only ever agree with itself.
        #
        # It has already earned its place once. It was written as 0.575 — the
        # recency-weighted answer, kalshi's stamp being eight hours fresher than
        # polymarket's — and #1999 (CERT-2667) landed on master between this
        # branch's gate run and its merge offer, making **recency decay an
        # in-play rule**. A scheduled game no longer decays, so the same two
        # readings now blend to the plain weighted 0.555 and this line went red
        # on current master. That is the guard working, not the guard breaking.
        #
        # So it is pinned from BOTH sides now rather than re-pointed at the new
        # number, because a one-sided literal cannot tell "#1999 applies here"
        # from "#1999 was reverted": `scheduled` must be 0.555 AND `live` must
        # still be 0.575. Deleting either arm makes the pair vacuous.
        assert card["win_probability"] == pytest.approx(0.555)

    def test_the_recency_rule_this_card_inherits_is_the_in_play_one(self):
        """🔴 #1999's rule, asserted from both sides on the specimen's own values.

        The card above takes whatever `compute_aggregate_probability` says, so
        this is not a second opinion of the blend — it is the statement that the
        two answers are DIFFERENT and which one a pre-game card is entitled to.
        Without it, a revert of #1999 moves every scheduled team card by two
        points and the suite above re-derives the new number and stays green.
        """
        pre_game = compute_aggregate_probability(
            FakeEvent(sources=TWIN_SOURCES, status="scheduled")
        )
        in_play = compute_aggregate_probability(
            FakeEvent(sources=TWIN_SOURCES, status="live")
        )
        # Not equal, or the rule #1999 shipped is not in force at all.
        assert pre_game != in_play, "#1999 reverted: recency is decaying a pre-game blend again"
        assert pre_game == pytest.approx(0.555)
        assert in_play == pytest.approx(0.575)

    def test_the_recent_rail_is_folded_too_and_not_only_the_upcoming_one(self):
        """🔴 Both rails, or the repair is half-applied.

        A settled game reads its result off the same card grammar, and a fold
        wired into `upcoming_q` alone would leave every finished game on a team
        page disagreeing with its own event page. Naming both rails in one call
        is what makes this structural rather than remembered.

        The twin's reading is `betting` rather than the `kalshi` used above,
        because settled means settled: `_tier1_readings` drops the prediction
        markets once a game is completed, so a market-only twin correctly folds
        to nothing here and the test would pass for the wrong reason.
        """
        played = datetime.now(timezone.utc) - timedelta(days=2)
        twin_reading = {"betting": {"value": 0.61, "updated_at": "2026-09-09T22:01:35+00:00"}}
        eng = _engine(
            _event(
                CANON_ID,
                home="Aryna Sabalenka",
                away="Elena Rybakina",
                home_team_id=HOME_TEAM_ID,
                away_team_id=AWAY_TEAM_ID,
                sources=None,
                when=played,
                status="completed",
                scores=(2, 0),
            ),
            _event(
                TWIN_ID,
                home="Sabalenka",
                away="Rybakina",
                sources=twin_reading,
                tags=[duplicate_tag(CANON_ID)],
                when=played,
                status="completed",
            ),
            teams=TEAMS,
        )
        page, _ = _page(eng, "aryna-sabalenka")
        assert page["upcoming_events"] == [], "fixture drifted onto the wrong rail"
        assert _card(page, rail="recent_events")["win_probability"] == pytest.approx(0.61)

    def test_one_lookup_serves_both_rails(self):
        """The N+1 guard at the caller.

        Two rails and several rows, ONE fold statement. The rails are capped at 5
        apiece so the cost is small either way — what this pins is that the page
        uses the shared batched form (#3937) rather than growing a second,
        per-row fold of its own that would then drift from it.
        """
        soon = datetime.now(timezone.utc) + timedelta(hours=6)
        played = datetime.now(timezone.utc) - timedelta(days=2)
        eng = _engine(
            _event(CANON_ID, home="Aryna Sabalenka", away="Elena Rybakina",
                   home_team_id=HOME_TEAM_ID, away_team_id=AWAY_TEAM_ID, when=soon),
            _event(TWIN_ID, home="Sabalenka", away="Rybakina", sources=TWIN_ONLY_SOURCE,
                   tags=[duplicate_tag(CANON_ID)], when=soon),
            _event(CANON_ID + 10, home="Aryna Sabalenka", away="Iga Swiatek",
                   home_team_id=HOME_TEAM_ID, when=soon + timedelta(days=2)),
            _event(CANON_ID + 20, home="Aryna Sabalenka", away="Coco Gauff",
                   home_team_id=HOME_TEAM_ID, when=played, status="completed", scores=(2, 1)),
            teams=TEAMS,
        )
        page, db = _page(eng, "aryna-sabalenka")
        # Not vacuous: the page really did render rows on both rails.
        assert len(page["upcoming_events"]) == 2 and len(page["recent_events"]) == 1
        assert db.fold_lookups == 1

    def test_a_page_with_no_games_asks_the_database_nothing_extra(self):
        """`or_()` of nothing is a constant-false WHERE — a round trip that cannot
        return a row. Plenty of team pages are out of season."""
        eng = _engine(teams=TEAMS)
        page, db = _page(eng, "aryna-sabalenka")
        assert page["upcoming_events"] == [] and page["recent_events"] == []
        assert db.fold_lookups == 0


class TestTheFoldDoesNotOVERreach:
    """The no-change half. Almost no fixture has a suppressed duplicate, and the
    fold must be invisible on every one of them."""

    def test_a_card_with_no_twin_is_exactly_what_it_was(self):
        soon = datetime.now(timezone.utc) + timedelta(hours=6)
        eng = _engine(
            _event(CANON_ID, home="Aryna Sabalenka", away="Elena Rybakina",
                   home_team_id=HOME_TEAM_ID, away_team_id=AWAY_TEAM_ID,
                   sources={"betting": {"value": 0.72}}, when=soon),
            teams=TEAMS,
        )
        assert _card(_page(eng, "aryna-sabalenka")[0])["win_probability"] == pytest.approx(0.72)

    def test_a_card_with_no_reading_anywhere_stays_null_rather_than_fabricating_50(self):
        """The fold must not turn "we know nothing" into a coin flip. This is the
        `TRUTH` clause the first presentation was graded GREEN on and it survives.
        """
        soon = datetime.now(timezone.utc) + timedelta(hours=6)
        eng = _engine(
            _event(CANON_ID, home="Aryna Sabalenka", away="Elena Rybakina",
                   home_team_id=HOME_TEAM_ID, away_team_id=AWAY_TEAM_ID, when=soon),
            _event(TWIN_ID, home="Sabalenka", away="Rybakina", sources=None,
                   tags=[duplicate_tag(CANON_ID)], when=soon),
            teams=TEAMS,
        )
        assert _card(_page(eng, "aryna-sabalenka")[0])["win_probability"] is None

    def test_the_canonicals_own_reading_is_never_replaced_by_the_twins(self):
        """GAP-FILL, not "richest wins" — `merge_probability_sources`'s rule, held
        through the route. A card printing a correct number today cannot have that
        number replaced by this repair, only joined by a venue already ours."""
        eng = _standard_page(
            twin_sources={"kalshi": {"value": 0.10}},
            canon_sources={"kalshi": {"value": 0.61}},
        )
        assert _card(_page(eng, "aryna-sabalenka")[0])["win_probability"] == pytest.approx(0.61)

    def test_a_swapped_twin_is_refused(self):
        """🔴 A reading is a HOME win probability whose meaning comes from its own
        row's names. Fold a twin that disagrees about which player is home and the
        card prints one player's number under the other's — 0.61 where 0.39 was
        true, with nothing on the card to reveal it."""
        eng = _standard_page(twin_sources=TWIN_ONLY_SOURCE,
                             twin_home="Rybakina", twin_away="Sabalenka")
        assert _card(_page(eng, "aryna-sabalenka")[0])["win_probability"] is None

    def test_an_untagged_lookalike_is_not_folded(self):
        """🔴 The TAG, and only the tag, attributes a twin.

        Same sport, same names, same time — only `event_tags` differs. A
        name-and-time route to another row's readings is the absorption
        ruling 048 bans, arriving as a read instead of a write.
        """
        eng = _standard_page(twin_sources=TWIN_ONLY_SOURCE, twin_tags=[])
        assert _card(_page(eng, "aryna-sabalenka")[0])["win_probability"] is None

    def test_a_tag_naming_a_DIFFERENT_canonical_is_not_folded(self):
        eng = _standard_page(twin_sources=TWIN_ONLY_SOURCE,
                             twin_tags=[duplicate_tag(CANON_ID + 1)])
        assert _card(_page(eng, "aryna-sabalenka")[0])["win_probability"] is None


class TestAFoldFailureCannotTakeTheTeamPageDown:
    def test_a_fold_that_raises_degrades_to_the_unfolded_number_and_says_so(self, caplog):
        """🔴 The rails are the CORE of a Priority-#3 page (#1197 / #1239).

        The rows are already in hand when the fold runs, so a throw here would
        replace a working team page with a 500 for the sake of a number the
        reader would otherwise still see. It degrades to each row's OWN readings
        — no price is lost, which is the hazard `folded_event_ids` names for its
        no-swallow rule (gotcha #53) — and it logs, which is the other half: a
        degradation nobody can see is the one that stays broken.
        """
        soon = datetime.now(timezone.utc) + timedelta(hours=6)
        eng = _engine(
            _event(CANON_ID, home="Aryna Sabalenka", away="Elena Rybakina",
                   home_team_id=HOME_TEAM_ID, away_team_id=AWAY_TEAM_ID,
                   sources={"betting": {"value": 0.72}}, when=soon),
            teams=TEAMS,
        )
        boom = RuntimeError("fold exploded")

        async def _raise(db, events):
            raise boom

        original = route.folded_probability_sources_batch
        route.folded_probability_sources_batch = _raise
        try:
            with caplog.at_level(logging.ERROR, logger=route.logger.name):
                page, _ = _page(eng, "aryna-sabalenka")
        finally:
            route.folded_probability_sources_batch = original

        card = _card(page)
        assert card["win_probability"] == pytest.approx(0.72), (
            "a fold failure blanked the row's own reading — the fallback must be "
            "the unfolded answer, never nothing"
        )
        assert card["opponent"] == "Elena Rybakina"  # the rest of the page lives
        assert any("twin fold failed" in r.getMessage() for r in caplog.records), (
            "the degradation was silent"
        )

    def test_a_malformed_sources_column_still_returns_a_page(self):
        """A truthy non-dict makes `merge_probability_sources` raise inside the
        BATCH, not inside the formatter — so the `isinstance` guard Part One pins
        is not the one that saves this. The rail degrades to unfolded and the
        poisoned row alone reads `None`."""
        soon = datetime.now(timezone.utc) + timedelta(hours=6)
        eng = _engine(
            _event(CANON_ID, home="Aryna Sabalenka", away="Elena Rybakina",
                   home_team_id=HOME_TEAM_ID, away_team_id=AWAY_TEAM_ID,
                   sources=["kalshi", 0.61], when=soon),
            _event(CANON_ID + 10, home="Aryna Sabalenka", away="Iga Swiatek",
                   home_team_id=HOME_TEAM_ID, sources={"betting": {"value": 0.72}},
                   when=soon + timedelta(days=2)),
            teams=TEAMS,
        )
        page, _ = _page(eng, "aryna-sabalenka")
        assert _card(page)["win_probability"] is None
        # gotcha #42: the healthy sibling survives the poisoned row.
        assert _card(page, event_id=CANON_ID + 10)["win_probability"] == pytest.approx(0.72)
