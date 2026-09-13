"""#5821 — one fixture, one event, when Polymarket publishes it as two containers.

## What a reader saw, on production

`GET /api/events/search?q=Al%20Nassr` (read 2026-09-13 05:18Z) served the same
AFC Champions League Elite match **twice**, as its first two results:

    15311506  Al Ain FC vs Al Nassr Club  live  commence 2026-09-13T03:16:17Z
    15311503  Al Ain FC vs Al Nassr Club  live  commence 2026-09-13T03:46:20Z

Four such pairs were minted in the same 65 seconds. The cause is at the venue and
is entirely structural: Polymarket publishes a soccer fixture as **two Gamma
events**, not one —

    id 1014521  ticker acle-ain-aln-2026-09-15                Al Ain FC vs. Al Nassr Club
    id 1014622  ticker acle-ain-aln-2026-09-15-more-markets   … - More Markets

— read from the venue's own API at 08:45Z. Two ids, so two id-less claims, so
(ruling 048 / gotcha #32, correctly) two CREATEs. `#2871` fixed the *derivative*
suffixes and wrote the seam this ship closes into the source: "The game's own
container market ('- More Markets') does not match this and still creates the
fixture normally."

## What this file gates

`_polymarket_container_sibling_event_id` — the lookup that lets the second
container find the event the first one already holds. The refusal half matters as
much as the finding half, so both are asserted:

* it FINDS the sibling in **either arrival order**, because tonight the companion
  minted FIRST (15311503 at 04:23:51.777Z, base 15311506 at 04:23:52.547Z);
* it REFUSES when the venue's kickoff differs, which is the second of the two
  independent signals notice 40 requires — a rematch between the same two clubs
  shares a title and is not the same fixture;
* it REFUSES a title that merely *starts with* this one's, which is what the
  exact `IN` list buys over a prefix match;
* it REFUSES when the venue gave us no kickoff at all, so every row minted before
  the ingest wrote `venue_game_start` keeps exactly today's behaviour.

## Why the finding half is real PostgreSQL and not a session double

The finding half IS a SQL predicate, and every way it can be wrong is a way a
double cannot see: `market_metadata["venue_game_start"].astext` compares a JSONB
member as text and has no SQLite equivalent; an `IN` list written as a `LIKE`
would sweep in the neighbouring fixture; dropping `FuturesMarket.id != market.id`
would let a row find itself; dropping `event_id.isnot(None)` would return a NULL
and silently unlink the market. A fake session asked for the answer returns the
answer it was handed.

The three REFUSALS that return before any query — wrong source, no kickoff, empty
title — are unit-graded below with `session=None`, which is the assertion that
they never reach the database (the same contract #2020 and #4242 use at this
call site).
"""

import os
from datetime import datetime, timezone

import pytest

from app.tasks import prediction_market_matching as pmm

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

#: The production specimen, with its real Gamma ids, real titles and the real
#: kickoff Polymarket published for it. The kickoff is 2026-09-15 — two days
#: AFTER the `commence_time` both rows were stamped with, which is #5862.
BASE_TITLE = "Al Ain FC vs. Al Nassr Club"
MORE_TITLE = f"{BASE_TITLE} - More Markets"
PROPS_TITLE = f"{BASE_TITLE} - Player Props"
VENUE_START = "2026-09-15T16:00:00+00:00"

#: A fixture with NO container of its own, and a DIFFERENT fixture whose title
#: starts with it. Kept apart from the specimen above so the prefix test cannot
#: pass on the specimen's own legitimate sibling: probing `PREFIX_PROBE_TITLE`
#: has exactly one way to return an event, and that way is a prefix match.
PREFIX_PROBE_TITLE = "Lone FC vs. Rival AC"
NEIGHBOUR_TITLE = f"{PREFIX_PROBE_TITLE} II"
NEIGHBOUR_START = "2026-10-01T18:00:00+00:00"

#: The REVERSE arrival order, which is the one production actually served: the
#: `- More Markets` container holds the event and the base container arrives
#: second. Tonight the companion minted 0.77s before its base.
REVERSE_TITLE = "Reverse FC vs. Order United"
REVERSE_MORE_TITLE = f"{REVERSE_TITLE} - More Markets"
REVERSE_START = "2026-09-20T14:00:00+00:00"

