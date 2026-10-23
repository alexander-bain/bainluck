"""#698 / #10955 — a closed DECOMPOSED Polymarket leg gains no new observation.

The parent-field writer stopped banking a closed child's frozen book
(`leg_snapshot_is_post_close`, PR #11183). CERT-4193 then ran the same mixed
field with `negRisk: false`: that shape also takes the decomposition branch of
`_process_event_batch`, which writes each child as its own sub-market row with
a `{condition}_yes` / `{condition}_no` pair, and both of the closed child's
legs still got a `FuturesOddsSnapshot` stamped `now` — 2 parent + 3 decomposed
rows where the closed child should have contributed none.

The fix skips ONLY those two snapshots, and only when the child's OWN market
says `closed: true` (`submarket_snapshot_is_post_close`). The tests run the
real parser and the real writer over the recording session the parent-field
guard uses (ruling 102) and assert both directions with exact outcome
identities: the closed child keeps its sub-market row, both outcome rows,
current prices and books but gains no snapshot on either side, while open
siblings in the same field write exactly one snapshot per side.

Controls: all-open, a closed PARENT over open children, an absent flag and an
extreme price all keep writing — closure is never inferred. Fix-forward only:
no delete, no existing row rewritten, `is_winner` never written.
"""

import pytest

from app.tasks import polymarket as poly
from tests.test_polymarket_closed_leg_writes_no_observation_698 import (
    _assert_no_grade_or_loss,
    _inserts,
    _legs,
    _neg_risk_field,
    _params,
    _parse,
    _run_batch,
    _snapshots_by_outcome,
)

_PRICES = {1: 0.55, 2: 0.34, 3: 0.11}


def _plain_field(closed_flags, *, parent_closed=False):
    """The 199045-shaped field with `negRisk: false`, so it decomposes.

    `closed_flags` maps child index -> the venue's `closed` value; `None`
    omits the key entirely (an absent flag, not False).
    """
    payload = _neg_risk_field(detroit_closed=False)
    payload["negRisk"] = False
    payload["closed"] = parent_closed
    for market in payload["markets"]:
        idx = int(market["conditionId"].removeprefix("0x698leg"))
        flag = closed_flags.get(idx, False)
        if flag is None:
            market.pop("closed", None)
        else:
            market["closed"] = flag
    event = _parse(payload)
    assert not event.neg_risk and len(event.markets) == 3, (
        "fixture must take the decomposition branch"
    )
    return event


def _sub_market_rows(fake):
    """condition_id -> VALUES of the decomposed `polymarket_sub_market` row."""
    out = {}
    for stmt in _inserts(fake, "futures_markets"):
        values = _params(stmt)
        if values.get("group_type") == "polymarket_sub_market":
            out[values["external_id"]] = values
    return out


def _decomposed_snaps(fake, idx):
    """(yes snapshots, no snapshots) for child `idx`, by exact outcome id."""
    legs = _legs(fake)
    snaps = _snapshots_by_outcome(fake)
    yes_id, _ = legs[f"0x698leg{idx}_yes"]
    no_id, _ = legs[f"0x698leg{idx}_no"]
    assert yes_id is not None and no_id is not None
    return snaps.get(yes_id, []), snaps.get(no_id, [])


def _conflict_update_keys(fake, external_id):
    for stmt in _inserts(fake, "futures_outcomes"):
        if _params(stmt)["external_id"] == external_id:
            return set(dict(stmt._post_values_clause.update_values_to_set))
    raise AssertionError(f"no outcome upsert for {external_id}")


# ── the predicate ──────────────────────────────────────────────────────────


class TestSubmarketSnapshotIsPostClose:
    def test_a_closed_market(self):
        event = _plain_field({3: True})
        flags = {m.condition_id: m for m in event.markets}
        assert poly.submarket_snapshot_is_post_close(flags["0x698leg3"]) is True
        assert poly.submarket_snapshot_is_post_close(flags["0x698leg1"]) is False

    def test_unknown_status_keeps_writing(self):
        from types import SimpleNamespace

        for market in (
            None,
            SimpleNamespace(),
            SimpleNamespace(closed=None),
            SimpleNamespace(closed="true"),
            SimpleNamespace(closed=1),
        ):
            assert poly.submarket_snapshot_is_post_close(market) is False, market

    def test_the_parent_field_helper_asks_the_same_question(self):
        from types import SimpleNamespace

        for flag in (True, False, None, "true"):
            market = SimpleNamespace(closed=flag)
            assert poly.leg_snapshot_is_post_close(
                {"market": market}
            ) is poly.submarket_snapshot_is_post_close(market)


# ── the real writer ────────────────────────────────────────────────────────


