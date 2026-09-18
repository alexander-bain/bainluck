"""#5821 Part B — the proven-duplicate search bridge, executed on real Postgres.

Lifted out of `tests/test_proven_duplicate_search_bridge_5821.py`, where these
cases were written as a `skipif`-gated class inside the unit file. They were
green there for the worst possible reason: nothing in CI ever set
`SEARCH_TEST_DATABASE_URL` for that path, so they SKIPPED on every run, and
`pytest` exits 0 on a skip. Armed by hand against a real database they did not
merely fail — they could not construct their own fixture (measured 2026-09-18,
both on `duplicate key value violates unique constraint "sports_pkey"`: the old
version pinned `Sport.id = 7` and the two production event ids, created two
tables with `checkfirst=True`, and deleted its rows on the HAPPY PATH ONLY, so
it assumed an empty database and the first failing case poisoned the next).
This file follows the convention its siblings in this directory already use:
drop and recreate the full schema per test and let the server assign ids.

THE SHIP IS ASSERTED THROUGH THE ROUTE, NOT THROUGH THE HELPER, and that is the
correction this file exists for. The lifted version called
`_event_name_match("atletico madrid", None)` — the house recall builder, but fed
the WHOLE query — and passed the result to `bridged_canonical_ids` as "the arm
the reader ran". It is not. For a multi-term query the route builds
`and_(*[_event_name_match(t, e) for t, e in expanded])` (routes/events.py ~5277):
one arm PER TERM, ANDed, so the terms may land in DIFFERENT columns. The
production ghost is `home_team_name='Atletico'`, `away_team_name='Real Madrid'`
— it is reached because "atletico" matches home and "madrid" matches away, and
it is reached by NO single-column `%atletico madrid%` at all. Measured here on
real Postgres before this rewrite: the lifted positive case returned `[]`
against a faithful seed, because the arm it built matched zero rows. A test can
use the right function and still assert against a filter no reader runs.

WHY POSTGRES AND NOT SQLITE. The recall arms compile to trigram and
word-boundary SQL that SQLite cannot serve, and `is_a_proven_duplicate` is a
prefix `LIKE` over a JSONB array — `event_tags` is shimmed to plain JSON under
SQLite, where the operators do not exist.

The partition property — `is_a_proven_duplicate` being the EXACT complement of
`not_a_proven_duplicate` — stays in the unit file, where it runs everywhere on
every push. That one is the durable guard; these are the proof that the walk
happens at all.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres proven-duplicate "
            "search bridge contract (CI job `search-recall` provides one)"
        ),
    ),
]

# ── The production specimen, to the name ────────────────────────────────────
#
# Read off production 2026-09-18: event 15312071 (odds_api, ACCENTED) and event
# 15307707 (kalshi, plain ASCII, and on the day the only one carrying the
# moneyline). Search does no diacritic folding at all — #6977, still open — so
# the unaccented row was a plain-keyboard reader's ONLY route to the derby, and
# folding it without this bridge turns the wrong page into an empty one.
#
# Ids are NOT pinned: the ids are the server's, and the duplicate tag is built
# from the canonical's assigned id after the flush. Pinning them is what
# collided with the sibling gates sharing this database.
CANONICAL_HOME = "Atlético Madrid"
CANONICAL_AWAY = "Real Madrid"
#: NOT "Atletico Madrid". The production ghost really is the bare club word; a
#: seed that spelled the full phrase here would pass a single-column arm and
#: hide exactly the defect this file was rewritten to catch.
GHOST_HOME = "Atletico"
GHOST_AWAY = "Real Madrid"

#: The spelling the ship is about — the one that regressed to an empty page.
UNACCENTED_QUERY = "Atletico Madrid"


@pytest.fixture
async def maker():
    """A clean schema and a sessionmaker, per test.

    Function-scoped for the reason `test_search_recall_contract.py` gives:
    `pytest.ini` leaves `asyncio_default_fixture_loop_scope` unset, so a
    module-scoped async fixture outlives the loop that created its engine.

    `drop_all` is the half that matters. These cases share one database with
    every other gate in the `search-recall` job, and the version of them that
    lived in the unit file assumed it would find `sports` empty.
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

    yield async_sessionmaker(engine, expire_on_commit=False)

    await engine.dispose()


@pytest.fixture
async def search(maker):
    """`GET /api/events/search` against the real app and the real database.

    🔴 Redis is patched to raise, and it is load-bearing rather than tidy, for
    the reason the sibling `test_search_proven_duplicate_pg.py` gives: `/search`
    has had a full response cache since LAT-P090, and every case here asks the
    SAME query — once with the ghost tagged, once without — so a live cache
    would serve the first answer to the second ask and the counterfactual would
    pass for the worst possible reason. Both routes treat a raising client as a
    miss, which is the pre-cache behaviour.
    """
    from unittest.mock import patch

    from httpx import ASGITransport, AsyncClient

    from app.dependencies.auth import get_optional_user
    from app.main import app
    from app.services.database import get_db, get_db_rw

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

            yield _search

    app.dependency_overrides.clear()


