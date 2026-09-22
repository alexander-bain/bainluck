"""A club whose providers spell it differently gets its whole schedule (#7929).

## What a reader saw

Production 2026-09-22 03:15Z, `bainluck.com/sport/hockey/nhl/team/montreal-canadiens`
at 390px, RECENT RESULTS:

    vs Ottawa Senators · Sep 21 · W 3–2

with **no** "we had them at X%". The identical game on `/team/ottawa-senators`
printed "we had them at 42%". Found while paying #7915's LOOK, filed as the
one club that fix could not reach.

## One club, three team rows, and a page that could reach one of them

    568    Montreal Canadiens    icehockey_nhl            espn_id 10
    3706   Montréal Canadiens    icehockey_nhl            espn_id 10
    19692  Montréal Canadiens    icehockey_nhl_preseason  espn_id NULL

`get_team`'s filter matched `home_team_id == 568`, `away_team_id == 568`, or the
exact string "Montreal Canadiens". Every row a provider spelled with the accent
failed all three. Measured on production over 09-01..10-22, the club's own page
was missing FOUR of its eight rows:

    15168032  nhl        Toronto v Montréal   aid=3706   completed  open 0.5108
    15316893  preseason  Montréal v Ottawa    hid=19692  completed  open 0.5830
    15169778  nhl        Pittsburgh v Montréal aid=3706  scheduled  open 0.5000
    15169783  nhl        Montréal v Carolina  hid=3706   scheduled  open 0.4826

The two completed rows are the twins that CARRY the pre-match line — their
visible counterparts (`15311331`, `15312790`) hold none — so #7915's fold had
nothing to carry from. The two scheduled rows have no counterpart at all: the
Canadiens' October 3 and October 6 fixtures were simply absent from the
Canadiens' page.

## Why the key is the fold's squash and NOT `espn_id`

The obvious anchor is poisoned, and the measurement is the reason this file
carries a control for it. Production 2026-09-22: 382 same-sport pairs share one
`espn_id` while disagreeing on name, and they are not all one club —

    espn 12    New York Islanders (54)      /  New Jersey (12716)
    espn 9723  Portland Timbers (21)        /  Portland Timbers 2 (15119)
    espn 183   Columbus Crew SC (22)        /  Columbus Crew 2 (14535)

Keying the club on `espn_id` would put a rival's and a reserve side's games on a
club's page — a truth defect bought with a missing caption. It also could never
have reached this specimen: all 21 NHL preseason team rows (and all 32 NFL ones)
carry no `espn_id` at all.

`team_name_fold_key` is the twin fold's own squash, imported rather than
rewritten. It folds diacritics and punctuation and nothing else, so it reads
`Montréal Canadiens` as 568's club and still reads `Portland Timbers 2` and
`Columbus Crew 2` as separate sides. It is also the key the fold downstream uses
to decide which rows are one fixture, so a row this admits is a row that fold
can collapse — which is what turns two rows into one card with a number on it.

## How this file is built

Real `get_team` against a real engine, the harness its sibling #5491 declares —
mocking the query would test the mock. Every fixture is a production specimen
read by `db-query` on 2026-09-22, ids and probabilities verbatim.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


# DDL shims so `create_all` can build the real schema on SQLite — the pair
# #5491 declares, for the same reason: the row-level predicates have Postgres
# arms, so the portable arm has to run against a real engine.
@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models.models import Base, Event, Sport, Team  # noqa: E402
from app.routes import teams as route  # noqa: E402

#: Production sport-row ids are not needed here, only their keys; these are
#: local and named so a reader can see the family relationships at a glance.
S_NHL = 70001
S_NHL_PRE = 70002
S_MLS = 70003
S_ALLSVENSKAN = 70004
S_SHL = 70005

#: The three rows that spell one club (`db-query`, 2026-09-22).
MTL_URL_ROW = 568
MTL_ACCENTED = 3706
MTL_PRESEASON = 19692

PLAIN = "Montreal Canadiens"
ACCENTED = "Montréal Canadiens"

OTTAWA = 56
OTTAWA_PRE = 19696
CAROLINA = 58
TORONTO = 115

#: The four rows the page could not reach.
ABSENT_UPCOMING = 15169783  # Montréal v Carolina, Oct 6, open 0.4826
ABSENT_COMPLETED = 15316893  # Montréal v Ottawa, the specimen, open 0.5830
#: Their visible counterparts, which hold no opening line of their own.
VISIBLE_COMPLETED = 15312790  # Montreal v Ottawa, open NULL


#: The twin sits this far after its counterpart — the gap the fold tolerates.
TWIN_GAP = timedelta(minutes=15)


def _ago(hours, now=None):
    """`hours` before now, truncated to the hour — offset FIRST, then truncate.

    The specimen pair is one row and its twin :data:`TWIN_GAP` later, and the
    fold buckets candidates by UTC *day* on purpose: `event_twin_fold` says
    two twins either side of midnight are never candidates and fail closed,
    which is two cards. An untruncated anchor therefore straddles midnight
    whenever ``now - 20h`` lands in the last quarter hour of a day, and the
    pair stops folding — red for fifteen minutes a day, green either side of
    it (gotcha #44). Truncating to the hour leaves 45 minutes of headroom in
    front of the boundary, which no offset in this file comes near.
    """
    return ((now or datetime.now(timezone.utc)) - timedelta(hours=hours)).replace(
        minute=0, second=0, microsecond=0
    )


def _soon(hours=72):
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
    opening=(None, None),
    tags=("provenance:unanchored",),
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
        opening_home_probability=opening[0],
        opening_away_probability=opening[1],
        event_tags=list(tags),
    )


def _the_canadiens_rows():
    """The specimen population, verbatim: two twins and one orphan fixture."""
    return [
        # The pair a reader sees ONE card for. Only the accented row carries
        # the line, and only the plain row is reachable today.
        _event(
            VISIBLE_COMPLETED,
            sport_id=S_NHL,
            when=_ago(20),
            home=PLAIN,
            away="Ottawa Senators",
            home_team_id=MTL_URL_ROW,
            away_team_id=OTTAWA,
            status="completed",
            scores=(3, 2),
            espn_id="401881921",
        ),
        _event(
            ABSENT_COMPLETED,
            sport_id=S_NHL_PRE,
            when=_ago(20) + TWIN_GAP,
            home=ACCENTED,
            away="Ottawa Senators",
            home_team_id=MTL_PRESEASON,
            away_team_id=OTTAWA_PRE,
            status="completed",
            scores=(3, 2),
            opening=(0.5830, 0.4170),
            tags=("provenance:source:odds_api", "provenance:unanchored"),
        ),
        # An upcoming fixture with NO plain-spelled counterpart at all.
        _event(
            ABSENT_UPCOMING,
            sport_id=S_NHL,
            when=_soon(),
            home=ACCENTED,
            away="Carolina Hurricanes",
            home_team_id=MTL_ACCENTED,
            away_team_id=CAROLINA,
            espn_id="401891815",
            opening=(0.4826, 0.5174),
            tags=("league:nhl", "level:professional"),
        ),
    ]


def _engine(*events, sports=(), teams=()):
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        for sport_id, key in sports:
            s.add(Sport(id=sport_id, key=key, name=key))
        for team in teams:
            s.add(team)
        for e in events:
            s.add(e)
        s.commit()
    return eng


def _the_nhl_world(*extra_events, extra_teams=()):
    """The three Montréal rows, their opponents, and the two NHL sport rows."""
    return _engine(
        *_the_canadiens_rows(),
        *extra_events,
        sports=[(S_NHL, "icehockey_nhl"), (S_NHL_PRE, "icehockey_nhl_preseason")],
        teams=[
            Team(
                id=MTL_URL_ROW,
                sport_id=S_NHL,
                name=PLAIN,
                slug="montreal-canadiens",
                espn_id="10",
            ),
            Team(
                id=MTL_ACCENTED,
                sport_id=S_NHL,
                name=ACCENTED,
                slug="montral-canadiens",
                espn_id="10",
            ),
            Team(
                id=MTL_PRESEASON,
                sport_id=S_NHL_PRE,
                name=ACCENTED,
                slug="montral-canadiens-nhl-preseason",
            ),
            Team(id=OTTAWA, sport_id=S_NHL, name="Ottawa Senators", slug="ottawa"),
            Team(
                id=OTTAWA_PRE,
                sport_id=S_NHL_PRE,
                name="Ottawa Senators",
                slug="ottawa-pre",
            ),
            Team(id=CAROLINA, sport_id=S_NHL, name="Carolina Hurricanes", slug="canes"),
            Team(id=TORONTO, sport_id=S_NHL, name="Toronto Maple Leafs", slug="leafs"),
            *extra_teams,
        ],
    )


def _page(eng, slug="montreal-canadiens"):
    """`get_team` for real — its real `select()`s, its real predicates."""
    with Session(eng) as s:

        class _Session:
            async def execute(self, statement):
                return s.execute(statement)

        return asyncio.run(route.get_team(slug, db=_Session()))


def _cards(page):
    return page["upcoming_events"] + page["recent_events"]


def _ids(page):
    return [c["id"] for c in _cards(page)]


# --------------------------------------------------------------------------
# The ship
# --------------------------------------------------------------------------


class TestTheCanadiensPage:
    def test_the_fixture_only_the_accented_row_knows_about_is_on_the_page(self):
        """🔴 THE SHIP, upcoming half. October 6 vs Carolina was simply absent.

        `15169783` is bound to team row 3706 and spelled with the accent, so
        neither id arm nor the exact-string arm could see it, and no
        plain-spelled row exists for that fixture to rescue it. The reader's
        version of this: the Canadiens' page did not list the Canadiens' game.
        """
        page = _page(_the_nhl_world())
        assert ABSENT_UPCOMING in _ids(page), (
            "the club's own upcoming fixture is missing from its own page — the "
            "filter is reading the URL's team row instead of the club"
        )

    def test_the_card_carries_the_number_the_opponents_page_prints(self):
        """🔴 THE SHIP, recent half — and the arm that names a NUMBER.

        The pair folds to ONE card. Phrased as "the card carries a caption"
        this arm would pass on the very regression it exists to catch: the
        survivor `15312790` holds NO opening line of its own, so 58% is on
        screen only because the fold carried it off `15316893`, the row this
        repair admits. One card, and it reads "we had them at 58%".
        """
        page = _page(_the_nhl_world())
        ottawa = [c for c in _cards(page) if c["opponent"] == "Ottawa Senators"]
        assert len(ottawa) == 1, (
            f"one fixture, one card — got {len(ottawa)}: {[c['id'] for c in ottawa]}"
        )
        assert ottawa[0]["pregame_win_probability"] == 0.5830, (
            "the pre-match number the Senators' page prints is still missing "
            f"from the Canadiens' page: {ottawa[0]['pregame_win_probability']}"
        )

    def test_the_side_is_read_against_the_club_not_the_urls_row(self):
        """A widening that repairs a missing card by mislabelling it is not one.

        `15169783` is a HOME game: `home_team_id` 3706, `home_team_name` the
        accented spelling. Ask `home_team_id == 568` and the card inverts, and
        the page tells a reader the Canadiens are away at Carolina.
        """
        page = _page(_the_nhl_world())
        card = next(c for c in _cards(page) if c["id"] == ABSENT_UPCOMING)
        assert card["is_home"] is True, "a home fixture is being printed as away"
        assert card["opponent"] == "Carolina Hurricanes"


# --------------------------------------------------------------------------
# The controls — each one convicts a DIFFERENT wrong way to write this
# --------------------------------------------------------------------------


class TestTheControls:
    def test_a_reserve_side_sharing_an_espn_id_is_not_this_club(self):
        """🔴 THE ANTI-ANCHOR CONTROL. Reds if anyone keys the club on `espn_id`.

        `Portland Timbers` (21) and `Portland Timbers 2` (15119) both carry
        espn_id 9723 on production, and `New York Islanders` and `New Jersey`
        both carry 12. The fold's squash reads `portlandtimbers2` and refuses;
        an id would not have.
        """
        eng = _engine(
            _event(
                90001,
                sport_id=S_MLS,
                when=_soon(),
                home="Portland Timbers 2",
                away="Tacoma Defiance",
                home_team_id=15119,
                away_team_id=15121,
            ),
            _event(
                90002,
                sport_id=S_MLS,
                when=_soon(),
                home="Portland Timbers",
                away="Seattle Sounders FC",
                home_team_id=21,
                away_team_id=2327,
            ),
            sports=[(S_MLS, "soccer_usa_mls")],
            teams=[
                Team(
                    id=21,
                    sport_id=S_MLS,
                    name="Portland Timbers",
                    slug="portland-timbers",
                    espn_id="9723",
                ),
                Team(
                    id=15119,
                    sport_id=S_MLS,
                    name="Portland Timbers 2",
                    slug="portland-timbers-2",
                    espn_id="9723",
                ),
                Team(id=15121, sport_id=S_MLS, name="Tacoma Defiance", slug="tacoma"),
                Team(
                    id=2327,
                    sport_id=S_MLS,
                    name="Seattle Sounders FC",
                    slug="sounders",
                ),
            ],
        )
        ids = _ids(_page(eng, slug="portland-timbers"))
        assert 90002 in ids, "the club lost its own fixture"
        assert 90001 not in ids, (
            "the reserve side's game reached the first team's page — the club "
            "is being resolved by a shared id instead of by its name's fold"
        )

    def test_a_namesake_in_another_sport_is_not_this_club(self):
        """The league-family scope #5491 established still binds.

        `Djurgardens IF` (soccer_sweden_allsvenskan, 2250) and
        `Djurgårdens IF` (icehockey_sweden_hockey_league, 1399) fold alike and
        are one institution playing two sports — never one schedule.
        """
        eng = _engine(
            _event(
                90003,
                sport_id=S_SHL,
                when=_soon(),
                home="Djurgårdens IF",
                away="Frölunda HC",
                home_team_id=1399,
                away_team_id=1400,
            ),
            _event(
                90004,
                sport_id=S_ALLSVENSKAN,
                when=_soon(),
                home="Djurgardens IF",
                away="AIK",
                home_team_id=2250,
                away_team_id=2251,
            ),
            sports=[
                (S_ALLSVENSKAN, "soccer_sweden_allsvenskan"),
                (S_SHL, "icehockey_sweden_hockey_league"),
            ],
            teams=[
                Team(
                    id=2250,
                    sport_id=S_ALLSVENSKAN,
                    name="Djurgardens IF",
                    slug="djurgardens-if",
                ),
                Team(
                    id=1399,
                    sport_id=S_SHL,
                    name="Djurgårdens IF",
                    slug="djurgardens-if-shl",
                ),
                Team(id=1400, sport_id=S_SHL, name="Frölunda HC", slug="frolunda"),
                Team(id=2251, sport_id=S_ALLSVENSKAN, name="AIK", slug="aik"),
            ],
        )
        ids = _ids(_page(eng, slug="djurgardens-if"))
        assert 90004 in ids
        assert 90003 not in ids, (
            "the ice-hockey namesake's game reached the football club's page"
        )

    def test_the_club_is_its_own_row_when_the_identity_lookup_fails(self):
        """Degrades to TODAY'S answer, never to a 500.

        These rails are the core of a Priority-#3 page (#1197 / #1239). If the
        club lookup raises, the reader gets the page they had before this
        repair — the plain-spelled row's schedule — and not an error.
        """
        import app.routes.teams as mod

        original = mod.team_name_fold_key
        mod.team_name_fold_key = lambda _name: (_ for _ in ()).throw(
            RuntimeError("fold key exploded")
        )
        try:
            page = _page(_the_nhl_world())
        finally:
            mod.team_name_fold_key = original

        ids = _ids(page)
        assert VISIBLE_COMPLETED in ids, "the page lost the rail it served before"
        assert ABSENT_UPCOMING not in ids, (
            "the fixture only the widening reaches is present, so this arm did "
            "not actually sever the widening and proves nothing"
        )


# --------------------------------------------------------------------------
# The anchor itself (gotcha #44)
# --------------------------------------------------------------------------


class TestTheAnchorsDoNotBranchOnTheClock:
    """The specimen pair must be ONE fold candidate at every minute of the day.

    This file went red in CI for the quarter hour when ``now - 20h`` landed in
    23:45–00:00 UTC: the twin is :data:`TWIN_GAP` later, so the pair sat either
    side of midnight, `event_twin_fold` refused them as candidates *by design*
    (it fails closed across the day boundary), and
    ``test_the_card_carries_the_number_the_opponents_page_prints`` counted two
    cards. Green at every other minute, so a re-run "fixed" it.

    A guard that runs at the real clock could only reproduce that for fifteen
    minutes a day, so this one drives the real helper with an injected instant
    and walks a whole day a minute at a time.
    """

    def test_the_pair_shares_a_utc_day_at_every_minute_of_a_day(self):
        offenders = []
        midnight = datetime(2026, 9, 22, tzinfo=timezone.utc)
        for minute in range(24 * 60):
            now = midnight + timedelta(minutes=minute)
            anchor = _ago(20, now=now)
            if anchor.date() != (anchor + TWIN_GAP).date():
                offenders.append(now.strftime("%H:%M"))

        assert not offenders, (
            "the twin pair straddles midnight UTC at "
            f"{len(offenders)} minute(s) of the day — {offenders[:5]} … — so the "
            "fold sees two candidates and the card count arm is red at exactly "
            "those clocks"
        )

    def test_the_guard_would_convict_the_anchor_it_was_written_for(self):
        """The rot pin: without the truncation this walk MUST find offenders.

        A day-walk that passes against the untruncated anchor too would be
        proving nothing about the repair.
        """
        offenders = []
        midnight = datetime(2026, 9, 22, tzinfo=timezone.utc)
        for minute in range(24 * 60):
            now = midnight + timedelta(minutes=minute)
            untruncated = now - timedelta(hours=20)
            if untruncated.date() != (untruncated + TWIN_GAP).date():
                offenders.append(now.strftime("%H:%M"))

        assert len(offenders) == 15, (
            "the pre-repair anchor is supposed to straddle midnight for the 15 "
            f"minutes when now-20h is 23:45–00:00; this walk found {offenders}"
        )
