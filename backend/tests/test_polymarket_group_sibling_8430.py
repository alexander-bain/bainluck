"""#8430 — one Polymarket game event, one row: children stop minting their own.

## What a reader saw, on production

`/search?q=Boyer` (2026-09-24 18:40Z, phone width) showed one GAMES card,
**Tristan Boyer vs Sebastian Gorzny · LIVE · No price yet** — event 15317846,
holding nothing. The match had **14 rows**: the priced one (15317904, 14
Polymarket markets), a Kalshi copy, a suspended previous-day row, and **11 empty
rows reading LIVE**, all tagged `provenance:source:polymarket`, minted in three
hourly batches (9/23 13:21, 14:21, 15:23Z), about four per batch.

## The two mechanisms, both read off production

1. **The poll wiped the matcher's links, hourly.** `_process_event_batch` upserts
   each decomposed child with `event_id = parent_event_id`. A game container is
   rejected by the matcher as a `parent_row`, so its `event_id` is NULL for life,
   and the ON CONFLICT arm wrote that NULL over whatever the matcher had linked.
   The children's receipts show `attempt_count` 7-8 across those hours — a linked
   market is never re-attempted, so something unlinked them each hour. 3,321
   children (534 groups) sat linked under an unlinked parent on 2026-09-24.
2. **Each re-orphaned child then minted alone.** Its best candidate (15317735,
   left at the pre-postponement date) was refused by #4965's venue-fixture guard,
   so it fell through to CREATE; an id-less Polymarket claim re-finds nothing
   (ruling 048), and the matched path's group sweep never runs on the create
   path. Every child of the group made its own row.

## What this file gates

* the poll's ON CONFLICT arm writes a parent's link and never a parent's NULL —
  driven through the REAL writer, reading the statement PostgreSQL would receive;
* `_polymarket_group_sibling_event_id`'s refusals that never reach the database
  (its SQL half runs on real PostgreSQL in
  `tests/integration/test_polymarket_group_sibling_8430_pg.py`, named by a
  `search-recall` step);
* the redirect returns a link, not a mint, and runs AFTER #5821's lookup.
"""

import contextlib
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects import postgresql

from app.tasks import prediction_market_matching as pmm

#: The production group, with its real Gamma event id.
GROUP = "polymarket:1067623"

VENUE_START = datetime(2026, 9, 24, 17, 0, tzinfo=timezone.utc)
SEEDED_NAME_PREFIX = "8430 probe:"


class _Market:
    """The attributes the lookup and the fixture guard read, and nothing else."""

    def __init__(
        self,
        *,
        id,
        group_id=GROUP,
        source="polymarket",
        group_type="polymarket_sub_market",
        venue_game_start=VENUE_START,
    ):
        self.id = id
        self.name = f"{SEEDED_NAME_PREFIX} Set 1 Winner: Boyer vs Gorzny"
        self.source = source
        self.group_id = group_id
        self.group_type = group_type
        self.external_id = f"0x8430{id}"
        self.market_metadata = (
            {"venue_game_start": venue_game_start.isoformat()}
            if venue_game_start
            else {}
        )


# ── the lookup's refusals that never reach the database ──────────────────────


class TestTheRefusalsThatNeverReachTheDatabase:
    """`session=None` is the assertion: a query would raise `AttributeError`."""

    @pytest.mark.asyncio
    async def test_a_kalshi_market_is_not_a_polymarket_child(self):
        market = _Market(id=1, source="kalshi")
        assert await pmm._polymarket_group_sibling_event_id(None, market) is None

    @pytest.mark.asyncio
    async def test_a_parent_container_is_not_a_child(self):
        """Only decomposed GAME children share a fixture by construction; a
        `polymarket_event` container can be a neg-risk ladder over many."""
        market = _Market(id=1, group_type="polymarket_event")
        assert await pmm._polymarket_group_sibling_event_id(None, market) is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("group_id", [None, ""])
    async def test_no_group_means_todays_behaviour(self, group_id):
        market = _Market(id=1, group_id=group_id)
        assert await pmm._polymarket_group_sibling_event_id(None, market) is None


# ── the redirect contract ─────────────────────────────────────────────────────


