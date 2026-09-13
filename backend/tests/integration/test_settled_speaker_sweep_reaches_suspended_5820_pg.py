"""#5820 / CERT-2787 — the SUSPENDED cohort is selected and retired, on real Postgres.

## What the BLOCK found, and why it needed a database to be caught

The settled-speaker clause shipped correct and unreachable. On the 15-minute
matcher it is only ever asked about rows **Phase 2 selected**, and Phase 2
selects::

    Event.status IN ('scheduled', 'live')
      OR (Event.status IN ('completed', 'closed') AND commence_time >= now - 24h)

Measured on production 2026-09-13 05:16Z, of the 150 resultless events
publishing a settled speaker, **144 are `suspended`** — including the issue's own
specimen, `/events/15310861` (Liu vs Blinkova), hero 99% – 1% over "No result
reported". The other live writer cannot rescue them: the WebSocket fast lane
recomputes only after a price batch, and a settled book is entitled never to
tick again. So the stored 0.99 could stand forever while every gate in the stack
agreed it was inadmissible.

`_phase2c_settled_speaker_sweep` is the scheduled path that selects them. Its
sibling unit file (`tests/test_settled_speaker_without_result_5820.py`, section
6) compiles the screen and drives the decision through a fake session — worth
having, and unable to prove the thing that matters here: **which rows come
back.** That is a property of `jsonb_exists` over a JSONB column, of a
correlated `EXISTS` over `futures_markets` with a second `EXISTS` over
`futures_outcomes` inside it, and of an expanding bind — none of which a fake
session evaluates, and the first of which does not exist outside PostgreSQL.
The 18 tests that shipped with the clause all passed against a build whose reach
was zero.

## The population seeded below, and what each row is for

    specimen      suspended, no result, market 'resolved'      RETIRED  <- the ship
    graded_open   suspended, no result, market 'open' + winner RETIRED  <- gotcha #33
    completed     completed_at set, market 'resolved'          KEPT     <- the 221
    unsettled     suspended, no result, market 'open', priced  KEPT     <- transient
    ancient       10 days old, no result, market 'resolved'    KEPT     <- the floor
    unplayed      kicks off in 6h, market 'resolved'           KEPT     <- #5771's

The four KEPT rows are the load-bearing half (gotcha #43): a sweep that retires
everything passes the first two assertions and destroys the number 221 finished
games are supposed to show.

There is no local Postgres in the agent sandbox (`initdb` dies on `shmget`), so
CI is the environment that runs this — the `search-recall` job, whose
skip-detector refuses to let an unrun gate read as a passing one.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the #5820 settled-speaker "
            "sweep gate against real Postgres (CI job `search-recall`)"
        ),
    ),
]

UTC = timezone.utc

HOME = "Claire Liu"
AWAY = "Anna Blinkova"

#: The stored leg every seeded event publishes. `espn` rides along on purpose:
#: a retirement removes ONE source key, and a sweep that clears the column would
#: pass every kalshi assertion in this file.
def _frozen_wps(source: str = "kalshi", value: float = 0.99) -> dict:
    return {
        source: {"value": value, "updated_at": "2026-09-13T03:53:13.405235+00:00"},
        "espn": {"value": 0.5, "updated_at": "2026-09-13T03:00:00+00:00"},
    }


@pytest.fixture
async def pg_session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    # Importing a name off the models module executes it, and executing it is
    # what registers every table on `Base` for `create_all`. One import STYLE
    # across the file (`from ... import ...`) — mixing it with `import x.y` is
    # CodeQL's `py/import-and-import-from`.
    from app.models.models import Event  # noqa: F401
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session

    await engine.dispose()


async def _seed(session, now) -> dict[str, int]:
    """The six rows above. Returns `{label: event_id}`."""
    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport

    sport = Sport(key="tennis_wta", name="WTA", group="Tennis")
    session.add(sport)
    await session.flush()

    ids: dict[str, int] = {}

    async def _row(
        label,
        *,
        hours_ago,
        status,
        completed,
        markets,
        source="kalshi",
    ):
        """`markets` is a list of `(suffix, name, status, outcomes, graded)`."""
        event = Event(
            sport_id=sport.id,
            external_id=f"test:{label}",
            home_team_name=HOME,
            away_team_name=AWAY,
            commence_time=now - timedelta(hours=hours_ago),
            status=status,
            completed_at=(now - timedelta(hours=1)) if completed else None,
            win_probability_sources=_frozen_wps(source),
        )
        session.add(event)
        await session.flush()

        for suffix, name, market_status, outcomes, graded in markets:
            market = FuturesMarket(
                source=source,
                external_id=f"KXWTAMATCH-{label.upper()}-{suffix}",
                name=name,
                category="sports",
                market_type="winner",
                market_tier=3,
                status=market_status,
                event_id=event.id,
                resolution_date=now + timedelta(days=1),
            )
            session.add(market)
            await session.flush()

            for rank, (outcome_name, probability) in enumerate(outcomes, start=1):
                session.add(
                    FuturesOutcome(
                        market_id=market.id,
                        external_id=f"{market.external_id}-{rank}",
                        name=outcome_name,
                        rank=rank,
                        current_probability=probability,
                        opening_probability=0.5,
                        is_winner=bool(graded and rank == 1),
                        last_updated=now,
                    )
                )
            await session.flush()
        ids[label] = event.id

    def _winner(status, *, graded=False, probabilities=(0.99, 0.01)):
        return [
            (
                "W",
                f"{HOME} vs {AWAY}",
                status,
                ((HOME, probabilities[0]), (AWAY, probabilities[1])),
                graded,
            )
        ]

    # ── the two the ship is for ──────────────────────────────────────────────
    await _row(
        "specimen",
        hours_ago=5,
        status="suspended",
        completed=False,
        markets=_winner("resolved"),
    )
    await _row(
        "graded_open",
        hours_ago=4,
        status="suspended",
        completed=False,
        # Kalshi leaves settled markets `status='open'` (gotcha #33); only the
        # crowned outcome says the question is closed.
        markets=_winner("open", graded=True),
    )
    # ── the five that must survive ───────────────────────────────────────────
    await _row(
        "completed",
        hours_ago=6,
        status="completed",
        completed=True,
        markets=_winner("resolved", graded=True),
    )
    await _row(
        "unsettled",
        hours_ago=3,
        status="suspended",
        completed=False,
        markets=_winner("open", probabilities=(0.64, 0.36)),
    )
    await _row(
        "ancient",
        hours_ago=24 * 10,
        status="suspended",
        completed=False,
        markets=_winner("resolved"),
    )
    await _row(
        "unplayed",
        hours_ago=-6,  # kicks off in six hours
        status="scheduled",
        completed=False,
        markets=_winner("resolved"),
    )
    # The one-cause discriminator. A Polymarket group of nothing but Exact
    # Score derivatives has no market ADMITTED to speak for the winner at all,
    # so it is silent for #5031's reason and not for this ship's. #5031's
    # retirement reaches Phase 2's population by design; whether it should also
    # reach the suspended cohort has never been measured, and a retirement is
    # destructive. The sweep therefore abstains — and this row is the only thing
    # in the fixture that can tell a sweep which asks "is this ONE cause?" from
    # one which asks "is this group silent?".
    await _row(
        "derivative",
        hours_ago=2,
        status="suspended",
        completed=False,
        source="polymarket",
        markets=[
            (
                "EXACT1",
                f"{HOME} vs. {AWAY} - Exact Score",
                "resolved",
                (("2 - 0", 1.0), ("1 - 2", 0.0)),
                False,
            ),
            (
                "EXACT2",
                f"{HOME} vs. {AWAY} - Exact Score",
                "open",
                (("2 - 1", 0.41), ("0 - 2", 0.59)),
                False,
            ),
        ],
    )

    await session.commit()
    return ids


async def _sweep(session, now, *, seconds_left=600.0):
    from app.tasks.prediction_market_matching import _phase2c_settled_speaker_sweep

    stats = {"funnel": {}, "errors": []}
    retired = await _phase2c_settled_speaker_sweep(
        session, now, stats, lambda: seconds_left
    )
    return stats, retired


async def _sources(session, event_id):
    return (
        await session.execute(
            text("SELECT win_probability_sources FROM events WHERE id = :i"),
            {"i": event_id},
        )
    ).scalar_one()


class TestTheSweepReachesWhatPhase2CannotSelect:
    async def test_suspended_settled_speaker_is_selected_and_retired_5820(
        self, pg_session
    ):
        """The ship, end to end on real rows: 144 of 150 stop publishing 0.99.

        The event is `suspended`, which is the status Phase 2's selector does
        not list, and it holds a `resolved` Kalshi market — the exact shape of
        `/events/15310861`.
        """
        now = datetime.now(UTC)
        ids = await _seed(pg_session, now)

        before = await _sources(pg_session, ids["specimen"])
        assert before["kalshi"]["value"] == 0.99, (
            "precondition: the frozen leg must be stored, or this proves nothing"
        )

        stats, retired = await _sweep(pg_session, now)

        after = await _sources(pg_session, ids["specimen"])
        assert "kalshi" not in after, (
            "the suspended specimen still publishes a settled market's price as "
            "its live probability — the sweep never selected it"
        )
        assert after["espn"]["value"] == 0.5, (
            "a retirement removes ONE source key and never touches a sibling"
        )
        assert retired == 2, "the specimen and the gotcha #33 row are the ship"
        assert stats["funnel"]["blend_source_retired_settled_without_result"] == 2
        assert stats["errors"] == []

    async def test_a_market_kalshi_left_open_is_still_selected_by_its_grade(
        self, pg_session
    ):
        """gotcha #33 through the SQL screen, not just the Python predicate.

        The screen's status arm cannot see this row: Kalshi settled the market
        and left `status='open'`. It is selected by the crowned outcome, which
        is the `EXISTS ... is_winner IS TRUE` half — a correlated subquery
        inside a correlated subquery, and nothing a fake session evaluates.
        """
        now = datetime.now(UTC)
        ids = await _seed(pg_session, now)

        await _sweep(pg_session, now)

        assert "kalshi" not in await _sources(pg_session, ids["graded_open"])

    async def test_it_writes_no_snapshot_for_a_game_still_unresolved(self, pg_session):
        """A withdrawal may not draw a new point on an unfinished chart (0t-1)."""
        now = datetime.now(UTC)
        await _seed(pg_session, now)

        await _sweep(pg_session, now)

        count = (
            await pg_session.execute(text("SELECT count(*) FROM win_prob_snapshots"))
        ).scalar_one()
        assert count == 0, "the sweep wrote a win_prob_snapshots row"

    async def test_it_is_idempotent_and_drains_its_own_population(self, pg_session):
        """The screen demands the key be PRESENT, so a retired row leaves.

        Without that the sweep would re-decide the same events every fifteen
        minutes forever, and a page of refusals could pin the cap.
        """
        now = datetime.now(UTC)
        ids = await _seed(pg_session, now)

        _, first = await _sweep(pg_session, now)
        stats, second = await _sweep(pg_session, now)

        assert first == 2
        assert second == 0, "the sweep retired the same legs twice"
        assert stats["funnel"]["phase2c_events_scanned"] == 1, (
            "a retired event is still a candidate — the population never drains"
        )
        # The one that stays is the refusal, and it is the reason the cap must
        # never bind: a refused candidate costs one in-memory decision forever.
        assert "kalshi" not in await _sources(pg_session, ids["specimen"])


class TestTheRowsThatMustSurvive:
    """gotcha #43's other direction, and it is the load-bearing one."""

    async def test_a_completed_event_keeps_the_number_it_is_supposed_to_show(
        self, pg_session
    ):
        """The 221. "Settled means settled" — a finished game shows its result."""
        now = datetime.now(UTC)
        ids = await _seed(pg_session, now)

        await _sweep(pg_session, now)

        kept = await _sources(pg_session, ids["completed"])
        assert kept["kalshi"]["value"] == 0.99, (
            "a finished game lost the settled price that IS its result"
        )

    async def test_a_live_book_on_a_resultless_event_is_untouched(self, pg_session):
        """The transient case: 0.64 is a price, not a settlement."""
        now = datetime.now(UTC)
        ids = await _seed(pg_session, now)

        await _sweep(pg_session, now)

        kept = await _sources(pg_session, ids["unsettled"])
        assert kept["kalshi"]["value"] == 0.99

    async def test_the_floor_and_the_kickoff_line_bound_the_scan(self, pg_session):
        """Both ends (gotcha #41), and the second is another lane's boundary.

        A market that settles BEFORE its event starts is #5771's pre-kickoff
        withdrawal; this scan must not become a second writer on it.
        """
        now = datetime.now(UTC)
        ids = await _seed(pg_session, now)

        await _sweep(pg_session, now)

        assert (await _sources(pg_session, ids["ancient"]))["kalshi"]["value"] == 0.99
        assert (await _sources(pg_session, ids["unplayed"]))["kalshi"]["value"] == 0.99

    async def test_a_group_silent_for_another_reason_keeps_its_leg(self, pg_session):
        """Property 2: this sweep retires for ONE cause.

        The Polymarket row holds nothing but Exact Score derivatives, so no
        market in it is admitted to speak for the winner at all — #5031's
        silence, whose retirement reaches Phase 2's population deliberately and
        has never been measured over the suspended cohort. Drop the one-cause
        gate and this leg disappears, which is a reach nobody asked for and
        nobody could undo.
        """
        now = datetime.now(UTC)
        ids = await _seed(pg_session, now)

        stats, _ = await _sweep(pg_session, now)

        kept = await _sources(pg_session, ids["derivative"])
        assert "polymarket" in kept, (
            "the sweep retired a leg for #5031's cause — its reach is supposed "
            "to be the settled-speaker clause and nothing else"
        )
        assert "blend_source_retired_no_winner_market" not in stats["funnel"]

    async def test_the_screen_admits_exactly_three_and_the_decision_refuses_one(
        self, pg_session
    ):
        """The reach claim, asserted from the funnel.

        Seven events in the table. Four are excluded by the SCREEN — so a
        widening of the query shows up here before it shows up as a lost
        number — and of the three it admits, the DECISION refuses one.
        """
        now = datetime.now(UTC)
        await _seed(pg_session, now)

        stats, retired = await _sweep(pg_session, now)

        assert stats["funnel"]["phase2c_events_scanned"] == 3
        assert retired == 2
        assert stats["funnel"]["phase2c_ceiling_hit"] is False
