"""T2-2 (#5059): the dropdown offers a team's NEXT game, against real Postgres.

`tests/test_typeahead_reaches_the_next_fixture_5059.py` compiles the or-NEXT arm
and asserts its clauses. What a compiled query cannot prove is that the clause
changes the ANSWER — and on this endpoint that gap is not theoretical. CERT-439's
file records the same lesson one surface over: a source assertion and a SQLite
predicate test were both green while `/search` was still returning the twin,
because neither drove the route.

So this file drives the route.

## what was broken, measured on production 2026-09-11 before any code moved

`/typeahead`'s upcoming pool is bounded at `now + 7 days`. Alex's rule for row 2
is "the live game, else the NEXT, else the last finished", and that bound deleted
the middle term for whole leagues at once:

    league   teams   next fixture <= 7d   next fixture > 7d   soonest
    NHL         32                    0                  32   8.6 days
    NBA         27                    0                  27   39.4 days
    NFL         32                   28                   4   2.3 days
    MLB         30                   30                    0   0.4 days
    EPL         18                   18                    0   1.2 days

59 teams — every NBA and NHL side — offered a reader no game whatsoever, and
#4411's or-LAST arm filled the slots with finished ones. Across all sports, 366
of the 1,560 teams with a future fixture were in that state. `routes/events.py`
already carried the specimen in a comment before this ship existed: "`pats` by
the or-LAST arm ONLY. The Patriots' next game is 2026-09-20".

## why real Postgres and not the mocked integration client

`tests/integration/conftest.py` hands every route a mock session that returns
empty lists, so a recall arm's WHERE clause never touches data. That is fine for
contract shape and useless here: the whole claim is about which rows a predicate
selects. `_next_match_query` also rides the same `ts_rank_cd`/`pg_trgm` recall
filter as its siblings, which runs nowhere but PostgreSQL. There is no local
Postgres in the agent sandbox (`initdb` dies on `shmget`), so CI's `search-recall`
service container is the environment that grades this — and the job step for this
file was added in the same commit, because a PG test file nobody names in the
workflow is a test that silently never runs.

## the controls, and why the ship is not provable without them

The arm is deliberately GATED and BOUNDED, so "the next game appears" is only a
third of the claim. Three seeds carry the other two thirds:

  * the Chiefs play in two days AND in sixty. The gate must keep the sixty-day
    fixture out — otherwise the arm has widened the candidate set for queries
    that were already working, which is precisely the cheaper fix it was chosen
    over.
  * the Dolphins' only fixture is two hundred days out. The ceiling must keep it
    out, and the or-LAST arm must still answer (gotcha #41 wants both ends).
  * the Patriots' finished game must DISAPPEAR when their next one appears. That
    is the lifecycle trace the issue asks for, and it is the short-circuit's
    only observable effect.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [pytest.mark.asyncio]

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres or-NEXT typeahead "
        "contract (CI job `search-recall` provides one)"
    ),
)

#: The production specimen from #5059. The Patriots played on the Thursday and
#: next play ten days later — which is every Thursday-game NFL club, for three
#: days of every week, not a one-off.
SUBJECT = "New England Patriots"
SUBJECT_NEXT_OPPONENT = "Cleveland Browns"
SUBJECT_LAST_OPPONENT = "Seattle Seahawks"

#: The gate control. A team the upcoming pool already answers, carrying a second
#: fixture inside the or-NEXT arm's reach so the gate has something to refuse.
CONTROL = "Kansas City Chiefs"

#: The ceiling control. Its only fixture is past the horizon.
CEILING = "Miami Dolphins"

#: #5201, the namesake family. `bruins` resolves BOSTON into slot 0 — NHL is a
#: prominent sport key and the pool is ordered on prominence — while the only
#: fixture in the seven-day pool belongs to UCLA. The or-NEXT arm above cannot
#: reach Boston's game: its gate asks whether any pooled row NAMES the query, and
#: `query_names_participant('bruins', [..., 'UCLA Bruins'])` is True.
#:
#: 🔴 Boston's fixture is named "Bruins", not "Boston Bruins", ON PURPOSE. It is
#: reachable ONLY by `away_team_id`, so this family proves the id arm rather than
#: the name arm that shadows it in every naive seed. Production carries the same
#: split: 1,378 of the 1,722 future fixtures inside the horizon have a team id,
#: and the four whose display name disagrees with the team's own name are exactly
#: the rows a name-only version loses.
NAMESAKE_SUBJECT = "Boston Bruins"
NAMESAKE_DECOY = "UCLA Bruins"

#: #5201, the second half: the same shape reachable ONLY by exact name. 344
#: future fixtures inside the horizon carry no `home_team_id` at all (143 of them
#: in `soccer_other` alone) and 81 of those name a real team row exactly. Chicago
#: is one of them here — no ids on the row, so the name arm is the only path.
NAME_ONLY_SUBJECT = "Chicago Bears"
NAME_ONLY_DECOY = "Hershey Bears"


async def _seed(session):
    """Four sports, eight teams, twelve events; ids assigned by the server."""
    from app.models.models import Event, Sport, Team

    nfl = Sport(key="americanfootball_nfl", name="NFL")
    nhl = Sport(key="icehockey_nhl", name="NHL")
    ncaaf = Sport(key="americanfootball_ncaaf", name="NCAAF")
    ahl = Sport(key="icehockey_ahl", name="AHL")
    session.add_all([nfl, nhl, ncaaf, ahl])
    await session.flush()

    now = datetime.now(timezone.utc)

    # --- the subject: a finished game behind it, the real fixture past the week
    subject_last = Event(
        sport_id=nfl.id,
        home_team_name=SUBJECT_LAST_OPPONENT,
        away_team_name=SUBJECT,
        commence_time=now - timedelta(days=3),
        status="completed",
        event_tags=None,
    )
    subject_next = Event(
        sport_id=nfl.id,
        home_team_name=SUBJECT_NEXT_OPPONENT,
        away_team_name=SUBJECT,
        # TEN days out: past the seven-day pool, well inside the horizon.
        commence_time=now + timedelta(days=10),
        status="scheduled",
        event_tags=None,
    )

    # --- the gate control: answered by the upcoming pool, plus a distant decoy
    control_soon = Event(
        sport_id=nfl.id,
        home_team_name=CONTROL,
        away_team_name="Denver Broncos",
        commence_time=now + timedelta(days=2),
        status="scheduled",
        event_tags=None,
    )
    control_distant = Event(
        sport_id=nfl.id,
        home_team_name=CONTROL,
        away_team_name="Buffalo Bills",
        # Inside the or-NEXT arm's window. It must NOT appear, because the arm
        # never runs for this query — the pool already named the participant.
        commence_time=now + timedelta(days=60),
        status="scheduled",
        event_tags=None,
    )

    # --- the ceiling control: one fixture beyond the horizon, one game behind it
    ceiling_beyond = Event(
        sport_id=nfl.id,
        home_team_name=CEILING,
        away_team_name="New York Jets",
        commence_time=now + timedelta(days=200),
        status="scheduled",
        event_tags=None,
    )
    ceiling_last = Event(
        sport_id=nfl.id,
        home_team_name=CEILING,
        away_team_name="Houston Texans",
        commence_time=now - timedelta(days=5),
        status="completed",
        event_tags=None,
    )

    session.add_all([
        subject_last,
        subject_next,
        control_soon,
        control_distant,
        ceiling_beyond,
        ceiling_last,
    ])

    # The team rows the dropdown's entity half resolves. Without them the query
    # still reaches the event arms, but the response would not resemble the one
    # a reader gets, and #4411's promotion rules would be exercised on a pool
    # that never contains a team.
    session.add_all([
        Team(sport_id=nfl.id, name=SUBJECT, abbreviation="NE"),
        Team(sport_id=nfl.id, name=CONTROL, abbreviation="KC"),
        Team(sport_id=nfl.id, name=CEILING, abbreviation="MIA"),
    ])

    # --- #5201: the namesake families ---------------------------------------
    # These teams are FLUSHED before their events, because the whole point of
    # the first family is that its fixture is found by `away_team_id` and by
    # nothing else.
    boston = Team(sport_id=nhl.id, name=NAMESAKE_SUBJECT, abbreviation="BOS")
    ucla = Team(sport_id=ncaaf.id, name=NAMESAKE_DECOY, abbreviation="UCLA")
    chicago = Team(sport_id=nfl.id, name=NAME_ONLY_SUBJECT, abbreviation="CHI")
    hershey = Team(sport_id=ahl.id, name=NAME_ONLY_DECOY, abbreviation="HER")
    session.add_all([boston, ucla, chicago, hershey])
    await session.flush()

    # The decoy: inside the seven-day pool, so it both fills the pool AND closes
    # the or-NEXT gate. This is the production shape exactly — UCLA played the
    # Saturday, Boston not for nineteen days.
    namesake_decoy_soon = Event(
        sport_id=ncaaf.id,
        home_team_name=NAMESAKE_DECOY,
        home_team_id=ucla.id,
        away_team_name="San Diego State Aztecs",
        commence_time=now + timedelta(days=1),
        status="scheduled",
        event_tags=None,
    )
    # 🔴 Named "Bruins", id-linked to Boston: reachable by the id arm only.
    namesake_subject_next = Event(
        sport_id=nhl.id,
        home_team_name="Buffalo Sabres",
        away_team_name="Bruins",
        away_team_id=boston.id,
        commence_time=now + timedelta(days=19),
        status="scheduled",
        event_tags=None,
    )
    # The ceiling, inside this family so the arm cannot pass by returning the
    # first Boston row it sees.
    namesake_subject_distant = Event(
        sport_id=nhl.id,
        home_team_name="Bruins",
        home_team_id=boston.id,
        away_team_name="Montreal Canadiens",
        commence_time=now + timedelta(days=200),
        status="scheduled",
        event_tags=None,
    )

    # The name-only family: no team ids anywhere on either row.
    name_only_decoy_soon = Event(
        sport_id=ahl.id,
        home_team_name=NAME_ONLY_DECOY,
        away_team_name="Wilkes-Barre Penguins",
        commence_time=now + timedelta(days=1),
        status="scheduled",
        event_tags=None,
    )
    name_only_subject_next = Event(
        sport_id=nfl.id,
        home_team_name=NAME_ONLY_SUBJECT,
        away_team_name="Green Bay Packers",
        commence_time=now + timedelta(days=25),
        status="scheduled",
        event_tags=None,
    )

    session.add_all([
        namesake_decoy_soon,
        namesake_subject_next,
        namesake_subject_distant,
        name_only_decoy_soon,
        name_only_subject_next,
    ])

    await session.commit()
    return {
        "subject_last": subject_last.id,
        "subject_next": subject_next.id,
        "control_soon": control_soon.id,
        "control_distant": control_distant.id,
        "ceiling_beyond": ceiling_beyond.id,
        "ceiling_last": ceiling_last.id,
        "namesake_decoy_soon": namesake_decoy_soon.id,
        "namesake_subject_next": namesake_subject_next.id,
        "namesake_subject_distant": namesake_subject_distant.id,
        "name_only_decoy_soon": name_only_decoy_soon.id,
        "name_only_subject_next": name_only_subject_next.id,
    }


@pytest.fixture
async def seeded():
    """Real Postgres, real schema, real `pg_trgm`.

    Function-scoped for the reason `test_search_recall_contract.py` gives:
    `pytest.ini` leaves `asyncio_default_fixture_loop_scope` unset, so a
    module-scoped async fixture outlives the loop that created its engine.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    # Imported as `from app.models import models`, not `import app.models.models`,
    # only so this module reaches `app.models.models` by ONE style — `_seed` above
    # already does `from app.models.models import ...`, and mixing the two forms
    # is a CodeQL note. Same module, same side effect.
    from app.models import models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        ids = await _seed(session)

    yield maker, ids

    await engine.dispose()


