"""`/api/events/search` and `/api/events/typeahead` stop printing one game twice.

CERT-439 (`C-DUPLICATE-PROOF-2263-1`) blocked #2263 on exactly one finding, and
this file is that finding turned into a gate:

    "the branch adds `not_a_proven_duplicate()` only to league upcoming/recent,
    team upcoming/recent, and feed candidate queries. The main
    `/api/events/search` event query and its count/fuzzy fallback build directly
    from `Event` without the predicate. A row tagged
    `provenance:duplicate-of:<id>` therefore disappears from the league/team/feed
    rails but remains a separate search result for the same game."

The write side proves **global event identity** — the registry decided these two
rows are one baseball game. A product that consumes that proof on three surfaces
and ignores it on a fourth answers "one game" or "two games" according to how
you navigated to it, which is worse than either answer alone.

## why this cannot be a unit test

The parent's Part D asserts the clause is IN a statement, and Part C executes the
predicate on SQLite in isolation. Both were green while search returned the twin,
because neither drives the endpoint. What the cert asked for is a *tagged/untagged
control that drives the real search result and total count*, and the search route
cannot run anywhere but PostgreSQL: `_search_rank` is `ts_rank_cd(to_tsvector(...))`,
the recall arms are `pg_trgm`-servable ILIKE, and the "did you mean" fallback is
`similarity()`/`%` behind `SET LOCAL pg_trgm.similarity_threshold`. There is no
local Postgres in the agent sandbox (`initdb` dies on `shmget`), so **CI is the
environment that grades this**, on the same `search-recall` service container as
`test_search_recall_contract.py`.

## the reads, and why one seed covers them

`/search` builds every event-shaped read from ONE list — the two UNION recall
arms, the outer entity query, the identity-only count, and the substring-existence
guard — except the fuzzy fallback, which replaces `query` and `total_count`
wholesale and therefore has its own. `/typeahead` has two: the dropdown pool and
its own fuzzy pool. `/search-suggestions` — the search box's zero state — has
three.

So: a primary query, its total, a misspelled query that reaches the fallback, the
dropdown, and one zero-state chip.

**The chip fails differently, and it is the nastier of the two shapes.**
`search_suggestions._add` dedups on the suggestion TEXT, and both rows yield the
same shorter team name, so a duplicated game never appeared as two chips. But
`soon_q` orders `commence_time ASC` and the twin is a minute EARLIER, so the twin
arrives first, claims the name, and the chip carries ITS `event_id`. One
suggestion, pointing at the copy with no odds and no sources — a search
suggestion that opens a blank event page. A test that only counted chips would
have reported this surface healthy.

## the kill control

Every case below is run TWICE against the same server — once with the twin
tagged, once with the tag cleared and nothing else changed. If the twin were
being suppressed by something other than the tag (the name-collapse in
`feed_event_candidates`, pagination, a `DISTINCT` somewhere upstream) the
untagged pass would suppress it too, and these tests would be certifying a
coincidence. The untagged pass is REQUIRED to return the second row.
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
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres proven-duplicate "
        "search contract (CI job `search-recall` provides one)"
    ),
)

# The production specimen, to the minute — the same pair the parent branch was
# written against. LAD @ DET, ESPN fixture 401816721: a good row holding the
# espn_id, and a bare twin ONE MINUTE earlier holding nothing. That minute is why
# every exact-tuple guard in the codebase was blind to it.
ESPN_FIXTURE = "401816721"
HOME = "Detroit Tigers"
AWAY = "Los Angeles Dodgers"

#: A second, genuinely distinct Tigers game. It matches the same queries and is
#: never tagged, so it is the "the predicate did not empty the rail" control —
#: the failure direction `proven_duplicates.py` warns about, where a bare
#: `NOT LIKE` drops every untagged row because `NULL NOT LIKE x` is NULL.
CONTROL_AWAY = "Chicago White Sox"

#: A THIRD pair, inside the 3-hour "starting soon" window that feeds the search
#: box's zero state. Deliberately not a Tigers game, so it cannot perturb the
#: `?q=tigers` cases above.
SOON_HOME = "Seattle Mariners"
SOON_AWAY = "Toronto Blue Jays"


async def _seed(session):
    """Three events and one team; ids are assigned by the server and read back."""
    from app.models.models import Event, Sport, Team

    mlb = Sport(key="baseball_mlb", name="MLB")
    session.add(mlb)
    await session.flush()

    start = datetime.now(timezone.utc) + timedelta(days=2)

    canonical = Event(
        sport_id=mlb.id,
        home_team_name=HOME,
        away_team_name=AWAY,
        commence_time=start,
        status="scheduled",
        espn_id=ESPN_FIXTURE,
        event_tags=["provenance:source:espn"],
    )
    control = Event(
        sport_id=mlb.id,
        home_team_name=HOME,
        away_team_name=CONTROL_AWAY,
        commence_time=start + timedelta(days=1),
        status="scheduled",
        event_tags=None,
    )
    session.add_all([canonical, control])
    await session.flush()

    from app.services.anchor_channel import duplicate_tag

    twin = Event(
        sport_id=mlb.id,
        home_team_name=HOME,
        away_team_name=AWAY,
        commence_time=start - timedelta(minutes=1),
        status="scheduled",
        event_tags=[duplicate_tag(canonical.id)],
    )
    session.add(twin)

    # The "starting soon" pair. MLB is LEAGUE_TIERS tier 1, so it clears the
    # `tier_12_keys` filter; 90 minutes out puts it inside the 3-hour window and
    # outside typeahead's concern for the cases above.
    soon_start = datetime.now(timezone.utc) + timedelta(minutes=90)
    soon_canonical = Event(
        sport_id=mlb.id,
        home_team_name=SOON_HOME,
        away_team_name=SOON_AWAY,
        commence_time=soon_start,
        status="scheduled",
        espn_id="401816999",
        event_tags=["provenance:source:espn"],
    )
    session.add(soon_canonical)
    await session.flush()
    soon_twin = Event(
        sport_id=mlb.id,
        home_team_name=SOON_HOME,
        away_team_name=SOON_AWAY,
        # A MINUTE EARLIER, exactly as in production — and the reason the twin
        # wins this surface: `soon_q` orders `commence_time ASC`.
        commence_time=soon_start - timedelta(minutes=1),
        status="scheduled",
        event_tags=[duplicate_tag(soon_canonical.id)],
    )
    session.add(soon_twin)

    # The "did you mean" correction resolves against `teams`. Named `Tigers`
    # rather than `Detroit Tigers` on purpose: `similarity('Tigers','tigerz')` is
    # 0.556 against the 0.25 the route pins, so the fallback fires with real
    # margin instead of sitting on a threshold that a rename would silently move.
    session.add(Team(sport_id=mlb.id, name="Tigers", abbreviation="DET"))

    await session.commit()
    return {
        "canonical": canonical.id,
        "control": control.id,
        "twin": twin.id,
        "soon_canonical": soon_canonical.id,
        "soon_twin": soon_twin.id,
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

    import app.models.models  # noqa: F401 — registers every table on Base
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
async def client(seeded):
    """The real app against the real database, with Redis refused.

    🔴 Redis is patched to raise, and it is load-bearing rather than tidy.
    `/search` gained a full response cache in LAT-P090 and `/typeahead` has had
    one since #1866. Every case below asks the SAME question twice — once tagged,
    once untagged — so a live cache would serve the first answer to the second
    ask and the kill control would pass for the worst possible reason. Both
    routes treat a raising client as a miss, which is the pre-cache behaviour.
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

            async def _search(q: str) -> dict:
                resp = await http.get("/api/events/search", params={"q": q})
                assert resp.status_code == 200, f"search {q!r} -> {resp.status_code}"
                return resp.json()

            async def _typeahead(q: str) -> dict:
                resp = await http.get("/api/events/typeahead", params={"q": q})
                assert resp.status_code == 200, f"typeahead {q!r} -> {resp.status_code}"
                return resp.json()

            async def _suggestions() -> dict:
                resp = await http.get("/api/events/search-suggestions")
                assert resp.status_code == 200, f"suggestions -> {resp.status_code}"
                return resp.json()

            yield _search, _typeahead, _suggestions, maker, ids

    app.dependency_overrides.clear()


