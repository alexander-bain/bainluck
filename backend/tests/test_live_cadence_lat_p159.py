"""LAT-P159 — a live game's odds stop being twice as stale as the constant claims.

WHAT A READER SAW BEFORE THIS FILE
----------------------------------
Alex, 2026-08-29, on a live Stanford game: the win probability lagged the action.
Betting odds carry weight 3.0 in `utils/aggregation.py` — the dominant term — so
"the number on the card" is, in practice, how fresh `poll_all_odds` is.

Two independent production surfaces, measured 2026-08-31:

    beat delivers the task    every  30.1 s   (223 deliveries / 6,710 s,
                                               /api/admin/celery/schedule-adherence)
    the task actually RUNS    every  60.0 s   (median of 49 consecutive gaps from
                                               /celery/task-metrics/poll_odds)
                              every  64.9 s   (1,331 terminals / 24 h — a second,
                                               independent surface agreeing)
    the constant claimed      every  32 s

Half of every beat delivery was discarded, and the reason was two seconds:
`should_poll_now()` gates on `elapsed >= LIVE_POLL_INTERVAL` (32) against a 30 s
beat, so two consecutive deliveries could never both pass. The per-sport gate then
multiplied by the sport tier on top, which made a LIVE game's cadence a function of
its league's popularity:

    tier 1 (NBA/NFL/MLB/NHL/NCAAB)   32 s ->  60 s effective
    tier 2 (includes NCAAF)          64 s -> 120 s effective   <- Alex's Stanford game
    tier 3 (default, unlisted)      128 s -> 180 s effective

WHY NO LANE FOUND IT
--------------------
This one did, in August, and then filed it as a design. LAT-P039 (#1609/#1716)
measured the 32-against-30 relationship on 2026-08-11 and taught the adherence
surface to expect a 0.50 delivery ratio for this task. That was RIGHT about the
instrument — a self-gated decline is not a missed beat — and it stopped there.
Explaining an anomaly is not deciding it is correct: the one surface that would
have flagged a task discarding half its deliveries had been calibrated to expect
exactly that.

WHAT THESE GUARDS ASSERT
------------------------
The EFFECTIVE cadence in seconds, by ticking the real gates at the real beat
period — not the value of a constant. The defect lived entirely in the
relationship between two numbers that were each individually defensible, so a
guard that asserts either number in isolation cannot see it. Nothing here reads
source text.
"""

import pytest

from app.tasks import config as cfg
from app.tasks.config import (
    LIVE_POLL_INTERVAL,
    ODDS_POLL_BEAT_SECONDS,
    SPORT_POLLING_DEFAULT_TIER,
    SPORT_POLLING_TIERS,
)


#: The pass duration distribution measured on production 2026-08-31 over the 50
#: most recent runs (`recent_durations_ms`, a 2,850 s window):
#: p50 4.1 s, p90 9.4 s, p95 15.1 s, max 90.7 s.
MEASURED_PASS_P50_S = 4.1
MEASURED_PASS_P95_S = 15.1


def _effective_cadence_s(interval_s: float, pass_duration_s: float,
                         beat_s: float = None, ticks: int = 40) -> float:
    """Seconds between actual polls, ticking the REAL gate at the REAL beat.

    Models both gates exactly as production runs them: the beat delivers every
    `beat_s`; a delivery polls iff `now - last_poll_end >= interval_s`; and
    `last_poll_end` is stamped when the pass FINISHES (`update_poll_state` is
    called at the end of `_poll_all_odds`), which is why the pass's own duration
    eats into the next delivery's elapsed time.
    """
    beat_s = ODDS_POLL_BEAT_SECONDS if beat_s is None else beat_s
    last_end = None
    polls = []
    for i in range(ticks):
        now = i * beat_s
        if last_end is None or (now - last_end) >= interval_s:
            polls.append(now)
            last_end = now + pass_duration_s
    if len(polls) < 3:
        return float("inf")
    # Drop the first (cold start) and average the rest.
    gaps = [b - a for a, b in zip(polls[1:], polls[2:])]
    return sum(gaps) / len(gaps)


def _live_interval_for(sport_key: str) -> float:
    """The live interval the task computes for this sport — via the SHIPPED
    helper `_poll_all_odds` calls, never a local copy of its rule."""
    from app.tasks.odds_polling import tier_adjusted_interval

    return tier_adjusted_interval(LIVE_POLL_INTERVAL, "live", sport_key)


# ---------------------------------------------------------------------------
# 1. THE SHIP — a live game refreshes on every beat the scheduler gives us
# ---------------------------------------------------------------------------


