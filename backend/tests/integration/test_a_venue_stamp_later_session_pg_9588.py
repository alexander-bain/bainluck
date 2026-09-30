"""A venue stamp does not start a match our StatPal schedule puts later. #9588, real Postgres.

``/events/15320754`` Bublik / Shang v Cerundolo / Rinderknech read LIVE from
05:00Z 9/29, Kalshi's expiry stamp, while its own StatPal anchor
(``tennis:2638141``) had it at the next day's Beijing session. The unit file
(``tests/test_a_venue_stamp_does_not_start_a_later_session_9588.py``) hands the
loop its anchor rows. This file lets Postgres answer the read, because it rides
on SQL a fake cannot see: ``claim_context->>'statpal_start_time'`` out of JSONB,
``ANY(:event_ids)`` bound by asyncpg, and the anchor's ``source_id`` matched to
the row's current fixture.

Each case seeds real ``events`` and ``event_provider_anchors`` rows, runs the
real ``_transition_event_statuses_impl``, and reads the status back.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

#: The #7617 step's disposable database, the same one the #8755 step reuses.
#: This file drops and creates only the tables it names, after that step.
DB_URL = os.environ.get("DELAY_CONTRACT_DATABASE_URL")

pytestmark = [pytest.mark.asyncio]

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set DELAY_CONTRACT_DATABASE_URL to run the real-Postgres later-session "
        "contract (CI job `search-recall` provisions a disposable one)"
    ),
)


#: What a pass that read the row writes, computed from the seed's own clock.
EXPECTED_STAMPS: dict = {}


async def _seed(session):
    from app.models.models import Event, EventProviderAnchor, Sport
    from app.utils.event_completion import (
        STATPAL_LATER_SESSION_KEY,
        statpal_later_session_value,
        statpal_released_session_value,
    )

    now = datetime.now(timezone.utc)
    tennis = Sport(key="tennis_atp", name="ATP")
    session.add(tennis)
    await session.flush()

    def _match(
        name, *, commence, source="kalshi", status="scheduled", fixture, sources=None
    ):
        return Event(
            sport_id=tennis.id,
            home_team_name=f"{name} A / B",
            away_team_name=f"{name} C / D",
            commence_time=commence,
            commence_time_source=source,
            status=status,
            statpal_fixture_id=fixture,
            win_probability_sources=sources,
        )

    rows = {
        # THE SHIP: Kalshi stamp an hour ago, StatPal session tomorrow.
        "the_held_match": _match(
            "Held", commence=now - timedelta(hours=1), fixture="958801"
        ),
        # THE REPAIR: already promoted, 3h past its stamp (inside the staleness
        # arm's read), StatPal session still ahead.
        "the_promoted_match": _match(
            "Promoted",
            commence=now - timedelta(hours=3),
            status="live",
            fixture="958802",
        ),
        # THE KILL CONTROL: StatPal's session has begun, so the clock runs.
        "the_session_reached": _match(
            "Reached", commence=now - timedelta(hours=2), fixture="958803"
        ),
        # The anchor names a fixture the row no longer carries: says nothing.
        "the_stale_fixture": _match(
            "Stale", commence=now - timedelta(hours=1), fixture="958804"
        ),
        # The census counterexample: a reported start is not overruled.
        "the_reported_start": _match(
            "Reported",
            commence=now - timedelta(hours=1),
            source="odds_api",
            fixture="958805",
        ),
        # #9613, THE BAND: 30h past its venue stamp (outside the promoter's 24h
        # window) and still held, StatPal's session 4h ahead. The stamp is
        # what brings it back into the read. RED before #9613: never read,
        # so the stamp was never maintained.
        "the_old_held_match": _match(
            "OldHeld",
            commence=now - timedelta(hours=30),
            fixture="958806",
            # Seeded an hour off the anchor, so only a pass that READ the row
            # can leave it at the anchor's start.
            sources={STATPAL_LATER_SESSION_KEY: (now + timedelta(hours=3)).isoformat()},
        ),
        # THE WINDOW CONTROL: the same shape with no stamp is ancient. A read
        # that dropped the 24h bound for everyone stamps it and fails here.
        "the_old_unstamped_match": _match(
            "OldBare", commence=now - timedelta(hours=30), fixture="958807"
        ),
        # #9613, THE CLOCK: StatPal's session began 5 minutes ago, 29h55m after
        # the venue stamp. Promoted, and on the same pass NOT suspended, because
        # its clock starts at StatPal's start. RED before #9613: never read.
        "the_old_released_match": _match(
            "OldReleased",
            commence=now - timedelta(hours=30),
            fixture="958808",
            sources={
                STATPAL_LATER_SESSION_KEY: (now - timedelta(minutes=5)).isoformat()
            },
        ),
        # #9588 AFTER-CHECK, THE THIRD DOOR: already suspended by the staleness
        # arm, 33h past its Kalshi stamp, and StatPal's session is 12h ahead
        # (15320752, Cash / Erler v Luz / Matos, 14:06Z 9/30). RED before: no
        # arm read a suspended row, so it read "No result reported".
        "the_suspended_held_match": _match(
            "SuspHeld",
            commence=now - timedelta(hours=33),
            status="suspended",
            fixture="958809",
        ),
        # THE BAND: 60h past its stamp, StatPal 9h ahead, a 69h gap (15320753,
        # Kalshi 05:00Z 9/29, StatPal 02:00Z 10/2). RED at the 48h band: the
        # hold failed OPEN and the row stayed suspended.
        "the_suspended_far_match": _match(
            "SuspFar",
            commence=now - timedelta(hours=60),
            status="suspended",
            fixture="958810",
        ),
        # THE SETTLEMENT CONTROL: the same shape with a resolved market. The
        # venue may have ended it, and rung 2 writes `suspended` too.
        "the_suspended_settled_match": _match(
            "SuspSettled",
            commence=now - timedelta(hours=33),
            status="suspended",
            fixture="958811",
        ),
        # THE KILL CONTROL: StatPal's session began an hour ago. An arm that
        # un-suspended every anchored Kalshi row passes the ship and fails here.
        "the_suspended_reached_match": _match(
            "SuspReached",
            commence=now - timedelta(hours=33),
            status="suspended",
            fixture="958812",
        ),
    }
    session.add_all(list(rows.values()))
    await session.flush()

    from app.models.models import FuturesMarket

    session.add(
        FuturesMarket(
            source="kalshi",
            external_id="KXATPDOUBLES-9588SETTLED",
            sport_id=tennis.id,
            name="SuspSettled A / B vs SuspSettled C / D",
            category="sports",
            commence_time=now - timedelta(hours=33),
            status="resolved",
            event_id=rows["the_suspended_settled_match"].id,
        )
    )

    def _anchor(name, source_id, start):
        session.add(
            EventProviderAnchor(
                event_id=rows[name].id,
                source="statpal",
                source_id=source_id,
                id_kind="game",
                claim_context={
                    "written_by": "link_tennis_statpal_fixtures",
                    "statpal_start_time": start.isoformat(),
                },
            )
        )

    tomorrow = now + timedelta(hours=17)
    _anchor("the_held_match", "tennis:958801", tomorrow)
    _anchor("the_promoted_match", "tennis:958802", tomorrow)
    _anchor("the_session_reached", "tennis:958803", now - timedelta(minutes=10))
    _anchor("the_stale_fixture", "tennis:111111", tomorrow)
    _anchor("the_reported_start", "tennis:958805", tomorrow)
    _anchor("the_old_held_match", "tennis:958806", now + timedelta(hours=4))
    EXPECTED_STAMPS["the_old_held_match"] = statpal_later_session_value(
        now + timedelta(hours=4)
    )
    _anchor("the_old_unstamped_match", "tennis:958807", now + timedelta(hours=4))
    _anchor("the_old_released_match", "tennis:958808", now - timedelta(minutes=5))
    EXPECTED_STAMPS["receipt:the_old_released_match"] = statpal_released_session_value(
        now - timedelta(minutes=5), "958808"
    )
    _anchor("the_suspended_held_match", "tennis:958809", now + timedelta(hours=12))
    EXPECTED_STAMPS["the_suspended_held_match"] = statpal_later_session_value(
        now + timedelta(hours=12)
    )
    _anchor("the_suspended_far_match", "tennis:958810", now + timedelta(hours=9))
    _anchor("the_suspended_settled_match", "tennis:958811", now + timedelta(hours=12))
    _anchor("the_suspended_reached_match", "tennis:958812", now - timedelta(hours=1))

    await session.commit()
    return {name: row.id for name, row in rows.items()}


@pytest.fixture
async def seeded():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    wanted = [
        Base.metadata.tables[name]
        for name in (
            "sports",
            "teams",
            "venues",
            "events",
            "event_provider_anchors",
            "odds_snapshots",
            "win_prob_snapshots",
            "futures_markets",
            "futures_outcomes",
        )
    ]

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=wanted, checkfirst=True)
        await conn.run_sync(Base.metadata.create_all, tables=wanted)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        ids = await _seed(session)

    yield maker, ids

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=wanted, checkfirst=True)
    await engine.dispose()


@pytest.fixture
async def statuses(seeded):
    import contextlib
    from unittest.mock import patch

    from sqlalchemy import select

    from app.models.models import Event

    maker, ids = seeded

    @contextlib.asynccontextmanager
    async def _session(**_kwargs):
        async with maker() as session:
            yield session
            await session.commit()

    from app.tasks.espn_sync import _transition_event_statuses_impl

    with patch("app.tasks.base.get_task_session", _session):
        stats = await _transition_event_statuses_impl()

    async with maker() as session:
        rows = (
            await session.execute(
                select(Event.id, Event.status).where(Event.id.in_(list(ids.values())))
            )
        ).all()

    by_id = {row.id: row.status for row in rows}
    return {name: by_id[event_id] for name, event_id in ids.items()}, stats


@pytest.fixture
async def stamps_after(seeded, statuses):
    """Each row's #9613 stamp as the run left it (None when absent)."""
    from sqlalchemy import select

    from app.models.models import Event
    from app.utils.event_completion import STATPAL_LATER_SESSION_KEY

    maker, ids = seeded
    async with maker() as session:
        rows = (
            await session.execute(
                select(Event.id, Event.win_probability_sources).where(
                    Event.id.in_(list(ids.values()))
                )
            )
        ).all()
    by_id = {
        row.id: (row.win_probability_sources or {}).get(STATPAL_LATER_SESSION_KEY)
        for row in rows
    }
    return {name: by_id[event_id] for name, event_id in ids.items()}