def _boyer_matchup():
    from app.utils.prediction_market_matching import MatchupInfo

    return MatchupInfo("Boyer", "Gorzny", "Boyer", "bare_matchup")


class TestTheRedirectReturnsALinkAndNotAMint:
    """Driven through the real `_create_event_from_prediction_market` with
    `session=None`: reaching any create-refusal gate below the redirect would
    need a session and raise, so a returned dict also proves the placement."""

    @pytest.mark.asyncio
    async def test_a_found_sibling_returns_its_event_and_says_nothing_was_created(
        self, monkeypatch
    ):
        async def _none(session, market):
            return None

        async def _found(session, market):
            return 15317904

        monkeypatch.setattr(pmm, "_polymarket_container_sibling_event_id", _none)
        monkeypatch.setattr(pmm, "_polymarket_group_sibling_event_id", _found)

        result = await pmm._create_event_from_prediction_market(
            None, _boyer_matchup(), _Market(id=62044479),
            datetime(2026, 9, 23, 13, 21, tzinfo=timezone.utc),
        )

        assert result is not None, "the child was refused instead of linked"
        assert result["event_id"] == 15317904
        assert result["auto_created"] is False, (
            "a link that reused a sibling's row reported itself as a mint"
        )
        assert result["group_sibling_link"] is True

    @pytest.mark.asyncio
    async def test_the_container_lookup_keeps_first_say(self, monkeypatch):
        """#5821 answers before #8430, so its funnel counter is unchanged."""
        calls = []

        async def _container(session, market):
            calls.append("container")
            return 111

        async def _group(session, market):
            calls.append("group")
            return 222

        monkeypatch.setattr(pmm, "_polymarket_container_sibling_event_id", _container)
        monkeypatch.setattr(pmm, "_polymarket_group_sibling_event_id", _group)

        result = await pmm._create_event_from_prediction_market(
            None, _boyer_matchup(), _Market(id=1),
            datetime(2026, 9, 23, 13, 21, tzinfo=timezone.utc),
        )
        assert result["event_id"] == 111 and calls == ["container"]


class TestTheFunnelCountsItAsALink:
    @pytest.mark.asyncio
    async def test_try_link_market_counts_a_group_link_under_its_own_key(
        self, monkeypatch
    ):
        async def _redirect(session, matchup, market, now):
            return {
                "event_id": 15317904, "home_team": "Boyer", "away_team": "Gorzny",
                "yes_is_home": True, "auto_created": False,
                "group_sibling_link": True,
            }

        monkeypatch.setattr(pmm, "_create_event_from_prediction_market", _redirect)
        monkeypatch.setattr(pmm, "_set_market_sport_fields", lambda m, e: None)

        class _S:
            async def commit(self):
                return None

        market = _Market(id=62044479)
        market.event_id = None
        stats = {"newly_linked": 0, "funnel": {"linked": 0}}
        await pmm._try_link_market(
            _S(), market, _boyer_matchup(), None, stats, None,
            datetime(2026, 9, 23, 13, 21, tzinfo=timezone.utc), [],
        )
        assert market.event_id == 15317904
        assert stats["funnel"].get("group_sibling_links") == 1
        assert "auto_created_events" not in stats["funnel"], (
            "a sibling link was counted as a mint — the number this ship is "
            "supposed to lower would not move"
        )


# ── mechanism 1: the poll must not write the parent's NULL ────────────────────


class _Result:
    def __init__(self, ident, scalar=None):
        self._ident = ident
        self._scalar = scalar

    def scalar_one(self):
        return self._ident

    def scalar_one_or_none(self):
        return self._scalar

    def scalar(self):
        return None

    def first(self):
        return None

    def all(self):
        return []

    def fetchall(self):
        return []

    def scalars(self):
        return self

    @property
    def rowcount(self):
        return 0

    def __iter__(self):
        return iter(())