#: A fixture whose base container exists and is LINKED TO NOTHING. Returning its
#: NULL `event_id` would have the caller set `market.event_id = None` and count
#: the row as successfully linked.
ORPHAN_TITLE = "Nobody FC vs. Nowhere SC"
ORPHAN_MORE_TITLE = f"{ORPHAN_TITLE} - More Markets"
ORPHAN_START = "2026-11-05T20:00:00+00:00"

#: A fixture with exactly ONE container, which HOLDS an event. It must not find
#: itself.
LONE_TITLE = "Solo FC vs. Only United"
LONE_START = "2026-11-12T19:30:00+00:00"

#: The only sport key this file creates or deletes. Named once so the teardown's
#: blast radius is readable beside the seeding — CI's `search-recall` job runs
#: every PG gate against ONE database.
SEEDED_SPORT_KEY = "soccer_afc_champions_league_5821"


class _Market:
    """The three attributes the lookup reads, and nothing else."""

    def __init__(self, *, id, name, source="polymarket", venue_game_start=VENUE_START):
        self.id = id
        self.name = name
        self.source = source
        self.market_metadata = (
            {"venue_game_start": venue_game_start} if venue_game_start else {}
        )


class TestTheRefusalsThatNeverReachTheDatabase:
    """`session=None` is the assertion: a query would raise `AttributeError`."""

    @pytest.mark.asyncio
    async def test_a_kalshi_container_is_not_a_polymarket_sibling(self):
        market = _Market(id=1, name=MORE_TITLE, source="kalshi")
        assert (
            await pmm._polymarket_container_sibling_event_id(None, market) is None
        ), "a non-Polymarket row reached the Polymarket container lookup"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("venue_game_start", [None, "", "   "])
    async def test_no_published_kickoff_means_todays_behaviour(self, venue_game_start):
        """The second signal is REQUIRED, not preferred.

        A title match alone is a candidate, never a member (notice 40). Rows
        minted before the ingest wrote `venue_game_start` fall through to the
        CREATE path unchanged — this ship narrows nothing retroactively.
        """
        market = _Market(id=1, name=MORE_TITLE, venue_game_start=venue_game_start)
        assert (
            await pmm._polymarket_container_sibling_event_id(None, market) is None
        ), "a container with no published kickoff was paired on its title alone"

    @pytest.mark.asyncio
    async def test_a_container_suffix_with_no_fixture_in_front_of_it_pairs_to_nothing(
        self,
    ):
        """`_strip_more_markets("- More Markets")` is empty, and an empty base
        name would make the `IN` list `['', ' - More Markets', ' - Player Props']`
        — a key that pairs every untitled row to every other one."""
        market = _Market(id=1, name="- More Markets")
        assert await pmm._polymarket_container_sibling_event_id(None, market) is None


class TestTheSuffixListIsTheInverseOfTheStripper:
    """The two must move together, so the relationship is asserted, not trusted."""

    def test_every_suffix_this_lookup_appends_is_one_the_stripper_removes(self):
        from app.utils.prediction_market_matching import _strip_more_markets

        for suffix in pmm._POLYMARKET_CONTAINER_SUFFIXES:
            assert _strip_more_markets(BASE_TITLE + suffix) == BASE_TITLE, (
                f"the lookup builds a candidate title ending {suffix!r} that "
                "_strip_more_markets does not strip — the two lists have drifted, "
                "and the container wearing it can never find its sibling"
            )


