"""Tests for the settled-means-settled evolution freeze (#1177, Queue #230).

When a futures market has a graded champion (exactly one outcome with
``is_winner=True``), the ``/{market_id}/history`` endpoint must resolve that
champion's path-to-resolution line to 1.0 at settlement time — regardless of
which source's snapshots were charted (odds_api can fizzle a settled winner to a
longshot value while Kalshi resolves to ~1.0). This is what greens the
Settled-Concept Sentinel's Check C (evolution resolves) generically, and it must
fire even while the winner market is stuck ``status='open'`` (gotcha #33), so it
keys on ``is_winner``, never on ``status``.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from app.routes.futures import _apply_settled_winner_freeze, get_futures_history


def _make_outcome(oid, name, prob=0.5, is_winner=False):
    o = MagicMock()
    o.id = oid
    o.name = name
    o.current_probability = prob
    o.is_winner = is_winner
    o.last_updated = None
    return o


def _make_market(market_id=1, outcomes=None, resolution_date=None, metadata=None):
    m = MagicMock()
    m.id = market_id
    m.name = "Winner Market"
    m.market_metadata = metadata
    m.resolution_date = resolution_date
    m.outcomes = outcomes or []
    return m


def _snap(outcome_id, captured_at, prob):
    s = MagicMock()
    s.outcome_id = outcome_id
    s.captured_at = captured_at
    s.probability = prob
    s.bookmaker = "test"
    return s


def _hist(points):
    """points = list of (iso_ts, prob)"""
    return [{"timestamp": ts, "probability": p, "american_odds": None, "bookmaker": "c"} for ts, p in points]


class TestApplySettledWinnerFreeze:
    def test_fizzled_champion_line_resolves_to_one(self):
        """Champion charted from a source that fizzled (0.587) gets a terminal 1.0."""
        now = datetime.now(timezone.utc)
        champ = _make_outcome(100, "Spain", prob=0.587, is_winner=True)
        other = _make_outcome(200, "France", prob=0.30)
        market = _make_market(outcomes=[champ, other])
        oh = {
            100: {"outcome_id": 100, "name": "Spain",
                  "history": _hist([((now - timedelta(days=2)).isoformat(), 0.55),
                                    ((now - timedelta(days=1)).isoformat(), 0.587)]),
                  "eliminated": False, "eliminated_at": None},
            200: {"outcome_id": 200, "name": "France",
                  "history": _hist([((now - timedelta(days=1)).isoformat(), 0.30)]),
                  "eliminated": False, "eliminated_at": None},
        }
        _apply_settled_winner_freeze(market, oh, {100: "Spain", 200: "France"})
        # Champion line ends at 1.0
        assert oh[100]["history"][-1]["probability"] == 1.0
        assert oh[100]["history"][-1]["bookmaker"] == "settlement"
        # Non-champion untouched (terminates at its own last real value)
        assert oh[200]["history"][-1]["probability"] == 0.30
        # Exactly one line resolves >= 0.90 → Check C would be GREEN
        latest = [h["history"][-1]["probability"] for h in oh.values()]
        assert sum(1 for p in latest if p >= 0.90) == 1

    def test_champion_with_no_snapshots_is_synthesized(self):
        champ = _make_outcome(100, "Ryan Fox", prob=0.004, is_winner=True)
        market = _make_market(outcomes=[champ])
        oh = {}  # champion had no charted snapshots at all
        _apply_settled_winner_freeze(market, oh, {100: "Ryan Fox"})
        assert 100 in oh
        assert oh[100]["history"][-1]["probability"] == 1.0
        assert oh[100]["name"] == "Ryan Fox"

    def test_future_resolution_date_is_clamped_to_now(self):
        """Kalshi resolution_date can be a future close-time artifact (gotcha #14)."""
        now = datetime.now(timezone.utc)
        future = now + timedelta(days=12)
        champ = _make_outcome(100, "Spain", prob=0.5, is_winner=True)
        market = _make_market(outcomes=[champ], resolution_date=future)
        oh = {100: {"outcome_id": 100, "name": "Spain",
                    "history": _hist([((now - timedelta(days=1)).isoformat(), 0.5)]),
                    "eliminated": False, "eliminated_at": None}}
        _apply_settled_winner_freeze(market, oh, {100: "Spain"})
        term_ts = datetime.fromisoformat(oh[100]["history"][-1]["timestamp"])
        assert term_ts <= now + timedelta(seconds=5)  # clamped, not 12 days out

    def test_terminal_never_precedes_last_real_point(self):
        """If resolution_date is BEFORE the last snapshot, terminal is placed after it."""
        now = datetime.now(timezone.utc)
        past_rd = now - timedelta(days=30)
        last_real = now - timedelta(hours=1)
        champ = _make_outcome(100, "Spain", prob=0.5, is_winner=True)
        market = _make_market(outcomes=[champ], resolution_date=past_rd)
        oh = {100: {"outcome_id": 100, "name": "Spain",
                    "history": _hist([(last_real.isoformat(), 0.5)]),
                    "eliminated": False, "eliminated_at": None}}
        _apply_settled_winner_freeze(market, oh, {100: "Spain"})
        term_ts = datetime.fromisoformat(oh[100]["history"][-1]["timestamp"])
        assert term_ts > last_real

    def test_already_resolved_champion_not_double_appended(self):
        now = datetime.now(timezone.utc)
        champ = _make_outcome(100, "Spain", prob=1.0, is_winner=True)
        market = _make_market(outcomes=[champ])
        oh = {100: {"outcome_id": 100, "name": "Spain",
                    "history": _hist([((now - timedelta(days=1)).isoformat(), 0.9998)]),
                    "eliminated": False, "eliminated_at": None}}
        before = len(oh[100]["history"])
        _apply_settled_winner_freeze(market, oh, {100: "Spain"})
        assert len(oh[100]["history"]) == before  # no duplicate terminal

    def test_no_winner_is_noop(self):
        champ = _make_outcome(100, "Spain", prob=0.5, is_winner=False)
        market = _make_market(outcomes=[champ])
        oh = {100: {"outcome_id": 100, "name": "Spain",
                    "history": _hist([("2026-01-01T00:00:00+00:00", 0.5)]),
                    "eliminated": False, "eliminated_at": None}}
        _apply_settled_winner_freeze(market, oh, {100: "Spain"})
        assert oh[100]["history"][-1]["probability"] == 0.5

    # --- #232: champion-by-NAME path (odds_api winner fields never grade) -------
    def test_champion_name_resolves_when_no_is_winner_grade(self):
        """WC-2026 class: odds_api winner field, Spain fizzled to 0.618, no
        is_winner on any outcome — the concept's structural crown resolves it."""
        now = datetime.now(timezone.utc)
        spain = _make_outcome(100, "Spain", prob=0.618, is_winner=False)
        france = _make_outcome(200, "France", prob=0.20, is_winner=False)
        market = _make_market(outcomes=[spain, france])
        oh = {
            100: {"outcome_id": 100, "name": "Spain",
                  "history": _hist([((now - timedelta(days=1)).isoformat(), 0.618)]),
                  "eliminated": False, "eliminated_at": None},
            200: {"outcome_id": 200, "name": "France",
                  "history": _hist([((now - timedelta(days=1)).isoformat(), 0.20)]),
                  "eliminated": False, "eliminated_at": None},
        }
        _apply_settled_winner_freeze(
            market, oh, {100: "Spain", 200: "France"}, champion_name="Spain"
        )
        assert oh[100]["history"][-1]["probability"] == 1.0
        assert oh[100]["history"][-1]["bookmaker"] == "settlement"
        assert oh[200]["history"][-1]["probability"] == 0.20  # non-champion untouched
        latest = [h["history"][-1]["probability"] for h in oh.values()]
        assert sum(1 for p in latest if p >= 0.90) == 1  # exactly one resolves → Check C GREEN

    def test_champion_name_matches_case_insensitively(self):
        now = datetime.now(timezone.utc)
        spain = _make_outcome(100, "Spain", prob=0.6, is_winner=False)
        market = _make_market(outcomes=[spain])
        oh = {100: {"outcome_id": 100, "name": "Spain",
                    "history": _hist([((now - timedelta(days=1)).isoformat(), 0.6)]),
                    "eliminated": False, "eliminated_at": None}}
        _apply_settled_winner_freeze(market, oh, {100: "Spain"}, champion_name="  spain  ")
        assert oh[100]["history"][-1]["probability"] == 1.0

    def test_is_winner_grade_takes_precedence_over_name(self):
        """A graded is_winner always wins; a conflicting name arg is ignored."""
        now = datetime.now(timezone.utc)
        spain = _make_outcome(100, "Spain", prob=0.5, is_winner=True)
        france = _make_outcome(200, "France", prob=0.4, is_winner=False)
        market = _make_market(outcomes=[spain, france])
        oh = {
            100: {"outcome_id": 100, "name": "Spain",
                  "history": _hist([((now - timedelta(days=1)).isoformat(), 0.5)]),
                  "eliminated": False, "eliminated_at": None},
            200: {"outcome_id": 200, "name": "France",
                  "history": _hist([((now - timedelta(days=1)).isoformat(), 0.4)]),
                  "eliminated": False, "eliminated_at": None},
        }
        _apply_settled_winner_freeze(market, oh, {100: "Spain", 200: "France"}, champion_name="France")
        assert oh[100]["history"][-1]["probability"] == 1.0  # graded Spain wins
        assert oh[200]["history"][-1]["probability"] == 0.4  # France untouched

    def test_champion_name_no_match_is_noop(self):
        spain = _make_outcome(100, "Spain", prob=0.6, is_winner=False)
        market = _make_market(outcomes=[spain])
        oh = {100: {"outcome_id": 100, "name": "Spain",
                    "history": _hist([("2026-01-01T00:00:00+00:00", 0.6)]),
                    "eliminated": False, "eliminated_at": None}}
        _apply_settled_winner_freeze(market, oh, {100: "Spain"}, champion_name="Portugal")
        assert oh[100]["history"][-1]["probability"] == 0.6  # unknown champ → no-op

    def test_multiple_winners_is_noop(self):
        """Ambiguous grade (two is_winner) — do not fabricate a single champion."""
        a = _make_outcome(100, "A", prob=0.5, is_winner=True)
        b = _make_outcome(200, "B", prob=0.5, is_winner=True)
        market = _make_market(outcomes=[a, b])
        oh = {100: {"outcome_id": 100, "name": "A",
                    "history": _hist([("2026-01-01T00:00:00+00:00", 0.5)]),
                    "eliminated": False, "eliminated_at": None}}
        _apply_settled_winner_freeze(market, oh, {100: "A"})
        assert oh[100]["history"][-1]["probability"] == 0.5

    def test_filter_to_non_champion_does_not_inject(self):
        champ = _make_outcome(100, "Spain", prob=0.5, is_winner=True)
        other = _make_outcome(200, "France", prob=0.3)
        market = _make_market(outcomes=[champ, other])
        oh = {200: {"outcome_id": 200, "name": "France",
                    "history": _hist([("2026-01-01T00:00:00+00:00", 0.3)]),
                    "eliminated": False, "eliminated_at": None}}
        _apply_settled_winner_freeze(market, oh, {200: "France"}, outcome_id_filter=200)
        assert 100 not in oh  # champion not injected into a non-champion view
        assert oh[200]["history"][-1]["probability"] == 0.3


class TestHistoryEndpointFreeze:
    @pytest.mark.asyncio
    async def test_endpoint_resolves_graded_longshot_winner(self):
        """End-to-end: a settled winner market whose champion fizzled on the
        charted source still returns a champion line that resolves to 1.0."""
        now = datetime.now(timezone.utc)
        champ = _make_outcome(100, "Spain", prob=0.587, is_winner=True)
        other = _make_outcome(200, "France", prob=0.05)
        market = _make_market(outcomes=[champ, other])

        snaps = []
        for i in range(30):
            ts = now - timedelta(hours=i * 2)
            snaps.append(_snap(100, ts, 0.55))
            snaps.append(_snap(200, ts, 0.05))

        call_count = 0

        async def mock_execute(query):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = market
                return result
            scalars_mock = MagicMock()
            scalars_mock.all.return_value = snaps
            result.scalars.return_value = scalars_mock
            return result

        db = AsyncMock()
        db.execute = mock_execute

        # outcome_id=None mirrors what FastAPI injects when the query param is
        # absent (a direct call would otherwise pass the Query() FieldInfo default).
        result = await get_futures_history(market_id=1, hours=8760, top_n=8, outcome_id=None, db=db)
        by_name = {o["name"]: o for o in result["outcomes"]}
        assert by_name["Spain"]["history"][-1]["probability"] == 1.0
        # Exactly one line resolves >= 0.90 (Check C's GREEN condition)
        resolved = [o for o in result["outcomes"] if o["history"] and o["history"][-1]["probability"] >= 0.90]
        assert len(resolved) == 1
        assert resolved[0]["name"] == "Spain"
