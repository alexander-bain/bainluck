"""Q504-b — the tennis match winner stops being unlinked, and the dyno says it is alive.

═══ THE SPECIMEN, measured on production 2026-09-01 ═══

Reported as "worker-ws is up but silent; Kalshi stamps on LIVE matches are
6.5-43 min old". Two of those three claims were wrong and the third had a
different cause than anyone could see from the outside.

**The socket was never silent.** A per-dyno log pull (Platform API; the CLI is
EPERM-blocked from an agent session) showed `worker-ws.1` connected, 23,456
tickers subscribed, 10,098 price updates and 252 flushes with 0 errors in one
ten-minute recycle. The "zero lines" reading came from `worker-realtime`
flooding the shared log buffer and evicting everything else.

**The stale blend was real.** Event 15293813 (Fery v Musetti, live):

    futures_outcomes.last_updated   22:38 - 22:45   <- the socket, working
    win_probability_sources.kalshi  22:31           <- frozen

and the reason was one row:

    KXATPMATCH-26AUG30FERMUS       event_id = NULL   <- the WINNER
    KXATPSETWINNER-…FERMUS-1/2/3   event_id = 15293813
    KXATPEXACTMATCH-…FERMUS        event_id = 15293813
    KXATPGTOTAL/GSPREAD-…FERMUS    event_id = 15293813

The only market that feeds the blend was the only one not linked. So
`compute_source_home_probability` returned None on every flush, the WS
subscription query (`event_id IS NOT NULL`) never subscribed the winner ticker,
and the hero's Kalshi number was whatever the last transient link had stamped.

**Why it was unlinked, every single run.** Two phases of `match_prediction_
markets` were fighting. `_reconcile_kalshi_match_segments` (Q435) adopts the
winner onto the event its segment siblings hold — id-anchored, ruling 048 arm A.
Then Phase 2's date-mismatch arm reads `26AUG30` out of the ticker, compares it
to a 2026-09-01 commence, and unlinks. The `26AUG30` is the TOURNAMENT SEGMENT's
date, not the match's. Every prop sibling carries the same stale date and none
of them ever reaches the check — they `continue` on `feeds_win_prob_blend` three
lines earlier — so the arm fired on exactly one market per match: the winner.

Measured in the 22:47Z run: `adopted=2` against `phase2_date_unlinked=27`, with
15 open ATP/WTA match-winner markets sitting unlinked beside linked siblings.

═══ WHAT THESE TESTS PIN ═══

1. The exemption predicate, on the real tickers, both directions.
2. That Phase 2's date-mismatch arm actually consults it (AST on the call site —
   the arm is inline in `_match_prediction_markets` and must stay there, because
   `test_kalshi_ticker_eastern_window_q439` scans that same function for its two
   deciders).
3. That the CONTROL still unlinks: an MLB game ticker two days off its event is
   the wrong-game class the arm exists for, and it must keep being unlinked.
4. That the heartbeat fires from outside both consumers while they hang — the
   state that could not report itself is now the state that does.
"""

import ast
import asyncio
import inspect
import logging
import textwrap
from datetime import datetime, timezone

import pytest

from app.tasks.prediction_market_matching import (
    _kalshi_prefix,
    _match_prediction_markets,
    _ticker_date_conflicts_with_event,
)
from app.utils.prediction_market_matching import (
    extract_game_date_from_ticker,
    feeds_win_prob_blend,
    is_combat_fight_ticker,
    is_kalshi_match_segment_ticker,
)


# The production rows, verbatim.
FERMUS_COMMENCE = datetime(2026, 9, 1, 20, 24, tzinfo=timezone.utc)
PUTBEN_COMMENCE = datetime(2026, 9, 1, 18, 48, 48, tzinfo=timezone.utc)

FERMUS_SIBLINGS = (
    "KXATPMATCH-26AUG30FERMUS",
    "KXATPSETWINNER-26AUG30FERMUS-1",
    "KXATPSETWINNER-26AUG30FERMUS-2",
    "KXATPSETWINNER-26AUG30FERMUS-3",
    "KXATPEXACTMATCH-26AUG30FERMUS",
    "KXATPGTOTAL-26AUG30FERMUS",
    "KXATPGSPREAD-26AUG30FERMUS",
)


# =============================================================================
# 1. The predicate
# =============================================================================


