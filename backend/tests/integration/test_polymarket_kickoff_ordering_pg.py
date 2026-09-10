"""#4896's ordering key, EXECUTED against real Postgres.

`tests/test_polymarket_condition_refresh_3879.py` asserts the ORDER BY as a
string. That is worth having — it is what stops the key being deleted — but a
string cannot tell you whether the key sorts the rows the way the sentence
claims, and this key has three parts that only a server evaluates: a LEFT JOIN
that must not multiply the pool, a CASE that must return NULL for every row that
is not a game, and `ASC NULLS LAST`, whose whole job is to leave ~10,600 rows
exactly where they were. A typo in any of them is a beat that quietly re-orders
production and logs nothing.

**THE DEFECT, IN THE PRODUCTION SHAPE THAT CAUSED IT** (measured 2026-09-10
20:5xZ, #4896). A Polymarket game market carries `market_tier` 5 and a
`resolution_date` a WEEK after the fixture — `Pegula vs Sabalenka`, on court
23:00Z that night, carried 2026-09-17. So both arms of `priority` read false for
a game about to be played, and the row sorted only on staleness, behind every
months-old election ladder. It ranked 7,947 of 10,675 with `CANDIDATE_LIMIT`
3,600: not starved, unselectable. `Rybakina vs Gauff` ranked 10,667.

So the fixture below gives the game markets exactly that shape — tier 5, a
`resolution_date` seven days out, a leg stale by a day — and gives their rival a
tier-1 futures market with a leg stale by ninety. Under the old ordering the
futures market wins every time, which is what `test_the_red_control_...` runs
to prove the fixture can actually fail; under the new key the three games lead
it, soonest kickoff first.

The rows, and why each is here:

    m_live          started 1h ago, not completed   FIRST  — a game in progress
    m_soon          starts in 2h                    SECOND — the ordinary case
    m_later         starts in 10h, inside the lead  THIRD
    m_ancient       no event, tier 1, 90d stale     after all three, and it is
                                                    still ahead of everything
                                                    below it — the old ordering
                                                    is intact for non-games
    m_completed     starts in 2h, `completed_at` set    NOT in the kickoff class
    m_past_tail     started 12h ago, beyond the tail    NOT in the kickoff class

The last two are the exits, and they are separate rows because they are separate
mechanisms: `completed_at` is the primary one and the tail is the backstop for
the row whose `completed_at` never arrives. A test that only held one would pass
against a selector that had dropped the other.

There is no local Postgres in the agent sandbox (`initdb` dies on `shmget`), so
CI is the environment that runs this — the `search-recall` job.
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
            "set SEARCH_TEST_DATABASE_URL to run the kickoff-ordering gate "
            "against real Postgres (CI job `search-recall` provides one)"
        ),
    ),
]

UTC = timezone.utc

#: Legs must be staler than the selector's own window or nothing is a candidate.
#: Read off the module rather than restated — a test that hard-codes 12 keeps
#: passing after someone changes the window, while covering nothing.
def _stale_hours() -> int:
    from app.tasks import polymarket_condition_refresh as rail

    return rail.SERVED_STALE_HOURS


@pytest.fixture
async def pg_session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    # Importing ANY name off the models module executes it, and executing it is
    # what registers every table on `Base` — which `create_all` below needs. The
    # `from` form rather than `import app.models.models` because `_seed` already
    # imports from it that way, and mixing the two forms is `py/import-and-
    # import-from` (CodeQL note-level, and the sibling gates carry it).
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


async def _seed(session) -> dict[str, int]:
    """The six rows. Returns `{label: market_id}`."""
    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport

    now = datetime.now(UTC)
    sport = Sport(key="americanfootball_nfl", name="NFL", group="Football")
    session.add(sport)
    await session.flush()

    def _event(hours, *, completed=False):
        e = Event(
            sport_id=sport.id,
            home_team_name="Rams",
            away_team_name="49ers",
            commence_time=now + timedelta(hours=hours),
            status="scheduled",
            completed_at=(now - timedelta(minutes=5)) if completed else None,
        )
        session.add(e)
        return e

    events = {
        "m_live": _event(-1),
        "m_soon": _event(2),
        "m_later": _event(10),
        "m_completed": _event(2, completed=True),
        "m_past_tail": _event(-12),
    }
    await session.flush()

    def _market(label, event, *, tier=5, resolves_in_days=7):
        m = FuturesMarket(
            source="polymarket",
            external_id=f"ext-{label}",
            name=f"49ers vs. Rams ({label})",
            category="game",
            # THE PRODUCTION SHAPE. Tier 5 and a resolution_date a week past the
            # fixture is what makes every arm of `priority` read false for a
            # game starting in two hours; a fixture that set either of them
            # helpfully would prove a defect nobody has.
            market_tier=tier,
            status="open",
            resolution_date=now + timedelta(days=resolves_in_days),
            event_id=event.id if event is not None else None,
            sport_id=sport.id,
        )
        session.add(m)
        return m

    markets = {label: _market(label, ev) for label, ev in events.items()}
    #: The rival: no event at all, tier 1 so `priority` is TRUE, and ninety days
    #: stale so it wins any stalest-first contest outright.
    markets["m_ancient"] = _market("m_ancient", None, tier=1, resolves_in_days=90)
    await session.flush()

    stale_by = timedelta(hours=_stale_hours() + 12)
    for label, market in markets.items():
        session.add(
            FuturesOutcome(
                market_id=market.id,
                # `writable_leg_sql` requires a bare condition id, ungraded.
                external_id=f"0x{label}",
                name="Yes",
                current_probability=0.5,
                rank=1,
                is_winner=False,
                resolution_source=None,
                last_updated=(
                    now - timedelta(days=90) if label == "m_ancient" else now - stale_by
                ),
            )
        )
    await session.commit()
    return {label: m.id for label, m in markets.items()}


async def _seed_warm(session) -> dict[str, int]:
    """Three rows, all refreshed 50 MINUTES ago. Returns `{label: market_id}`.

    50 minutes is chosen to sit in the gap the repair opens: past
    `KICKOFF_STALE_MINUTES` (45) and far short of `SERVED_STALE_HOURS` (12), so
    the two classes must answer differently or one of the assertions fails.
    """
    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport

    now = datetime.now(UTC)
    sport = Sport(key="americanfootball_nfl", name="NFL", group="Football")
    session.add(sport)
    await session.flush()

    def _event(hours, *, completed=False):
        e = Event(
            sport_id=sport.id,
            home_team_name="Rams",
            away_team_name="49ers",
            commence_time=now + timedelta(hours=hours),
            status="scheduled",
            completed_at=(now - timedelta(minutes=5)) if completed else None,
        )
        session.add(e)
        return e

    game, done = _event(2), _event(2, completed=True)
    await session.flush()

    def _market(label, event):
        m = FuturesMarket(
            source="polymarket",
            external_id=f"warm-{label}",
            name=f"warm {label}",
            category="game",
            market_tier=5,
            status="open",
            resolution_date=now + timedelta(days=7),
            event_id=event.id if event is not None else None,
            sport_id=sport.id,
        )
        session.add(m)
        return m

    markets = {
        "warm_game": _market("game", game),
        "warm_completed": _market("completed", done),
        "warm_futures": _market("futures", None),
    }
    await session.flush()

    for label, market in markets.items():
        session.add(
            FuturesOutcome(
                market_id=market.id,
                external_id=f"0x{label}",
                name="Yes",
                current_probability=0.5,
                rank=1,
                is_winner=False,
                resolution_source=None,
                last_updated=now - timedelta(minutes=50),
            )
        )
    await session.commit()
    return {label: m.id for label, m in markets.items()}


async def _order(session, sql: str) -> list[int]:
    """Market ids in the order the selector would take them."""
    rows = (
        await session.execute(
            text(sql), {"stale_hours": _stale_hours(), "limit": 100}
        )
    ).all()
    return [r[0] for r in rows]


def _without_the_kickoff_key(sql: str) -> str:
    """The ORDER BY as it read before #4896 — the red control.

    Derived from the shipped statement rather than pasted, so the control
    cannot quietly stop being the same query with one key removed.
    """
    control = sql.replace("p.kickoff ASC NULLS LAST, ", "", 1)
    assert control != sql, "the kickoff key is not in the ORDER BY at all"
    return control


class TestAGameAboutToBePlayedLeadsTheQueue:
    """#4896: the one key here that is not about waiting."""

    async def test_the_three_kickoff_rows_lead_soonest_first(self, pg_session):
        from app.tasks import polymarket_condition_refresh as rail

        ids = await _seed(pg_session)
        order = await _order(pg_session, rail._CANDIDATE_SQL)

        assert order[:3] == [ids["m_live"], ids["m_soon"], ids["m_later"]], (
            "expected the in-progress game, then the one in 2h, then the one in "
            f"20h; got {order[:3]} against {ids}"
        )

    async def test_the_red_control_puts_the_ancient_futures_first(self, pg_session):
        """The fixture must be able to fail, or the assertion above is decoration.

        This is the OLD ordering, run on the same rows: a ninety-day-old tier-1
        futures market takes the head and every game waits behind it. That is
        the production behaviour #4896 measured, reproduced here in six rows.
        """
        from app.tasks import polymarket_condition_refresh as rail

        ids = await _seed(pg_session)
        order = await _order(
            pg_session, _without_the_kickoff_key(rail._CANDIDATE_SQL)
        )

        assert order[0] == ids["m_ancient"], (
            "the control did not reproduce the defect, so this file proves "
            f"nothing; got {order} against {ids}"
        )

    async def test_a_completed_game_does_not_hold_the_head(self, pg_session):
        """`completed_at` is the primary exit from the kickoff class."""
        from app.tasks import polymarket_condition_refresh as rail

        ids = await _seed(pg_session)
        order = await _order(pg_session, rail._CANDIDATE_SQL)

        assert order.index(ids["m_completed"]) > order.index(ids["m_ancient"]), (
            "a finished game outranked the ordinary queue; `completed_at` is "
            f"not being read. order={order} ids={ids}"
        )

    async def test_a_game_past_the_tail_does_not_hold_the_head(self, pg_session):
        """The backstop, for the row whose `completed_at` never arrives.

        Separate from the test above on purpose: one mechanism can be deleted
        while the other still passes, and a rail that only had the tail would
        keep re-reading a finished game for six hours.
        """
        from app.tasks import polymarket_condition_refresh as rail

        ids = await _seed(pg_session)
        order = await _order(pg_session, rail._CANDIDATE_SQL)

        assert order.index(ids["m_past_tail"]) > order.index(ids["m_ancient"]), (
            "a game that started beyond KICKOFF_TAIL_HOURS ago still led the "
            f"queue. order={order} ids={ids}"
        )


