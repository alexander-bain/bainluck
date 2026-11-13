"""#11937 (Alex, 7:42 AM PT Fri Nov 13): a market that is not trading is not featured.

"If they're stale because of illiquid trading, we just shouldn't be featuring
the market." Sized on #11937 from Nov 13's served Discover: a seven-day no-trade
rule removes 20 single cards (seat 3, the Grammys Record of the Year market,
last traded 10.5 days earlier) and trims 31 stale members out of five round-ups.

What must hold:
* a market read as quiet (zero venue 24h volume) for six days or more is "not
  trading"; five days is not; an unknown stamp is never stale;
* the switch turns the rule off;
* a round-up loses each not-trading member from every place it draws or counts
  it, and is dropped when fewer than two remain;
* Discover's futures scoring loop and the cached market snapshot both carry it.
"""

from __future__ import annotations

import ast
import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils import not_trading as nt

NOW = datetime(2026, 11, 13, 17, 0, tzinfo=timezone.utc)


class TestTheRule:
    @pytest.mark.parametrize("days,expected", [(6, True), (19, True), (5.9, False), (0, False)])
    def test_quiet_for_six_days_is_not_trading(self, days, expected):
        assert nt.is_not_trading(NOW - timedelta(days=days), NOW) is expected

    def test_unknown_is_never_stale(self):
        assert nt.is_not_trading(None, NOW) is False

    def test_the_switch_turns_it_off(self, monkeypatch):
        market = SimpleNamespace(quiet_since=NOW - timedelta(days=30))
        monkeypatch.setenv(nt.SWITCH_ENV, "false")
        assert nt.market_not_trading(market, NOW) is False
        monkeypatch.setenv(nt.SWITCH_ENV, "true")
        assert nt.market_not_trading(market, NOW) is True

    def test_a_market_without_the_attribute_is_kept(self):
        assert nt.market_not_trading(SimpleNamespace(), NOW) is False


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
        rows = [(1, NOW - timedelta(days=20)), (2, NOW - timedelta(days=1)), (3, None), (5, NOW - timedelta(days=9))]

        class DB:
            calls = 0

            async def execute(self, stmt):
                DB.calls += 1
                return SimpleNamespace(all=lambda: rows)

        cards = [_roundup([1, 2, 3]), _roundup([4, 5])]
        covered = lambda item: set(item["data"]["member_ids"])
        out = await nt.drop_not_trading_roundup_members(DB(), cards, NOW, covered)
        assert DB.calls == 1
        assert [c["data"]["member_ids"] for c in out] == [[2, 3]]  # second card fell below two


class TestWiring:
    def test_the_feed_scoring_loop_skips_not_trading_markets_before_scoring(self):
        from app.routes import feed

        src = inspect.getsource(feed._score_futures)
        loop = src[src.index("for market in markets:"):]
        assert loop.index("market_not_trading(market, now)") < loop.index("recent_dismissed_futures_ids")

    def test_the_cached_snapshot_carries_the_column(self):
        from app.utils.futures_market_snapshot import MARKET_COLUMNS

        assert "quiet_since" in MARKET_COLUMNS

    def test_roundup_placement_trims_before_placing(self):
        from app.utils import roundup_containers as rc

        src = inspect.getsource(rc.add_roundup_feed_items)
        assert src.index("drop_not_trading_roundup_members") < src.index("insert_roundup_feed_items(")

    def test_the_trigger_sql_keeps_the_first_zero_and_clears_on_volume(self):
        sql = nt.CREATE_FUNCTION_SQL
        assert "NEW.volume_24h > 0 THEN" in sql and "NEW.quiet_since := NULL" in sql
        assert "NEW.quiet_since := OLD.quiet_since" in sql and "NEW.quiet_since := now()" in sql
        assert "UPDATE OF volume_24h" in nt.CREATE_TRIGGER_SQL

    def test_the_migration_is_reversible_and_named_short(self):
        import importlib.util
        from pathlib import Path

        path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "fm_quiet_since_11937.py"
        spec = importlib.util.spec_from_file_location("m", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert len(mod.revision) <= 32 and mod.down_revision == "open_futures_outcomes_4437"
        assert "downgrade" in dir(mod)