class TestIsKalshiMatchSegmentTicker:
    @pytest.mark.parametrize("ticker", FERMUS_SIBLINGS)
    def test_every_specimen_sibling_is_a_match_segment(self, ticker):
        assert is_kalshi_match_segment_ticker(ticker) is True

    @pytest.mark.parametrize(
        "ticker",
        [
            "KXWTAMATCH-26AUG30PUTBEN",
            "KXWTASETWINNER-26AUG30PUTBEN-2",
            "KXWTAGTOTAL-26AUG30PUTBEN",
            "KXWTAEXACTMATCH-26AUG30PUTBEN",
        ],
    )
    def test_the_wta_half_of_the_specimen_too(self, ticker):
        assert is_kalshi_match_segment_ticker(ticker) is True

    @pytest.mark.parametrize(
        "ticker",
        [
            # The wrong-game class this exemption must NOT reach. Colorado plays
            # Cincinnati on two consecutive days and both games' markets match by
            # team name; the date is the only thing that separates them.
            "KXMLBGAME-26APR291840COLCIN",
            "KXNBAGAME-26FEB20BOSGSW",
            "KXNFLGAME-26SEP07KCBAL",
            "KXNCAAMBGAME-26FEB22IOWAWIS",
            "KXCS2GAME-26MAR01NAVIG2",
            # Combat already had its own exemption; it must not acquire a second
            # identity through this one.
            "KXUFCFIGHT-26JUL11JONMIO",
            # Tennis futures are not match segments.
            "KXATPGRANDSLAM-26",
            "KXWTATOURNWIN-26USOPEN",
            None,
            "",
        ],
    )
    def test_refuses_everything_that_is_not_a_match_segment(self, ticker):
        assert is_kalshi_match_segment_ticker(ticker) is False

    def test_the_ticker_date_really_does_conflict(self):
        """The exemption is load-bearing, not decorative.

        If the underlying decider ever stopped seeing a conflict here, every
        assertion below would pass for the wrong reason — the arm would be
        skipping the unlink because there is nothing to unlink, not because the
        exemption fired. Pin the premise (memory: a control that is green in
        both arms proves nothing).
        """
        for ticker, commence in (
            ("KXATPMATCH-26AUG30FERMUS", FERMUS_COMMENCE),
            ("KXWTAMATCH-26AUG30PUTBEN", PUTBEN_COMMENCE),
        ):
            td = extract_game_date_from_ticker(ticker)
            assert _ticker_date_conflicts_with_event(
                td, commence, _kalshi_prefix(ticker)
            ) is True, f"{ticker} no longer reads as a date conflict"

    def test_the_winner_is_the_only_sibling_that_reaches_the_check(self):
        """Why the arm fired once per match instead of seven times.

        Phase 2 skips non-blend-feeding Kalshi markets before the date check, so
        the six props were never at risk. This is the asymmetry that made the
        bug look like a Kalshi outage rather than a linkage fight.
        """
        reach = [t for t in FERMUS_SIBLINGS if feeds_win_prob_blend(t)]
        assert reach == ["KXATPMATCH-26AUG30FERMUS"]


# =============================================================================
# 2. The call site — the arm must actually consult the exemption
# =============================================================================


def _calls_in(node):
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            name = getattr(n.func, "id", None) or getattr(n.func, "attr", None)
            if name:
                out.append(name)
    return out


class TestPhase2DateArmIsExempted:
    """AST, not a string scan.

    A `getsource` substring check would be satisfied by the explanatory comment
    that sits directly above the condition — the classic vacuous guard. Walking
    the tree sees only real calls, so deleting the `and not
    is_kalshi_match_segment_ticker(...)` operand reds this immediately while the
    comment stays put.
    """

    def _date_mismatch_arm(self):
        """The BoolOp that decides the date-mismatch unlink.

        Identified by the operand no other arm has: `is_combat_fight_ticker`.
        The Phase-2 wrong-game arm (the other `_ticker_date_conflicts_with_event`
        call site) is a bare `if not ...: continue`, not a BoolOp, and it is
        gated on `WRONG_GAME_PREFIXES`, which carries no tennis prefix.
        """
        tree = ast.parse(textwrap.dedent(inspect.getsource(_match_prediction_markets)))
        found = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.BoolOp)
            and "is_combat_fight_ticker" in _calls_in(n)
            and "_ticker_date_conflicts_with_event" in _calls_in(n)
        ]
        assert len(found) == 1, (
            "expected exactly one date-mismatch unlink arm combining the combat "
            f"exemption with the date decider; found {len(found)}"
        )
        return found[0]

    def test_the_arm_consults_the_segment_exemption(self):
        arm = self._date_mismatch_arm()
        assert "is_kalshi_match_segment_ticker" in _calls_in(arm), (
            "Phase 2's date-mismatch arm no longer exempts Kalshi tennis match "
            "segments, so `_reconcile_kalshi_match_segments` will adopt the "
            "match winner and this arm will unlink it again in the same run — "
            "the 2026-09-01 fight, restored"
        )

    def test_the_exemption_is_negated(self):
        """`and not f(...)`, never `and f(...)`.

        A dropped `not` inverts the fix into an unlink-only-tennis arm, which
        would read as 'the exemption is wired' to any call-count guard.
        """
        arm = self._date_mismatch_arm()
        negated = [
            n for n in ast.walk(arm)
            if isinstance(n, ast.UnaryOp)
            and isinstance(n.op, ast.Not)
            and "is_kalshi_match_segment_ticker" in _calls_in(n)
        ]
        assert negated, "the segment exemption is not negated — the arm is inverted"

    def test_the_wrong_game_control_is_untouched(self):
        """The other unlink arm must not acquire the exemption.

        Its job is the same-day doubleheader, where the date IS the evidence.
        """
        tree = ast.parse(textwrap.dedent(inspect.getsource(_match_prediction_markets)))
        for n in ast.walk(tree):
            if not isinstance(n, ast.BoolOp):
                continue
            names = _calls_in(n)
            if "is_combat_fight_ticker" in names:
                continue
            assert "is_kalshi_match_segment_ticker" not in names, (
                "the wrong-game arm must keep deciding on the date alone"
            )