class TestAnImminentGameReentersEachHourlyBeat:
    """CERT-2546's required repair, executed.

    Leading the queue decides who goes first among rows that are ELIGIBLE. Both
    eligibility gates were sized for the 12-hour producer window, so #4896's
    first cut gave a game ONE refresh and then dropped it for eleven beats. The
    `CASE` in the WHERE clause is what fixes it, and a `CASE` in a WHERE clause
    is precisely what a string assertion cannot evaluate.
    """

    async def test_imminent_game_reenters_on_the_next_hourly_beat(self, pg_session):
        """A warm imminent row is due again; an equally warm ordinary row is not.

        Both legs are stamped 50 minutes ago — past `KICKOFF_STALE_MINUTES` (45)
        and nowhere near `SERVED_STALE_HOURS` (12). One row is a game two hours
        from kickoff and one is an ordinary futures market, and that is the ONLY
        difference between them, so the assertion cannot pass for any other
        reason.
        """
        from app.tasks import polymarket_condition_refresh as rail

        ids = await _seed_warm(pg_session)
        order = await _order(pg_session, rail._CANDIDATE_SQL)

        assert ids["warm_game"] in order, (
            "a game 2h from kickoff, refreshed 50 minutes ago, is NOT due on "
            "this beat — leading the queue bought it one refresh and no "
            f"cadence. order={order} ids={ids}"
        )
        assert ids["warm_futures"] not in order, (
            "an ordinary futures market refreshed 50 minutes ago became due — "
            "the kickoff window is leaking onto the whole pool and every "
            f"non-game row will now churn hourly. order={order} ids={ids}"
        )

    async def test_a_warm_completed_game_is_not_due_either(self, pg_session):
        """The short window must follow the kickoff CLASS, not the event link.

        Without this, a finished game whose `completed_at` is set would still
        re-enter every 45 minutes forever — the short window applied to a row
        the ordering no longer promotes.
        """
        from app.tasks import polymarket_condition_refresh as rail

        ids = await _seed_warm(pg_session)
        order = await _order(pg_session, rail._CANDIDATE_SQL)

        assert ids["warm_completed"] not in order, (
            "a COMPLETED game refreshed 50 minutes ago is being re-read on the "
            f"short kickoff cadence. order={order} ids={ids}"
        )


