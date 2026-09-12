"""A team page serves ONE card per fixture (#5487) — the twin fold's third surface.

## Why this file exists

Alex opens `/teams/boston-red-sox`. Measured on production 2026-09-12 03:4xZ,
it served **two cards for tomorrow's 20:10Z game against Kansas City**:

    15310368  scheduled  20:10:00Z  espn_id=401816907  external_id=faaa421b…
                                    sources={betting 0.6288}
    15305549  scheduled  20:10:00Z  statpal_fixture_id=364963
                                    sources={kalshi 0.635}

Both carry `provenance:unanchored`. Neither carries a `provenance:duplicate-of:`
tag.

**THE CONTROL IS WHAT MAKES THIS A ONE-LINE DIAGNOSIS.** At the same minute,
`GET /api/events?sport=baseball_mlb` returned only `15310368` — the twin fold
(#4100) has run there since `ac6eb2c1`, and on `/api/feed` before that. The team
page is served by a third endpoint, `GET /api/teams/{identifier}`, which never
called the helper. So this is not a matcher defect and not a new fold: it is
#4100's third surface, and this file is the sibling of
`test_events_list_twin_fold_4100.py`.

Neither existing mechanism can drain it, for one shared reason. The registry
correctly refuses to absorb — each row is anchored to a DIFFERENT provider's
game id, so there is nothing to join on (ruling 048 / gotcha #32; loosening
absorption was put to Alex on 2026-08-20 and REJECTED). And the proven-duplicate
filter, already on both team-page queries, reads a tag that only a prover
writes. The durable repair is the shared id (#2693 / #1946); this fold keeps the
bug off the reader's page until that lands.

## The two riders this route does not share with `list_events`

1. **THE CAP IS APPLIED AFTER THE FOLD HERE — THE OPPOSITE OF `list_events`,
   AND THE DIFFERENCE IS REASONED RATHER THAN INHERITED.** That route folds
   after its DB `limit` because it is OFFSET-PAGINATED: over-fetching would make
   page one consume more raw rows than `limit`, so `offset=limit` would re-serve
   rows page one already showed. This route has a fixed five-card rail and no
   offset, so that hazard cannot arise — and folding after a `limit` of 5 would
   instead spend a card slot on a row it then drops, leaving the reader FOUR
   upcoming games. `test_the_rail_still_fills_to_five_…` is that assertion, and
   it fails on a fold that is merely bolted on after the query.

2. **THE UNION IS LOAD-BEARING ON THIS SPECIMEN, NOT COSMETIC.** The survivor is
   elected on its ESPN id and carries only `betting`. The row it drops is the
   only holder of `kalshi 0.635`. A fold that picks a survivor and discards the
   loser's venues silently deletes a venue's price for the game — which is what
   the "blend is the product" ruling forbids. Picking a survivor is half the
   fix.

## Shape

Real `get_team` against a real engine, per the CERT-2235 lesson its sibling
`test_team_card_probability_5382.py` records: a blend map injected below the
seam proves the formatter, not the route. The fixtures are the production rows
verbatim, except that `updated_at` is stamped RELATIVE TO NOW — source weights
decay with age, so a frozen stamp would make these assertions drift with the
calendar (gotcha #44: offset first, never branch on the clock).

🔴 REAL `Event` OBJECTS, NEVER MagicMock. The union is delivered with
`set_committed_value`, which reaches through `_sa_instance_state`; on a MagicMock
that call is absorbed into an auto-attribute, raising nothing and doing nothing,
and `test_the_dropped_rows_venue_reaches_the_card` would pass against a fold
that merged nothing.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


# DDL shims so `create_all` can build the real schema on SQLite — the same pair
# `test_team_card_probability_5382.py` declares, for the same reason: the
# proven-duplicate filter's Postgres arm is an `@>` operator, so the portable
# arm has to be exercised against a real engine rather than a mock.
@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models.models import Base, Event, Sport, Team  # noqa: E402
from app.routes import teams as route  # noqa: E402

#: The production pair, verbatim (read 2026-09-12 03:4xZ, `db-query`).
ESPN_ID = 15310368  # espn_id + external_id set, 188 odds snapshots
STATPAL_ID = 15305549  # statpal_fixture_id=364963, 0 odds snapshots
S_MLB = 53232
RED_SOX_ID = 10709
ROYALS_ID = 11625

RED_SOX = "Boston Red Sox"
ROYALS = "Kansas City Royals"


def _fresh(value: float) -> dict:
    """A reading stamped now, so source-weight decay cannot move the assertion."""
    return {
        "value": value,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _event(
    event_id,
    *,
    when,
    home=RED_SOX,
    away=ROYALS,
    sources=None,
    espn_id=None,
    external_id=None,
    status="scheduled",
    scores=(None, None),
):
    return Event(
        id=event_id,
        sport_id=S_MLB,
        home_team_id=RED_SOX_ID,
        away_team_id=ROYALS_ID,
        home_team_name=home,
        away_team_name=away,
        commence_time=when,
        status=status,
        home_score=scores[0],
        away_score=scores[1],
        espn_id=espn_id,
        external_id=external_id,
        win_probability_sources=sources,
        event_tags=["provenance:unanchored"],
    )


def _engine(*events):
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=S_MLB, key="baseball_mlb", name="MLB"))
        s.add(Team(id=RED_SOX_ID, sport_id=S_MLB, name=RED_SOX, slug="boston-red-sox"))
        s.add(Team(id=ROYALS_ID, sport_id=S_MLB, name=ROYALS, slug="kansas-city-royals"))
        for e in events:
            s.add(e)
        s.commit()
    return eng


def _page(eng, slug="boston-red-sox"):
    """`get_team` for real — its real `select()`s, its real fold call."""
    with Session(eng) as s:

        class _Session:
            async def execute(self, statement):
                return s.execute(statement)

        return asyncio.run(route.get_team(slug, db=_Session()))


def _soon(hours=6):
    return datetime.now(timezone.utc) + timedelta(hours=hours)


def _production_pair_page(when=None):
    """The served page for the two rows exactly as production holds them."""
    when = when or _soon()
    return _page(_engine(
        _event(STATPAL_ID, when=when, sources={"kalshi": _fresh(0.635)}),
        _event(
            ESPN_ID,
            when=when,
            espn_id="401816907",
            external_id="faaa421be783eb6c7c0a7508f6d200a8",
            sources={"betting": _fresh(0.6288), "betting_book_count": 15},
        ),
    ))


class TestTheRedSoxPage:
    def test_one_game_is_one_card(self):
        """🔴 THE SHIP. Alex's page stops showing tomorrow's game twice."""
        page = _production_pair_page()
        rail = page["upcoming_events"]

        assert len(rail) == 1, (
            "the team page served both rows for one fixture — this is the "
            f"production bug, got ids {[c['id'] for c in rail]}"
        )

    def test_the_survivor_is_the_anchored_row_not_the_statpal_one(self):
        """Which row survives is not arbitrary and must not flicker.

        `twin_identity_rank` elects on an ESPN id before source count, so the
        row a reader keeps is the one the event page, the chart and the
        settlement path can all still reach. Serving `15305549` instead would
        be one card — and a card that leads nowhere.
        """
        page = _production_pair_page()

        assert page["upcoming_events"][0]["id"] == ESPN_ID

    def test_the_real_specimen_still_prints_its_number(self):
        """The surviving card is a working card, not a deduplicated blank.

        MEASURED, AND IT CORRECTS A CLAIM WORTH CORRECTING: on THIS pair the
        union does not move the number at all. The blend is a weighted MEDIAN,
        `betting` weighs 3.0 against Kalshi's 0.8, and both rows read ~0.63 —
        so folding Kalshi in leaves the card at 0.6288 either way. The union is
        still right (a venue is not deleted from the fixture), but on this
        specimen it is INVISIBLE to a reader, and a test asserting otherwise
        would be asserting a fiction.

        Where the union is visible is the next test, and that case is real too.
        """
        card = _production_pair_page()["upcoming_events"][0]

        assert card["win_probability"] is not None

    def test_a_survivor_with_no_reading_prints_the_dropped_rows_number(self):
        """🔴 THE UNION, WHERE IT IS ACTUALLY LOAD-BEARING.

        The survivor is elected on its ESPN id — NOT on how many venues it
        holds (`twin_identity_rank` ranks source count fourth, because
        lane1/197 measured that richness points the wrong way in 2 of 5 pairs).
        So the elected row can be the one with no price at all, and the row it
        drops can be the only holder of one. That is the #5382 / CERT-2662
        specimen exactly, arriving through a different door: a card that
        printed nothing while the price sat on its twin.

        Binary and clock-safe: without the union this card is `null`, with it
        the card is 0.61. A single reading IS its own blend, so the expected
        number is stated outright with no arithmetic between fixture and
        assertion.
        """
        when = _soon()
        page = _page(
            _engine(
                # Holds the only price; loses the election (no ESPN id).
                _event(STATPAL_ID, when=when, sources={"kalshi": _fresh(0.61)}),
                # Wins the election; owns no reading whatsoever.
                _event(ESPN_ID, when=when, espn_id="401816907", sources=None),
            )
        )
        rail = page["upcoming_events"]

        assert len(rail) == 1
        assert rail[0]["id"] == ESPN_ID
        assert rail[0]["win_probability"] == 0.61, (
            "the survivor was served without the dropped row's venue — the "
            "card prints nothing while the price sits on a row the reader "
            f"can no longer see (got {rail[0]['win_probability']!r})"
        )


class TestTheCapIsAppliedAfterTheFold:
    def test_the_rail_still_fills_to_five_when_a_twin_pair_is_at_the_top(self):
        """A twin at the top must not cost the reader a card.

        This is the assertion that a fold bolted on AFTER a DB `limit(5)`
        fails: the query would return five rows, the fold would collapse two of
        them, and the rail would serve four games while a fifth was sitting in
        the table. The route over-fetches for exactly this reason.
        """
        base = _soon(2)
        rows = [
            # The twinned fixture, earliest so it lands at the top of the rail.
            _event(STATPAL_ID, when=base, sources={"kalshi": _fresh(0.635)}),
            _event(ESPN_ID, when=base, espn_id="401816907"),
        ]
        # Five further DISTINCT fixtures, so a full rail is available.
        for i in range(5):
            rows.append(
                _event(
                    9000 + i,
                    when=base + timedelta(days=i + 1),
                    away=f"Opponent {i}",
                )
            )

        page = _page(_engine(*rows))
        rail = page["upcoming_events"]

        assert len(rail) == 5, (
            f"the rail lost a card to the fold — served {len(rail)}: "
            f"{[c['id'] for c in rail]}"
        )
        ids = [c["id"] for c in rail]
        assert STATPAL_ID not in ids
        assert ids.count(ESPN_ID) == 1

    def test_the_rail_is_never_longer_than_the_cap(self):
        """Over-fetching must not leak extra cards onto the page.

        The query now asks for more rows than the rail shows; if the truncation
        were dropped, a team with ten upcoming games would serve ten cards.
        """
        base = _soon(2)
        rows = [
            _event(9100 + i, when=base + timedelta(days=i), away=f"Opponent {i}")
            for i in range(9)
        ]

        page = _page(_engine(*rows))

        assert len(page["upcoming_events"]) == 5


class TestTheFoldDoesNotOverreach:
    def test_a_doubleheader_is_never_folded(self):
        """🔴 THE NEGATIVE CONTROL. Two real games, same teams, same day.

        CONSTRUCTED, AND SAID SO RATHER THAN QUIETLY DROPPED. The ±9-day
        production window carried no true MLB doubleheader when this shipped
        (authority/147's recon measured the distribution and found none), so
        there is no specimen to lift. That is a reason to build the fixture, not
        a reason to skip the case: a doubleheader is precisely the shape a
        name-and-day matcher gets wrong, and the whole licence for this fold is
        that its key admits no false positives.

        The key is `(sport, away, home, commence MINUTE)`, so the two legs
        differ in the only field that matters. The pair is deliberately hours
        apart AND on one UTC date, because `date_trunc('day', commence_time)`
        is a UTC day rather than a slate — a guard keyed on the calendar day
        would both split real slates and merge unrelated ones.
        """
        day = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)
        game_one = day + timedelta(hours=17, minutes=10)
        game_two = day + timedelta(hours=20, minutes=40)

        page = _page(
            _engine(
                _event(9200, when=game_one, espn_id="401816900"),
                _event(9201, when=game_two, espn_id="401816901"),
            )
        )
        rail = page["upcoming_events"]

        assert len(rail) == 2, (
            "a doubleheader was folded into one card — both legs are real "
            f"games, got {[c['id'] for c in rail]}"
        )
        assert {c["id"] for c in rail} == {9200, 9201}

    def test_two_different_opponents_at_one_instant_are_never_folded(self):
        """The key carries the teams, not just the clock."""
        when = _soon()
        page = _page(
            _engine(
                _event(9300, when=when, away=ROYALS),
                _event(9301, when=when, away="New York Yankees"),
            )
        )

        assert len(page["upcoming_events"]) == 2

    def test_a_lone_row_is_untouched(self):
        """No twin, no change — the ordinary page must not move."""
        eng = _engine(
            _event(
                ESPN_ID,
                when=_soon(),
                espn_id="401816907",
                sources={"betting": _fresh(0.6288)},
            )
        )
        rail = _page(eng)["upcoming_events"]

        assert len(rail) == 1
        assert rail[0]["id"] == ESPN_ID
        assert rail[0]["win_probability"] is not None


class TestTheRecentRailToo:
    def test_the_recent_rail_is_folded_and_not_only_the_upcoming_one(self):
        """51 of the 63 measured MLB twin pairs sit on games already played.

        A fold wired into one rail and not the other leaves the duplicate on the
        half of the page that carries most of them.
        """
        played = datetime.now(timezone.utc) - timedelta(days=2)
        page = _page(
            _engine(
                _event(
                    STATPAL_ID,
                    when=played,
                    status="completed",
                    scores=(4, 2),
                    sources={"kalshi": _fresh(0.635)},
                ),
                _event(
                    ESPN_ID,
                    when=played,
                    status="completed",
                    scores=(4, 2),
                    espn_id="401816907",
                ),
            )
        )
        rail = page["recent_events"]

        assert len(rail) == 1, (
            f"the recent rail served both rows, got {[c['id'] for c in rail]}"
        )


class TestAFoldFailureCannotTakeTheTeamPageDown:
    def test_a_fold_that_raises_serves_the_unfolded_rail_and_says_so(
        self, caplog, monkeypatch
    ):
        """Gotcha #42 for a whole stage: the fold improves the rail, it is never
        a precondition for having one.

        The degraded answer is today's page — two cards — not a 500 and not an
        empty rail on a Priority-#3 surface (#1197 / #1239). `logger.exception`
        makes it the opposite of silent.
        """

        def _boom(rows):
            raise RuntimeError("fold exploded")

        monkeypatch.setattr(route, "fold_twin_events", _boom)

        with caplog.at_level(logging.ERROR, logger=route.logger.name):
            page = _production_pair_page()

        assert len(page["upcoming_events"]) == 2, "the rail should degrade to unfolded"
        assert any(
            "twin fold failed" in r.message or "twin fold failed" in r.getMessage()
            for r in caplog.records
        ), "the failure was swallowed silently"

    def test_the_degraded_rail_is_still_capped(self):
        """The truncation must not live inside the `try`.

        If the cap were applied only on the happy path, a fold failure would
        serve every over-fetched row — turning a fold bug into a page-length
        bug.
        """
        base = _soon(2)
        rows = [
            _event(9400 + i, when=base + timedelta(days=i), away=f"Opponent {i}")
            for i in range(9)
        ]

        original = route.fold_twin_events
        try:
            route.fold_twin_events = lambda r: (_ for _ in ()).throw(
                RuntimeError("fold exploded")
            )
            page = _page(_engine(*rows))
        finally:
            route.fold_twin_events = original

        assert len(page["upcoming_events"]) == 5
