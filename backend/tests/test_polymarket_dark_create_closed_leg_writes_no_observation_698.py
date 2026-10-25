"""#698 / #10955 — a dark market's leg first seen after its own close gains no observation.

`_refresh_linked_polymarket_books` (#3613) gives first legs to a linked
Polymarket market that holds none. For every leg its `ON CONFLICT DO NOTHING`
insert created, it then inserted a `FuturesOddsSnapshot` stamped `now`,
unconditionally. A Polymarket event stays open while its children close one by
one, so a child the venue had already closed arrived here with the last price
its book held, and that frozen price became the first point of a chart, dated
as a fresh observation. The opening on the same leg was already refused
(`opening_capture_is_hindsight`, CERT-3202); the snapshot never asked.

The fix skips ONLY that snapshot, and only when the leg's OWN sub-market says
`closed: true` (`leg_snapshot_is_post_close`, the question the poll's writers
already ask). The leg is still created: current price, book, rank, explicit
NULL grade, the label correction and the field re-rank are unchanged, so a
reader still sees the venue's price.

These tests drive the real pass end to end: venue-shaped Gamma JSON goes
through the real `PolymarketAPIService._parse_event` and the real
`_parent_outcome_data`, and every assertion reads bound parameters off a
statement the pass emitted (ruling 102). Controls: a closed PARENT over open
children, an absent flag and an extreme open quote all keep writing, so
closure is never inferred, and a leg that lost the conflict race is neither
created nor refused.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from sqlalchemy import Delete, Update
from sqlalchemy.sql.expression import Insert, TextClause

from app.services.polymarket_api import PolymarketAPIService
from app.tasks import polymarket as poly
from tests.test_polymarket_dark_linked_market_gets_a_price_3613 import (
    _Row,
    _SelectorResult,
    _WriteResult,
)
from tests.test_polymarket_under_snapshot_book_p097 import (
    RecordingSession,
    _bound_params,
)


# ── recording session: the selector, then every write ──────────────────────


class _Session(RecordingSession):
    """The #3613 dark-pass recorder, with the conflict decided PER LEG.

    `conflict_ids` names the outcome external ids whose insert loses the
    `ON CONFLICT DO NOTHING` race (`RETURNING` yields None), so a field can mix
    created and conflicted legs, which the global switch in the #3613 harness
    cannot express.
    """

    def __init__(self, rows, *, conflict_ids=()):
        super().__init__()
        self._rows = rows
        self._answered_selector = False
        self._conflict_ids = set(conflict_ids)
        self._next_outcome_id = 7000
        self.created: dict[str, int] = {}
        self.executions: list[tuple[object, object]] = []

    async def execute(self, stmt, *args, **kwargs):
        if not self._answered_selector:
            self._answered_selector = True
            return _SelectorResult(self._rows)
        params = args[0] if args else kwargs.get("parameters")
        self.executions.append((stmt, params))
        await super().execute(stmt, *args, **kwargs)
        if (
            isinstance(stmt, Insert)
            and stmt.table.name == "futures_outcomes"
        ):
            ext = _bound_params(stmt)["external_id"]
            if ext in self._conflict_ids:
                return _WriteResult(None)
            self._next_outcome_id += 1
            self.created[ext] = self._next_outcome_id
            return _WriteResult(self._next_outcome_id)
        return _WriteResult(None)


class _Gamma:
    """Gamma as the pass uses it: raw event JSON, parsed by the REAL parser."""

    def __init__(self, payloads):
        self.payloads = payloads
        self._parser = PolymarketAPIService()

    async def get_events_by_ids(self, ids):
        return [self.payloads[i] for i in ids if i in self.payloads]

    def _parse_event(self, raw):
        return self._parser._parse_event(raw)

    async def close(self):
        return None


async def _run(monkeypatch, rows, payloads, *, conflict_ids=()):
    session = _Session(rows, conflict_ids=conflict_ids)
    gamma = _Gamma(payloads)

    @asynccontextmanager
    async def _fake_session():
        yield session

    monkeypatch.setattr(poly, "get_task_session", _fake_session)
    monkeypatch.setattr(
        "app.services.polymarket_api.PolymarketAPIService", lambda *a, **k: gamma
    )
    stats = await poly._refresh_linked_polymarket_books()
    assert not stats["errors"], stats["errors"]
    assert stats["terminal"] == "complete"
    return stats, session


def _legs(session):
    """external_id -> bound VALUES of the futures_outcomes INSERT."""
    return {
        _bound_params(s)["external_id"]: _bound_params(s)
        for s in session.statements
        if isinstance(s, Insert) and s.table.name == "futures_outcomes"
    }


def _snapshots(session):
    """outcome_id -> [bound VALUES of each futures_odds_snapshots INSERT]."""
    out: dict[int, list[dict]] = {}
    for s in session.statements:
        if isinstance(s, Insert) and s.table.name == "futures_odds_snapshots":
            values = _bound_params(s)
            out.setdefault(values["outcome_id"], []).append(values)
    return out


def _label_corrections(session):
    return [
        params["id"]
        for stmt, params in session.executions
        if isinstance(stmt, TextClause) and "SET category = 'game_prop'" in stmt.text
    ]


def _reranks(session):
    return [
        stmt
        for stmt, _ in session.executions
        if isinstance(stmt, Update) and stmt.table.name == "futures_outcomes"
    ]


def _assert_nothing_graded_or_deleted(session):
    for stmt in session.statements:
        assert not isinstance(stmt, Delete), "the pass deleted rows"
        if isinstance(stmt, Insert) and stmt.table.name == "futures_outcomes":
            values = _bound_params(stmt)
            assert "is_winner" in values and values["is_winner"] is None
            assert values["resolution_source"] is None


# ── venue-shaped Gamma JSON ────────────────────────────────────────────────


_OMIT = object()


def _child(idx, title, price, *, closed):
    market = {
        "id": f"m-698d-{idx}",
        "conditionId": f"0x698dark{idx}",
        "question": f"Will {title} win the division?",
        "groupItemTitle": title,
        "slug": f"dark-leg-{idx}",
        "outcomes": '["Yes", "No"]',
        "outcomePrices": f'["{price}", "{round(1 - price, 6)}"]',
        "clobTokenIds": f'["{idx}1", "{idx}2"]',
        # A tight two-sided book with a trade, so every gate upstream of the
        # snapshot passes and the leg is one the pass genuinely prices.
        "bestBid": round(price - 0.01, 4),
        "bestAsk": round(price + 0.01, 4),
        "lastTradePrice": price,
    }
    # `_OMIT` drops the key; any other value is sent as given.
    if closed is not _OMIT:
        market["closed"] = closed
    return market


#: (condition id, team, price) — sorted by price, so the index IS the rank.
FIELD = (("0x698dark1", "Cleveland", 0.55),
         ("0x698dark2", "Kansas City", 0.34),
         ("0x698dark3", "Detroit", 0.11))


def _neg_risk_field(event_id="199045", *, closed=(), parent_closed=False,
                    absent=()):
    """An open (unless `parent_closed`) negRisk field; `closed` names children.

    `absent` children carry no `closed` key at all.
    """
    markets = []
    for n, (cid, team, price) in enumerate(FIELD, 1):
        if cid in absent:
            flag = _OMIT
        else:
            flag = cid in closed
        markets.append(_child(n, team, price, closed=flag))
    return {
        "id": event_id,
        "title": "AL Central Winner",
        "slug": f"al-central-winner-{event_id}",
        "active": True,
        "closed": parent_closed,
        "archived": False,
        "endDate": "2026-12-01T00:00:00Z",
        "startDate": "2026-03-01T00:00:00Z",
        "negRisk": True,
        "markets": markets,
    }


MATCHUP = "Flyers vs. Hurricanes"


def _sole_child(event_id="972698", *, price=0.62, child_closed=False):
    """One game sub-market naming both sides: the pass emits two legs."""
    market = {
        "id": "m-698d-sole",
        "conditionId": "0x698dsole",
        "question": MATCHUP,
        "slug": "flyers-hurricanes-698d",
        "outcomes": '["Flyers", "Hurricanes"]',
        "outcomePrices": f'["{price}", "{round(1 - price, 6)}"]',
        "clobTokenIds": '["d1", "d2"]',
        "bestBid": round(price - 0.02, 4),
        "bestAsk": min(1.0, round(price + 0.01, 4)),
        "lastTradePrice": price,
    }
    market["closed"] = child_closed
    return {
        "id": event_id,
        "title": MATCHUP,
        "slug": f"flyers-vs-hurricanes-{event_id}",
        "active": True,
        "closed": False,
        "archived": False,
        "endDate": "2026-12-01T00:00:00Z",
        "startDate": "2026-05-03T23:00:00Z",
        "negRisk": False,
        "markets": [market],
    }


SOLE_LEGS = {"0x698dsole", "0x698dsole_side1"}


def _field_row(ident=60199045, external_id="199045"):
    # Not a one-contest name, so the label correction never fires here; the
    # re-rank does whenever a leg was created.
    return _Row(ident, external_id, "AL Central Winner")


def _matchup_row(ident=60972698, external_id="972698"):
    # The #3613 specimen's own production shape: tier 5, born `championship`.
    return _Row(ident, external_id, MATCHUP)


# ── the causal case ────────────────────────────────────────────────────────


class TestAClosedChildFirstSeenHereGainsNoObservation:
    @pytest.mark.asyncio
    async def test_a_closed_sole_child_is_created_with_no_snapshot(
        self, monkeypatch
    ):
        """RED before the fix: the first create banked two `now` snapshots."""
        stats, session = await _run(
            monkeypatch, [_matchup_row()],
            {"972698": _sole_child(child_closed=True)},
        )
        legs = _legs(session)
        assert set(legs) == SOLE_LEGS
        assert set(session.created) == SOLE_LEGS, "both legs must be CREATED"

        assert _snapshots(session) == {}, (
            "a leg first seen after its own market closed was given a frozen "
            "price stamped as a fresh observation"
        )
        assert stats["outcomes_created"] == 2
        assert stats["snapshots_written"] == 0
        assert stats["snapshots_refused_closed_leg"] == 2

        # The row the reader sees still lands, whole.
        flyers = legs["0x698dsole"]
        assert flyers["market_id"] == 60972698
        assert flyers["current_probability"] == pytest.approx(0.62)
        assert flyers["current_yes_bid"] == pytest.approx(0.60)
        assert flyers["current_yes_ask"] == pytest.approx(0.63)
        assert flyers["current_american_odds"] is not None
        assert {v["rank"] for v in legs.values()} == {1, 2}
        # The existing opening refusal is unchanged.
        for ext, values in legs.items():
            assert values["opening_probability"] is None, ext
            assert values["opening_captured_at"] is None, ext
        assert stats["opening_refused_hindsight"] == 2
        _assert_nothing_graded_or_deleted(session)

    @pytest.mark.asyncio
    async def test_zero_snapshots_still_relabel_and_rerank(self, monkeypatch):
        """The label and re-rank key on legs CREATED, not snapshots written."""
        stats, session = await _run(
            monkeypatch, [_matchup_row()],
            {"972698": _sole_child(child_closed=True)},
        )
        assert stats["snapshots_written"] == 0
        assert _label_corrections(session) == [60972698]
        assert stats["display_labels_corrected"] == 1
        assert len(_reranks(session)) == 1

    @pytest.mark.asyncio
    async def test_the_same_child_open_writes_both_snapshots(self, monkeypatch):
        """Non-vacuity twin: only the child's flag differs."""
        stats, session = await _run(
            monkeypatch, [_matchup_row()],
            {"972698": _sole_child(child_closed=False)},
        )
        snaps = _snapshots(session)
        assert len(snaps) == 2
        flyers_id = session.created["0x698dsole"]
        [snap] = snaps[flyers_id]
        assert snap["probability"] == pytest.approx(0.62)
        assert snap["bookmaker"] == "polymarket"
        assert snap["captured_at"] is not None
        assert stats["snapshots_written"] == 2
        assert stats.get("snapshots_refused_closed_leg", 0) == 0
        assert _legs(session)["0x698dsole"]["opening_probability"] == 0.62


    @pytest.mark.asyncio
    async def test_the_refusal_count_is_present_at_zero(self, monkeypatch):
        """Rows created and observations written are told apart by a number
        that is there even when nothing was refused (gotcha #53)."""
        stats, _ = await _run(
            monkeypatch, [_matchup_row()],
            {"972698": _sole_child(child_closed=False)},
        )
        assert stats["snapshots_refused_closed_leg"] == 0
        assert stats["outcomes_created"] - stats["snapshots_written"] == 0


