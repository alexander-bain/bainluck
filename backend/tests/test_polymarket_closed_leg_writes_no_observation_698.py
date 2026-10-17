"""#698 / #10955 — a closed Polymarket leg gains no new observation.

The parent-field writer in `_process_event_batch` upserted each leg and then
inserted a `FuturesOddsSnapshot` stamped `now`, unconditionally. A Polymarket
event stays open while its children close one by one, so a child the venue
had closed kept arriving with the last price its book held and was banked
hourly as a fresh observation (Detroit on 199045: 26 days of frozen rows after
its own market closed). The opening stamp on the same leg already refused it
(CERT-3202); the snapshot never asked.

The fix skips ONLY that snapshot, and only when the leg's OWN sub-market says
`closed: true`. The rail tests start the real writer over a recording fake
session (ruling 102) and assert both directions: the closed leg keeps its
outcome row, current price and book but gains no snapshot, while open legs —
including siblings in the same field — write exactly as before.

Controls: an extreme price, a past end date, a closed PARENT over an open
child and an absent flag all keep writing — closure is never inferred.
Fix-forward only: no existing row is touched and `is_winner` is never written.
"""

from collections import defaultdict
from types import SimpleNamespace

from sqlalchemy import Delete, Insert, Update
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
from app.services.polymarket_api import PolymarketAPIService
from app.tasks import polymarket as poly
from app.utils.market_label_normalization import compute_market_tier
from app.utils.odds_math import probability_to_american


# ── recording fake session ─────────────────────────────────────────────────


class _FakeResult:
    def __init__(self, fake, stmt):
        self._fake = fake
        self._stmt = stmt

    def scalar_one(self):
        self._fake._next_id += 1
        self._fake.returned_ids[id(self._stmt)] = self._fake._next_id
        return self._fake._next_id

    def scalar_one_or_none(self):
        return None

    def scalar(self):
        return None

    @property
    def rowcount(self):
        return 0


class _Savepoint:
    is_active = True

    async def commit(self):
        self.is_active = False

    async def rollback(self):
        self.is_active = False


class _FakeSession:
    def __init__(self):
        self.statements = []
        self.returned_ids = {}
        self._next_id = 1000

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, stmt):
        self.statements.append(stmt)
        return _FakeResult(self, stmt)

    async def commit(self):
        pass

    async def begin_nested(self):
        return _Savepoint()


def _params(stmt):
    return stmt.compile(dialect=postgresql.dialect()).params


def _inserts(fake, table):
    return [
        s for s in fake.statements
        if isinstance(s, Insert) and s.table.name == table
    ]


def _legs(fake):
    """external_id -> (outcome_id the writer got back, the VALUES arm)."""
    out = {}
    for stmt in _inserts(fake, "futures_outcomes"):
        values = _params(stmt)
        out[values["external_id"]] = (fake.returned_ids.get(id(stmt)), values)
    return out


def _snapshots_by_outcome(fake):
    by_outcome = defaultdict(list)
    for stmt in _inserts(fake, "futures_odds_snapshots"):
        values = _params(stmt)
        by_outcome[values["outcome_id"]].append(values)
    return by_outcome


async def _run_batch(monkeypatch, event):
    fake = _FakeSession()
    monkeypatch.setattr(poly, "get_task_session", lambda: fake)
    stats = defaultdict(int, {"by_category": {}, "errors": []})
    await poly._process_event_batch(
        [event],
        stats,
        FuturesMarket,
        FuturesOutcome,
        FuturesOddsSnapshot,
        pg_insert,
        probability_to_american,
        compute_market_tier,
    )
    assert not stats.get("errors"), f"the writer errored: {stats.get('errors')}"
    return fake, stats


def _assert_no_grade_or_loss(fake):
    """No delete, and no write of `is_winner` / `resolution_source` other than
    the explicit NULL the INSERT arm has always carried (#4788)."""
    for stmt in fake.statements:
        assert not isinstance(stmt, Delete), "the writer deleted rows"
        if isinstance(stmt, (Insert, Update)) and stmt.table.name == "futures_outcomes":
            values = _params(stmt)
            assert values.get("is_winner") is None, "a grade was written"
            assert values.get("resolution_source") is None


# ── venue-shaped fixtures, through the REAL parser ─────────────────────────


