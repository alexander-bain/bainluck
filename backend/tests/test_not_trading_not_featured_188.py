"""Ruling 188 (#11937): a market nobody is trading never takes a Discover seat.

Alex, Nov 13: "If they're stale because of illiquid trading, we just shouldn't
be featuring the market." Built with no schema change: a market whose newest
price change (``futures_outcomes.price_changed_at``) is a week old, and whose
venue reports no 24-hour volume, is not trading.

What must hold:
* a week of still prices with no volume is "not trading"; any volume, any
  recent move, or an unknown price age is not;
* the switch turns the rule off;
* the cached snapshot and an ORM row give the same answer (one folded stamp);
* a round-up loses each not-trading member from every place it draws or counts
  it, with one read, and is dropped when fewer than two remain;
* Discover's futures scoring loop refuses the market before anything else.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils import not_trading as nt

NOW = datetime(2026, 11, 15, 23, 0, tzinfo=timezone.utc)


def _ago(days):
    return NOW - timedelta(days=days)


class TestTheRule:
    @pytest.mark.parametrize(
        "days,volume,expected",
        [
            (7, None, True),
            (30, 0, True),
            (6.9, None, False),
            (0, 0, False),
            (30, 12, False),  # any volume is trading, whatever the price did
            (30, 0.04, False),  # Kalshi's sub-unit volumes are real (#7747)
        ],
    )
    def test_a_still_week_with_no_volume_is_not_trading(self, days, volume, expected):
        assert nt.is_not_trading(_ago(days), volume, NOW) is expected

    def test_an_unknown_price_age_is_never_stale(self):
        assert nt.is_not_trading(None, 0, NOW) is False

    def test_the_switch_turns_it_off(self, monkeypatch):
        market = SimpleNamespace(price_changed_at=_ago(30), volume_24h=0)
        monkeypatch.setenv(nt.SWITCH_ENV, "false")
        assert nt.market_not_trading(market, NOW) is False
        monkeypatch.setenv(nt.SWITCH_ENV, "true")
        assert nt.market_not_trading(market, NOW) is True


class TestBothCarriersAgree:
    def test_an_orm_shaped_row_folds_its_outcomes(self):
        market = SimpleNamespace(
            volume_24h=None,
            outcomes=[SimpleNamespace(price_changed_at=_ago(40)), SimpleNamespace(price_changed_at=_ago(9))],
        )
        assert nt.market_not_trading(market, NOW) is True
        market.outcomes.append(SimpleNamespace(price_changed_at=_ago(1)))
        assert nt.market_not_trading(market, NOW) is False

    def test_a_leg_without_a_stamp_does_not_make_a_market_stale(self):
        market = SimpleNamespace(volume_24h=0, outcomes=[SimpleNamespace(price_changed_at=None)])
        assert nt.market_not_trading(market, NOW) is False

    def test_the_snapshot_carries_the_folded_stamp(self):
        from app.utils import futures_market_snapshot as fs

        assert "price_changed_at" in fs.DERIVED_MARKET_COLUMNS
        assert "price_changed_at" in fs.OUTCOME_LOAD_ONLY_EXTRA
        assert "volume_24h" in fs.MARKET_COLUMNS
        folded = SimpleNamespace(price_changed_at=_ago(12), volume_24h=None, outcomes=[])
        assert fs.price_change_stamp(folded) == _ago(12)


def _roundup(ids):
    return {"type": "bundle", "data": {
        "id": "roundup:x", "member_ids": list(ids), "item_count": len(ids),
        "items": [{"type": "futures", "data": {"id": i}} for i in ids],
        "roundup": {"rows": [{"market_id": i, "label": str(i)} for i in ids]},
    }}


class TestRoundups:
    def test_a_stale_member_leaves_every_place_the_card_draws_it(self):
        out = nt.trim_roundup(_roundup([1, 2, 3, 4]), {2})
        data = out["data"]
        assert data["member_ids"] == [1, 3, 4] and data["item_count"] == 3
        assert [i["data"]["id"] for i in data["items"]] == [1, 3, 4]
        assert [r["market_id"] for r in data["roundup"]["rows"]] == [1, 3, 4]

    def test_too_few_left_drops_the_roundup(self):
        assert nt.trim_roundup(_roundup([1, 2, 3]), {2, 3}) is None

    def test_no_stale_member_leaves_it_alone(self):
        card = _roundup([1, 2, 3])
        assert nt.trim_roundup(card, set()) is card

    async def test_one_read_covers_every_roundup(self):
        # (market id, volume_24h, newest price change)
        rows = [(1, 0, _ago(20)), (2, None, _ago(1)), (3, 0, None), (4, 50, _ago(30)), (5, None, _ago(9))]

        class DB:
            calls = 0

            async def execute(self, stmt):
                DB.calls += 1
                return SimpleNamespace(all=lambda: rows)

        cards = [_roundup([1, 2, 3]), _roundup([5, 6]), _roundup([4, 2])]
        covered = lambda item: set(item["data"]["member_ids"])
        out = await nt.drop_not_trading_roundup_members(DB(), cards, NOW, covered)
        assert DB.calls == 1
        # 1 and 5 are dead; 6 alone is too few; 4 trades (volume) so its card stays whole.
        assert [c["data"]["member_ids"] for c in out] == [[2, 3], [4, 2]]


class TestWiring:
    def test_the_feed_scoring_loop_refuses_before_anything_else(self):
        from app.routes import feed

        src = inspect.getsource(feed._score_futures)
        loop = src[src.index("for market in markets:"):]
        assert loop.index("market_not_trading(market, now)") < loop.index("recent_dismissed_futures_ids")

    def test_roundup_placement_trims_before_placing(self):
        from app.utils import roundup_containers as rc

        src = inspect.getsource(rc.add_roundup_feed_items)
        assert src.index("drop_not_trading_roundup_members") < src.index("insert_roundup_feed_items(")

    def test_no_schema_change(self):
        from app.models.models import FuturesMarket

        assert "quiet_since" not in FuturesMarket.__table__.columns


def test_a_market_rebuilt_from_the_cache_gives_the_same_answer_as_the_row_it_came_from():
    """The cached path and the build path must refuse the same markets: the fold
    happens in `to_plain` and the rebuilt row carries it."""
    from app.utils import futures_market_snapshot as fs

    def outcome(i, changed):
        o = SimpleNamespace(**{c: None for c in fs.OUTCOME_COLUMNS + fs.OUTCOME_LOAD_ONLY_EXTRA})
        o.id, o.name, o.current_probability, o.price_changed_at = i, f"o{i}", 0.5, changed
        return o

    def market(mid, changes, volume):
        m = SimpleNamespace(**{c: None for c in fs.MARKET_COLUMNS})
        m.id, m.name, m.source, m.volume_24h = mid, f"m{mid}", "polymarket", volume
        m.outcomes = [outcome(mid * 10 + n, c) for n, c in enumerate(changes)]
        m.sport = None
        return m

    rows = [market(1, [_ago(30), _ago(12)], 0), market(2, [_ago(30), _ago(2)], None), market(3, [None], 0)]
    rebuilt = fs.from_plain(fs.to_plain(rows))
    assert [m.id for m in rebuilt] == [1, 2, 3]
    assert [nt.market_not_trading(m, NOW) for m in rows] == [True, False, False]
    assert [nt.market_not_trading(m, NOW) for m in rebuilt] == [True, False, False]
    assert rebuilt[0].__dict__["price_changed_at"] == _ago(12)


def test_the_count_line_follows_the_rows_that_remain():
    """Monday's render (Nov 16): "By November 30" drew 4 rows under "Showing 5 of 6"."""
    from app.utils.not_trading import trim_roundup

    def card(n, line, shown=5):
        return {"data": {"member_ids": list(range(1, n + 1)), "items": [],
                         "roundup": {"rows": [{"market_id": i} for i in range(1, shown + 1)], "count_line": line}}}

    assert trim_roundup(card(6, "Showing 5 of 6"), {1})["data"]["roundup"]["count_line"] == "Showing 4 of 5"
    assert trim_roundup(card(30, "Showing 5 of 30 clubs"), {1, 2, 20, 21})["data"]["roundup"]["count_line"] == "Showing 3 of 26 clubs"
    # The one hidden member was the quiet one: nothing is hidden any more, so no line.
    assert trim_roundup(card(6, "Showing 5 of 6"), {6})["data"]["roundup"]["count_line"] is None