class TestTheRedirectReturnsALinkAndNotAMint:
    """The dict contract the caller's funnel counter reads.

    Asserted on the real function with the lookup stubbed, which also proves the
    redirect sits AHEAD of the create-refusal gates: nothing below it (a sport
    key, a session, a covered-league read) is provided here, so reaching any of
    them would raise rather than return.
    """

    @pytest.mark.asyncio
    async def test_a_found_sibling_returns_its_event_and_says_nothing_was_created(
        self, monkeypatch
    ):
        from app.utils.prediction_market_matching import MatchupInfo

        async def _found(session, market):
            return 15311506

        monkeypatch.setattr(
            pmm, "_polymarket_container_sibling_event_id", _found
        )
        matchup = MatchupInfo("Al Ain FC", "Al Nassr Club", "Al Ain FC", "bare_matchup")
        market = _Market(id=60911050, name=MORE_TITLE)
        market.external_id = "1014622"

        result = await pmm._create_event_from_prediction_market(
            None, matchup, market, datetime(2026, 9, 13, 4, 23, tzinfo=timezone.utc)
        )

        assert result is not None, "the container was refused instead of linked"
        assert result["event_id"] == 15311506
        assert result["auto_created"] is False, (
            "a link that reused an existing row reported itself as a mint — the "
            "auto_created_events counter would hide this ship's whole effect"
        )
        assert result["container_sibling_link"] is True


@pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #5821 sibling "
        "lookup gate (CI job `search-recall` provides one)"
    ),
)
@pytest.mark.asyncio
class TestTheLookupOnRealPostgres:
    """The finding half, against the JSONB predicate it is actually made of."""

    async def test_the_companion_finds_the_event_its_base_already_holds(
        self, seeded
    ):
        session, ids = seeded
        companion = _Market(id=ids[MORE_TITLE], name=MORE_TITLE)
        assert (
            await pmm._polymarket_container_sibling_event_id(session, companion)
            == ids["event"]
        )

    async def test_the_base_finds_the_event_its_companion_already_holds(self, seeded):
        """Tonight's ACTUAL order: the companion minted 0.77s before the base.

        A rule that only taught the companion to look for its base would have
        left this specimen exactly as it was. Its own fixture family, because
        the question is which row holds the event: here the `- More Markets`
        container does, and the BASE is the one arriving second.
        """
        session, ids = seeded
        base = _Market(
            id=ids["unused_probe_id"],
            name=REVERSE_TITLE,
            venue_game_start=REVERSE_START,
        )
        assert (
            await pmm._polymarket_container_sibling_event_id(session, base)
            == ids["reverse_event"]
        )

    async def test_a_player_props_container_pairs_to_the_same_fixture(self, seeded):
        session, ids = seeded
        props = _Market(id=ids[PROPS_TITLE], name=PROPS_TITLE)
        assert (
            await pmm._polymarket_container_sibling_event_id(session, props)
            == ids["event"]
        )

    async def test_a_rematch_at_a_different_kickoff_is_not_this_fixture(self, seeded):
        """The second signal, doing the work it is there for.

        Same two clubs, same two titles, a kickoff a week later. On the title
        alone this pairs; on the venue's kickoff it does not.
        """
        session, ids = seeded
        # A probe id belonging to NO seeded row, so `id != market.id` cannot be
        # what refuses this — the kickoff has to be.
        rematch = _Market(
            id=ids["unused_probe_id"],
            name=MORE_TITLE,
            venue_game_start="2026-09-22T16:00:00+00:00",
        )
        assert (
            await pmm._polymarket_container_sibling_event_id(session, rematch) is None
        ), "a rematch was folded onto the first leg's event by its title"

    async def test_a_title_that_merely_starts_with_this_one_is_not_swept_in(
        self, seeded
    ):
        """What the exact `IN` list buys over a prefix match.

        `PREFIX_PROBE_TITLE` has no container of its own in the table. The only
        row whose title begins with it is `NEIGHBOUR_TITLE`, a different fixture,
        and that row DOES hold an event — so under a `LIKE base || '%'` this
        returns that event, and under the `IN` list it returns nothing. The probe
        carries the neighbour's kickoff too, so the second signal cannot be what
        refuses it.
        """
        session, ids = seeded
        probe = _Market(
            id=ids["unused_probe_id"],
            name=PREFIX_PROBE_TITLE,
            venue_game_start=NEIGHBOUR_START,
        )
        assert (
            await pmm._polymarket_container_sibling_event_id(session, probe) is None
        ), (
            "a different fixture was paired because its title shares a prefix — "
            f"returned the event held by {NEIGHBOUR_TITLE!r}"
        )

    async def test_a_row_never_finds_itself(self, seeded):
        """`FuturesMarket.id != market.id`. Without it the FIRST container to
        arrive links to its own event — which, on the CREATE path, does not exist
        yet, but on a re-poll would make every already-linked row look paired and
        mask a genuine twin."""
        session, ids = seeded
        lone = _Market(
            id=ids["lone"], name=LONE_TITLE, venue_game_start=LONE_START
        )
        assert await pmm._polymarket_container_sibling_event_id(session, lone) is None

    async def test_an_unlinked_sibling_does_not_shadow_the_linked_one(self, seeded):
        """A half-ingested family still pairs, and never answers NULL.

        Returning a NULL `event_id` would have the caller run
        `market.event_id = None` and count the row as successfully linked — a
        silent UNLINK dressed as this ship's own success.

        Two mechanisms prevent it and they are load-bearing TOGETHER, which is
        why this asserts the outcome rather than either clause:
        `event_id.isnot(None)` drops the unlinked row from the candidate set,
        and `ORDER BY event_id` sorts NULLs last in PostgreSQL. Deleting just one
        leaves the behaviour correct, so a guard naming just one could never
        fail; deleting the clause AND writing `NULLS FIRST` reds this.

        The family: an UNLINKED base container and a LINKED companion. The probe
        is the third container form, which no row carries.
        """
        session, ids = seeded
        probe = _Market(
            id=ids["unused_probe_id"],
            name=f"{ORPHAN_TITLE} - Player Props",
            venue_game_start=ORPHAN_START,
        )
        assert (
            await pmm._polymarket_container_sibling_event_id(session, probe)
            == ids["orphan_event"]
        ), "the unlinked sibling shadowed the linked one and answered NULL"