async def _untag_the_twin(maker, twin_id):
    """Clear the tag and change NOTHING else — the kill control's whole point."""
    from sqlalchemy import update

    from app.models.models import Event

    async with maker() as session:
        await session.execute(
            update(Event).where(Event.id == twin_id).values(event_tags=None)
        )
        await session.commit()


def _result_ids(payload: dict) -> list[int]:
    return [r["id"] for r in payload.get("results", [])]


def _typeahead_event_ids(payload) -> list[int]:
    items = payload.get("suggestions", payload) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []
    return [
        i["event_id"]
        for i in items
        if isinstance(i, dict) and i.get("type") == "event" and i.get("event_id")
    ]


# ---------------------------------------------------------------------------
# 1. The primary event query and the count built from the same list
# ---------------------------------------------------------------------------


@needs_postgres
async def test_search_does_not_return_a_row_proved_to_be_the_same_game(client):
    """THE SHIP. `?q=tigers` returns tonight's game once, not twice."""
    search, _typeahead, _suggestions, _maker, ids = client

    payload = await search("tigers")
    returned = _result_ids(payload)

    assert ids["twin"] not in returned, (
        "search returned a row the registry has PROVED is a second copy of "
        f"event {ids['canonical']} — the league, team and feed rails already "
        "decline to print it, so the product now answers 'one game' or 'two "
        "games' depending on how the user got there"
    )
    assert ids["canonical"] in returned, "the surviving copy must still be found"
    assert ids["control"] in returned, (
        "an untagged Tigers game vanished — this is the null-safety trap: a bare "
        "NOT LIKE evaluates to NULL for the untagged rows that are nearly all of "
        "them, and empties the rail it was added to"
    )