class _RecordingSession:
    """Answers the ONE read the writer makes about linkage — the parent's
    `event_id` — with ``parent_event_id``; everything else is permissive."""

    def __init__(self, parent_event_id):
        self.parent_event_id = parent_event_id
        self.statements = []
        self._next_id = 5000

    async def execute(self, stmt, *a, **k):
        self.statements.append(stmt)
        self._next_id += 1
        sql = str(stmt)
        if sql.lstrip().startswith("SELECT futures_markets.event_id"):
            return _Result(self._next_id, scalar=self.parent_event_id)
        return _Result(self._next_id)

    async def commit(self):
        return None

    async def rollback(self):
        return None

    async def flush(self):
        return None

    def add(self, *a, **k):
        return None


def _tennis_event():
    from app.services.polymarket_api import PolymarketEvent, PolymarketMarket

    def _leg(cid, question):
        return PolymarketMarket(
            condition_id=cid,
            question=question,
            outcomes=["Boyer", "Gorzny"],
            outcome_prices=[0.55, 0.45],
            best_bid=0.54,
            best_ask=0.56,
            last_trade_price=0.55,
            volume=12_000.0,
            active=True,
        )

    return PolymarketEvent(
        id="1067623",
        title="San Diego 2: Tristan Boyer vs Sebastian Gorzny",
        slug="atp-boyer-gorzny-2026-09-24",
        active=True,
        closed=False,
        neg_risk=False,
        tags=["Sports", "Tennis"],
        start_date=datetime(2026, 9, 23, 5, 5, tzinfo=timezone.utc),
        markets=[
            _leg("0xd1347776", "Set 1 Winner: Tristan Boyer vs Sebastian Gorzny"),
            _leg("0x88e02d05", "San Diego 2: Tristan Boyer vs Sebastian Gorzny"),
        ],
    )


async def _child_conflict_sets(monkeypatch, parent_event_id) -> dict[str, dict]:
    """`condition id -> the ON CONFLICT DO UPDATE set of that child's upsert`."""
    from app.models.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
    from app.tasks import polymarket as poly
    from app.utils.market_label_normalization import compute_market_tier
    from app.utils.odds_math import probability_to_american
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    session = _RecordingSession(parent_event_id)

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield session

    monkeypatch.setattr(poly, "get_task_session", _fake_session)
    stats: dict = defaultdict(int)
    stats["errors"] = []
    await poly._process_event_batch(
        [_tennis_event()], stats, FuturesMarket, FuturesOutcome,
        FuturesOddsSnapshot, pg_insert, probability_to_american,
        compute_market_tier,
    )
    assert not stats["errors"], f"writer raised: {stats['errors']}"

    out: dict[str, dict] = {}
    for stmt in session.statements:
        table = getattr(stmt, "table", None)
        if table is None or table.name != "futures_markets":
            continue
        clause = getattr(stmt, "_post_values_clause", None)
        if clause is None:
            continue
        params = stmt.compile(dialect=postgresql.dialect()).params
        if params.get("group_type") != "polymarket_sub_market":
            continue
        out[params["external_id"]] = {
            (getattr(col, "name", None) or str(col)): value
            for col, value in dict(clause.update_values_to_set).items()
        }
    return out


class TestThePollKeepsTheMatchersLink:
    @pytest.mark.asyncio
    async def test_an_unlinked_parent_does_not_unlink_its_children(self, monkeypatch):
        sets = await _child_conflict_sets(monkeypatch, parent_event_id=None)
        assert set(sets) == {"0xd1347776", "0x88e02d05"}, (
            f"the writer emitted no child upsert to inspect: {sorted(sets)}"
        )
        for cid, update in sets.items():
            assert "event_id" not in update, (
                f"child {cid}'s re-poll writes event_id={update.get('event_id')!r} "
                "from a parent linked to nothing — every poll wipes the matcher's "
                "link and the next matcher run re-mints (#8430)"
            )

    @pytest.mark.asyncio
    async def test_a_linked_parent_still_carries_its_link_to_every_child(
        self, monkeypatch
    ):
        """The control: the propagation the upsert exists for is unchanged."""
        sets = await _child_conflict_sets(monkeypatch, parent_event_id=15317904)
        assert sets, "the writer emitted no child upsert to inspect"
        for cid, update in sets.items():
            assert update.get("event_id") == 15317904, (
                f"child {cid} no longer inherits its linked parent's event"
            )