@pytest.fixture
async def seeded():
    """Real Postgres, the specimen population, torn down by title.

    Scoped by the exact titles this file writes rather than by a bare DELETE:
    CI's `search-recall` job runs every PG gate against ONE database, so a
    table-wide delete here is this file reaching into another gate's rows.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.models.models import Event, FuturesMarket, Sport
    from app.services.database import Base

    titles = [
        BASE_TITLE, MORE_TITLE, PROPS_TITLE, NEIGHBOUR_TITLE,
        LONE_TITLE,
        ORPHAN_TITLE,
        ORPHAN_MORE_TITLE,
        f"{ORPHAN_TITLE} - Player Props",
        REVERSE_MORE_TITLE,
    ]
    seeded_home_teams = [
        "Al Ain FC", "Lone FC", "Reverse FC", "Solo FC", "Nobody FC",
    ]

    def _closure(*roots):
        seen: dict = {}
        pending = list(roots)
        while pending:
            table = pending.pop()
            if table.key in seen:
                continue
            seen[table.key] = table
            for fk in table.foreign_keys:
                pending.append(fk.column.table)
        return list(seen.values())

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync: Base.metadata.create_all(
                sync,
                tables=_closure(
                    Sport.__table__, Event.__table__, FuturesMarket.__table__
                ),
                checkfirst=True,
            )
        )
        await conn.execute(
            text("DELETE FROM futures_markets WHERE name = ANY(:t)"), {"t": titles}
        )
        await conn.execute(
            text("DELETE FROM events WHERE home_team_name = ANY(:h)"),
            {"h": seeded_home_teams},
        )
        await conn.execute(
            text("DELETE FROM sports WHERE key = :k"), {"k": SEEDED_SPORT_KEY}
        )

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        from sqlalchemy import text as _text

        sport_id = (
            await session.execute(
                _text(
                    "INSERT INTO sports (key, name, active) "
                    "VALUES (:k, :k, TRUE) RETURNING id"
                ),
                {"k": SEEDED_SPORT_KEY},
            )
        ).scalar()

        async def _event(home, away, start):
            return (
                await session.execute(
                    _text(
                        "INSERT INTO events (sport_id, home_team_name, "
                        "away_team_name, commence_time, status) "
                        "VALUES (:sp, :h, :a, :s, 'scheduled') RETURNING id"
                    ),
                    {
                        "sp": sport_id,
                        "h": home,
                        "a": away,
                        "s": datetime.fromisoformat(start),
                    },
                )
            ).scalar()

        event_id = await _event("Al Ain FC", "Al Nassr Club", VENUE_START)
        neighbour_event_id = await _event("Lone FC", "Rival AC II", NEIGHBOUR_START)
        reverse_event_id = await _event(
            "Reverse FC", "Order United", REVERSE_START
        )
        lone_event_id = await _event("Solo FC", "Only United", LONE_START)
        orphan_event_id = await _event("Nobody FC", "Nowhere SC", ORPHAN_START)

        async def _market(name, *, event=None, vgs=VENUE_START):
            return (
                await session.execute(
                    _text(
                        "INSERT INTO futures_markets "
                        "  (source, external_id, name, category, "
                        "   mutually_exclusive, status, event_id, "
                        "   market_metadata) "
                        "VALUES ('polymarket', :ext, :n, 'sports', "
                        "        FALSE, 'open', :e, "
                        # CAST, because asyncpg infers parameter types from the
                        # server and jsonb_build_object's value argument is
                        # `anyelement` — it raises IndeterminateDatatypeError
                        # rather than defaulting to text.
                        "        jsonb_build_object('venue_game_start', "
                        "                           CAST(:v AS text))) "
                        "RETURNING id"
                    ),
                    {"ext": f"seed-{name}", "n": name, "e": event, "v": vgs},
                )
            ).scalar()

        ids = {
            # The base container holds the event; the companion and the props
            # container do not. Each test asks from the side it needs.
            BASE_TITLE: await _market(BASE_TITLE, event=event_id),
            MORE_TITLE: await _market(MORE_TITLE),
            PROPS_TITLE: await _market(PROPS_TITLE),
            # The prefix trap: a DIFFERENT fixture, holding its own event, whose
            # title begins with PREFIX_PROBE_TITLE. `PREFIX_PROBE_TITLE` itself
            # is deliberately NOT seeded — so a probe for it has exactly one way
            # to come back with an event, and that way is a prefix match.
            NEIGHBOUR_TITLE: await _market(
                NEIGHBOUR_TITLE, event=neighbour_event_id, vgs=NEIGHBOUR_START
            ),
            # The self-exclusion family: ONE container, and it HOLDS an event.
            # It must not find itself. Linked deliberately — an unlinked row
            # would be refused by `event_id.isnot(None)` instead, and the test
            # would pass with the self-exclusion clause deleted.
            "lone": await _market(
                LONE_TITLE, event=lone_event_id, vgs=LONE_START
            ),
            # The orphan family: the BASE exists and holds NO event. The probe
            # is its COMPANION, under an id no row carries — so neither
            # `id != market.id` nor the title list nor the kickoff can be what
            # refuses it. Only `event_id.isnot(None)` can.
            ORPHAN_TITLE: await _market(ORPHAN_TITLE, vgs=ORPHAN_START),
            ORPHAN_MORE_TITLE: await _market(
                ORPHAN_MORE_TITLE, event=orphan_event_id, vgs=ORPHAN_START
            ),
            # The reverse family: only the COMPANION exists, and it holds the
            # event. The base title is deliberately absent from the table.
            REVERSE_MORE_TITLE: await _market(
                REVERSE_MORE_TITLE, event=reverse_event_id, vgs=REVERSE_START
            ),
            "event": event_id,
            "neighbour_event": neighbour_event_id,
            "reverse_event": reverse_event_id,
            "orphan_event": orphan_event_id,
        }
        # An id no seeded row carries, so a probe using it is never refused by
        # `FuturesMarket.id != market.id`. Derived from the seeded ids rather
        # than hardcoded, because a literal could collide with a serial value.
        ids["unused_probe_id"] = max(
            v for k, v in ids.items() if isinstance(v, int)
        ) + 1000
        await session.commit()

        yield session, ids

    async with engine.begin() as conn:
        from sqlalchemy import text as _t

        await conn.execute(
            _t("DELETE FROM futures_markets WHERE name = ANY(:t)"), {"t": titles}
        )
        await conn.execute(
            _t("DELETE FROM events WHERE id = ANY(:e)"),
            {
                "e": [
                    event_id, neighbour_event_id, reverse_event_id,
                    lone_event_id, orphan_event_id,
                ]
            },
        )
        await conn.execute(
            _t("DELETE FROM sports WHERE key = :k"), {"k": SEEDED_SPORT_KEY}
        )
    await engine.dispose()