def _leg_market(idx, title, price, *, closed):
    market = {
        "id": f"m-698-{idx}",
        "conditionId": f"0x698leg{idx}",
        "question": f"Will {title} win the division?",
        "groupItemTitle": title,
        "slug": f"leg-{idx}",
        "outcomes": '["Yes", "No"]',
        "outcomePrices": f'["{price}", "{round(1 - price, 6)}"]',
        "clobTokenIds": f'["{idx}1", "{idx}2"]',
        # A tight two-sided book with a trade, so every gate upstream of the
        # snapshot passes and the leg is one the writer genuinely prices.
        "bestBid": round(price - 0.01, 4),
        "bestAsk": round(price + 0.01, 4),
        "lastTradePrice": price,
    }
    if closed is not None:
        market["closed"] = closed
    return market


def _neg_risk_field(*, detroit_closed, end_date="2026-12-01T00:00:00Z"):
    """An OPEN negRisk parent whose Detroit child the venue has closed."""
    return {
        "id": "199045",
        "title": "AL Central Winner",
        "slug": "al-central-winner",
        "active": True,
        "closed": False,
        "archived": False,
        "endDate": end_date,
        "startDate": "2026-03-01T00:00:00Z",
        "negRisk": True,
        "markets": [
            _leg_market(1, "Cleveland", 0.55, closed=False),
            _leg_market(2, "Kansas City", 0.34, closed=False),
            _leg_market(3, "Detroit", 0.11, closed=detroit_closed),
        ],
    }


def _sole_child(*, price, child_closed, parent_closed=False,
                end_date="2026-12-01T00:00:00Z"):
    """One sub-market naming both sides, so the writer emits two legs."""
    market = {
        "id": "m-698-sole",
        "conditionId": "0x698sole",
        "question": "Flyers vs. Hurricanes",
        "slug": "flyers-hurricanes-698",
        "outcomes": '["Flyers", "Hurricanes"]',
        "outcomePrices": f'["{price}", "{round(1 - price, 6)}"]',
        "clobTokenIds": '["s1", "s2"]',
        "bestBid": round(price - 0.02, 4),
        "bestAsk": min(1.0, round(price + 0.01, 4)),
        "lastTradePrice": price,
    }
    if child_closed is not None:
        market["closed"] = child_closed
    return {
        "id": "evt-698-sole",
        "title": "Flyers vs. Hurricanes",
        "slug": "flyers-vs-hurricanes-698",
        "active": True,
        "closed": parent_closed,
        "archived": False,
        "endDate": end_date,
        "startDate": "2026-05-03T23:00:00Z",
        "negRisk": False,
        "markets": [market],
    }


def _parse(payload):
    event = PolymarketAPIService()._parse_event(payload)
    assert event is not None, "the parser refused a venue-shaped payload"
    assert poly._parent_outcome_data(event), "no writable leg — fixture inert"
    return event


# ── the predicate ──────────────────────────────────────────────────────────


class TestLegSnapshotIsPostClose:
    def test_a_leg_whose_own_market_is_closed(self):
        leg = {"market": SimpleNamespace(closed=True)}
        assert poly.leg_snapshot_is_post_close(leg) is True

    def test_an_open_leg(self):
        leg = {"market": SimpleNamespace(closed=False)}
        assert poly.leg_snapshot_is_post_close(leg) is False

    def test_unknown_status_keeps_writing(self):
        """Absent, None or non-boolean status is not a closure."""
        for leg in (
            {},
            {"market": None},
            {"market": SimpleNamespace()},
            {"market": SimpleNamespace(closed=None)},
            {"market": SimpleNamespace(closed="true")},
            None,
        ):
            assert poly.leg_snapshot_is_post_close(leg) is False, leg

    def test_the_parser_types_the_flag_as_a_bool(self):
        """The strict `is True` reads the real DTO, not a truthy string."""
        event = _parse(_neg_risk_field(detroit_closed=True))
        flags = {m.condition_id: m.closed for m in event.markets}
        assert flags["0x698leg3"] is True
        assert flags["0x698leg1"] is False


# ── the real writer ────────────────────────────────────────────────────────