@pytest.fixture
async def typeahead(seeded):
    """The real app against the real database, with Redis refused.

    🔴 Redis is patched to raise, and it is load-bearing rather than tidy.
    `/typeahead` has had a full response cache since #1866, and these cases ask
    about the same league repeatedly. A live cache would serve one query's
    answer to the next and the controls would pass for the worst possible
    reason. The route treats a raising client as a miss, which is the pre-cache
    behaviour.
    """
    from unittest.mock import patch

    from httpx import ASGITransport, AsyncClient

    from app.dependencies.auth import get_optional_user
    from app.main import app
    from app.services.database import get_db, get_db_rw

    maker, ids = seeded

    async def _override():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[get_db_rw] = _override
    app.dependency_overrides[get_optional_user] = lambda: None

    with patch(
        "app.tasks.redis_state.get_redis_client",
        side_effect=RuntimeError("no redis in the recall gate"),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as http:

            async def _typeahead(q: str) -> dict:
                resp = await http.get("/api/events/typeahead", params={"q": q})
                assert resp.status_code == 200, f"typeahead {q!r} -> {resp.status_code}"
                return resp.json()

            yield _typeahead, ids

    app.dependency_overrides.clear()


def _event_ids(payload) -> list[int]:
    """Event ids in the order the reader sees them."""
    items = payload.get("suggestions", payload) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []
    return [
        i["event_id"]
        for i in items
        if isinstance(i, dict) and i.get("type") == "event" and i.get("event_id")
    ]


# ---------------------------------------------------------------------------
# 1. The ship
# ---------------------------------------------------------------------------


@needs_postgres
async def test_the_next_fixture_past_the_week_reaches_the_dropdown(typeahead):
    """🔴 THE SHIP. Ten days out, and the reader can see it.

    Before the or-NEXT arm this returned the Seahawks game — played, final, and
    the only thing `patriots` could offer.
    """
    ask, ids = typeahead

    returned = _event_ids(await ask("patriots"))

    assert ids["subject_next"] in returned, (
        "the Patriots' actual next game is still invisible — the or-NEXT arm did "
        f"not reach it. Returned: {returned}"
    )


@needs_postgres
async def test_the_next_game_replaces_the_finished_one(typeahead):
    """The lifecycle trace #5059 asks for: next REPLACES last, not joins it.

    Asserted as an absence because that is what the short-circuit does — if the
    team has a real next fixture there is nothing a finished game answers. A
    version that merged both pools would pass the test above and still show a
    reader last Thursday's result beside next Sunday's kickoff.
    """
    ask, ids = typeahead

    returned = _event_ids(await ask("patriots"))

    assert ids["subject_next"] in returned
    assert ids["subject_last"] not in returned, (
        "the finished Seahawks game is still being offered alongside the next "
        f"fixture — the or-LAST arm was not short-circuited. Returned: {returned}"
    )


# ---------------------------------------------------------------------------
# 2. The gate — the control that makes the ship a repair and not a widening
# ---------------------------------------------------------------------------


@needs_postgres
async def test_a_team_playing_this_week_is_untouched(typeahead):
    """🔴 THE REFUSAL, driven through the route.

    The Chiefs play in two days and again in sixty. Widening the upcoming pool —
    the cheap-looking fix — would return both and change what every working
    query fetches. The gated arm never runs here at all, because the pool
    already named the participant.

    If this fails, the repair has become the thing it was chosen over, and the
    compiled-SQL sibling test cannot see it: the arm's own clauses would still
    be perfectly correct.
    """
    ask, ids = typeahead

    returned = _event_ids(await ask("chiefs"))

    assert ids["control_soon"] in returned, (
        f"the Chiefs' game in two days went missing: {returned}"
    )
    assert ids["control_distant"] not in returned, (
        "a sixty-day-out fixture entered a query the upcoming pool already "
        f"answered — the or-NEXT arm is not gated. Returned: {returned}"
    )


# ---------------------------------------------------------------------------
# 3. The ceiling — gotcha #41 wants both ends
# ---------------------------------------------------------------------------


@needs_postgres
async def test_the_horizon_is_a_ceiling_and_the_fallback_survives_it(typeahead):
    """A fixture past the horizon is not an answer, and the arm behind it still is.

    Both halves in one test on purpose. "The distant game is absent" passes
    trivially if the arm is broken and returns nothing at all; pairing it with
    "the finished game is still offered" proves the endpoint is alive and that
    #4411's or-LAST arm survived the short-circuit for the case it owns — a team
    with no reachable fixture.
    """
    ask, ids = typeahead

    returned = _event_ids(await ask("dolphins"))

    assert ids["ceiling_beyond"] not in returned, (
        "a fixture two hundred days out was offered — the horizon is not being "
        f"applied. Returned: {returned}"
    )
    assert ids["ceiling_last"] in returned, (
        "no game at all for the Dolphins: the or-LAST arm stopped answering the "
        f"case it exists for. Returned: {returned}"
    )


# ---------------------------------------------------------------------------
# 4. #5201 — the arm above admits only rows the query NAMES, and a NAMESAKE
#    names it. Same harness, because it is the same question one step in: not
#    "is there a fixture" but "is there THIS team's fixture".
# ---------------------------------------------------------------------------


@needs_postgres
async def test_the_resolved_teams_own_fixture_reaches_the_dropdown(typeahead):
    """🔴 THE SHIP (#5201). `bruins` reaches BOSTON's game.

    Production, 2026-09-11: the reader got a Boston Bruins card in slot 0 and,
    as the only game on the page, *San Diego State Aztecs at UCLA Bruins*.
    Boston's own next fixture existed — three of them inside the horizon — and
    no path on the endpoint could reach it, because the or-NEXT gate was
    satisfied by UCLA and the or-NEXT query's eight-row window over 120 days
    fills with UCLA's weekly fixtures long before it arrives at Boston's.

    The seeded row is named "Bruins" and carries Boston's `away_team_id`, so
    this passes only if the arm selects on IDENTITY. A version that matched the
    team's display name — which is 99.7% as good on production and looks
    equivalent in review — returns nothing here.
    """
    ask, ids = typeahead

    returned = _event_ids(await ask("bruins"))

    assert ids["namesake_subject_next"] in returned, (
        "the Bruins' own next game is still unreachable — the reader gets a "
        f"Boston card above another club's fixture. Returned: {returned}"
    )


@needs_postgres
async def test_the_namesakes_fixture_is_not_taken_away(typeahead):
    """The ship is ADDITIVE, and this is the assertion that holds it to that.

    Nothing about UCLA's fixture is wrong — it is a real game that really
    matches the query, and a reader who meant UCLA is entitled to it. The repair
    is that Boston's game is THERE TOO, not that somebody else's is gone. A
    version that re-gated the pool on the resolved team would pass the test
    above and quietly delete this row.
    """
    ask, ids = typeahead

    returned = _event_ids(await ask("bruins"))

    assert ids["namesake_decoy_soon"] in returned, (
        "UCLA's fixture disappeared: the new arm is filtering the pool instead "
        f"of adding to it. Returned: {returned}"
    )


@needs_postgres
async def test_the_horizon_still_binds_on_the_new_arm(typeahead):
    """gotcha #41 wants both ends, and the arm takes exactly ONE row.

    Boston has a fixture at nineteen days and another at two hundred. The near
    one is the answer; the far one must never be, or the arm has become an
    unbounded "find me anything by this team" and a dissolved club answers with
    a fixture from a season nobody asked about.

    Paired with the positive assertion deliberately: "the distant row is absent"
    passes trivially when the arm is broken and returns nothing at all.
    """
    ask, ids = typeahead

    returned = _event_ids(await ask("bruins"))

    assert ids["namesake_subject_next"] in returned
    assert ids["namesake_subject_distant"] not in returned, (
        "a fixture two hundred days out was offered — the new arm is not "
        f"ceilinged, or it is not sorted by the soonest. Returned: {returned}"
    )


@needs_postgres
async def test_a_fixture_with_no_team_ids_is_still_reached(typeahead):
    """The name arm, and it is not symmetry — it is 81 measured rows.

    Of the 344 future fixtures inside the horizon with no `home_team_id`
    (production 2026-09-11), 81 name a real team row exactly; `soccer_other`
    carries 143 id-less fixtures on its own. This family has ids on NEITHER row,
    so it passes only if the exact-name arm survives.

    🔴 And it must be an EQUALITY. The decoy here is *Hershey Bears*, inside the
    pool and inside the seven days: a LIKE would match it, close the gate, and
    put the ship back exactly where #5201 found it.
    """
    ask, ids = typeahead

    returned = _event_ids(await ask("bears"))

    assert ids["name_only_subject_next"] in returned, (
        "the Bears' own fixture is unreachable — the name arm is gone and the "
        f"id arm cannot see a row with no ids. Returned: {returned}"
    )
    assert ids["name_only_decoy_soon"] in returned, (
        f"Hershey's fixture disappeared — the arm is filtering. Got: {returned}"
    )


@needs_postgres
async def test_the_arm_does_not_offer_a_game_the_pool_already_holds(typeahead):
    """The gate and the query must not disagree, seen from the reader's side.

    If the gate's test for "this team's fixture is already here" is narrower
    than the query that fetches one, the arm re-fetches a row the pool already
    holds and the reader sees the same game twice — #2263's complaint, arriving
    through a new door. Asserted over every query in the file, because the
    cheapest way to introduce it is to repair one family and not notice another.
    """
    ask, _ = typeahead

    for query in ("bruins", "bears", "patriots", "chiefs", "dolphins"):
        returned = _event_ids(await ask(query))
        assert len(returned) == len(set(returned)), (
            f"{query!r} offered the same game twice: {returned}"
        )