async def _seed_derby(session, *, tag_the_ghost: bool):
    """The accented canonical, plus the ASCII twin — tagged or not.

    Returns `(canonical_id, ghost_id)`. The duplicate tag embeds the canonical's
    id, so the canonical is flushed first and its assigned id read back.

    The kickoff is RELATIVE (gotcha #44): the route scopes on
    `commence_time >= cutoff`, so a pinned calendar date is a test that passes
    until that date and silently stops exercising the route afterwards. The
    production pair kicks off 2026-09-20; what matters to the contract is that
    it is upcoming, not which day it is.
    """
    from app.models.models import Event, Sport
    from app.services.anchor_channel import duplicate_tag

    kickoff = datetime.now(timezone.utc) + timedelta(days=2)

    la_liga = Sport(key="soccer_spain_la_liga", name="La Liga")
    session.add(la_liga)
    await session.flush()

    canonical = Event(
        sport_id=la_liga.id,
        home_team_name=CANONICAL_HOME,
        away_team_name=CANONICAL_AWAY,
        commence_time=kickoff,
        status="scheduled",
        event_tags=["provenance:source:odds_api"],
    )
    session.add(canonical)
    await session.flush()

    ghost = Event(
        sport_id=la_liga.id,
        home_team_name=GHOST_HOME,
        away_team_name=GHOST_AWAY,
        # Three hours later, as in production, so neither row can win the other's
        # place in the ordering by accident.
        commence_time=kickoff + timedelta(hours=3),
        status="scheduled",
        event_tags=(
            [duplicate_tag(canonical.id)]
            if tag_the_ghost
            else ["provenance:source:kalshi"]
        ),
    )
    session.add(ghost)
    await session.commit()

    return canonical.id, ghost.id


def _event_ids(payload) -> list[int]:
    """The game-card ids in a `/api/events/search` response.

    The key is `results`, not `events` — and `.get("events", [])` reads `[]` on
    every response, so a probe keyed on the wrong name reports "the route served
    nothing" for a route that served the row. Asserted rather than assumed:
    a missing `results` key is a contract change, not an empty answer.
    """
    assert "results" in payload, (
        f"search response has no `results` key; got {sorted(payload)}"
    )
    return [event["id"] for event in payload["results"]]


async def test_the_unaccented_spelling_reaches_the_accented_canonical(maker, search):
    """THE SHIP, asserted where the reader stands.

    A plain-keyboard reader types the derby's name. The only row their text
    reaches has been proved a duplicate and is no longer printed — so without
    the bridge the response is empty, which is the regression CERT-3071 caught.
    With it, they are handed the canonical they were always trying to reach.
    """
    async with maker() as db:
        canonical_id, ghost_id = await _seed_derby(db, tag_the_ghost=True)

    served = _event_ids(await search(UNACCENTED_QUERY))

    assert canonical_id in served, (
        f"the bridge did not walk {UNACCENTED_QUERY!r} to the canonical; "
        f"served {served}"
    )
    assert ghost_id not in served, (
        "the folded duplicate was printed — the fold itself has regressed"
    )


async def test_without_the_tag_the_same_text_never_reaches_the_canonical(maker, search):
    """THE COUNTERFACTUAL, and the reason the case above is not self-fulfilling.

    The seed is identical but for the tag. Untagged, the ghost is printable, so
    the response is the ghost and the canonical is NOT in it — which is the
    proof that the canonical's appearance above is caused by the duplicate tag
    and not by the reader's text reaching the accented row on its own. If search
    ever learns to fold diacritics (#6977) this case is the one that will go
    red, and it should: the bridge would no longer be what earns that row.
    """
    async with maker() as db:
        canonical_id, ghost_id = await _seed_derby(db, tag_the_ghost=False)

    served = _event_ids(await search(UNACCENTED_QUERY))

    assert ghost_id in served, (
        f"the untagged ASCII row is the reader's only match and was not served; "
        f"got {served} — the specimen no longer reproduces the defect"
    )
    assert canonical_id not in served, (
        "the accented canonical was reached without the duplicate tag, so the "
        "case above no longer proves the bridge did anything"
    )


async def test_an_untagged_match_is_never_bridged(maker):
    """THE REFUSAL DIRECTION (gotcha #43), at the helper.

    A bridge that fired on an untagged row would resurrect rows the surface
    deliberately declined — the mirror image of the defect, and invisible to
    both cases above, where an untagged ghost prints and the bridge is never
    reached at all.

    🔴 The positive control is not decoration. `bridged_canonical_ids` returns
    `[]` both when it correctly refuses an untagged row and when the arm it was
    handed matches nothing — which is exactly how the lifted version of this
    file passed while its sibling failed. Asserting the arm reaches the ghost
    FIRST is what makes the refusal mean something.
    """
    from sqlalchemy import select

    from app.models.models import Event
    from app.utils.proven_duplicates import bridged_canonical_ids

    async with maker() as db:
        _, ghost_id = await _seed_derby(db, tag_the_ghost=False)

        arm = _route_recall_arm(UNACCENTED_QUERY)

        reached = (await db.execute(select(Event.id).where(arm))).scalars().all()
        assert list(reached) == [ghost_id], (
            f"the arm no longer reaches the ghost ({reached}) — the refusal below "
            f"would pass vacuously"
        )

        assert await bridged_canonical_ids(db, arm, limit=64) == []


def _route_recall_arm(query: str):
    """The event recall arm `/api/events/search` builds for `query`.

    Assembled from the route's OWN primitives in the route's own order
    (`routes/events.py` ~5230–5280) rather than hand-rolled, because a second
    spelling of "what the reader matched" is the drift this module has already
    been repaired for once — and because the near-miss is subtle: the
    single-term branch is a different predicate from the multi-term one, and
    feeding a two-word query to the single-term builder produces an arm that
    matches neither production row.

    It is still a mirror, so it can still drift. The two route-level cases above
    are the guard: they run the real endpoint and would go red if this stopped
    resembling it.
    """
    from sqlalchemy import and_

    from app.routes.events import (
        _apply_search_synonyms,
        _event_name_match,
        _strip_search_scaffolding,
        expand_search_terms,
    )

    terms = _strip_search_scaffolding(query.strip().split())
    expanded = _apply_search_synonyms(expand_search_terms(terms))
    if len(terms) > 1:
        return and_(*[_event_name_match(t, e) for t, e in expanded])
    term, expansion = expanded[0]
    return _event_name_match(term, expansion)