class TestTheWrongGameControlStillUnlinks:
    """Green in BOTH arms: this must hold before and after the fix.

    The exemption is only correct if the class the check exists for still gets
    caught. These are the rows Phase 2 must keep unlinking.
    """

    @pytest.mark.parametrize(
        "ticker,commence",
        [
            ("KXMLBGAME-26APR291840COLCIN", datetime(2026, 4, 27, 22, 40, tzinfo=timezone.utc)),
            ("KXNBAGAME-26FEB20BOSGSW", datetime(2026, 2, 24, 1, 0, tzinfo=timezone.utc)),
        ],
    )
    def test_a_wrong_dated_game_ticker_is_still_a_conflict_and_not_exempt(
        self, ticker, commence
    ):
        td = extract_game_date_from_ticker(ticker)
        prefix = _kalshi_prefix(ticker)
        assert _ticker_date_conflicts_with_event(td, commence, prefix) is True
        assert is_kalshi_match_segment_ticker(ticker) is False
        assert is_combat_fight_ticker(ticker) is False


# =============================================================================
# 3. The heartbeat
# =============================================================================


class TestWsLivenessRegistry:
    def setup_method(self):
        from app.tasks.ws_liveness import reset

        reset()

    def test_an_arm_that_never_reported_is_named_not_omitted(self):
        from app.tasks.ws_liveness import render, report

        report("kalshi", "streaming", now=100.0, legs=23456)
        line = render(("kalshi", "polymarket"), now=100.0)
        assert "polymarket[NEVER REPORTED]" in line, (
            "a consumer that died before its first report must be visible; "
            "omitting it makes a dead arm look like an unconfigured one"
        )

    def test_age_is_the_load_bearing_column(self):
        from app.tasks.ws_liveness import render, report

        report("kalshi", "loading_slate", now=10.0)
        assert "age=0s" in render(("kalshi",), now=10.0)
        assert "age=300s" in render(("kalshi",), now=310.0)

    def test_subscription_counts_and_blend_counters_are_printed(self):
        from app.tasks.ws_liveness import render, report

        report("kalshi", "streaming", now=0.0, legs=23456, stamped=118, no_reading=6)
        report("polymarket", "streaming", now=0.0, legs=1153)
        line = render(("kalshi", "polymarket"), now=0.0)
        assert "legs=23456" in line and "legs=1153" in line
        # `no_reading` is the counter that would have named the 2026-09-01 bug
        # on the first heartbeat instead of on the fourth hour.
        assert "no_reading=6" in line and "stamped=118" in line

    def test_a_later_report_replaces_the_earlier_one(self):
        from app.tasks.ws_liveness import render, report

        report("kalshi", "loading_slate", now=0.0)
        report("kalshi", "streaming", now=5.0, legs=7)
        line = render(("kalshi",), now=5.0)
        assert "streaming" in line and "loading_slate" not in line

    def test_render_never_reads_a_clock(self):
        """gotcha #44 — the guard fixes the instant, so it cannot drift."""
        from app.tasks import ws_liveness

        src = inspect.getsource(ws_liveness.render)
        assert "monotonic" not in src and "utcnow" not in src


@pytest.mark.asyncio
class TestHeartbeatFiresWhileTheConsumersHang:
    async def test_main_logs_a_heartbeat_with_both_arms_wedged(
        self, monkeypatch, caplog
    ):
        """THE regression guard for "up and silent".

        Both consumer arms are replaced with coroutines that never return and
        never log — exactly the state the 2026-09-01 report assumed and the
        state the dyno could not distinguish from health. `main()` must still
        produce a line naming both arms.

        This runs the real `main()`, so it also pins that `heartbeat()` is in
        the gather: drop it from the `asyncio.gather` call and this test hangs
        to its timeout and fails, which no source-scan guard would catch.
        """
        import run_kalshi_ws
        from app.tasks.ws_liveness import report, reset

        reset()
        monkeypatch.setattr(run_kalshi_ws, "HEARTBEAT_SECONDS", 0)

        async def _wedged():
            await asyncio.Event().wait()

        for arm in (
            "run_kalshi", "run_polymarket",
            "run_kalshi_shadow", "run_polymarket_shadow",
        ):
            monkeypatch.setattr(run_kalshi_ws, arm, _wedged)

        # One arm got far enough to report; the other never did. Both must show.
        report("kalshi", "loading_slate", legs=0)

        with caplog.at_level(logging.INFO, logger="ws_runner"):
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(run_kalshi_ws.main(), timeout=1.0)

        beats = [r.getMessage() for r in caplog.records if "heartbeat" in r.getMessage()]
        assert beats, (
            "worker-ws produced no heartbeat while both consumers were wedged — "
            "'up and silent' is possible again"
        )
        assert "kalshi[loading_slate" in beats[-1]
        assert "polymarket[NEVER REPORTED]" in beats[-1]
        assert "uptime=" in beats[-1]