class TestAMixedFieldRefusesOnlyItsClosedLeg:
    @pytest.mark.parametrize("closed_cid", [c for c, _, _ in FIELD],
                             ids=["first", "middle", "last"])
    @pytest.mark.asyncio
    async def test_one_closed_child_in_any_position(self, monkeypatch, closed_cid):
        stats, session = await _run(
            monkeypatch, [_field_row()],
            {"199045": _neg_risk_field(closed={closed_cid})},
        )
        legs = _legs(session)
        snaps = _snapshots(session)
        assert set(session.created) == {c for c, _, _ in FIELD}

        for rank, (cid, _, price) in enumerate(FIELD, 1):
            oid = session.created[cid]
            assert legs[cid]["current_probability"] == pytest.approx(price)
            assert legs[cid]["rank"] == rank
            if cid == closed_cid:
                assert oid not in snaps, f"closed {cid} gained an observation"
                assert legs[cid]["opening_probability"] is None
            else:
                assert [s["probability"] for s in snaps[oid]] == [
                    pytest.approx(price)
                ], cid
                assert legs[cid]["opening_probability"] == pytest.approx(price)

        assert stats["outcomes_created"] == 3
        assert stats["snapshots_written"] == 2
        assert stats["snapshots_refused_closed_leg"] == 1
        assert stats["opening_refused_hindsight"] == 1
        assert len(_reranks(session)) == 1
        _assert_nothing_graded_or_deleted(session)

    @pytest.mark.asyncio
    async def test_every_child_closed_creates_three_rows_and_no_snapshot(
        self, monkeypatch
    ):
        stats, session = await _run(
            monkeypatch, [_field_row()],
            {"199045": _neg_risk_field(closed={c for c, _, _ in FIELD})},
        )
        assert set(session.created) == {c for c, _, _ in FIELD}
        assert _snapshots(session) == {}
        assert stats["outcomes_created"] == 3
        assert stats["snapshots_written"] == 0
        assert stats["snapshots_refused_closed_leg"] == 3
        assert len(_reranks(session)) == 1

    @pytest.mark.asyncio
    async def test_a_closed_market_does_not_silence_the_next_market(
        self, monkeypatch
    ):
        """Two dark markets in one pass: the refusal is per leg, not sticky."""
        stats, session = await _run(
            monkeypatch,
            [_matchup_row(), _field_row()],
            {
                "972698": _sole_child(child_closed=True),
                "199045": _neg_risk_field(),
            },
        )
        snaps = _snapshots(session)
        for ext in SOLE_LEGS:
            assert session.created[ext] not in snaps
        for cid, _, price in FIELD:
            assert [s["probability"] for s in snaps[session.created[cid]]] == [
                pytest.approx(price)
            ]
        assert stats["outcomes_created"] == 5
        assert stats["snapshots_written"] == 3
        assert stats["snapshots_refused_closed_leg"] == 2


