"""#5918 — `GET /api/events` serves one card per fixture, tagged pairs included.

## What a reader sees, and what this file is for

`https://bainluck.com/sports/soccer_spain_la_liga`, production, 2026-09-13
16:5xZ, `GET /api/events?sport=soccer_spain_la_liga&days=7` — **one fixture,
two cards**::

    15310518  Malaga CF @ RC Celta de Vigo   suspended   2026-09-13T12:00:00Z
    15298077  Málaga    @ Celta Vigo         completed   2026-09-13T12:00:00Z

Same minute, same fixture, and `15310518` has carried
`provenance:duplicate-of:15298077` all along. The tag is written. The page
serves both anyway.

## Why the fold that already runs here cannot see it

`list_events` applies the NAME-keyed `fold_twin_events` (#4100), whose key is
`(sport_id, _squash(away), _squash(home), commence_minute)`.
`_squash("RC Celta de Vigo")` is `rcceltadevigo` and `_squash("Celta Vigo")` is
`celtavigo`, so the name arm can never group this pair — and a pair whose names
ARE equal never needed the tag in the first place. **The tag exists for exactly
the population the name key cannot see**, which is why
`test_the_name_fold_alone_leaves_both_rows_standing` is in this file: without
it, every assertion below could be satisfied by the fold that was already
there, and the guard would be vacuous.

Twelve other queries in `routes/events.py` already carry
`not_a_proven_duplicate()`. This route was the last list surface without it.

## Why the filter ALONE would be a regression, and why that is the other half

`twin_identity_rank` elects on score-then-anchor, so the row that gets TAGGED is
routinely the one holding the prices. Hiding it without carrying its numbers
across trades two cards for one blank one — "the blend is the product". Two
numbers have to travel, and they live in two different places:

* the LIVE card's, `win_probability_sources` — already folded on this route
  (`folded_probability_sources_batch`, #3937);
* the SETTLED card's, `Event.opening_*` — the "Pre-match · sportsbooks"
  percentage, which has never been in that bag. #5853 built
  `merge_opening_line` for it and wired `/api/leagues`; this route gets it here.

`test_a_settled_card_keeps_the_opening_only_its_suppressed_twin_held` is the
second half stated as a test, and it fails on the DESIGN: wiring only the fold
that already existed passes every other assertion in this file and still serves
a finished fixture with no percentage.

## Reach, measured before building

Production 2026-09-13 16:4xZ, every row carrying a `provenance:duplicate-of:`
tag inside THIS route's own window and status set::

    tagged in window          4
    canonical row missing     0
    canonical out of window   0
    canonical wrong status    0

so no suppressed row is orphaned today. Of the four, two are pairs the name arm
already collapses (`Brest`/`Brest`, `St.Louis Cardinals`/`St. Louis Cardinals`)
and two are the pairs it cannot (`RC Celta de Vigo`/`Celta Vigo` on one league
page, `Sabalenka`/`Aryna Sabalenka` across two tennis keys).

🔴 REAL ROWS IN A REAL ENGINE, NOT MagicMock. The duplicate-tag predicate's
Postgres arm is a `@>` operator and its portable arm is a quoted `LIKE`, so a
mock that answers every statement with the same rows would pass this file while
the WHERE clause did nothing at all. The harness below is the one
`test_league_page_tag_fold_5853.py` and `test_team_page_twin_fold_5487.py` use,
for that reason.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
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


from sqlalchemy import select  # noqa: E402

from app.models.models import Base, Event, OddsSnapshot, Sport  # noqa: E402
from app.routes.events import list_events  # noqa: E402
from app.services.anchor_channel import duplicate_tag  # noqa: E402
from app.utils.event_twin_fold import fold_twin_events, twin_fold_key  # noqa: E402
from app.utils.soccer_team_matching import soccer_pair_matches  # noqa: E402

#: The production pair, verbatim.
CANONICAL = 15298077  # "Celta Vigo", completed, holds its own opening line
SUPPRESSED = 15310518  # "RC Celta de Vigo", suspended, tagged duplicate

S_LA_LIGA = 1317
SPORT_KEY = "soccer_spain_la_liga"

CANON_HOME = "Celta Vigo"
DUP_HOME = "RC Celta de Vigo"
CANON_AWAY = "Málaga"
DUP_AWAY = "Malaga CF"

OPEN_HOME = 0.7528
OPEN_AWAY = 0.2472


def _fresh(value: float) -> dict:
    """A reading stamped now, so source-weight decay cannot move an assertion.

    Gotcha #44: offset from the clock, never a literal stamp.
    """
    return {"value": value, "updated_at": datetime.now(timezone.utc).isoformat()}


def _played(hours_ago=4):
    """A kick-off in the past, so `opening_consensus_has_frozen` is True.

    The opening line may only be PUBLISHED once its writer has stopped writing
    it (#3922). A pair of tests about a printed "Pre-match" percentage on a
    fixture that has not started would assert nothing.
    """
    return datetime.now(timezone.utc) - timedelta(hours=hours_ago)


def _event(
    event_id,
    *,
    home,
    away,
    when,
    sources=None,
    tags=None,
    opening=(None, None),
    status="completed",
    scores=(1, 0),
    espn_id=None,
):
    return Event(
        id=event_id,
        sport_id=S_LA_LIGA,
        home_team_name=home,
        away_team_name=away,
        commence_time=when,
        completed_at=when + timedelta(hours=2) if status == "completed" else None,
        status=status,
        home_score=scores[0],
        away_score=scores[1],
        espn_id=espn_id,
        win_probability_sources=sources,
        event_tags=tags if tags is not None else ["provenance:unanchored"],
        opening_home_probability=opening[0],
        opening_away_probability=opening[1],
    )


def _the_production_pair(
    *, canonical_opening=(OPEN_HOME, OPEN_AWAY), canonical_status="completed"
):
    """The two La Liga rows as production holds them, canonical first."""
    when = _played()
    canonical = _event(
        CANONICAL,
        home=CANON_HOME,
        away=CANON_AWAY,
        when=when,
        status=canonical_status,
        espn_id="401884111",
        sources={"betting": _fresh(0.62)},
        opening=canonical_opening,
    )
    suppressed = _event(
        SUPPRESSED,
        home=DUP_HOME,
        away=DUP_AWAY,
        when=when,
        status="suspended",
        sources={"kalshi": _fresh(0.71), "polymarket": _fresh(0.70)},
        tags=["provenance:source:statpal", duplicate_tag(CANONICAL)],
        opening=(OPEN_HOME, OPEN_AWAY),
    )
    return canonical, suppressed


def _engine(*events):
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=S_LA_LIGA, key=SPORT_KEY, name="La Liga", group="Soccer"))
        for e in events:
            s.add(e)
        s.commit()
    return eng


class _Session:
    """A real engine behind the async surface `list_events` calls."""

    def __init__(self, session):
        self._s = session

    async def execute(self, statement, *args, **kwargs):
        return self._s.execute(statement, *args)


def _portable_odds_query(event_ids):
    """The odds enrichment read, in a form SQLite can parse.

    `latest_odds_per_bookmaker_query` is a recursive CTE joined `LATERAL` — a
    deliberate Postgres shape (LAT-P030 measured it 36x faster than the window
    function it replaced) that no other dialect can execute. Its own guards live
    in `test_search_latency_contract.py` and
    `tests/integration/test_search_odds_enrichment_equivalence.py`, against real
    Postgres.

    Substituting a portable SELECT keeps the route executing an odds statement
    and running its real grouping, staleness-filtering and aggregation code over
    whatever comes back. Every test here stores NO snapshots, so the truthful
    answer is the empty one either way, and this swap changes which SQL is
    parsed rather than what the page is told.
    """
    return select(OddsSnapshot).where(OddsSnapshot.event_id.in_(event_ids))


def _payload(*events, **params):
    """The served `GET /api/events` body, through the real route.

    `_load_gei_percentiles` and `_build_team_lookup` are page furniture — colour
    swatches and percentile bands — and are patched out so a failure here is
    always about which rows were served and what numbers they carry.
    """
    eng = _engine(*events)
    call = {"sport": SPORT_KEY, "status": None, "days": 7, "limit": 200, "offset": 0}
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


def _by_id(payload) -> dict:
    return {card["id"]: card for card in payload["events"]}


# ---------------------------------------------------------------------------
# the ship
# ---------------------------------------------------------------------------


class TestOneFixtureOneCard:
    def test_the_la_liga_page_stops_printing_the_fixture_twice(self):
        """🔴 THE SHIP. Alex's league page shows Celta–Málaga once, not twice."""
        served = _by_id(_payload(*_the_production_pair()))

        assert SUPPRESSED not in served, (
            "the tagged duplicate was served as its own card — this is the "
            f"production bug (ids served: {sorted(served)})"
        )
        assert CANONICAL in served, (
            "suppressing the duplicate must leave the canonical card standing, "
            f"not empty the fixture (ids served: {sorted(served)})"
        )

    def test_count_reports_what_was_actually_served(self):
        """`count` is the honest length of the list, never the pre-filter number."""
        payload = _payload(*_the_production_pair())

        assert payload["count"] == len(payload["events"]) == 1

    def test_the_name_fold_alone_leaves_both_rows_standing(self):
        """🔴 READ THIS ONE FIRST — it proves the guard above is not vacuous.

        `fold_twin_events` has run on this route since #4100. If it could group
        this pair, every assertion in this file would pass with the tag
        predicate deleted. It cannot: the two rows spell one club two ways, so
        their keys differ and the fold hands both back.
        """
        canonical, suppressed = _the_production_pair()

        assert twin_fold_key(canonical) != twin_fold_key(suppressed), (
            "the name key grouped this pair, so this file can no longer tell an "
            "id-anchored fix from the name fold that was already here"
        )

        kept = fold_twin_events([canonical, suppressed]).events
        assert len(kept) == 2, (
            "the name fold collapsed the pair by itself — pick a specimen it "
            "cannot group, or this whole file is a test of #4100"
        )


class TestTheSurvivingCardKeepsWhatTheHiddenRowHeld:
    def test_the_card_carries_the_price_only_the_suppressed_row_had(self):
        """Hiding the tagged row may not delete a venue from the number.

        The two rows' venues are disjoint on purpose — `betting` at .62 on the
        canonical, `kalshi` .71 and `polymarket` .70 on the row being suppressed
        — so a survivor blending only its own is a reader losing real prices.
        The assertion is on the HERO, which is where the fold is delivered
        (`resolve_hero` over `FoldedBlendView`): an unfolded card prints exactly
        .62 and a folded one cannot.

        Both rows are `suspended` rather than completed here for one reason: a
        completed card's hero is the SETTLED result (`hero_probability 1.0`,
        source `settled`), which is the same number folded or not, so the
        obvious version of this test asserts nothing.
        """
        card = _by_id(_payload(*_the_production_pair(canonical_status="suspended")))[
            CANONICAL
        ]

        assert card["hero_probability_source"] != "settled", (
            "the specimen settled, so the hero no longer reads the blend and "
            "this assertion cannot see the fold"
        )
        assert card["hero_probability"] != pytest.approx(0.62), (
            "the hero is still the canonical's own lone `betting` reading — the "
            "two venues on the row this change stopped printing did not reach "
            f"the page (got {card['hero_probability']!r})"
        )
        assert 0.62 < card["hero_probability"] < 0.72, (
            "the folded hero should sit among the three readings (.62/.70/.71), "
            f"got {card['hero_probability']!r}"
        )

    def test_a_settled_card_keeps_the_opening_only_its_suppressed_twin_held(self):
        """🔴 THE SECOND HALF. It fails on the DESIGN, not on the code.

        Wiring only the fold that already existed
        (`folded_probability_sources_batch`, #3937) satisfies every other
        assertion in this file and still serves this card with no percentage:
        the printed "Pre-match · sportsbooks" number comes from `opening_odds`,
        which is served from the `Event.opening_*` COLUMNS and has never been in
        the JSONB bag. This is the Bundesliga defect of #5853 arriving on this
        surface by way of its own fix.
        """
        canonical, suppressed = _the_production_pair(canonical_opening=(None, None))

        card = _by_id(_payload(canonical, suppressed))[CANONICAL]

        assert card.get("opening_odds") is not None, (
            "the surviving card prints no pre-match line while the row it "
            "suppressed holds one — the card lost a number by being deduped"
        )
        assert card["opening_odds"]["home_probability"] == pytest.approx(OPEN_HOME)
        assert card["opening_odds"]["away_probability"] == pytest.approx(OPEN_AWAY)

    def test_the_fold_is_gap_fill_and_never_replaces_the_canonicals_own_line(self):
        """A card printing a correct pair today can never have it changed.

        `merge_opening_line` is additive by construction and this pins it on the
        served payload: the canonical opened at .7528 here and the twin at .40,
        and the number that reaches the reader is the canonical's own.
        """
        canonical, suppressed = _the_production_pair()
        suppressed.opening_home_probability = 0.40
        suppressed.opening_away_probability = 0.60

        card = _by_id(_payload(canonical, suppressed))[CANONICAL]

        assert card["opening_odds"]["home_probability"] == pytest.approx(OPEN_HOME), (
            "the twin's opening replaced the canonical's own — the fold is a "
            "gap-fill, not a preference"
        )


class TestWhatMustNotChange:
    """TWO licences reach this route now, and this class pins the boundary.

    This file originally asserted that the `duplicate-of:` tag was the WHOLE
    licence for folding a card, citing ruling 048. That was too strong, and
    authority/181's `0ccf6e77c` — shipped under this same issue an hour later —
    made master red by being correct: it added a soccer name-pair pass to
    `fold_twin_events`, and this file's own fixture (`Celta Vigo` /
    `RC Celta de Vigo`, `Málaga` / `Malaga CF`) is precisely the exonym family
    that pass exists to fold.

    Ruling 048 and gotcha #32 govern the REGISTRY's absorb-vs-create at WRITE
    time: an id-less claim never absorbs, it creates. Neither row here is
    absorbed, deleted or repointed. Both passes act at SERVE time, both elect a
    survivor and union its sources rather than dropping a row, and serve-time
    folding on a non-tag licence predates both of them on this route
    (`fold_twin_events` since #4100). So the tag is *a* licence, not the only
    one, and the thing actually worth pinning is that **the tag predicate does
    not sweep rows no licence reaches** — which is what the test below now says.
    """

    def test_the_tag_predicate_does_not_sweep_a_pair_no_licence_reaches(self):
        """The predicate removes TAGGED rows and nothing else.

        The fixture is deliberately a pair BOTH licences refuse: no
        `duplicate-of:` tag, and a squad qualifier on one side, which
        `soccer_team_matching` refuses by construction because `Celta Vigo B`
        is a different squad of the same club. If the tag predicate were ever
        widened into a matcher of its own, this is the test that fails.
        """
        canonical, suppressed = _the_production_pair()
        suppressed.home_team_name = CANON_HOME + " B"
        suppressed.away_team_name = CANON_AWAY
        suppressed.event_tags = ["provenance:source:statpal"]

        assert not soccer_pair_matches(
            (canonical.home_team_name, canonical.away_team_name),
            (suppressed.home_team_name, suppressed.away_team_name),
        ), (
            "the name pass accepts this pair, so it is no longer a pair 'no "
            "licence reaches' and this test proves nothing about the tag"
        )

        served = _by_id(_payload(canonical, suppressed))

        assert sorted(served) == sorted([CANONICAL, SUPPRESSED]), (
            "a row that neither the tag nor the name pass licenses was "
            f"suppressed anyway (served: {sorted(served)})"
        )

    def test_an_untagged_exonym_pair_is_folded_by_the_name_pass_and_keeps_both_sources(
        self,
    ):
        """The other licence, stated so nobody restores the assertion above.

        Strip the tag from the production pair and the rows are STILL one card
        — folded by authority/181's soccer name pass, not by this ship. That is
        the intended behaviour and the reason master went red when the two
        halves of #5918 met.

        The half that makes it safe is asserted here rather than described: the
        survivor carries the sources of the row it absorbed. This pass merges
        and unions; it does not filter. On the real pair the priced row and the
        id-bearing row are different rows, so a filter would have deleted the
        only priced card — which is the regression #5918 was filed to refuse.
        """
        canonical, suppressed = _the_production_pair()
        suppressed.event_tags = ["provenance:source:statpal"]

        served = _by_id(_payload(canonical, suppressed))

        assert sorted(served) == [CANONICAL], (
            "the soccer name pass no longer folds the exonym pair this file is "
            f"built on (served: {sorted(served)})"
        )
        card = served[CANONICAL]
        assert card.get("opening_odds") is not None, (
            "the survivor lost the pre-match line — a fold that drops a number "
            "is the filter this ship exists to refuse"
        )

    def test_a_lone_untagged_row_is_untouched(self):
        """The ordinary page: no tags anywhere, one card, its own numbers."""
        canonical, _ = _the_production_pair()

        card = _by_id(_payload(canonical))[CANONICAL]

        assert card["opening_odds"]["home_probability"] == pytest.approx(OPEN_HOME)
        assert sorted((card.get("win_probability_sources") or {})) == ["betting"]

    def test_a_tagged_row_whose_canonical_is_absent_is_still_hidden(self):
        """Stated because it is the one way this can cost a reader a card.

        Measured zero on production today (4 tagged rows in this route's window,
        0 with an unreachable canonical), and it is the shipped behaviour of
        `not_a_proven_duplicate()` on twelve sibling queries, so this test
        RECORDS the trade rather than claiming it cannot happen. If that
        measurement ever turns non-zero this is the sentence to revisit.
        """
        _, suppressed = _the_production_pair()

        payload = _payload(suppressed)

        assert payload["events"] == []
        assert payload["count"] == 0