@pytest.fixture
async def played_second_pass(seeded, statuses):
    """CERT-3811's second pass, on Postgres. After the first pass released
    ``the_old_released_match``, StatPal writes play onto it (a period and a
    score, Core update as the livescores writer does, no win-prob snapshot),
    and the task runs again. Returns (receipt after pass 1, status, stats)."""
    import contextlib
    from unittest.mock import patch

    from sqlalchemy import select, update

    from app.models.models import Event
    from app.utils.event_completion import STATPAL_RELEASED_SESSION_KEY

    maker, ids = seeded
    event_id = ids["the_old_released_match"]
    async with maker() as session:
        receipt = (
            await session.execute(
                select(Event.win_probability_sources).where(Event.id == event_id)
            )
        ).scalar_one()
        await session.execute(
            update(Event)
            .where(Event.id == event_id)
            .values(period="1st Set", home_score=0, away_score=0)
        )
        await session.commit()

    @contextlib.asynccontextmanager
    async def _session(**_kwargs):
        async with maker() as session:
            yield session
            await session.commit()

    from app.tasks.espn_sync import _transition_event_statuses_impl

    with patch("app.tasks.base.get_task_session", _session):
        stats = await _transition_event_statuses_impl()

    async with maker() as session:
        status = (
            await session.execute(select(Event.status).where(Event.id == event_id))
        ).scalar_one()
    return (receipt or {}).get(STATPAL_RELEASED_SESSION_KEY), status, stats