class TestLiveCadenceIsTheBeat:

    def test_the_gate_no_longer_throws_away_every_other_delivery(self):
        """🔴 THE DEFECT, stated as the number a person waits.

        At the measured median pass duration the live gate must admit EVERY beat
        delivery. Before the fix this asserted 60 s against a 30 s beat.
        """
        cadence = _effective_cadence_s(LIVE_POLL_INTERVAL, MEASURED_PASS_P50_S)
        assert cadence == pytest.approx(ODDS_POLL_BEAT_SECONDS), (
            f"live odds refresh every {cadence}s against a "
            f"{ODDS_POLL_BEAT_SECONDS}s beat — the gate is discarding deliveries"
        )

    def test_it_still_holds_at_the_p95_pass_duration(self):
        """A slow pass must not silently halve the cadence again. p95 is 15.1 s;
        the gate has to leave room for it."""
        cadence = _effective_cadence_s(LIVE_POLL_INTERVAL, MEASURED_PASS_P95_S)
        assert cadence == pytest.approx(ODDS_POLL_BEAT_SECONDS), (
            f"a p95-duration pass ({MEASURED_PASS_P95_S}s) drops the cadence to "
            f"{cadence}s — the interval has no room for the pass's own runtime"
        )

    def test_stanfords_league_is_no_longer_slower_than_the_nba(self):
        """🔴 ALEX'S CASE. Stanford is `americanfootball_ncaaf`, Tier 2, and the
        tier multiplier used to apply to `live` — so its odds were 120 s old while
        an NBA game's were 60 s. A live game is live whatever the league."""
        ncaaf = _effective_cadence_s(
            _live_interval_for("americanfootball_ncaaf"), MEASURED_PASS_P50_S)
        nba = _effective_cadence_s(
            _live_interval_for("basketball_nba"), MEASURED_PASS_P50_S)
        unlisted = _effective_cadence_s(
            _live_interval_for("cricket_ipl"), MEASURED_PASS_P50_S)

        assert ncaaf == nba == unlisted, (
            f"live cadence still depends on the sport tier: ncaaf={ncaaf}s "
            f"nba={nba}s unlisted={unlisted}s"
        )
        assert ncaaf <= 2 * ODDS_POLL_BEAT_SECONDS


# ---------------------------------------------------------------------------
# 2. THE SAFETY ARGUMENT — this cannot be worse than what it replaces
# ---------------------------------------------------------------------------


class TestItCannotMakeAnyCadenceWorse:

    #: What shipped before this queue.
    OLD_LIVE_INTERVAL = 32

    @pytest.mark.parametrize("pass_duration", [0, 1, 4.1, 9.4, 15.1, 25, 29, 45, 90.7])
    def test_never_slower_than_the_old_gate_at_any_pass_duration(self, pass_duration):
        """🔴 THE LOAD-BEARING SAFETY PROPERTY, and it is arithmetic, not hope.

        `elapsed` runs from the END of the previous pass, so a longer pass eats
        the next delivery's elapsed budget. A SMALLER interval is therefore
        weakly more permissive at every duration — the fix degrades gracefully
        back toward the old behaviour under load instead of stacking work on a
        struggling box. Swept across the whole measured duration range including
        the 90.7 s outlier.
        """
        new = _effective_cadence_s(LIVE_POLL_INTERVAL, pass_duration)
        old = _effective_cadence_s(self.OLD_LIVE_INTERVAL, pass_duration)
        assert new <= old, (
            f"at a {pass_duration}s pass the new gate is SLOWER "
            f"({new}s) than the one it replaces ({old}s)"
        )

    def test_the_beat_is_a_hard_floor_so_a_small_interval_cannot_run_away(self):
        """The quota argument. No interval, however small, produces more than one
        poll per delivery — so lowering it cannot multiply spend without bound.
        """
        for interval in (0, 1, 5, 15):
            cadence = _effective_cadence_s(interval, MEASURED_PASS_P50_S)
            assert cadence >= ODDS_POLL_BEAT_SECONDS, (
                f"interval {interval}s produced a {cadence}s cadence, faster than "
                f"the {ODDS_POLL_BEAT_SECONDS}s beat — the floor is not holding"
            )


# ---------------------------------------------------------------------------
# 3. THE TWO NUMBERS MUST STAY IN THEIR RELATIONSHIP
# ---------------------------------------------------------------------------