# ── closure is never inferred ──────────────────────────────────────────────


class TestClosureIsNeverInferred:
    @pytest.mark.asyncio
    async def test_a_closed_parent_over_open_children_still_writes(
        self, monkeypatch
    ):
        """The parent's flag refuses the OPENING (event arm), not the snapshot."""
        stats, session = await _run(
            monkeypatch, [_field_row()],
            {"199045": _neg_risk_field(parent_closed=True)},
        )
        legs = _legs(session)
        assert stats["snapshots_written"] == 3
        assert stats.get("snapshots_refused_closed_leg", 0) == 0
        assert all(v["opening_probability"] is None for v in legs.values())
        assert stats["opening_refused_hindsight"] == 3

    @pytest.mark.asyncio
    async def test_an_absent_flag_keeps_writing(self, monkeypatch):
        stats, session = await _run(
            monkeypatch, [_field_row()],
            {"199045": _neg_risk_field(absent={"0x698dark3"})},
        )
        assert session.created["0x698dark3"] in _snapshots(session)
        assert stats["snapshots_written"] == 3
        assert stats.get("snapshots_refused_closed_leg", 0) == 0

    @pytest.mark.asyncio
    async def test_an_extreme_open_quote_keeps_writing(self, monkeypatch):
        stats, session = await _run(
            monkeypatch, [_matchup_row()],
            {"972698": _sole_child(price=0.99, child_closed=False)},
        )
        snaps = _snapshots(session)
        [snap] = snaps[session.created["0x698dsole"]]
        assert snap["probability"] == pytest.approx(0.99)
        assert stats["snapshots_written"] == 2
        assert stats.get("snapshots_refused_closed_leg", 0) == 0

    def test_the_parser_types_the_child_flag_as_a_bool(self):
        """What the strict `is True` reads off the real DTO.

        `PolymarketMarket.closed` is a pydantic `bool`: an absent key parses
        False, so it keeps writing (above). No unknown value can reach the
        writer: the parser never hands it a None.
        """
        event = PolymarketAPIService()._parse_event(
            _neg_risk_field(closed={"0x698dark3"}, absent={"0x698dark2"})
        )
        flags = {m.condition_id: m.closed for m in event.markets}
        assert flags == {
            "0x698dark1": False, "0x698dark2": False, "0x698dark3": True,
        }


