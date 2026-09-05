"""CERT-949 — the stamp that says "fresh" has to be the PRICE poll.

## The BLOCK, in one sentence

ux/1070 shipped a freshness bound on My Stuff's followed-sport section and fed it
`FuturesMarket.updated_at`. That column is `onupdate=func.now()` — it means ANY
write — and `app/tasks/enrich_markets.py` runs a six-hourly UPDATE of
`hook_description` / `hook_generated_at` / `hook_leader_at_generation` /
`market_metadata` that touches no price at all. So a market whose prices last
moved ten days ago reads as hours fresh, and the eleven stale cards the bound was
written to remove come straight back.

Worse than a coarse signal, and this is the part worth keeping: the enricher
selects markets whose hooks have gone stale, which are disproportionately the
markets whose PRICES have gone stale. The wrong clock is correlated with the
defect it hides.

## What this file proves, in the order it has to be proven

1. **The premise is real, not assumed** — the actual enrichment UPDATE, run
   against a real engine, moves `futures_markets.updated_at` while every
   `futures_outcomes.last_updated` stays where it was. Without this leg the rest
   is a test of a story.
2. **The derived stamp answers the right question** — the shipped candidate
   query, with the shipped load options, executed against real rows: the fold
   returns `MAX(FuturesOutcome.last_updated)` per market and `None` for a market
   with no outcome rows (unknown ⇒ not fresh).
3. **It survives the carrier** — the value reaches the scoring loop on BOTH
   paths: the build path that runs the SELECT, and the shared-snapshot path that
   runs none. A market excluded when the rows are hot must stay excluded when the
   same request is served from the artifact, or the defect simply moves.
4. **The call site cannot slide back** to the free-but-wrong column.

Legs 1 and 2 use the synchronous SQLite rail (`test_reconcile_anchor_schedule_
paging.py` established it — there is no aiosqlite in this sandbox), so the
statements under test are the ones the task and the route build, executed by a
real engine against real rows.

The price age is folded out of the hydrated outcome rows at snapshot-build time,
NOT read from a second `GROUP BY` query: that query was written first and
measured on production at 423 ms warm — ~72% of the entire 588 ms `market_load`
stage — while the column it needs rides along in the SELECT already fetching
those rows for free.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.routes import feed as feed_module
from app.utils import futures_market_snapshot as fms
from app.utils.personalization import (
    MY_STUFF_MAX_PRICE_AGE_HOURS,
    PersonalizationContext,
)

UTC = timezone.utc

#: The US Open's second Friday, and the clock every leg here is anchored to.
#: Offset FIRST, then use — never a branch on the wall clock (gotcha #44).
NOW = datetime(2026, 9, 4, 18, 0, tzinfo=UTC)

#: The specimen. Measured on production 2026-09-04: eight "To Reach the …"
#: bracket fields, all polled 237.4-239.9h earlier, all still listing players who
#: had been knocked out days before.
TEN_DAYS_STALE = NOW - timedelta(hours=239)

#: What a live field looks like on the same day — the Polymarket US Open Winner
#: fields, 5.3-5.7h. The gap between this and the line above holds NOTHING, which
#: is what makes 48h a threshold rather than a knife edge.
FRESHLY_POLLED = NOW - timedelta(hours=5)


@compiles(JSONB, "sqlite")
def _jsonb_as_json_for_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL only
    return "JSON"


class _AsyncSessionOverSync:
    """A synchronous `Session` with the one `await`able method the route uses.

    Same rail as `test_reconcile_anchor_schedule_paging.py`, for the same reason:
    the sandbox has no aiosqlite, and wrapping is honest where re-implementing
    the query would not be — the statement executed is the one
    `market_load_options()` builds, against a real engine.
    """

    def __init__(self, session: Session):
        self._session = session

    async def execute(self, statement, *args, **kwargs):
        return self._session.execute(statement)


@pytest.fixture
def sqlite_db():
    from app.models.models import Base, FuturesMarket, FuturesOutcome

    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine, tables=[FuturesMarket.__table__, FuturesOutcome.__table__]
    )
    with Session(engine) as session:
        yield session, _AsyncSessionOverSync(session)


def _seed(session, *, market_id: int, name: str, polled_at, updated_at=None) -> None:
    """One market and two outcomes whose prices were last written at `polled_at`.

    `polled_at=None` seeds a market with NO outcome rows — the empty-shell shape
    six of the eighteen in-window golf markets had on 2026-09-04.
    """
    from app.models.models import FuturesMarket, FuturesOutcome

    session.add(
        FuturesMarket(
            id=market_id,
            source="kalshi",
            external_id=f"ext-{market_id}",
            name=name,
            market_type="championship",
            status="open",
            created_at=NOW - timedelta(days=60),
            updated_at=updated_at or polled_at or NOW - timedelta(days=60),
        )
    )
    if polled_at is not None:
        for i in range(2):
            session.add(
                FuturesOutcome(
                    id=market_id * 10 + i,
                    market_id=market_id,
                    external_id=f"ext-{market_id}-{i}",
                    name=f"Player {i}",
                    current_probability=0.5,
                    # Deliberately staggered: the aggregate must return the
                    # NEWEST poll, not the first row it meets.
                    last_updated=polled_at - timedelta(hours=i * 3),
                )
            )
    session.commit()


# ══════════════════════════════════════════════════════════════════════════
# 1. THE PREMISE — a real non-price write, run for real
# ══════════════════════════════════════════════════════════════════════════


class TestTheHookEnricherIsWhyTheMarketRowLies:
    """`updated_at` is not a price clock, and this proves it by running the writer."""

    def test_the_enrichment_update_moves_updated_at_and_no_price(self, sqlite_db):
        """The exact statement `enrich_markets` issues, on a ten-day-stale market.

        Not a paraphrase of it: the `.values(...)` set is read off the task's own
        source below, so a change to what the enricher writes reaches this test.
        """
        from app.models.models import FuturesMarket, FuturesOutcome

        session, _ = sqlite_db
        _seed(
            session,
            market_id=9001,
            name="US Open 2026: To Reach the Quarterfinals",
            polled_at=TEN_DAYS_STALE,
        )
        before_market = session.execute(
            select(FuturesMarket.updated_at).where(FuturesMarket.id == 9001)
        ).scalar_one()
        before_prices = session.execute(
            select(func.max(FuturesOutcome.last_updated)).where(
                FuturesOutcome.market_id == 9001
            )
        ).scalar_one()

        # THE REAL WRITE (app/tasks/enrich_markets.py) — hook fields and
        # metadata, not one price among them.
        session.execute(
            update(FuturesMarket)
            .where(FuturesMarket.id == 9001)
            .values(
                hook_description="Two seeds are out and the draw has opened up",
                hook_generated_at=NOW,
                hook_leader_at_generation="Carlos Alcaraz",
                market_metadata={"hook_prob": 0.41},
            )
        )
        session.commit()

        after_market = session.execute(
            select(FuturesMarket.updated_at).where(FuturesMarket.id == 9001)
        ).scalar_one()
        after_prices = session.execute(
            select(func.max(FuturesOutcome.last_updated)).where(
                FuturesOutcome.market_id == 9001
            )
        ).scalar_one()

        assert after_market != before_market, (
            "`updated_at` is `onupdate=func.now()`; if a non-price UPDATE stopped "
            "bumping it, THIS test is the one to re-read before trusting the "
            "column again"
        )
        assert after_prices == before_prices, "the enricher wrote no price"
        assert after_prices == TEN_DAYS_STALE.replace(
            tzinfo=None
        ), "and the prices are still ten days old, which is the whole point"

    def test_the_enricher_still_writes_only_hook_fields(self):
        """Pin the premise to the task's source, not to this file's memory of it.

        If the enrichment write ever starts touching a price column, the story
        above changes and the pin fails — which is the correct time to re-argue
        the choice of stamp, rather than the day someone notices bad cards.
        """
        from app.tasks import enrich_markets

        src = inspect.getsource(enrich_markets)
        # The HOOK write specifically — this module also has an image-enrichment
        # `update(FuturesMarket)`, which is a second non-price writer and makes
        # the point twice rather than weakening it. Anchor on the hook one.
        block = src[src.index("hook_description=hook") - 200 :][:600]
        for field in (
            "hook_description=",
            "hook_generated_at=",
            "hook_leader_at_generation=",
            "market_metadata=",
        ):
            assert field in block, field
        for price_field in ("current_probability", "last_updated", "price_changed_at"):
            assert price_field not in block, (
                f"the hook enricher now writes {price_field} — re-read "
                "`_price_polled_at_by_market`'s reasoning"
            )


# ══════════════════════════════════════════════════════════════════════════
# 2. THE DERIVED STAMP — the shipped aggregate, executed
# ══════════════════════════════════════════════════════════════════════════


class TestThePricePolledAtDerivation:
    """The REAL candidate query, the REAL load options, a real engine.

    This is the leg that proves the column is projected. `to_plain` reads the
    stamp through `__dict__.get`, so an outcome projection that stopped loading
    `last_updated` would not raise — every market would quietly become "price
    age unknown" and My Stuff's followed-sport section would empty. Running the
    shipped `market_load_options()` against real rows is what catches that.
    """

    def _hydrate(self, session, market_ids):
        from app.models.models import FuturesMarket

        return (
            session.execute(
                select(FuturesMarket)
                .options(*fms.market_load_options())
                .where(FuturesMarket.id.in_(market_ids))
            )
            .scalars()
            .unique()
            .all()
        )

    def test_the_newest_poll_wins_and_the_projection_carries_it(self, sqlite_db):
        session, _ = sqlite_db
        _seed(session, market_id=9101, name="Stale bracket", polled_at=TEN_DAYS_STALE)
        _seed(session, market_id=9102, name="Live field", polled_at=FRESHLY_POLLED)

        markets = self._hydrate(session, [9101, 9102])
        rebuilt = {m.id: m for m in fms.from_plain(fms.to_plain(markets))}

        # SQLite hands back naive datetimes; what is asserted is WHICH stamp was
        # selected — the newest of the two staggered outcomes, not the first.
        assert rebuilt[9101].price_polled_at.replace(tzinfo=UTC) == TEN_DAYS_STALE
        assert rebuilt[9102].price_polled_at.replace(tzinfo=UTC) == FRESHLY_POLLED

    def test_a_market_with_no_outcomes_is_unknown_rather_than_fresh(self, sqlite_db):
        """An empty shell has no price, and "no price" is not "priced now".

        `None` is the only honest answer and the consumer must read it as
        exclusion (gotcha #53). Six of the eighteen in-window golf markets on
        2026-09-04 were exactly this shape.
        """
        session, _ = sqlite_db
        _seed(session, market_id=9103, name="Empty shell", polled_at=None)

        markets = self._hydrate(session, [9103])
        rebuilt = fms.from_plain(fms.to_plain(markets))[0]

        assert rebuilt.price_polled_at is None

    def test_the_wire_still_does_not_carry_a_per_outcome_stamp(self):
        """Loaded is not carried, and that distinction is the cost saving.

        `last_updated` on 193 outcomes per market was measured at +15% of a
        2.9 MB size-capped artifact. It is loaded so the fold can happen and
        then dropped, so nothing downstream may read it off a rebuilt outcome —
        that read is an `AttributeError` in the per-item serializer, which
        empties the whole futures pool (gotcha #42).
        """
        assert "last_updated" not in fms.OUTCOME_COLUMNS
        assert "last_updated" in fms.OUTCOME_LOAD_ONLY_EXTRA

        market = _orm_market(9104, "US Open Men's Singles Winner")
        for outcome in market.outcomes:
            outcome.last_updated = FRESHLY_POLLED
        rebuilt = fms.from_plain(fms.to_plain([market]))[0]

        assert rebuilt.price_polled_at == FRESHLY_POLLED
        assert not hasattr(rebuilt.outcomes[0], "last_updated")

    def test_no_consumer_reads_the_dropped_column_off_a_snapshot(self):
        """The other half of the line above, read off the route's source.

        `feed.py` may load the column; it may not READ it per outcome, because
        the rebuilt snapshots it scores do not have it.
        """
        # CODE lines only. The comments in this file's own call site explain the
        # column at length, and a scan that counted them would be a pin nobody
        # could satisfy — the residue-scan substring collision, one more time.
        code = [
            line
            for line in inspect.getsource(feed_module).splitlines()
            if not line.lstrip().startswith("#")
        ]
        offenders = [line.strip() for line in code if ".last_updated" in line]
        assert offenders == [], (
            "the futures path reads a per-outcome `last_updated`, which is "
            f"loaded for the fold but never carried on the wire: {offenders}"
        )


class TestTheSnapshotCarriesIt:
    def test_the_value_survives_the_wire(self):
        market = _orm_market(9201, "US Open Men's Singles Winner")
        for outcome in market.outcomes:
            outcome.last_updated = FRESHLY_POLLED
        payload = fms.to_plain([market])

        rebuilt = fms.from_plain(payload)[0]

        assert rebuilt.__dict__["price_polled_at"] == FRESHLY_POLLED

    def test_a_market_with_no_stamps_reads_as_unknown(self):
        market = _orm_market(9202, "Empty shell", outcome_count=0)
        rebuilt = fms.from_plain(fms.to_plain([market]))[0]

        assert rebuilt.__dict__["price_polled_at"] is None

    def test_the_version_moves_when_the_row_shape_does(self):
        """The bump is a CONVENTION, so it needs a guard that fails on omission.

        Written after the mutation battery found the omission survivable: with
        the version left at 2, an in-flight predecessor entry is still refused —
        by ARITY, one row too short — so nothing serves wrong data, and the only
        symptom is two builds rejecting each other's entries and rebuilding the
        2.9 MB artifact in turn. Cheap enough to miss, expensive enough to guard,
        and the module's own note says why arity is not the version's backstop:
        two same-width columns swapped keep the arity and change the meaning of
        every position.

        This tuple is MEANT to rot. Changing the wire shape should fail here and
        be fixed by bumping the version in the same commit.
        """
        shape = (
            fms.SNAPSHOT_SCHEMA_VERSION,
            len(fms.MARKET_ROW_COLUMNS),
            len(fms.OUTCOME_COLUMNS),
            len(fms.SPORT_COLUMNS),
        )
        assert shape == (3, 30, 12, 2), (
            "the snapshot wire shape changed. Bump `SNAPSHOT_SCHEMA_VERSION` "
            "(it is part of the shared cache key, so the bump is what stops this "
            "build reading a predecessor's rows) and update this tuple."
        )

    def test_a_previous_schema_entry_is_never_read(self):
        """The v2 artifact has a market row one value SHORT.

        Read under v3 it would give every market an unknown price age for the
        life of the entry — the section emptying for a TTL, blamed on anything
        but a schema. The version bump means those entries are not read at all.
        """
        market = _orm_market(9203, "Older build's row")
        stale_payload = fms.to_plain([market])
        stale_payload["v"] = 2
        for row in stale_payload["rows"]:
            row[0] = row[0][: len(fms.MARKET_COLUMNS)]

        assert fms.is_snapshot_payload(stale_payload) is False
        assert fms.from_plain(stale_payload) == []

    def test_the_derived_block_is_not_in_the_load_surface(self):
        """`market_load_options()` projects columns; a derived name would raise.

        Stated as a test because the failure it prevents is a 500 on the feed,
        not a wrong card.
        """
        assert not set(fms.DERIVED_MARKET_COLUMNS) & set(fms.MARKET_COLUMNS)
        assert fms.MARKET_ROW_COLUMNS == fms.MARKET_COLUMNS + fms.DERIVED_MARKET_COLUMNS
        feed_module._futures_feed_load_options()  # raises on a bogus attribute


#: Real entrants, because `classify_market_quality` suppresses a field whose
#: outcomes read as `Player 1 / Player 2 …` (anonymised outcomes, numeric
#: ladder) — correctly, and it would have made every admission assertion below
#: vacuously "excluded".
_DRAW = ("Carlos Alcaraz", "Jannik Sinner", "Novak Djokovic", "Taylor Fritz")


def _orm_market(market_id: int, name: str, *, outcome_count: int = 4, polled_at=None):
    """A real `FuturesMarket` ORM instance, never added to a session.

    Real, not a stand-in: `to_plain` reads rows through `instance.__dict__`, and
    the direct path hands it exactly this — a `load_only`-restricted ORM object.
    """
    from app.models.models import FuturesMarket, FuturesOutcome, Sport

    return FuturesMarket(
        id=market_id,
        name=name,
        source="kalshi",
        external_id=f"ext-{market_id}",
        sport_id=7,
        category="sports",
        llm_sport_category="tennis",
        market_tier=2,
        market_type="championship",
        canonical_market_key=f"canon-{market_id}",
        group_id=None,
        group_type=None,
        image_url=None,
        image_width=None,
        image_height=None,
        hook_description=None,
        hook_generated_at=None,
        hook_leader_at_generation=None,
        market_metadata={},
        curation_score_adj=0,
        volume_24h=None,
        # FRESH, on every specimen in this file: the market row is the liar.
        updated_at=NOW - timedelta(minutes=30),
        commence_time=NOW - timedelta(days=7),
        resolution_date=NOW + timedelta(days=3),
        status="open",
        created_at=NOW - timedelta(days=60),
        llm_league=None,
        llm_gender=None,
        llm_level=None,
        sport=Sport(id=7, key="tennis_atp_us_open", name="Tennis"),
        outcomes=[
            FuturesOutcome(
                id=market_id * 10 + i,
                market_id=market_id,
                external_id=f"ext-{market_id}-{i}",
                name=_DRAW[i % len(_DRAW)],
                team_id=None,
                current_probability=0.25,
                probability_change_24h=0.0,
                rank=i + 1,
                rank_change_24h=0,
                opening_probability=0.25,
                calibration_probability=None,
                current_yes_bid=0.24,
                current_yes_ask=0.26,
                # The PRICE clock. Staggered so the fold has to take a maximum
                # rather than whichever row it meets first.
                last_updated=(
                    None if polled_at is None else polled_at - timedelta(hours=i)
                ),
            )
            for i in range(outcome_count)
        ],
    )


# ══════════════════════════════════════════════════════════════════════════
# 3. THE SHIP — My Stuff scoring, on the build path AND the snapshot path
# ══════════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _clean_shared_cache():
    """No artifact may survive between tests here.

    The whole second half of this file turns on whether the SECOND call reads a
    shared artifact, so a cache warmed by a previous test is the one leak that
    would make a broken carrier look correct.
    """
    from app.utils.principal_independent_cache import clear_shared_builds

    clear_shared_builds()
    yield
    clear_shared_builds()


@pytest.fixture(autouse=True)
def _no_cross_worker(monkeypatch):
    monkeypatch.setenv("FEED_SHARED_BUILD_CROSS_WORKER", "0")


def _my_stuff_db(markets, counts):
    """A DB that answers the candidate hydration SELECT and nothing else."""

    def _empty():
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        result.scalars.return_value.unique.return_value.all.return_value = []
        result.scalars.return_value.first.return_value = None
        result.scalar_one_or_none.return_value = None
        result.scalar.return_value = None
        result.fetchall.return_value = []
        result.all.return_value = []
        result.first.return_value = None
        return result

    async def _execute(statement, *args, **kwargs):
        text = str(statement)
        if "FROM futures_markets" in text and all(
            f"futures_markets.{c}" in text for c in fms.MARKET_COLUMNS
        ):
            counts["hydration"] += 1
            result = _empty()
            result.scalars.return_value.unique.return_value.all.return_value = list(
                markets
            )
            return result
        # There is deliberately NO second statement to answer here: the price
        # age is folded out of the rows above. A `GROUP BY` aggregate over the
        # same ids was measured at 423 ms warm on production and dropped, so a
        # build that starts issuing one fails the count assertions below.
        counts["other"] += 1
        return _empty()

    db = AsyncMock()
    db.execute.side_effect = _execute
    return db


async def _my_stuff_futures(db, monkeypatch, market_ids):
    """Run the futures scorer the way My Stuff runs it: golf/tennis follows only."""
    from app.utils import candidate_base as candidate_base_module

    async def _fake_base(now, sport_filter, static_tag_filter, stages=None):
        return list(market_ids), "fresh", set()

    monkeypatch.setattr(candidate_base_module, "get_candidate_base", _fake_base)

    ctx = PersonalizationContext(sport_affinities={"tennis": 1.0})
    return await feed_module._score_futures(
        db,
        NOW,
        None,
        ctx,
        my_teams_only=True,
        my_team_names=[],
        my_team_sport_categories={},
    )


def _names(items) -> set[str]:
    return {(item.get("data") or {}).get("name") for item in items}


#: The specimen card, by name. Every fixture below carries a market row stamped
#: 30 minutes ago — `_orm_market` sets `updated_at` that way on purpose, because
#: a fresh market row is the enricher's signature and the whole hazard.
STALE_BRACKET = "US Open 2026: To Reach the Quarterfinals"
LIVE_FIELD = "US Open Men's Singles Winner"


class TestAStalePricedFieldDoesNotReachMyStuff:
    """The BLOCK's named test. Fresh market row, ten-day-old prices, both paths."""

    @pytest.mark.asyncio
    async def test_the_build_path_excludes_it(self, monkeypatch):
        counts = {"hydration": 0, "other": 0}
        db = _my_stuff_db(
            [_orm_market(9301, STALE_BRACKET, polled_at=TEN_DAYS_STALE)], counts
        )

        items = await _my_stuff_futures(db, monkeypatch, [9301])

        assert counts["hydration"] == 1
        assert _names(items) == set(), (
            "a bracket whose prices are ten days old reached My Stuff — the "
            "market row's `updated_at` is 30 minutes old on this fixture, which "
            "is exactly the lie CERT-949 blocked"
        )

    @pytest.mark.asyncio
    async def test_the_same_market_is_admitted_when_its_prices_are_polled(
        self, monkeypatch
    ):
        """The other side of the gate — otherwise "excludes" is just "excludes all"."""
        counts = {"hydration": 0, "other": 0}
        db = _my_stuff_db(
            [_orm_market(9301, STALE_BRACKET, polled_at=FRESHLY_POLLED)], counts
        )

        items = await _my_stuff_futures(db, monkeypatch, [9301])

        assert STALE_BRACKET in _names(items)

    @pytest.mark.asyncio
    async def test_the_snapshot_path_gives_the_same_verdict(self, monkeypatch):
        """Second reader, zero SELECTs, same exclusion.

        This is the leg the carrier can fail on its own: a value folded at build
        time and dropped from the wire is correct on the first request and gone
        from the artifact, so the stale card returns for every reader after the
        first — which is most of them.
        """
        counts = {"hydration": 0, "other": 0}
        db = _my_stuff_db(
            [
                _orm_market(9301, STALE_BRACKET, polled_at=TEN_DAYS_STALE),
                _orm_market(9302, LIVE_FIELD, polled_at=FRESHLY_POLLED),
            ],
            counts,
        )

        first = await _my_stuff_futures(db, monkeypatch, [9301, 9302])
        second = await _my_stuff_futures(db, monkeypatch, [9301, 9302])

        assert counts["hydration"] == 1, "the second call must read the artifact"
        assert _names(second) == _names(first) == {LIVE_FIELD}

    @pytest.mark.asyncio
    async def test_a_market_with_no_price_at_all_is_not_admitted(self, monkeypatch):
        counts = {"hydration": 0, "other": 0}
        db = _my_stuff_db(
            [_orm_market(9303, "US Open Women's Singles Winner", polled_at=None)],
            counts,
        )

        items = await _my_stuff_futures(db, monkeypatch, [9303])

        assert _names(items) == set()


# ══════════════════════════════════════════════════════════════════════════
# 4. THE CALL SITE — it cannot slide back to the free-but-wrong column
# ══════════════════════════════════════════════════════════════════════════


class TestTheCallSiteReadsTheDerivedStamp:
    @staticmethod
    def _source() -> str:
        return inspect.getsource(feed_module)

    def test_it_passes_price_polled_at(self):
        assert 'priced_at=_utc(market.__dict__.get("price_polled_at"))' in (
            self._source()
        )

    def test_it_does_not_pass_the_market_rows_own_timestamp(self):
        """The specific regression, named.

        `market.updated_at` is free, already loaded, and wrong; it is the exact
        thing this repair removed, so it gets its own line rather than being
        implied by the assertion above.
        """
        assert "priced_at=_utc(market.updated_at)" not in self._source()

    def test_the_build_stays_one_statement(self):
        """The fold rides the hydration SELECT; no second query joins it.

        Measured, not preferred: the `GROUP BY` version of this cost 423 ms warm
        on production against a 588 ms stage. A future edit that reintroduces it
        should have to argue with that number, so the number has a test.
        """
        assert "return _futures_snapshot.to_plain(result.scalars().unique().all())" in (
            self._source()
        )
        # Code lines only — the call site's own comment names the statement it
        # rejected, and a scan that counted the comment could never pass.
        code = "\n".join(
            line
            for line in self._source().splitlines()
            if not line.lstrip().startswith("#")
        )
        assert "func.max(FuturesOutcome.last_updated)" not in code

    def test_the_bound_is_still_the_measured_one(self):
        """48h, and a test that fails if someone tightens it into the poll cadence.

        A threshold below the real refresh interval makes live cards blink in and
        out — a failure nobody would trace back to a constant.
        """
        assert MY_STUFF_MAX_PRICE_AGE_HOURS == 48
        assert 6 < MY_STUFF_MAX_PRICE_AGE_HOURS < 92