@needs_postgres
class TestAReleasedSessionKeepsItsClockOncePlayed:
    async def test_the_release_receipt_is_persisted(self, played_second_pass):
        """The JSONB round trip: the first pass's ORM write of a new sources
        dict lands, carrying StatPal's start and its fixture."""
        receipt, _, _ = played_second_pass
        assert receipt == EXPECTED_STAMPS["receipt:the_old_released_match"]

    async def test_played_it_stays_live_on_statpals_clock(self, played_second_pass):
        """THE SHIP, CERT-3811. RED at f6d229bc23: play ends the hold's
        predicate, the clock falls back to the 30h-old venue stamp, and the
        match being played is suspended."""
        _, status, stats = played_second_pass
        assert status == "live"
        assert stats["live_to_suspended"] == 0


@needs_postgres
class TestAVenueStampDoesNotStartALaterSession:
    async def test_the_held_match_stays_scheduled(self, statuses):
        """THE SHIP. RED before #9588: promoted on Kalshi's stamp.

        Two holds: this row and #9613's ``the_old_held_match``."""
        by_case, stats = statuses
        assert by_case["the_held_match"] == "scheduled"
        assert stats["held_statpal_later_session"] == 2

    async def test_the_promoted_match_goes_back(self, statuses):
        by_case, stats = statuses
        assert by_case["the_promoted_match"] == "scheduled"
        assert stats["demoted_statpal_later_session"] == 1

    async def test_a_reached_session_goes_live(self, statuses):
        """THE KILL CONTROL. A hold that refused every anchored Kalshi row
        passes the ship and fails here."""
        by_case, _ = statuses
        assert by_case["the_session_reached"] == "live"

    async def test_an_anchor_for_another_fixture_says_nothing(self, statuses):
        by_case, _ = statuses
        assert by_case["the_stale_fixture"] == "live"

    async def test_a_reported_start_is_not_overruled(self, statuses):
        by_case, _ = statuses
        assert by_case["the_reported_start"] == "live"

    async def test_an_old_held_match_is_still_maintained(self, statuses, stamps_after):
        """#9613, THE BAND. The stamp brought a 30h-old row back into the read,
        the hold ran on it, and the stamp is StatPal's start, rewritten from
        the anchor rather than left over from the seed."""
        by_case, _ = statuses
        assert by_case["the_old_held_match"] == "scheduled"
        assert stamps_after["the_old_held_match"] == EXPECTED_STAMPS["the_old_held_match"]

    async def test_an_old_unstamped_row_is_still_ancient(self, statuses, stamps_after):
        """THE WINDOW CONTROL. Outside 24h and never held: nothing touches it."""
        by_case, _ = statuses
        assert by_case["the_old_unstamped_match"] == "scheduled"
        assert stamps_after["the_old_unstamped_match"] is None

    async def test_a_released_old_match_goes_live_and_stays_live(
        self, statuses, stamps_after
    ):
        """#9613, THE CLOCK. Promoted at StatPal's start and, on the same pass,
        measured from it: 5 minutes, not 30 hours."""
        by_case, stats = statuses
        assert by_case["the_old_released_match"] == "live"
        assert stamps_after["the_old_released_match"] is None
        assert stats["live_to_suspended"] == 0