class TestAClosedDecomposedChildUnderAnOpenParent:
    @pytest.mark.parametrize("closed_idx", [1, 2, 3])
    async def test_both_sides_of_the_closed_child_gain_no_snapshot(
        self, monkeypatch, closed_idx
    ):
        """The CERT-4193 counterexample, closed child first/middle/last."""
        event = _plain_field({closed_idx: True})
        assert not event.closed and event.active, "the PARENT must be open"
        fake, stats = await _run_batch(monkeypatch, event)
        legs = _legs(fake)
        price = _PRICES[closed_idx]

        yes_snaps, no_snaps = _decomposed_snaps(fake, closed_idx)
        assert yes_snaps == [], "a closed child's Yes leg banked a frozen price"
        assert no_snaps == [], "a closed child's No leg banked a frozen price"

        # Its rows, current prices and books still write; opening still refused.
        sub_row = _sub_market_rows(fake)[f"0x698leg{closed_idx}"]
        assert sub_row["status"] == "resolved"
        _, yes = legs[f"0x698leg{closed_idx}_yes"]
        _, no = legs[f"0x698leg{closed_idx}_no"]
        assert yes["current_probability"] == price
        assert no["current_probability"] == pytest.approx(1 - price)
        assert yes["current_yes_bid"] == pytest.approx(price - 0.01)
        assert yes["current_yes_ask"] == pytest.approx(price + 0.01)
        assert no["current_yes_bid"] is not None
        assert no["current_yes_ask"] is not None
        assert yes["opening_probability"] is None
        assert no["opening_probability"] is None
        for side in ("yes", "no"):
            keys = _conflict_update_keys(fake, f"0x698leg{closed_idx}_{side}")
            assert {
                "current_probability", "current_yes_bid", "current_yes_ask",
                "rank", "last_updated",
            } <= keys, side
            assert not keys & {
                "is_winner", "resolution_source", "opening_probability",
            }, side

        # Open siblings write exactly one snapshot per side, at their own price.
        for idx, sib_price in _PRICES.items():
            if idx == closed_idx:
                continue
            yes_snaps, no_snaps = _decomposed_snaps(fake, idx)
            assert [s["probability"] for s in yes_snaps] == [sib_price], idx
            assert [s["probability"] for s in no_snaps] == [
                pytest.approx(1 - sib_price)
            ], idx

        # Parent field (PR #11183): the same child's parent leg is refused too.
        snaps = _snapshots_by_outcome(fake)
        parent_id, _ = legs[f"0x698leg{closed_idx}"]
        assert snaps.get(parent_id) is None

        # 2 parent legs + 2 open children x 2 sides; 1 + 2 refused.
        assert len(_inserts(fake, "futures_odds_snapshots")) == 6
        assert stats["snapshots_refused_closed_leg"] == 3
        # Parent writer counts per leg (2), decomposed per sub-market (2).
        assert stats["snapshots_created"] == 4
        _assert_no_grade_or_loss(fake)

    async def test_every_child_closed_writes_rows_and_no_snapshot(
        self, monkeypatch
    ):
        event = _plain_field({1: True, 2: True, 3: True})
        fake, stats = await _run_batch(monkeypatch, event)
        assert _inserts(fake, "futures_odds_snapshots") == []
        assert set(_sub_market_rows(fake)) == {
            "0x698leg1", "0x698leg2", "0x698leg3",
        }
        assert stats["snapshots_refused_closed_leg"] == 3 + 6
        assert stats.get("snapshots_created", 0) == 0
        _assert_no_grade_or_loss(fake)


class TestClosureIsNeverInferred:
    async def test_the_same_field_open_writes_every_snapshot(self, monkeypatch):
        """Non-vacuity twin: only the child's flag differs."""
        event = _plain_field({})
        fake, stats = await _run_batch(monkeypatch, event)
        for idx, price in _PRICES.items():
            yes_snaps, no_snaps = _decomposed_snaps(fake, idx)
            assert [s["probability"] for s in yes_snaps] == [price], idx
            assert len(no_snaps) == 1, idx
        assert len(_inserts(fake, "futures_odds_snapshots")) == 3 + 6
        assert stats.get("snapshots_refused_closed_leg", 0) == 0

    async def test_a_closed_parent_over_open_children_is_not_this_rule(
        self, monkeypatch
    ):
        event = _plain_field({}, parent_closed=True)
        assert event.closed
        fake, stats = await _run_batch(monkeypatch, event)
        for idx in _PRICES:
            yes_snaps, no_snaps = _decomposed_snaps(fake, idx)
            assert len(yes_snaps) == 1 and len(no_snaps) == 1, idx
        assert stats.get("snapshots_refused_closed_leg", 0) == 0

    async def test_an_absent_flag_keeps_writing(self, monkeypatch):
        event = _plain_field({3: None})
        fake, stats = await _run_batch(monkeypatch, event)
        yes_snaps, no_snaps = _decomposed_snaps(fake, 3)
        assert [s["probability"] for s in yes_snaps] == [0.11]
        assert len(no_snaps) == 1
        assert stats.get("snapshots_refused_closed_leg", 0) == 0

    async def test_an_open_child_at_an_extreme_price_still_writes(
        self, monkeypatch
    ):
        payload = _neg_risk_field(detroit_closed=False)
        payload["negRisk"] = False
        detroit = payload["markets"][2]
        detroit.update({
            "outcomePrices": '["0.995", "0.005"]',
            "bestBid": 0.99, "bestAsk": 1.0, "lastTradePrice": 0.995,
        })
        fake, stats = await _run_batch(monkeypatch, _parse(payload))
        yes_snaps, no_snaps = _decomposed_snaps(fake, 3)
        assert [s["probability"] for s in yes_snaps] == [0.995]
        assert len(no_snaps) == 1
        assert stats.get("snapshots_refused_closed_leg", 0) == 0
