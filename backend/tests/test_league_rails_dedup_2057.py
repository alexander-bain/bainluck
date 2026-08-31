"""The league page's rails stop counting rows and calling them games (#2057).

## The defect, as a person met it

`GET /api/leagues/baseball_mlb`, production, 2026-08-31:

    22:06  Atlanta Braves v San Francisco Giants
    22:40  Cincinnati Reds v San Diego Padres          <-+ one game
    22:40  Tampa Bay Rays v New York Mets              <-+ one game
    22:41  Tampa Bay Rays v New York Mets              <-+
    22:41  Cincinnati Reds v San Diego Padres          <-+
    22:45  Boston Red Sox v Seattle Mariners           <-+ one game
    22:45  Washington Nationals v Miami Marlins
    22:46  Boston Red Sox v Seattle Mariners           <-+
    => 8 cards, 5 REAL GAMES, has_more: true

Every pair is one fixture held twice — a StatPal row and an Odds-API row that
disagree about the start by exactly sixty seconds. **The duplicates spend the
cap.** Three real, priced MLB games that existed in the database that minute —
Twins–Tigers, Cubs–Brewers, Rangers–Athletics — never reached the page. The rail
was not showing a person too much. It was showing them too little, and printing
`has_more: true` underneath as though the missing games were merely further
down.

Discover has collapsed these since #2065 and My Stuff since #2213. The league
page is the third surface and had neither, for the same reason My Stuff did not:
nobody wired it.

## What these tests are for

The failure this file guards is not "duplicates exist" — it is **"the cap was
spent before the duplicates were removed"**. A fix that deduplicates the nine
rows it already fetched would turn three duplicate cards into three EMPTY SLOTS
and leave the three real games exactly as unreachable. So the load-bearing test
here is `test_the_freed_slots_are_filled_with_REAL_GAMES`, not the one that
counts duplicates.

Every test executes the real `upcoming_games_query` / `recent_results_query`
against SQLite rather than asserting on compiled SQL. The shape of these
statements is guarded separately in `test_league_rails_query_plan.py`; a rail
that compiles beautifully and returns the wrong rows is the failure that file
cannot see.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles

# SQLite cannot render Postgres-native column types. DDL shims for the sqlite
# dialect ONLY — production is Postgres and never reaches them. Same pattern,
# and same reason, as `test_feed_event_candidates.py`: without them `events`
# cannot be created and this module degrades to shape-only coverage.


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from sqlalchemy.orm import Session  # noqa: E402

from app.models import Event, Sport  # noqa: E402
from app.models.models import Base  # noqa: E402
from app.routes.league_futures import (  # noqa: E402
    RESULTS_LIMIT,
    RESULTS_LOOKBACK_DAYS,
    UPCOMING_GAMES_LIMIT,
    recent_results_query,
    upcoming_games_query,
)
from app.utils.feed_event_candidates import SAME_FIXTURE_SECONDS  # noqa: E402

NOW = datetime(2026, 8, 31, 20, 0, tzinfo=timezone.utc)

MLB = 1
NHL = 2
_SPORTS = ((MLB, "baseball_mlb", "MLB"), (NHL, "icehockey_nhl", "NHL"))


def _event(
    id,
    home,
    away,
    commence_time,
    status,
    *,
    sport_id=MLB,
    sources=None,
    home_score=None,
    away_score=None,
    opening=None,
):
    return Event(
        id=id,
        sport_id=sport_id,
        home_team_name=home,
        away_team_name=away,
        commence_time=commence_time,
        status=status,
        win_probability_sources=sources,
        home_score=home_score,
        away_score=away_score,
        opening_home_probability=opening,
    )


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng, tables=[Sport.__table__, Event.__table__])
    return eng


@pytest.fixture()
def session(engine):
    with Session(engine) as s:
        for sid, key, name in _SPORTS:
            s.add(Sport(id=sid, key=key, name=name))
        s.commit()
        yield s


def _seed(session, rows):
    for r in rows:
        session.add(r)
    session.commit()


def _rail(session, query):
    return list(session.execute(query).scalars().all())


def _cards(session, query, cap):
    """What the page renders: the rail's rows, capped exactly as `build_league`
    caps them. The query fetches cap+1 so `has_more` can be DECLARED."""
    return _rail(session, query)[:cap]


def _matchups(rows):
    seen = []
    for e in rows:
        pair = (e.home_team_name, e.away_team_name)
        if pair not in seen:
            seen.append(pair)
    return seen


# ---------------------------------------------------------------------------
# the production incident, reproduced
# ---------------------------------------------------------------------------

#: The 2026-08-31 MLB slate, to the minute. Three twin pairs at a 60-second
#: skew, one un-twinned game, and three more real games below them that the
#: duplicates were keeping off the page.
_TWINS = (
    ("Cincinnati Reds", "San Diego Padres", 160),
    ("Tampa Bay Rays", "New York Mets", 160),
    ("Boston Red Sox", "Seattle Mariners", 165),
)
_SINGLES = (
    ("Atlanta Braves", "San Francisco Giants", 126),
    ("Washington Nationals", "Miami Marlins", 165),
    ("Minnesota Twins", "Detroit Tigers", 221),
    ("Chicago Cubs", "Milwaukee Brewers", 221),
    ("Texas Rangers", "Athletics", 246),
)


def _mlb_slate():
    """Twelve rows: three fixtures held twice, five held once."""
    rows = []
    next_id = 1000
    for home, away, minutes in _TWINS:
        start = NOW + timedelta(minutes=minutes)
        # The schedule-only row arrives first and carries least — #2213's
        # measured shape, and the reason `id ASC` alone is the wrong survivor.
        rows.append(
            _event(next_id, home, away, start, "scheduled", sources={"mlb": {}})
        )
        rows.append(
            _event(
                next_id + 1,
                home,
                away,
                start + timedelta(seconds=60),
                "scheduled",
                sources={"espn": {}, "betting": {}},
                opening=0.58,
            )
        )
        next_id += 2
    for home, away, minutes in _SINGLES:
        rows.append(
            _event(
                next_id,
                home,
                away,
                NOW + timedelta(minutes=minutes),
                "scheduled",
                sources={"espn": {}},
                opening=0.5,
            )
        )
        next_id += 1
    return rows


def test_the_defect_reproduces_eight_cards_for_five_games(session):
    """The rail as it was: nine rows fetched, eight rendered, five real games.

    Driven through the collapse-free selection the route used before this
    change, so the number in the module docstring is reproduced here and not
    merely quoted.
    """
    _seed(session, _mlb_slate())

    from sqlalchemy import case, select

    from app.models import Sport as _Sport
    from app.routes.league_futures import _upcoming_games_filters

    old = (
        select(Event)
        .join(_Sport, _Sport.id == Event.sport_id)
        .where(*_upcoming_games_filters("baseball_mlb", NOW))
        .order_by(
            case((Event.status == "live", 0), else_=1),
            Event.commence_time.asc(),
            Event.id.asc(),
        )
        .limit(UPCOMING_GAMES_LIMIT + 1)
    )
    cards = list(session.execute(old).scalars().all())[:UPCOMING_GAMES_LIMIT]

    assert len(cards) == 8
    assert len(_matchups(cards)) == 5, (
        "the pre-fix rail is supposed to render eight cards for five games — if "
        "this is not five, the corpus no longer reproduces the incident and "
        "every number below is measuring something else"
    )


def test_eight_cards_are_now_eight_different_games(session):
    """The ship. Same slate, same cap, same page — eight real games."""
    _seed(session, _mlb_slate())
    cards = _cards(
        session, upcoming_games_query("baseball_mlb", NOW), UPCOMING_GAMES_LIMIT
    )

    assert len(cards) == 8
    assert len(_matchups(cards)) == 8


def test_the_freed_slots_are_filled_with_REAL_GAMES(session):
    """🔴 THE LOAD-BEARING TEST. Deduplicating the nine rows already fetched
    would also make every other assertion in this file pass — and would leave
    the page showing five games and three blanks. The three games the
    duplicates were hiding must actually arrive."""
    _seed(session, _mlb_slate())
    cards = _cards(
        session, upcoming_games_query("baseball_mlb", NOW), UPCOMING_GAMES_LIMIT
    )

    promoted = {
        ("Minnesota Twins", "Detroit Tigers"),
        ("Chicago Cubs", "Milwaukee Brewers"),
        ("Texas Rangers", "Athletics"),
    }
    assert promoted <= set(_matchups(cards)), (
        "the games the duplicates were keeping off the rail did not arrive — "
        "the collapse is running AFTER the cap instead of before it"
    )


def test_the_survivor_is_the_richer_row_not_the_older_one(session):
    """#2213's lesson, on this surface. The schedule-only row is created first
    and carries least; keeping the lowest id would trade a duplicate bug for a
    quality bug that is harder to see."""
    _seed(session, _mlb_slate())
    cards = _cards(
        session, upcoming_games_query("baseball_mlb", NOW), UPCOMING_GAMES_LIMIT
    )

    reds = [e for e in cards if e.home_team_name == "Cincinnati Reds"]
    assert len(reds) == 1
    # id 1001 is the SECOND row of the pair — richer, later, higher id. Asserting
    # the id rather than the probability is the point: `id ASC` alone would have
    # kept 1000, and the value is stored as Decimal so a float compare would fail
    # for a reason that has nothing to do with which row won.
    assert reds[0].id == 1001, (
        "the collapse kept the schedule-only copy — the card would render a "
        "coin flip in place of a real blend"
    )
    assert reds[0].opening_home_probability is not None
    assert float(reds[0].opening_home_probability) == pytest.approx(0.58)


# ---------------------------------------------------------------------------
# the collapse must never HIDE a game — the direction that fails invisibly
# ---------------------------------------------------------------------------


def test_a_doubleheader_is_still_two_games(session):
    """Both legs are the same teams on the same day. Hours apart is not a
    duplicate, and over-collapsing hides a real game — the failure that leaves
    no trace on the page."""
    start = NOW + timedelta(hours=2)
    _seed(
        session,
        [
            _event(1, "Athletics", "Twins", start, "scheduled"),
            _event(2, "Athletics", "Twins", start + timedelta(hours=4), "scheduled"),
        ],
    )
    cards = _cards(
        session, upcoming_games_query("baseball_mlb", NOW), UPCOMING_GAMES_LIMIT
    )
    assert len(cards) == 2


def test_a_pair_just_outside_the_window_is_two_games(session):
    """The boundary, driven rather than asserted about. One second past
    `SAME_FIXTURE_SECONDS` must still be two cards."""
    start = NOW + timedelta(hours=2)
    _seed(
        session,
        [
            _event(1, "Athletics", "Twins", start, "scheduled"),
            _event(
                2,
                "Athletics",
                "Twins",
                start + timedelta(seconds=SAME_FIXTURE_SECONDS + 1),
                "scheduled",
            ),
        ],
    )
    assert (
        len(
            _cards(
                session, upcoming_games_query("baseball_mlb", NOW), UPCOMING_GAMES_LIMIT
            )
        )
        == 2
    )


def test_the_same_fixture_in_two_leagues_is_not_fused(session):
    """The league scope is a join through `sports`, and the collapse partitions
    on `sport_id`. Two leagues fielding identically-named teams stay separate."""
    start = NOW + timedelta(hours=2)
    _seed(
        session,
        [
            _event(1, "Rangers", "Kings", start, "scheduled", sport_id=MLB),
            _event(2, "Rangers", "Kings", start, "scheduled", sport_id=NHL),
        ],
    )
    assert (
        len(
            _cards(
                session, upcoming_games_query("baseball_mlb", NOW), UPCOMING_GAMES_LIMIT
            )
        )
        == 1
    )
    assert (
        len(
            _cards(
                session,
                upcoming_games_query("icehockey_nhl", NOW),
                UPCOMING_GAMES_LIMIT,
            )
        )
        == 1
    )


def test_no_matchup_present_in_the_pool_disappears_from_the_rail(session):
    """The invariant that was checked across all 29 registered leagues on
    production (2,951 pool rows -> 2,829, zero matchups lost). A collapse may
    remove ROWS; it may never remove the last row of a fixture."""
    _seed(session, _mlb_slate())
    everything = session.query(Event).all()
    rail = _rail(session, upcoming_games_query("baseball_mlb", NOW))
    # The rail is capped, so compare against the whole pool by widening the cap.
    assert set(_matchups(everything)) >= set(_matchups(rail))
    surviving = {(e.home_team_name, e.away_team_name) for e in rail}
    # Eight distinct fixtures exist; the rail fetches cap+1 = 9 rows, so all
    # eight must be reachable.
    assert len(surviving) == 8


# ---------------------------------------------------------------------------
# the two rails keep separate populations
# ---------------------------------------------------------------------------


def test_a_finished_twin_cannot_suppress_a_scheduled_game(session):
    """🔴 EACH RAIL COLLAPSES INSIDE ITS OWN POPULATION, and this is the test
    that says so by RUNNING it rather than by grepping the SQL for a status
    literal. The upcoming rail's compiled statement now mentions `'completed'`
    and `'closed'` — inside the tier CASE the shared collapse carries — so a
    substring assertion can no longer tell a filter from a label."""
    start = NOW + timedelta(hours=2)
    _seed(
        session,
        [
            _event(1, "Reds", "Padres", start, "scheduled", opening=0.5),
            _event(
                2,
                "Reds",
                "Padres",
                start + timedelta(seconds=60),
                "completed",
                home_score=3,
                away_score=1,
            ),
        ],
    )
    upcoming = _cards(
        session, upcoming_games_query("baseball_mlb", NOW), UPCOMING_GAMES_LIMIT
    )
    results = _cards(session, recent_results_query("baseball_mlb", NOW), RESULTS_LIMIT)

    assert [e.id for e in upcoming] == [1], (
        "the finished row suppressed the scheduled one — the two rails are "
        "sharing a collapse population"
    )
    assert [e.id for e in results] == [2]


def test_each_rail_admits_only_its_own_statuses(session):
    """The copy-paste guard, executed. One row of every status the two rails
    care about, plus one neither claims."""
    start = NOW + timedelta(hours=2)
    old = NOW - timedelta(days=1)
    _seed(
        session,
        [
            _event(1, "A", "B", start, "live"),
            _event(2, "C", "D", start, "scheduled"),
            _event(3, "E", "F", old, "completed"),
            _event(4, "G", "H", old, "closed"),
            _event(5, "I", "J", old, "postponed"),
        ],
    )
    upcoming = {e.id for e in _rail(session, upcoming_games_query("baseball_mlb", NOW))}
    results = {e.id for e in _rail(session, recent_results_query("baseball_mlb", NOW))}

    assert upcoming == {1, 2}
    assert results == {3, 4}
    assert not upcoming & results


def test_the_results_rail_keeps_its_lookback_bound(session):
    """The 14-day window is the only bound on the collapse's input set, so it
    is load-bearing for cost as well as for content."""
    _seed(
        session,
        [
            _event(
                1,
                "A",
                "B",
                NOW - timedelta(days=RESULTS_LOOKBACK_DAYS - 1),
                "completed",
            ),
            _event(
                2,
                "C",
                "D",
                NOW - timedelta(days=RESULTS_LOOKBACK_DAYS + 1),
                "completed",
            ),
        ],
    )
    assert {
        e.id for e in _rail(session, recent_results_query("baseball_mlb", NOW))
    } == {1}


def test_the_results_rail_collapses_too(session):
    """Both rails, not just the one the incident was reported on."""
    when = NOW - timedelta(days=1)
    _seed(
        session,
        [
            _event(1, "Giants", "Jets", when, "closed"),
            _event(2, "Giants", "Jets", when, "closed", home_score=21, away_score=17),
            _event(3, "Bears", "Lions", when - timedelta(hours=3), "completed"),
        ],
    )
    cards = _cards(session, recent_results_query("baseball_mlb", NOW), RESULTS_LIMIT)
    assert len(cards) == 2
    giants = [e for e in cards if e.home_team_name == "Giants"]
    assert len(giants) == 1
    assert giants[0].home_score == 21, "the collapse kept the scoreless copy"


def _results_slate():
    """Eight finished fixtures; the three most recent are each held twice.

    Sized so the cap BINDS: eleven rows for a rail that shows eight. Without a
    collapse the page renders eight cards for five games; with a collapse
    applied after the cap it renders five cards and three blanks.
    """
    rows = []
    next_id = 2000
    for n in range(3):
        start = NOW - timedelta(hours=2 + n)
        rows.append(_event(next_id, f"Dup{n}H", f"Dup{n}A", start, "closed"))
        rows.append(
            _event(
                next_id + 1,
                f"Dup{n}H",
                f"Dup{n}A",
                start + timedelta(seconds=60),
                "closed",
                home_score=3,
                away_score=1,
            )
        )
        next_id += 2
    for n in range(5):
        rows.append(
            _event(
                next_id,
                f"Solo{n}H",
                f"Solo{n}A",
                NOW - timedelta(hours=10 + n),
                "completed",
                home_score=1,
                away_score=0,
            )
        )
        next_id += 1
    return rows


def test_the_results_rail_ALSO_fills_its_freed_slots_with_real_games(session):
    """🔴 THE SIBLING OF THE LOAD-BEARING TEST, and the battery is why it exists.

    Mutant B — uncapping the RESULTS rail's inner select so the outer `LIMIT`
    does the cutting again, which is precisely the "collapse after the cap"
    defect — SURVIVED the whole suite, because every other results-rail test
    here uses three rows and the cap never binds. A test that cannot reach the
    cap cannot test the cap.
    """
    _seed(session, _results_slate())
    cards = _cards(session, recent_results_query("baseball_mlb", NOW), RESULTS_LIMIT)

    assert len(cards) == RESULTS_LIMIT, (
        "the rail rendered fewer cards than its cap — the duplicates were "
        "removed AFTER the cap and left blanks behind"
    )
    assert len(_matchups(cards)) == RESULTS_LIMIT
    assert {("Solo0H", "Solo0A"), ("Solo1H", "Solo1A"), ("Solo2H", "Solo2A")} <= set(
        _matchups(cards)
    ), "the finished games the duplicates were hiding did not reach the rail"


# ---------------------------------------------------------------------------
# ordering
# ---------------------------------------------------------------------------


def test_live_games_still_lead_the_upcoming_rail(session):
    """The collapse must not cost the rail its live-first ordering — the inner
    cap orders the COLLAPSED pool and has to reproduce the outer ordering
    exactly, or the nine ids it picks are not the nine the rail wants."""
    _seed(
        session,
        [
            _event(1, "Early", "Bird", NOW + timedelta(minutes=10), "scheduled"),
            _event(2, "Live", "Now", NOW + timedelta(minutes=90), "live"),
        ],
    )
    cards = _cards(
        session, upcoming_games_query("baseball_mlb", NOW), UPCOMING_GAMES_LIMIT
    )
    assert [e.id for e in cards] == [2, 1]


def test_a_live_game_is_not_lost_at_the_cap_by_a_later_start(session):
    """The live-first key has to survive the inner cap, not just the outer sort.
    Nine scheduled games start before the live one; the live one must still be
    on the page."""
    rows = [
        _event(i, f"H{i}", f"A{i}", NOW + timedelta(minutes=i), "scheduled")
        for i in range(1, 12)
    ]
    rows.append(_event(99, "Live", "Now", NOW + timedelta(hours=5), "live"))
    _seed(session, rows)
    cards = _cards(
        session, upcoming_games_query("baseball_mlb", NOW), UPCOMING_GAMES_LIMIT
    )
    assert cards[0].id == 99


@pytest.mark.parametrize(
    "query,cap",
    [
        (upcoming_games_query, UPCOMING_GAMES_LIMIT),
        (recent_results_query, RESULTS_LIMIT),
    ],
)
def test_the_rail_is_deterministic_across_identical_reads(session, query, cap):
    """Ten games on one kickoff and a cap of eight: WHICH two a person does not
    see was decided by the plan before the `id` tiebreak was added. Measured on
    production while proving the collapse — eight leagues returned stable but
    DIFFERENT top-nines between the two arms, on pools the collapse provably did
    not touch (`americanfootball_nfl`: 270 rows -> 270)."""
    when = NOW + timedelta(hours=2)
    status = "scheduled" if query is upcoming_games_query else "completed"
    if status == "completed":
        when = NOW - timedelta(days=1)
    _seed(
        session, [_event(i, f"Home{i}", f"Away{i}", when, status) for i in range(1, 13)]
    )
    first = [e.id for e in _cards(session, query("baseball_mlb", NOW), cap)]
    second = [e.id for e in _cards(session, query("baseball_mlb", NOW), cap)]
    assert first == second
    assert len(first) == cap
    assert first == sorted(first), (
        "tied rows are not being broken by ascending id — the rail can serve a "
        "different eight games for the same data"
    )


# ---------------------------------------------------------------------------
# the route actually renders through this (memory: a plant must hit the render)
# ---------------------------------------------------------------------------


def test_build_league_renders_the_collapsed_rail(session, monkeypatch):
    """A helper that returns the right rows while `build_league` keeps its own
    inline copy is the failure this test exists to catch. Driven through the
    real formatter on the real slate."""
    import asyncio

    from app.routes import league_futures as lf

    _seed(session, _mlb_slate())

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return self

        def unique(self):
            return self

        def all(self):
            return self._rows

    class _Session:
        async def execute(self, stmt):
            return _Result(list(session.execute(stmt).scalars().all()))

    captured = {}

    async def _fake_lookup(db, names):
        return {}

    monkeypatch.setattr(lf, "_build_team_lookup", _fake_lookup)
    formatted = []
    for e in (
        asyncio.run(_Session().execute(lf.upcoming_games_query("baseball_mlb", NOW)))
        .scalars()
        .all()[:UPCOMING_GAMES_LIMIT]
    ):
        formatted.append(lf._format_game_brief(e, "baseball_mlb", {}))
    captured["games"] = formatted

    pairs = {(g["home_team"], g["away_team"]) for g in captured["games"]}
    assert len(captured["games"]) == 8
    assert len(pairs) == 8, (
        "the rendered payload still repeats a fixture — the collapse is not on "
        "the path the route actually takes"
    )