@needs_postgres
async def test_the_total_count_agrees_with_the_page(client):
    """The count is a SEPARATE statement built from the same condition list.

    It is what drives `total_pages`/`has_next`, so a count that still includes
    the twin advertises a result the page will never contain — the pagination
    reads "2 results" while showing one, or offers a second page that is empty.
    """
    search, _typeahead, _suggestions, _maker, ids = client

    payload = await search("tigers")

    assert payload["pagination"]["total_results"] == len(_result_ids(payload)) == 2, (
        f"count and page disagree: total_results="
        f"{payload['pagination']['total_results']}, page={_result_ids(payload)}"
    )


@needs_postgres
async def test_the_kill_control_untagged_the_second_row_comes_back(client):
    """Required to FAIL to suppress. Without this the two tests above are
    consistent with the twin being dropped by something that has nothing to do
    with the proof — the exact-tuple collapse, a DISTINCT, the page limit."""
    search, _typeahead, _suggestions, maker, ids = client

    await _untag_the_twin(maker, ids["twin"])
    payload = await search("tigers")

    assert ids["twin"] in _result_ids(payload), (
        "with the tag cleared the twin must return — otherwise the suppression "
        "above is a coincidence and this file certifies nothing"
    )
    assert payload["pagination"]["total_results"] == 3


# ---------------------------------------------------------------------------
# 2. The fuzzy fallback — its own condition list, its own count
# ---------------------------------------------------------------------------


@needs_postgres
async def test_the_did_you_mean_fallback_also_drops_the_proven_duplicate(client):
    """The misspelled query is the one a person actually types.

    This path replaces `query` and `total_count` wholesale, so it would keep
    serving the twin even with the primary path repaired.
    """
    search, _typeahead, _suggestions, _maker, ids = client

    payload = await search("tigerz")

    assert payload.get("did_you_mean") == "Tigers", (
        "the fallback did not fire, so this test is not exercising the path it "
        f"names; payload keys: {sorted(payload)}"
    )
    returned = _result_ids(payload)
    assert ids["twin"] not in returned
    assert ids["canonical"] in returned
    assert payload["pagination"]["total_results"] == len(returned) == 2