class TestAClosedChildUnderAnOpenParent:
    async def test_mixed_field_closed_leg_gains_no_snapshot(self, monkeypatch):
        """The causal case: open parent, two live legs, one closed child."""
        event = _parse(_neg_risk_field(detroit_closed=True))
        assert not event.closed and event.active, "the PARENT must be open"
        fake, stats = await _run_batch(monkeypatch, event)
        legs = _legs(fake)
        snaps = _snapshots_by_outcome(fake)

        assert set(legs) == {"0x698leg1", "0x698leg2", "0x698leg3"}
        detroit_id, detroit = legs["0x698leg3"]
        assert detroit_id is not None
        assert snaps.get(detroit_id) is None, (
            "a closed child's frozen price was banked as a new observation"
        )
        # The outcome row, current price and book still write.
        assert detroit["current_probability"] == 0.11
        assert detroit["current_yes_bid"] == 0.10
        assert detroit["current_yes_ask"] == 0.12
        # The existing opening refusal is unchanged.
        assert detroit["opening_probability"] is None

        # Live siblings in the same field write exactly as before.
        for ext, price in (("0x698leg1", 0.55), ("0x698leg2", 0.34)):
            oid, values = legs[ext]
            assert [s["probability"] for s in snaps[oid]] == [price], ext
            assert values["opening_probability"] == price

        assert stats["snapshots_refused_closed_leg"] == 1
        assert stats["snapshots_created"] == 2
        assert stats["outcomes_updated"] == 3
        _assert_no_grade_or_loss(fake)

    async def test_the_same_field_open_writes_every_snapshot(self, monkeypatch):
        """Non-vacuity twin: only Detroit's flag differs."""
        event = _parse(_neg_risk_field(detroit_closed=False))
        fake, stats = await _run_batch(monkeypatch, event)
        legs = _legs(fake)
        snaps = _snapshots_by_outcome(fake)
        detroit_id, _ = legs["0x698leg3"]
        assert [s["probability"] for s in snaps[detroit_id]] == [0.11]
        assert stats["snapshots_created"] == 3
        assert stats.get("snapshots_refused_closed_leg", 0) == 0

    async def test_a_closed_sole_child_writes_rows_but_no_snapshot(
        self, monkeypatch
    ):
        event = _parse(_sole_child(price=0.62, child_closed=True))
        fake, stats = await _run_batch(monkeypatch, event)
        legs = _legs(fake)
        assert set(legs) == {"0x698sole", "0x698sole_side1"}
        for ext, (_, values) in legs.items():
            assert values["current_probability"] is not None, ext
            assert values["opening_probability"] is None, ext
        assert _inserts(fake, "futures_odds_snapshots") == []
        assert stats["snapshots_refused_closed_leg"] == 2
        assert stats.get("snapshots_created", 0) == 0
        _assert_no_grade_or_loss(fake)


class TestClosureIsNeverInferred:
    async def test_an_open_leg_at_an_extreme_price_still_writes(self, monkeypatch):
        event = _parse(_sole_child(price=0.99, child_closed=False))
        fake, stats = await _run_batch(monkeypatch, event)
        legs = _legs(fake)
        snaps = _snapshots_by_outcome(fake)
        oid, _ = legs["0x698sole"]
        assert [s["probability"] for s in snaps[oid]] == [0.99]
        assert len(_inserts(fake, "futures_odds_snapshots")) == 2
        assert stats.get("snapshots_refused_closed_leg", 0) == 0

    async def test_a_past_end_date_refuses_the_opening_not_the_snapshot(
        self, monkeypatch
    ):
        event = _parse(_sole_child(
            price=0.62, child_closed=False, end_date="2026-05-04T00:00:00Z",
        ))
        fake, stats = await _run_batch(monkeypatch, event)
        legs = _legs(fake)
        for ext, (_, values) in legs.items():
            assert values["opening_probability"] is None, ext
        assert stats["opening_refused_hindsight"] >= 1
        assert len(_inserts(fake, "futures_odds_snapshots")) == 2
        assert stats.get("snapshots_refused_closed_leg", 0) == 0

    async def test_a_closed_parent_over_an_open_child_is_not_this_rule(
        self, monkeypatch
    ):
        """The rule reads the leg's own flag; the parent's alone is not it."""
        event = _parse(_sole_child(
            price=0.62, child_closed=False, parent_closed=True,
        ))
        fake, stats = await _run_batch(monkeypatch, event)
        assert len(_inserts(fake, "futures_odds_snapshots")) == 2
        assert stats.get("snapshots_refused_closed_leg", 0) == 0

    async def test_an_absent_flag_keeps_writing(self, monkeypatch):
        event = _parse(_sole_child(price=0.62, child_closed=None))
        fake, stats = await _run_batch(monkeypatch, event)
        assert len(_inserts(fake, "futures_odds_snapshots")) == 2
        assert stats.get("snapshots_refused_closed_leg", 0) == 0
