"""A club page shows only its OWN league's games (#5491).

## What a reader saw

Alex's Red Sox page, `/sport/baseball/mlb/team/boston-red-sox`, RECENT RESULTS,
screenshotted from production 2026-09-12 06:5xZ while paying #5487's LOOK:

    vs Texas Rangers — Sep 11 — No result reported

**The Red Sox did not play Texas on Sep 11.** They played Kansas City
(`15309637`, L 2–3), which sat on the same rail two cards away.

## The row, and the family it belongs to

    15310222  sport=baseball_other  status=suspended  commence=2026-09-11 13:00:40Z
              espn_id=NULL  external_id=NULL  home_team_id=NULL  away_team_id=NULL
              tags=['provenance:source:polymarket', 'provenance:unanchored']

It is not a phantom matchup — Boston DO play Texas, on Sep 15. It is a real
fixture ingested with the INGEST TIME written into `commence_time`. Measured on
production, all eighteen of its siblings from that batch sit at
`13:00:3x`–`13:00:5x` UTC on one date, each a real MLB pairing, each unanchored
and unbound: Twins–Angels `13:00:41`, Phillies–Mets `13:00:37`,
Tigers–White Sox `13:00:37`, Royals–Astros `13:00:36`, Padres–Rockies
`13:00:35`, Athletics–Rays `13:00:32`, Dodgers–Reds `13:00:31`,
Brewers–Pirates `13:00:30`. The tennis half of the same defect is identical in
shape — `tennis_other`, `23:05:1x`, suspended, unbound — which is why the fix
is a rule about leagues and not a rule about baseball.

## Why it reached an MLB page

`get_team`'s event filter has four arms. Two match on `team_id`; two match on
`Event.home_team_name == team.name`. The NAME arms are a fallback for rows whose
team binding never landed — which is exactly this row's state — and they were
unconstrained by league, so a `baseball_other` row bearing the string
"Boston Red Sox" landed on the `baseball_mlb` club's page.

## Why the guard is scoped to UNBOUND rows, and why that scoping is the fix

The obvious repair — constrain the name arms to the team's league — is a
REGRESSION, and the measurement says so. Over a ±21-day window on production
2026-09-12, constraining every name-matched row would have excluded 9,784 rows,
including an EPL match reaching a club registered under `soccer_england_efl_cup`
and a Serie A match reaching one registered under `soccer_italy_coppa_italia`.
Clubs play in several competitions; cutting on league alone empties their pages.

Scoping the guard to rows with NO binding on either side — the only population
the name arms serve — cuts that to 4,521 rows, of which **4,447 (98.4%) come
from a `*_other` catch-all bucket**. The league/cup pairs vanish from the cut
entirely, because those events carry real team ids and are never tested. The 74
remaining rows are name collisions that should always have been cut:
`mma_mixed_martial_arts` → `soccer_epl`, `esports` →
`soccer_germany_bundesliga`, `tennis_wta` → `soccer_epl`.

**Disclosed residual:** ~12 of those 74 are a promoted or relegated club
(`soccer_spain_la_liga` event → `soccer_spain_segunda_division` club) losing an
unbound card. Those rows have no team binding either, so the card was of poor
quality regardless; `test_a_relegation_pair_is_the_disclosed_residual` pins the
behaviour so it is a decision on the record rather than a surprise.

## Why the comparison is `league_family_identity` and never `sport_id`

Two separate traps, each with its own test here:

1. **A row id is not a league** (#1798 / #4945). Every MLB club has a
   `baseball_mlb_preseason` row as well as a `baseball_mlb` one, so
   `sport_id == team.sport_id` reads a season variant as a foreign league and
   would cut all 30 clubs (#2498's bug, one surface over).
2. **A tour's tournaments are its own play.** A player registered under
   `tennis_atp_us_open` must keep their `tennis_atp` matches; 1,454 of the
   unbound name-matched rows in the window are exactly that. `league_identity`
   alone does NOT collapse those — `league_family_identity` adds the tour arm,
   and `test_a_tour_players_matches_survive` is the assertion that catches a
   repair that reaches for the smaller helper.

## Shape

Real `get_team` against a real engine, the harness
`test_team_page_twin_fold_5487.py` established for this route and for the same
reason: the predicate under test is SQL, and a mocked session proves the
formatter instead of the query. Every fixture is a real production specimen.
Clock-relative offsets throughout (gotcha #44) — the rails are time-windowed, so
a frozen stamp would drift the assertions with the calendar.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


# DDL shims so `create_all` can build the real schema on SQLite — the pair this
# route's sibling tests declare, for the same reason: the proven-duplicate
# filter's Postgres arm is an `@>` operator, so the portable arm has to be
# exercised against a real engine rather than a mock.
@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models.models import Base, Event, Sport, Team  # noqa: E402
from app.routes import teams as route  # noqa: E402
from app.utils.sport_keys import (  # noqa: E402
    league_family_identity,
    league_identity,
)

#: Production sport-row ids (`db-query`, 2026-09-12).
S_MLB = 53232
S_MLB_PRESEASON = 33178
S_BASEBALL_OTHER = 60001
S_ATP = 60002
S_ATP_US_OPEN = 60003
S_LA_LIGA = 60004
S_SEGUNDA = 60005
S_TENNIS_OTHER = 60006

RED_SOX_ID = 10709
ROYALS_ID = 11625

RED_SOX = "Boston Red Sox"
ROYALS = "Kansas City Royals"
RANGERS = "Texas Rangers"

#: The specimen from Alex's screenshot.
PHANTOM_ID = 15310222
#: The real game on the same rail, two cards away.
REAL_ID = 15309637


def _ago(hours):
    return datetime.now(timezone.utc) - timedelta(hours=hours)


def _soon(hours=6):
    return datetime.now(timezone.utc) + timedelta(hours=hours)


def _event(
    event_id,
    *,
    sport_id,
    when,
    home,
    away,
    home_team_id=None,
    away_team_id=None,
    status="scheduled",
    scores=(None, None),
    espn_id=None,
):
    return Event(
        id=event_id,
        sport_id=sport_id,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home_team_name=home,
        away_team_name=away,
        commence_time=when,
        status=status,
        home_score=scores[0],
        away_score=scores[1],
        espn_id=espn_id,
        event_tags=["provenance:unanchored"],
    )


def _the_polymarket_row(sport_id=S_BASEBALL_OTHER):
    """`15310222` verbatim: real pairing, ingest time, no anchor, NO BINDING.

    `sport_id` is a parameter because the control needs this exact row in
    `baseball_mlb` — see `test_the_same_row_in_the_clubs_own_league_is_served`.
    """
    return _event(
        PHANTOM_ID,
        sport_id=sport_id,
        when=_ago(18),
        home=RED_SOX,
        away=RANGERS,
        status="suspended",
        home_team_id=None,
        away_team_id=None,
    )


def _the_real_game():
    """`15309637`, L 2–3 against Kansas City — bound, anchored, completed."""
    return _event(
        REAL_ID,
        sport_id=S_MLB,
        when=_ago(20),
        home=RED_SOX,
        away=ROYALS,
        home_team_id=RED_SOX_ID,
        away_team_id=ROYALS_ID,
        status="completed",
        scores=(2, 3),
        espn_id="401816892",
    )


def _engine(*events, sports=(), teams=()):
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=S_MLB, key="baseball_mlb", name="MLB"))
        for sport_id, key in sports:
            s.add(Sport(id=sport_id, key=key, name=key))
        s.add(Team(id=RED_SOX_ID, sport_id=S_MLB, name=RED_SOX, slug="boston-red-sox"))
        s.add(Team(id=ROYALS_ID, sport_id=S_MLB, name=ROYALS, slug="kansas-city-royals"))
        for team in teams:
            s.add(team)
        for e in events:
            s.add(e)
        s.commit()
    return eng


def _page(eng, slug="boston-red-sox"):
    """`get_team` for real — its real `select()`s, its real predicate."""
    with Session(eng) as s:

        class _Session:
            async def execute(self, statement):
                return s.execute(statement)

        return asyncio.run(route.get_team(slug, db=_Session()))


def _ids(page):
    return [c["id"] for c in page["upcoming_events"] + page["recent_events"]]


# --------------------------------------------------------------------------
# The ship
# --------------------------------------------------------------------------


class TestTheRedSoxPage:
    def test_the_foreign_league_row_is_gone(self):
        """🔴 THE SHIP. "vs Texas Rangers — No result reported" leaves the page."""
        page = _page(_engine(
            _the_polymarket_row(),
            _the_real_game(),
            sports=[(S_BASEBALL_OTHER, "baseball_other")],
        ))

        assert PHANTOM_ID not in _ids(page), (
            "the `baseball_other` row reached the MLB club's page by name — "
            f"this is the production bug, got {_ids(page)}"
        )

    def test_the_real_game_is_still_there(self):
        """The guard removed a card; it must not have removed the rail.

        Without this, a fix that returned an empty page for every club would
        pass the assertion above.
        """
        page = _page(_engine(
            _the_polymarket_row(),
            _the_real_game(),
            sports=[(S_BASEBALL_OTHER, "baseball_other")],
        ))

        assert REAL_ID in _ids(page), (
            f"the club's own completed game vanished with it, got {_ids(page)}"
        )

    def test_the_same_row_in_the_clubs_own_league_is_served(self):
        """🔴 THE CONTROL, and it is the whole non-vacuity argument.

        The identical unbound, unanchored, suspended row — same id, same names,
        same timestamp, same missing bindings — placed in `baseball_mlb`
        instead. It MUST still reach the page: the name arms exist for exactly
        this row, and only its LEAGUE is disqualifying.

        If this ever fails, the guard is cutting on unboundedness rather than on
        league and the ship has become a different, worse change.
        """
        page = _page(_engine(
            _the_polymarket_row(sport_id=S_MLB),
            sports=[(S_BASEBALL_OTHER, "baseball_other")],
        ))

        assert PHANTOM_ID in _ids(page), (
            "an unbound row in the club's OWN league was cut — the guard is "
            "keying on the binding, not on the league"
        )


# --------------------------------------------------------------------------
# The two families that must survive the guard
# --------------------------------------------------------------------------


class TestWhatMustNotBeCut:
    def test_a_season_variants_games_survive(self):
        """#2498 / #4945: `baseball_mlb_preseason` is the Red Sox, not a rival.

        A `sport_id` comparison cuts this row and takes all 30 clubs' preseason
        schedules with it. `league_identity` collapses the suffix, so the row
        stays.
        """
        preseason = _event(
            15400001,
            sport_id=S_MLB_PRESEASON,
            when=_soon(),
            home=RED_SOX,
            away=ROYALS,
            home_team_id=None,
            away_team_id=None,
        )
        page = _page(_engine(
            preseason,
            sports=[(S_MLB_PRESEASON, "baseball_mlb_preseason")],
        ))

        assert 15400001 in _ids(page), (
            "a season variant was read as a foreign league — this is the "
            "`sport_id` trap (#1798/#4945), one surface over from #2498"
        )

    def test_a_tour_players_matches_survive(self):
        """A player registered under a TOURNAMENT keeps ALL their own play.

        🔴 THIS TEST CARRIES A FOREIGN ROW ON PURPOSE, AND THAT IS THE WHOLE
        POINT OF IT. Asserting only that the tour match SURVIVES is vacuous: it
        is equally true when the guard is working and when the guard has
        silently switched itself off. Two real mutants did exactly that —
        computing `team_family` with `league_identity` while the sport rows are
        classified with `league_family_identity` yields an EMPTY family set, the
        `if family_sport_ids:` fail-open fires, and every assertion about a
        surviving row still passes while the guard protects nothing.

        So the specimen is all three rows at once, and the page must separate
        them:

          * `tennis_atp`           — the tour's own play          → SERVED
          * `tennis_atp_us_open`   — the player's own tournament   → SERVED
          * `tennis_other`         — the catch-all defect bucket   → CUT

        The third assertion is what proves a rule ran at all; the second is what
        catches classifying the SPORT rows with the smaller helper, which cuts a
        US Open match off a US Open player's page.
        """
        player = Team(
            id=70001,
            sport_id=S_ATP_US_OPEN,
            name="Jaume Munar",
            slug="jaume-munar",
        )
        opponent = "Facundo Acosta"

        def _match(event_id, sport_id, hours):
            return _event(
                event_id,
                sport_id=sport_id,
                when=_soon(hours),
                home="Jaume Munar",
                away=opponent,
                home_team_id=None,
                away_team_id=None,
            )

        page = _page(
            _engine(
                _match(15400002, S_ATP, 6),
                _match(15400005, S_ATP_US_OPEN, 8),
                _match(15400006, S_TENNIS_OTHER, 10),
                sports=[
                    (S_ATP, "tennis_atp"),
                    (S_ATP_US_OPEN, "tennis_atp_us_open"),
                    (S_TENNIS_OTHER, "tennis_other"),
                ],
                teams=[player],
            ),
            slug="jaume-munar",
        )
        served = _ids(page)

        assert 15400002 in served, (
            "a tour player lost their own TOUR match — the guard used "
            f"`league_identity` where it needs `league_family_identity`, got {served}"
        )
        assert 15400005 in served, (
            "a US Open match was cut from a US Open player's page — the SPORT "
            f"rows are being classified with the smaller helper, got {served}"
        )
        assert 15400006 not in served, (
            "the `tennis_other` catch-all row survived on a tour player's page: "
            "the family set came back EMPTY and the fail-open disabled the "
            f"guard entirely, so the two assertions above prove nothing. {served}"
        )

    def test_a_bound_row_is_never_tested_at_all(self):
        """The scoping clause, stated as an assertion.

        A row carrying a real team id reaches the page by name even from a
        foreign league. This is what keeps an EPL match on the page of a club
        registered under `soccer_england_efl_cup`, and it is why the cut is
        4,521 rows instead of 9,784. A repair that drops the `isnot(None)` arms
        passes every other test in this file and fails this one.
        """
        bound_but_foreign = _event(
            15400003,
            sport_id=S_BASEBALL_OTHER,
            when=_soon(),
            home=RED_SOX,
            away=RANGERS,
            home_team_id=ROYALS_ID,  # bound to SOME team, just not this one
            away_team_id=None,
        )
        page = _page(_engine(
            bound_but_foreign,
            sports=[(S_BASEBALL_OTHER, "baseball_other")],
        ))

        assert 15400003 in _ids(page), (
            "a BOUND row was cut — the guard has widened past the unbound "
            "population it was measured on, and soccer club pages will empty"
        )

    def test_a_relegation_pair_is_the_disclosed_residual(self):
        """The ~12 rows this ship knowingly costs, pinned as a decision.

        A club registered under `soccer_spain_segunda_division` loses an UNBOUND
        `soccer_spain_la_liga` card. This is not an accident and not a bug
        report: it is the measured residual, recorded here so that changing it
        is a choice someone makes on purpose.
        """
        promoted = Team(
            id=70002,
            sport_id=S_SEGUNDA,
            name="Real Oviedo",
            slug="real-oviedo",
        )
        top_flight = _event(
            15400004,
            sport_id=S_LA_LIGA,
            when=_soon(),
            home="Real Oviedo",
            away="Getafe",
            home_team_id=None,
            away_team_id=None,
        )
        page = _page(
            _engine(
                top_flight,
                sports=[
                    (S_LA_LIGA, "soccer_spain_la_liga"),
                    (S_SEGUNDA, "soccer_spain_segunda_division"),
                ],
                teams=[promoted],
            ),
            slug="real-oviedo",
        )

        assert 15400004 not in _ids(page), (
            "the disclosed residual changed — if this is now SERVED the ship "
            "has widened, and the docstring's 4,521-row measurement is stale"
        )


# --------------------------------------------------------------------------
# The helper, on its own
# --------------------------------------------------------------------------


class TestLeagueFamilyIdentity:
    def test_a_season_variant_collapses_onto_its_parent(self):
        assert league_family_identity("baseball_mlb_preseason") == (
            league_family_identity("baseball_mlb")
        )

    def test_a_tour_tournament_collapses_onto_its_tour(self):
        assert league_family_identity("tennis_atp_us_open") == "tennis_atp"
        assert league_family_identity("tennis_atp") == "tennis_atp"

    def test_the_tour_arm_is_what_league_identity_lacks(self):
        """Pins WHY this helper exists rather than reusing the smaller one.

        If `league_identity` ever starts collapsing tournaments itself, this
        fails and `league_family_identity` should be deleted, not patched.
        """
        assert league_identity("tennis_atp_us_open") != league_identity("tennis_atp")
        assert league_family_identity("tennis_atp_us_open") == (
            league_family_identity("tennis_atp")
        )

    def test_a_catch_all_bucket_is_not_its_sports_league(self):
        """The whole ship, at the helper level."""
        assert league_family_identity("baseball_other") != (
            league_family_identity("baseball_mlb")
        )
        assert league_family_identity("tennis_other") != (
            league_family_identity("tennis_atp")
        )

    def test_a_womens_league_is_not_the_mens(self):
        """`sport_keys` is explicit that a women's competition is its own league.

        A tour-prefix test that fired on `soccer_` or on any shared stem would
        merge them; this is the read-side twin of gotcha #32's absorption.
        """
        assert league_family_identity("soccer_germany_bundesliga_women") != (
            league_family_identity("soccer_germany_bundesliga")
        )
        assert league_family_identity("aussierules_aflw") != (
            league_family_identity("aussierules_afl")
        )

    def test_a_missing_key_is_none_not_a_shared_bucket(self):
        """Callers decide their own fallback; `None` must never equate unknowns.

        The route reads this directly — a helper returning `""` here would make
        every unresolved sport one family and silently disable the guard.
        """
        assert league_family_identity(None) is None
        assert league_family_identity("") is None