class TestTheKeyReordersThePoolWithoutChangingIt:
    """The LEFT JOIN is the risk: a join that multiplies is a budget that lies."""

    async def test_membership_is_identical_to_the_ordering_it_replaced(
        self, pg_session
    ):
        from app.tasks import polymarket_condition_refresh as rail

        await _seed(pg_session)
        after = await _order(pg_session, rail._CANDIDATE_SQL)
        before = await _order(
            pg_session, _without_the_kickoff_key(rail._CANDIDATE_SQL)
        )

        assert sorted(after) == sorted(before), (
            "the kickoff key changed WHICH markets are candidates, not just "
            "their order — the LEFT JOIN is dropping or multiplying rows"
        )
        assert len(after) == len(set(after)), (
            f"the LEFT JOIN multiplied rows: {after}"
        )
        assert after != before, "the ordering did not change at all"

    async def test_the_census_counts_the_same_population(self, pg_session):
        """`served_markets`/`stale_markets` ride the same statement.

        A join that fanned out would inflate both silently, and they are the
        numbers the rail's own health is read from.
        """
        from app.tasks import polymarket_condition_refresh as rail

        ids = await _seed(pg_session)
        rows = (
            await pg_session.execute(
                text(rail._CANDIDATE_SQL),
                {"stale_hours": _stale_hours(), "limit": 100},
            )
        ).all()

        assert int(rows[0][3]) == len(ids), (
            f"stale_markets={rows[0][3]} but {len(ids)} markets were seeded"
        )
        assert int(rows[0][4]) == len(ids), (
            f"served_markets={rows[0][4]} but {len(ids)} markets were seeded"
        )


    async def test_the_kickoff_class_admits_whole_inside_one_run(self, pg_session):
        """The budget claim, executed rather than asserted about constants.

        The measured production figure is 72 markets / 277 condition ids for the
        whole window against a 1,000-id `CONDITION_BUDGET` — the class is swept
        WHOLE every hour, which is the entire reason it cannot starve. Here the
        same property is checked structurally: every row in the kickoff class
        reaches the front, contiguously, before the first non-game row. A key
        that promoted only SOME games would still pass the ordering test above
        if it happened to promote the three it names.
        """
        from app.tasks import polymarket_condition_refresh as rail

        ids = await _seed(pg_session)
        order = await _order(pg_session, rail._CANDIDATE_SQL)
        games = {ids["m_live"], ids["m_soon"], ids["m_later"]}

        leading = order[: len(games)]
        assert set(leading) == games, (
            "the kickoff class is not contiguous at the head — some game was "
            f"left behind the ordinary queue. order={order} ids={ids}"
        )