@needs_postgres
class TestASuspendedRowStatPalPutsLaterGoesBack:
    """#9588 after-check: the hold's third door, ``suspended → scheduled``."""

    async def test_the_suspended_held_match_goes_back_stamped(
        self, statuses, stamps_after
    ):
        """THE SHIP. RED before: nothing read a suspended row. The stamp is
        what keeps the readers off "No result reported" and brings the row
        into the next pass's hold."""
        by_case, stats = statuses
        assert by_case["the_suspended_held_match"] == "scheduled"
        assert (
            stamps_after["the_suspended_held_match"]
            == EXPECTED_STAMPS["the_suspended_held_match"]
        )
        assert stats["unsuspended_statpal_later_session"] == 2

    async def test_a_69h_gap_is_inside_the_band(self, statuses):
        """THE BAND. RED at 48h: outside the band the hold fails OPEN."""
        by_case, _ = statuses
        assert by_case["the_suspended_far_match"] == "scheduled"

    async def test_a_resolved_market_keeps_it_suspended(self, statuses, stamps_after):
        by_case, _ = statuses
        assert by_case["the_suspended_settled_match"] == "suspended"
        assert stamps_after["the_suspended_settled_match"] is None

    async def test_a_reached_session_stays_suspended(self, statuses):
        """THE KILL CONTROL."""
        by_case, _ = statuses
        assert by_case["the_suspended_reached_match"] == "suspended"