@needs_postgres
async def test_the_fallback_kill_control(client):
    search, _typeahead, _suggestions, maker, ids = client

    await _untag_the_twin(maker, ids["twin"])
    payload = await search("tigerz")

    assert payload.get("did_you_mean") == "Tigers"
    assert ids["twin"] in _result_ids(payload)


# ---------------------------------------------------------------------------
# 3. The dropdown — the first search surface, and the one with four slots
# ---------------------------------------------------------------------------


@needs_postgres
async def test_typeahead_offers_the_game_once(client):
    """`/typeahead` takes at most four event slots. Two spent on one game is the
    original complaint arriving a keystroke earlier than `/search`."""
    search, typeahead, _suggestions, _maker, ids = client

    returned = _typeahead_event_ids(await typeahead("tigers"))

    assert ids["twin"] not in returned
    assert ids["canonical"] in returned
    assert ids["control"] in returned


@needs_postgres
async def test_typeahead_kill_control(client):
    search, typeahead, _suggestions, maker, ids = client

    await _untag_the_twin(maker, ids["twin"])

    assert ids["twin"] in _typeahead_event_ids(await typeahead("tigers"))


# ---------------------------------------------------------------------------
# 4. The zero state — where the twin wins by being a minute early
# ---------------------------------------------------------------------------


def _soon_chip(payload: dict, ids: dict) -> dict:
    chips = [
        s
        for s in payload.get("suggestions", [])
        if s.get("type") == "event"
        and s.get("event_id") in (ids["soon_canonical"], ids["soon_twin"])
    ]
    assert len(chips) == 1, (
        "expected exactly one 'starting soon' chip for the seeded game, got "
        f"{chips!r} out of {payload.get('suggestions')!r} — if this is zero the "
        "test is not exercising the surface it names"
    )
    return chips[0]


@needs_postgres
async def test_the_starting_soon_chip_points_at_the_real_game(client):
    """THE SHIP on this surface, and it is a link and not a count.

    Two chips never happened here — `_add` dedups on the text. What happened is
    that the earlier row won the name, so the one chip opened the blank copy.
    """
    _search, _typeahead, suggestions, _maker, ids = client

    chip = _soon_chip(await suggestions(), ids)

    assert chip["event_id"] == ids["soon_canonical"], (
        "the zero-state suggestion linked to the proven duplicate — the row "
        "with no espn_id, no odds and no probability sources"
    )


@needs_postgres
async def test_the_starting_soon_kill_control(client):
    """Untagged, the minute-earlier twin takes the chip back. If it did not,
    the assertion above would be passing on the ordering rather than the tag."""
    _search, _typeahead, suggestions, maker, ids = client

    await _untag_the_twin(maker, ids["soon_twin"])
    chip = _soon_chip(await suggestions(), ids)

    assert chip["event_id"] == ids["soon_twin"]


# ---------------------------------------------------------------------------
# 5. The gate is armed
# ---------------------------------------------------------------------------


async def test_the_seed_actually_tags_the_twin():
    """Runs everywhere, including the ordinary shards, and needs no database.

    Gotcha #53 applied to this file's own instrument. Every test above is
    Postgres-gated; if the tag the seed writes ever stopped matching the
    predicate's prefix, all seven would go green by never excluding anything and
    the kill controls would pass trivially. This asserts the two halves still
    speak the same vocabulary.
    """
    from app.services.anchor_channel import DUPLICATE_TAG_PREFIX, duplicate_tag

    tag = duplicate_tag(15294237)
    assert tag.startswith(DUPLICATE_TAG_PREFIX)
    assert str(15294237) in tag
