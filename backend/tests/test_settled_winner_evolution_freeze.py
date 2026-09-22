"""Tests for the settled-means-settled evolution freeze (#1177, Queue #230).

When a futures market has a graded champion, the ``/{market_id}/history``
endpoint must resolve that champion's path-to-resolution line to 1.0 at
settlement time — regardless of which source's snapshots were charted (odds_api
can fizzle a settled winner to a longshot value while Kalshi resolves to ~1.0).
This is what greens the Settled-Concept Sentinel's Check C (evolution resolves)
generically, and it must fire even while the winner market is stuck
``status='open'`` (gotcha #33), so it keys on ``is_winner``, never on ``status``.

"A champion" is ONE outcome with ``is_winner=True`` on a mutually-exclusive
field, and EVERY graded winner on an independent one (#7921): a cumulative
ladder settles several rungs YES and a golf cut settles dozens, and each of those
is a completed journey owed its ending. Two winners on a MUTEX field stays a
no-op — that is a contradiction, and stamping 1.0 on both would publish it as a
settled result.
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


def _make_market(
    market_id=1,
    outcomes=None,
    resolution_date=None,
    metadata=None,
    mutually_exclusive=True,
):
    m = MagicMock()
    m.id = market_id
    m.name = "Winner Market"
    m.market_metadata = metadata
    m.resolution_date = resolution_date
    m.outcomes = outcomes or []
    # #7921 — SET EXPLICITLY. A bare MagicMock auto-creates this attribute as a
    # truthy Mock, so leaving it unset would send every co-winner test down the
    # "we do not know" arm while reading as though it had proven the
    # mutually-exclusive one. Default True matches the column's own default.
    m.mutually_exclusive = mutually_exclusive
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

    def test_multiple_winners_on_a_mutex_field_is_noop(self):
        """Two is_winner where only ONE is possible — a contradiction, not a grade.

        #7921 narrowed this from "any two winners" to "two winners on a mutually
        exclusive field". Freezing both to 1.0 here would publish a grading bug
        as a settled result on the chart.
        """
        a = _make_outcome(100, "A", prob=0.5, is_winner=True)
        b = _make_outcome(200, "B", prob=0.5, is_winner=True)
        market = _make_market(outcomes=[a, b], mutually_exclusive=True)
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


class TestCoWinnersOnAnIndependentField:
    """#7921 — several winners is the ANSWER on a non-mutex field, not an ambiguity.

    `>= 75 wins` and `>= 80 wins` both settle YES on one cumulative ladder; 73
    golfers make the cut. Measured on production 2026-09-22: 119,870 co-winner
    markets carry `mutually_exclusive = false` and 8,162 of them hold a graded
    winner still priced under 50%, while the same page's table already printed
    "Won · Settled" beside that line.
    """

    def test_every_graded_winner_ends_at_the_win(self):
        a = _make_outcome(100, ">= 75 wins", prob=0.98, is_winner=True)
        b = _make_outcome(200, ">= 80 wins", prob=0.99, is_winner=True)
        c = _make_outcome(300, ">= 105 wins", prob=0.0, is_winner=False)
        market = _make_market(outcomes=[a, b, c], mutually_exclusive=False)
        oh = {
            100: {"outcome_id": 100, "name": ">= 75 wins",
                  "history": _hist([("2026-01-01T00:00:00+00:00", 0.98)]),
                  "eliminated": False, "eliminated_at": None},
            200: {"outcome_id": 200, "name": ">= 80 wins",
                  "history": _hist([("2026-01-01T00:00:00+00:00", 0.99)]),
                  "eliminated": False, "eliminated_at": None},
            300: {"outcome_id": 300, "name": ">= 105 wins",
                  "history": _hist([("2026-01-01T00:00:00+00:00", 0.06)]),
                  "eliminated": False, "eliminated_at": None},
        }
        _apply_settled_winner_freeze(market, oh, {100: ">= 75 wins", 200: ">= 80 wins", 300: ">= 105 wins"})
        # BOTH winners resolve — the defect was that neither did.
        assert oh[100]["history"][-1]["probability"] == 1.0
        assert oh[200]["history"][-1]["probability"] == 1.0
        assert oh[100]["history"][-1]["bookmaker"] == "settlement"
        assert oh[200]["history"][-1]["bookmaker"] == "settlement"
        # The UNGRADED rung is untouched: a loser's line still ends at its own
        # last real value. Ending it at 0.0 is the LOST arm (#4597), deliberately
        # not shipped here.
        assert oh[300]["history"][-1]["probability"] == 0.06
        assert len(oh[300]["history"]) == 1

    def test_a_winner_with_no_charted_line_is_not_synthesized(self):
        """Synthesis stays a SINGLE-champion affordance.

        A 73-winner golf cut would otherwise inject 73 brand-new one-point series
        into a chart nobody asked to redraw. The defect is a drawn line ending in
        the wrong place, not a missing line.
        """
        a = _make_outcome(100, "Made the cut A", prob=0.41, is_winner=True)
        b = _make_outcome(200, "Made the cut B", prob=0.38, is_winner=True)
        market = _make_market(outcomes=[a, b], mutually_exclusive=False)
        oh = {100: {"outcome_id": 100, "name": "Made the cut A",
                    "history": _hist([("2026-01-01T00:00:00+00:00", 0.41)]),
                    "eliminated": False, "eliminated_at": None}}
        _apply_settled_winner_freeze(market, oh, {100: "Made the cut A", 200: "Made the cut B"})
        assert oh[100]["history"][-1]["probability"] == 1.0
        assert 200 not in oh  # no new series conjured onto the chart

    def test_unknown_mutual_exclusivity_fails_closed(self):
        """Never measured => treated as mutex => no-op. Unknown is not licence."""
        a = _make_outcome(100, "A", prob=0.5, is_winner=True)
        b = _make_outcome(200, "B", prob=0.5, is_winner=True)
        market = _make_market(outcomes=[a, b], mutually_exclusive=None)
        oh = {100: {"outcome_id": 100, "name": "A",
                    "history": _hist([("2026-01-01T00:00:00+00:00", 0.5)]),
                    "eliminated": False, "eliminated_at": None}}
        _apply_settled_winner_freeze(market, oh, {100: "A"})
        assert oh[100]["history"][-1]["probability"] == 0.5

    def test_a_filtered_view_still_only_gets_the_outcome_it_asked_for(self):
        a = _make_outcome(100, "A", prob=0.4, is_winner=True)
        b = _make_outcome(200, "B", prob=0.45, is_winner=True)
        market = _make_market(outcomes=[a, b], mutually_exclusive=False)
        oh = {
            100: {"outcome_id": 100, "name": "A",
                  "history": _hist([("2026-01-01T00:00:00+00:00", 0.4)]),
                  "eliminated": False, "eliminated_at": None},
            200: {"outcome_id": 200, "name": "B",
                  "history": _hist([("2026-01-01T00:00:00+00:00", 0.45)]),
                  "eliminated": False, "eliminated_at": None},
        }
        _apply_settled_winner_freeze(market, oh, {100: "A", 200: "B"}, outcome_id_filter=200)
        assert oh[200]["history"][-1]["probability"] == 1.0
        assert oh[100]["history"][-1]["probability"] == 0.4  # untouched


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