# ── the conflict race ──────────────────────────────────────────────────────


class TestTheConflictRace:
    @pytest.mark.asyncio
    async def test_a_closed_leg_that_lost_the_race_is_neither_created_nor_refused(
        self, monkeypatch
    ):
        """A concurrent writer's row wins; this pass wrote nothing for it."""
        stats, session = await _run(
            monkeypatch, [_matchup_row()],
            {"972698": _sole_child(child_closed=True)},
            conflict_ids=SOLE_LEGS,
        )
        assert session.created == {}
        assert _snapshots(session) == {}
        assert stats["outcomes_created"] == 0
        assert stats.get("snapshots_refused_closed_leg", 0) == 0
        assert _label_corrections(session) == []
        assert _reranks(session) == []

    @pytest.mark.asyncio
    async def test_open_legs_lost_the_race_closed_leg_created_zero_snapshots(
        self, monkeypatch
    ):
        """The one created leg is closed: a row, no observation, re-ranked."""
        stats, session = await _run(
            monkeypatch, [_field_row()],
            {"199045": _neg_risk_field(closed={"0x698dark2"})},
            conflict_ids={"0x698dark1", "0x698dark3"},
        )
        assert set(session.created) == {"0x698dark2"}
        assert _snapshots(session) == {}
        assert stats["outcomes_created"] == 1
        assert stats["snapshots_written"] == 0
        assert stats["snapshots_refused_closed_leg"] == 1
        assert len(_reranks(session)) == 1

    @pytest.mark.asyncio
    async def test_closed_leg_lost_the_race_open_siblings_still_write(
        self, monkeypatch
    ):
        stats, session = await _run(
            monkeypatch, [_field_row()],
            {"199045": _neg_risk_field(closed={"0x698dark1"})},
            conflict_ids={"0x698dark1"},
        )
        snaps = _snapshots(session)
        assert set(session.created) == {"0x698dark2", "0x698dark3"}
        assert all(session.created[c] in snaps for c in session.created)
        assert stats["snapshots_written"] == 2
        assert stats.get("snapshots_refused_closed_leg", 0) == 0