class TestTheConstantsCannotDriftApart:

    def test_the_declared_beat_equals_the_beat_actually_scheduled(self):
        """🔴 The whole defect was a constant that disagreed with the scheduler
        enforcing it. `ODDS_POLL_BEAT_SECONDS` is only meaningful if it is the
        real one, so this reads the live beat schedule rather than a literal."""
        from app.tasks import celery_app

        entry = celery_app.conf.beat_schedule["poll-odds-adaptive"]
        assert entry["task"] == "app.tasks.poll_all_odds"
        assert float(entry["schedule"]) == float(ODDS_POLL_BEAT_SECONDS), (
            f"config says the odds beat is {ODDS_POLL_BEAT_SECONDS}s, the beat "
            f"schedule says {entry['schedule']}s — the cadence derived from the "
            "first is fiction"
        )

    def test_the_live_gate_is_met_with_room_and_not_exactly(self):
        """🔴 A bound met exactly is not met — CERT-515, this lane, two cycles ago.

        32 against 30 was two seconds on the WRONG side. `beat // 2` = 15 was a
        tenth of a second on the wrong side (30 - 15.1 = 14.9) and this guard
        caught that draft. The gate must clear the beat minus the pass's own p95,
        with margin left over.
        """
        assert LIVE_POLL_INTERVAL < ODDS_POLL_BEAT_SECONDS
        headroom = ODDS_POLL_BEAT_SECONDS - LIVE_POLL_INTERVAL
        assert headroom > MEASURED_PASS_P95_S, (
            f"{headroom}s of room for a pass whose measured p95 is "
            f"{MEASURED_PASS_P95_S}s — the p95 pass loses its delivery and the "
            "cadence silently halves back to where it started"
        )
        assert headroom - MEASURED_PASS_P95_S >= 3, (
            f"only {headroom - MEASURED_PASS_P95_S:.1f}s of margin over the p95 — "
            "met-with-room means room, not a rounding error"
        )

    def test_the_live_interval_is_derived_from_what_it_is_bounded_BY(self):
        """Re-timing the beat, or re-measuring the pass, must move the gate — or
        the numbers drift apart again, which is exactly how this defect was born
        (#2236's discipline)."""
        assert LIVE_POLL_INTERVAL == (
            ODDS_POLL_BEAT_SECONDS
            - cfg.SLOWEST_MEASURED_ODDS_PASS_SECONDS
            - cfg.LIVE_POLL_MARGIN_SECONDS
        )
        # And the measured p95 the config pins must not have drifted from the one
        # these guards simulate against.
        assert cfg.SLOWEST_MEASURED_ODDS_PASS_SECONDS >= MEASURED_PASS_P95_S


# ---------------------------------------------------------------------------
# 4. THE TASK ITSELF — the tier multiplier is a pre-game economy
# ---------------------------------------------------------------------------


class TestTheShippedRule:
    """Calls `tier_adjusted_interval` — the function `_poll_all_odds` actually
    calls — rather than a copy of it. A guard that re-implements the rule under
    test agrees with the bug as readily as with the fix (LAT-P156)."""

    def test_the_task_calls_this_helper_and_not_an_inline_copy(self):
        """The extraction is only worth anything if the shipped path goes through
        it. Anchored on the AST call node, not a source substring, because a
        containment check is satisfied by a sibling call site
        (`reference_containment_guard_satisfied_by_sibling_call_sites`)."""
        import ast
        import inspect

        from app.tasks import odds_polling

        tree = ast.parse(inspect.getsource(odds_polling._poll_all_odds))
        called = {
            n.func.id
            for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }
        assert "tier_adjusted_interval" in called, (
            "`_poll_all_odds` no longer calls the helper these guards exercise — "
            "everything below this line is now testing dead code"
        )

    @pytest.mark.parametrize("sport_key,expected_tier", [
        ("basketball_nba", 1),
        ("americanfootball_ncaaf", 2),
        ("cricket_ipl", 3),
    ])
    def test_live_is_flat_across_every_tier(self, sport_key, expected_tier):
        """🔴 The fix, through the shipped function."""
        from app.tasks.odds_polling import tier_adjusted_interval

        assert SPORT_POLLING_TIERS.get(
            sport_key, SPORT_POLLING_DEFAULT_TIER) == expected_tier
        assert tier_adjusted_interval(
            LIVE_POLL_INTERVAL, "live", sport_key) == LIVE_POLL_INTERVAL

    @pytest.mark.parametrize("sport_key,mult", [
        ("basketball_nba", 1),
        ("americanfootball_ncaaf", 2),
        ("cricket_ipl", 4),
    ])
    def test_soon_and_later_KEEP_their_multiplier(self, sport_key, mult):
        """The economy this change preserves, and the must-not-regress control:
        tiering pre-game traffic is the whole reason the quota survives. If this
        goes green while `live` is also multiplied, the fix did nothing; if it
        goes red, the fix took the economy down with it."""
        from app.tasks.odds_polling import tier_adjusted_interval

        assert tier_adjusted_interval(
            cfg.SOON_POLL_INTERVAL, "soon", sport_key) == cfg.SOON_POLL_INTERVAL * mult
        assert tier_adjusted_interval(
            cfg.LATER_POLL_INTERVAL, "later", sport_key) == cfg.LATER_POLL_INTERVAL * mult

    def test_an_unlisted_sport_still_defaults_to_the_long_tail(self):
        from app.tasks.odds_polling import tier_adjusted_interval

        assert SPORT_POLLING_DEFAULT_TIER == 3
        assert tier_adjusted_interval(
            cfg.SOON_POLL_INTERVAL, "soon", "underwater_hockey_zz"
        ) == cfg.SOON_POLL_INTERVAL * 4
