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

import logging
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks import config as cfg
from app.tasks import odds_polling
from app.tasks.config import (
    LIVE_POLL_INTERVAL,
    ODDS_POLL_BEAT_SECONDS,
    SPORT_POLLING_DEFAULT_TIER,
    SPORT_POLLING_TIERS,
)
from app.tasks.redis_state import (
    QUOTA_GUARD_CONSERVATION_INTERVAL,
    QUOTA_GUARD_PRIORITY_SPORTS,
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


# ---------------------------------------------------------------------------
# 5. THE FLOORS — every one applied BEFORE the single gate that reads it
# ---------------------------------------------------------------------------


class TestEveryFloorReachesTheGate:
    """🔴 CERT-523's finding, and it is the one that mattered most.

    There is exactly ONE `elapsed < poll_interval` check in `_poll_all_odds`.
    `SPORT_MIN_POLL_INTERVALS` and `QUOTA_GUARD_CONSERVATION_INTERVAL` were
    applied BELOW it — so both were dead. Nothing downstream reads
    `poll_interval`; the only thing it can affect is the skip decision, and it
    was being raised after the decision had been taken. Live AFL never saw its
    declared 600 s minimum, and FULL_STOP conservation never slowed a live sport
    at all.

    That hole PREDATES this queue. What this queue did was make it material: a
    10 s gate against a 600 s declared floor, at exactly the moment quota is most
    constrained. **Widening a rate must enumerate what the widening newly
    admits** — LAT-P156's own lesson, missed here first time round.

    🔴 AND THE GUARD GAP IS THE POINT. `test_sport_min_overrides_base` and the
    conservation-floor test in `test_polling_config.py` DID assert both floors —
    against `compute_effective_interval`, which production never called. ~30
    tests guarding a helper nothing ran, all green, while the shipped path
    ignored the floors. These guards assert the interval the SHIPPED path
    computes.
    """

    @staticmethod
    def _shipped_interval(base, sport_key, tier, unchanged=0, conservation=False):
        """The interval the task computes, through the same two helpers it calls
        and in the same order."""
        from app.tasks.odds_polling import tier_adjusted_interval
        from app.utils.polling_config import compute_effective_interval

        return compute_effective_interval(
            base_interval=tier_adjusted_interval(base, tier, sport_key),
            sport_key=sport_key,
            tier=tier,
            unchanged_count=unchanged,
            quota_conservation=conservation,
        )

    def test_the_gate_is_computed_before_the_only_check_that_reads_it(self):
        """Source ORDER, because ordering IS the defect and no value assertion can
        see it. Anchored on the AST — the call node must precede the comparison,
        not merely co-exist with it in the function."""
        import ast
        import inspect

        from app.tasks import odds_polling

        src = inspect.getsource(odds_polling._poll_all_odds)
        tree = ast.parse(src)

        floor_lines = [
            n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == "compute_effective_interval"
        ]
        gate_lines = [
            n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Compare)
            and any(isinstance(c, ast.Name) and c.id == "poll_interval"
                    for c in ast.walk(n))
        ]
        assert floor_lines, "the shipped path no longer computes the floors at all"
        assert gate_lines, "the elapsed-vs-interval gate has moved or been renamed"
        assert max(floor_lines) < min(gate_lines), (
            f"the floors are applied at line(s) {floor_lines} but the gate that "
            f"reads them is at {gate_lines} — a floor below the gate is dead code"
        )

    def test_no_floor_is_applied_inside_the_task_at_all(self):
        """A SECOND, independent anchor on the same property.

        The ordering guard above is one AST assertion and therefore one point of
        failure. This one comes at it from the other side: once the floors live in
        `compute_effective_interval`, the task has no business naming them at all,
        so re-introducing one inline — above OR below the gate — trips this even if
        the ordering check is satisfied or has drifted.
        """
        import ast
        import inspect

        from app.tasks import odds_polling

        tree = ast.parse(inspect.getsource(odds_polling._poll_all_odds))
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        for floor in ("SPORT_MIN_POLL_INTERVALS", "QUOTA_GUARD_CONSERVATION_INTERVAL",
                      "SLOW_POLL_INTERVAL", "MEDIUM_POLL_INTERVAL"):
            assert floor not in names, (
                f"`{floor}` is applied inline in `_poll_all_odds` again. Every floor "
                "belongs in `compute_effective_interval`, which runs before the one "
                "gate that reads the result — an inline copy is how CERT-523's dead "
                "floor was written the first time."
            )

    def test_live_afl_honours_its_declared_ten_minute_minimum(self):
        """🔴 The exact case CERT-523 named. AFL is the only entry in
        `SPORT_MIN_POLL_INTERVALS` and it is there because even Tier 3 was too
        aggressive for its event count. The cadence change took it to 10 s."""
        interval = self._shipped_interval(LIVE_POLL_INTERVAL, "aussierules_afl", "live")
        assert interval == cfg.SPORT_MIN_POLL_INTERVALS["aussierules_afl"] == 600, (
            f"live AFL gates at {interval}s against a declared 600s minimum"
        )
        cadence = _effective_cadence_s(interval, MEASURED_PASS_P50_S)
        assert cadence >= 600

    def test_full_stop_conservation_still_slows_a_live_priority_sport(self):
        """🔴 The second half. In FULL_STOP the guard permits ONLY priority sports
        and ONLY live ones — which is precisely when the conservation floor is the
        last thing standing between us and the quota wall. It must bind on live."""
        from app.tasks.redis_state import QUOTA_GUARD_CONSERVATION_INTERVAL

        for sport in ("basketball_nba", "baseball_mlb", "basketball_ncaab"):
            interval = self._shipped_interval(
                LIVE_POLL_INTERVAL, sport, "live", conservation=True)
            assert interval >= QUOTA_GUARD_CONSERVATION_INTERVAL, (
                f"{sport} polls every {interval}s in FULL_STOP conservation, under "
                f"the {QUOTA_GUARD_CONSERVATION_INTERVAL}s emergency floor"
            )

    def test_the_ordinary_live_case_is_untouched_by_the_floors(self):
        """The control. A sport with no minimum, outside conservation, must still
        get the fast cadence this queue exists to deliver — otherwise the floor
        repair has quietly undone the ship."""
        for sport in ("basketball_nba", "americanfootball_ncaaf", "cricket_ipl"):
            interval = self._shipped_interval(LIVE_POLL_INTERVAL, sport, "live")
            assert interval == LIVE_POLL_INTERVAL, (sport, interval)
            assert _effective_cadence_s(interval, MEASURED_PASS_P50_S) == pytest.approx(
                ODDS_POLL_BEAT_SECONDS)

    def test_the_adaptive_slowdown_still_spares_live_and_still_binds_pre_game(self):
        """Moving the slowdown into the shared helper must not change who it
        applies to: pre-game slows when odds stop moving, live never does."""
        from app.tasks.config import SLOW_POLL_INTERVAL, SLOW_THRESHOLD

        soon = self._shipped_interval(
            cfg.SOON_POLL_INTERVAL, "basketball_nba", "soon", unchanged=SLOW_THRESHOLD)
        assert soon >= SLOW_POLL_INTERVAL

        live = self._shipped_interval(
            LIVE_POLL_INTERVAL, "basketball_nba", "live", unchanged=SLOW_THRESHOLD + 10)
        assert live == LIVE_POLL_INTERVAL, "the slowdown reached a live game"


# ===========================================================================
# CERT-528 — a quota re-read may only ADD constraint, never remove it
# ===========================================================================
#
# CERT-523's repair moved every cadence floor above the gate that reads it.
# CERT-528 then found the floor could still be ERASED, by the two lines that
# compute it. Inside the FULL_STOP branch the per-sport re-check read:
#
#     _, guard_reason = check_quota_guard("poll_odds", sport_key=sport_key)
#     quota_conservation = "conservation" in guard_reason
#
# Both halves are fail-open, and the casualty is the outer FULL_STOP result —
# the thing the task already knew:
#
#   * the allow/deny boolean is DISCARDED, so quota crossing `absolute_stop`
#     mid-pass ("no exceptions, no priority sports, nothing") polls anyway;
#   * `check_quota_guard` returns (True, "redis_error") from its own bare
#     `except`, and "redis_error" contains no "conservation", so a transient
#     Redis blip REASSIGNS conservation to False and drops a known-constrained
#     live sport from its 600 s floor to the flat 10 s live cadence.
#
# Both spend the constrained API at exactly the moment the breaker says not to.
#
# THIS IS THE SIXTH INSTANCE OF ONE SHAPE in this queue (513/515/518/521/523):
# the code KNEW and the thing that acts on it did not. A counter the verdict
# drops, a floor the gate never sees, and here a deny boolean assigned to `_`.
#
# WHY THESE GUARDS DRIVE THE TASK AND NOT A HELPER
# ------------------------------------------------
# CERT-528's finding was reachable only by executing `_poll_all_odds`. The
# floor guards written for CERT-523 exercised `compute_effective_interval`,
# which is correct in isolation and was NOT where the defect lived — the same
# error that let the floors sit dead behind the gate for months (~30 tests
# green against a helper production never called). No test in this repo had
# ever run this task; these are the first. They assert on the Odds API call
# ledger, because every per-sport block here ends in a broad `except: continue`
# and every Redis read is individually swallowed, so "it did not raise" is not
# evidence of anything.


class _Result:
    """The three SQLAlchemy result shapes `_poll_all_odds` consumes."""

    def __init__(self, rows=(), scalar=None):
        self._rows = list(rows)
        self._scalar = scalar

    def all(self):
        return list(self._rows)

    def scalar(self):
        return self._scalar

    def scalars(self):
        return self


class _FakeSession:
    """Dispatches on the rendered SQL — the task issues four distinct shapes."""

    def __init__(self, sport_rows, score_sports):
        self.sport_rows = sport_rows
        self.score_sports = score_sports

    async def execute(self, statement):
        sql = str(statement)
        if "GROUP BY" in sql:               # the sport-data query
            return _Result(rows=self.sport_rows)
        if "DISTINCT" in sql:               # sports needing scores
            return _Result(rows=[(k,) for k in self.score_sports])
        if "count(" in sql:                 # ESPN-coverage probe; non-zero =>
            return _Result(scalar=5)        # not covered => scores really fetch
        return _Result(rows=[])

    def add(self, _obj):
        pass

    async def commit(self):
        pass


class _FakeRedis:
    def __init__(self, last_poll_ts, sport_404=(), quota_hash=None):
        self.last_poll_ts = last_poll_ts
        self.sport_404 = set(sport_404)
        self.quota_hash = quota_hash

    def get(self, key):
        if key.startswith("bainluck:last_poll:"):
            return str(self.last_poll_ts).encode()
        if key.startswith("bainluck:sport_404:"):
            sport = key.split("bainluck:sport_404:", 1)[1]
            return b"1" if sport in self.sport_404 else None
        return None                          # no unchanged_count

    def hget(self, *_a, **_k):
        return None

    def hgetall(self, *_a, **_k):
        # Only consulted when a test runs the REAL `check_quota_guard`.
        return dict(self.quota_hash) if self.quota_hash else {}

    def set(self, *_a, **_k):
        return True

    def incr(self, *_a, **_k):
        return 1

    def expire(self, *_a, **_k):
        return True


async def _run_poll(*, outer, per_sport, sport_key="basketball_nba",
                    last_poll_age_s=100.0, score_sports=(), sports=None,
                    sport_404=(), boundary=None):
    """Execute the real `_poll_all_odds` and hand back its Odds API ledger.

    `sports` drives a MULTI-sport pass (the sport-data query returns one live
    row per key, in order) — without it a mid-pass transition is untestable,
    because a one-sport pass cannot distinguish "stopped at sport 2" from
    "never started". `per_sport` may be a single (ok, reason) tuple applied to
    every sport, or a dict keyed by sport key so the quota state can CHANGE
    between sports the way real quota does.
    """
    now_ts = time.time()
    sport_keys = list(sports) if sports else [sport_key]
    session = _FakeSession(
        [(k, datetime.now(timezone.utc) - timedelta(minutes=5), True)
         for k in sport_keys],
        list(score_sports),
    )

    service = MagicMock()
    service.get_odds = AsyncMock(return_value=[])
    service.get_scores = AsyncMock(return_value=[])
    service.close = AsyncMock()
    service.last_requests_remaining = None   # a MagicMock here is `is not None`
    service.last_requests_used = None        # and would hit the real recorder

    guard_calls = []
    passwide_calls = []

    def _guard(_task_type, sport_key=None, quiet=False):
        # `quiet` is accepted and ignored on purpose: it must not be able to
        # change a verdict, and `TestAPerSportReReadDoesNotFloodTheBreakersOwnLog`
        # asserts that against the REAL guard rather than this stub.
        if sport_key is None:
            # TWO pass-wide reads exist and they are not the same moment: the
            # outer one at the top, and the boundary one between the odds loop
            # and the scores fetch. `boundary=` models quota MOVING across the
            # pass — which is the only way to reach CERT-541's defect, where the
            # pass's own last odds response is what crosses the absolute stop.
            passwide_calls.append(len(passwide_calls))
            if boundary is not None and len(passwide_calls) > 1:
                return boundary
            return outer
        guard_calls.append(sport_key)
        if isinstance(per_sport, dict):
            return per_sport[sport_key]
        return per_sport

    class _CM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_a):
            return False

    with patch("app.tasks.odds_polling.check_quota_guard", side_effect=_guard), \
            patch("app.tasks.odds_polling.OddsAPIService", return_value=service), \
            patch("app.tasks.odds_polling.get_redis_client",
                  return_value=_FakeRedis(now_ts - last_poll_age_s, sport_404)), \
            patch("app.tasks.odds_polling.get_task_session", return_value=_CM()), \
            patch("app.tasks.odds_polling.detect_and_close_stale_events",
                  # live/048: two outcomes, not one. StatPal's end time closes a
                  # row; quiet books only suspend it, so a single `int` could no
                  # longer say which arm fired.
                  AsyncMock(return_value={"closed": 0, "suspended": 0})), \
            patch("app.tasks.odds_polling.update_poll_state", MagicMock()), \
            patch("app.tasks.excitement_index.update_live_ei", AsyncMock(return_value=0)):
        result = await odds_polling._poll_all_odds()

    service.guard_calls = guard_calls
    service.passwide_guard_reads = len(passwide_calls)
    return result, service


#: Every reason `check_quota_guard` can return that ALLOWS the call but does not
#: say "conservation". Each one used to clear the floor established by the outer
#: FULL_STOP read. `redis_error` and `no_redis` are the bare-except and
#: no-client escapes; `ok_*` is quota refilling mid-pass.
NON_CONSERVATION_ALLOW_REASONS = [
    "redis_error",
    "no_redis",
    "no_quota_data",
    "ok_600000",
]

#: Reasons that DENY. `absolute_stop` documents itself as having no exceptions.
DENY_REASONS = ["absolute_stop_0", "full_stop_9000"]


class TestTheHarnessCanSeeAnOddsCall:
    """If these fail, every zero below is vacuous."""

    async def test_an_unconstrained_live_sport_really_does_poll(self):
        result, service = await _run_poll(
            outer=(True, "ok_600000"), per_sport=(True, "ok_600000"),
            last_poll_age_s=100.0,
        )
        assert service.get_odds.await_count == 1, result
        assert result["sports_polled"] == 1, result

    async def test_scores_really_do_fire_when_nothing_stops_them(self):
        _result, service = await _run_poll(
            outer=(True, "ok_600000"), per_sport=(True, "ok_600000"),
            score_sports=("basketball_nba",),
        )
        assert service.get_scores.await_count == 1


class TestARereadCannotErodeAKnownFullStop:

    @pytest.mark.parametrize("reason", NON_CONSERVATION_ALLOW_REASONS)
    async def test_no_allow_reason_can_clear_the_conservation_floor(self, reason):
        # 100 s since the last poll: far past the 10 s live cadence, far short of
        # the 600 s conservation floor. So the poll happens if and only if the
        # floor was erased — which is exactly the bug.
        result, service = await _run_poll(
            outer=(False, "full_stop_10000"), per_sport=(True, reason),
            last_poll_age_s=100.0,
        )
        assert service.get_odds.await_count == 0, (
            f"per-sport re-read {reason!r} cleared the conservation floor the "
            f"outer FULL_STOP established and spent quota at 100 s"
        )
        assert result["sports_skipped"] == 1, result

    @pytest.mark.parametrize("reason", DENY_REASONS)
    async def test_a_denied_sport_never_polls_however_old_its_last_poll(self, reason):
        result, service = await _run_poll(
            outer=(False, "full_stop_10000"), per_sport=(False, reason),
            last_poll_age_s=86_400.0,      # a day: no interval can gate this
        )
        assert service.get_odds.await_count == 0, (
            f"per-sport re-read denied with {reason!r} and the task polled anyway"
        )
        assert result["sports_skipped"] == 1, result

    async def test_absolute_stop_halts_the_scores_fetch_too(self):
        # The scores block runs off its own independent query and consults no
        # quota guard at all, so breaking the odds loop alone still spends.
        _result, service = await _run_poll(
            outer=(False, "full_stop_10000"), per_sport=(False, "absolute_stop_0"),
            score_sports=("basketball_nba",),
        )
        assert service.get_scores.await_count == 0, (
            "absolute stop means no exceptions; scores are Odds API calls too"
        )

    async def test_the_floor_is_the_conservation_constant_and_not_a_coincidence(self):
        # Bracket it: just under the declared floor must skip, just over must
        # poll. Asserts the FLOOR, not a number that happens to agree today.
        floor = QUOTA_GUARD_CONSERVATION_INTERVAL
        _r, under = await _run_poll(
            outer=(False, "full_stop_10000"), per_sport=(True, "conservation_9000"),
            last_poll_age_s=floor - 30,
        )
        _r2, over = await _run_poll(
            outer=(False, "full_stop_10000"), per_sport=(True, "conservation_9000"),
            last_poll_age_s=floor + 30,
        )
        assert under.get_odds.await_count == 0, "polled inside the conservation floor"
        assert over.get_odds.await_count == 1, "never polls at all — floor is not a floor"


#: The two quota modes a pass can START in that are NOT full-stop. Both were
#: outside CERT-528's repair, and in both of them the per-sport re-read never
#: ran, so `absolute_stop_hit` could not be set at all.
NON_FULL_STOP_STARTS = [
    (True, "live_only_501"),   # the cert's own case: one unit above the stop
    (True, "ok_600000"),       # and the ordinary one, which is most passes
]


class TestTheHarnessCanSeeAMidPassTransition:
    """🔴 A ZERO OR A ONE IS ONLY EVIDENCE IF THE INSTRUMENT CAN SEE A TWO.

    Every claim below this point is `await_count == 0` or `== 1` on a pass whose
    quota state CHANGES between sports. A one-sport harness cannot tell "halted
    at the second sport" from "never ran a second sport", and a harness whose
    404 branch is unreachable cannot tell "skipped before the re-read" from
    "there was no re-read". These three controls buy the meaning of those
    numbers, and they are written first on purpose.
    """

    async def test_two_unconstrained_sports_really_do_poll_twice(self):
        _result, service = await _run_poll(
            outer=(True, "ok_600000"), per_sport=(True, "ok_600000"),
            sports=("basketball_nba", "baseball_mlb"),
        )
        assert service.get_odds.await_count == 2, (
            "the harness cannot see a second sport at all, so every '== 1' "
            "below would be satisfied by a pass that never had two"
        )

    async def test_the_per_sport_guard_is_consulted_once_per_sport(self):
        _result, service = await _run_poll(
            outer=(True, "ok_600000"), per_sport=(True, "ok_600000"),
            sports=("basketball_nba", "baseball_mlb"),
        )
        assert service.guard_calls == ["basketball_nba", "baseball_mlb"], (
            f"the re-read did not run for every sport: {service.guard_calls}"
        )

    async def test_a_404_cached_sport_still_lets_the_scores_fetch_fire(self):
        # The 404 branch has to be REACHED for the ordering guard below to mean
        # anything: odds must be zero because of the cache, and scores must be
        # one because nothing has stopped them.
        #
        # The scored sport is deliberately a DIFFERENT one: the scores loop has
        # its own 404 skip, so scoring the same cached sport would read zero
        # whatever the odds loop did — a control that cannot fail.
        _result, service = await _run_poll(
            outer=(True, "ok_600000"), per_sport=(True, "ok_600000"),
            sport_404=("basketball_nba",), score_sports=("baseball_mlb",),
        )
        assert service.get_odds.await_count == 0, "the 404 cache branch is not reached"
        assert service.get_scores.await_count == 1, (
            "scores never fire in this shape, so the ordering guard below would "
            "read zero for a reason that has nothing to do with the re-read"
        )


class TestAnAbsoluteStopIsSeenFromEveryStartingState:
    """🔴 CERT-535, and it is the first of this queue's seven blocks where the
    value was computed correctly and the GUARD AROUND THE GUARD was wrong.

    The per-sport re-read and all `absolute_stop_hit` handling sat inside
    `if quota_full_stop:`. So the flag could only ever be set on a pass that was
    ALREADY in full stop — and a pass that begins at `live_only_501`, one unit
    above the 500-unit absolute stop, spends its first sport, crosses the line,
    and then polls every remaining sport and every score with the breaker open.
    `absolute_stop` documents itself as "no exceptions, no priority sports,
    nothing".

    Enumerate the ENTRY STATES, not just the code paths.
    """

    @pytest.mark.parametrize("outer", NON_FULL_STOP_STARTS)
    async def test_a_pass_that_did_not_start_in_full_stop_still_halts(self, outer):
        result, service = await _run_poll(
            outer=outer, per_sport=(False, "absolute_stop_400"),
            last_poll_age_s=86_400.0,      # a day: no interval can be what gates it
        )
        assert service.get_odds.await_count == 0, (
            f"a pass starting at {outer[1]!r} crossed the absolute stop mid-pass "
            f"and called the Odds API anyway"
        )
        assert result["sports_skipped"] == 1, result

    @pytest.mark.parametrize("outer", NON_FULL_STOP_STARTS)
    async def test_a_pass_that_did_not_start_in_full_stop_halts_scores_too(self, outer):
        _result, service = await _run_poll(
            outer=outer, per_sport=(False, "absolute_stop_400"),
            score_sports=("basketball_nba",),
        )
        assert service.get_scores.await_count == 0, (
            f"a pass starting at {outer[1]!r} kept spending on get_scores after "
            f"the breaker reached its absolute stop"
        )

    async def test_the_crossing_stops_the_pass_at_the_sport_it_happens_on(self):
        # The realistic shape: quota is fine for the first sport, that sport's
        # own calls take it over the line, and the second sport reads the stop.
        # One poll, not two — and the control above proves two is visible.
        result, service = await _run_poll(
            outer=(True, "live_only_501"),
            per_sport={
                "basketball_nba": (True, "live_only_501"),
                "baseball_mlb": (False, "absolute_stop_400"),
            },
            sports=("basketball_nba", "baseball_mlb"),
            score_sports=("basketball_nba",),
        )
        assert service.get_odds.await_count == 1, (
            f"the pass did not stop at the crossing: {result}"
        )
        assert service.get_scores.await_count == 0, (
            "the odds loop broke but the independent scores block spent anyway"
        )

    async def test_the_re_read_is_above_the_404_skip_and_not_below_it(self):
        # 🔴 The reachability half of the same lesson. If every sport in the
        # pass is 404-cached, a re-read written below that `continue` never
        # runs, `absolute_stop_hit` stays False, and the scores block spends
        # under an open breaker — the CERT-535 defect rebuilt one branch lower.
        _result, service = await _run_poll(
            outer=(True, "ok_600000"), per_sport=(False, "absolute_stop_400"),
            sport_404=("basketball_nba",), score_sports=("baseball_mlb",),
        )
        assert service.get_scores.await_count == 0, (
            "a 404-cached sport skipped before the quota re-read, so the "
            "absolute stop was never seen and scores spent anyway"
        )


class TestAMidPassTighteningIsNeverWidenedBack:
    """The same monotonic rule CERT-528 established for the conservation floor,
    now applied to the quota MODE — because the mode is what decides who the
    floor is applied to. A re-read may only ADD constraint."""

    async def test_crossing_into_the_full_stop_band_applies_its_floor(self):
        # An ORDINARY pass. Quota crosses into the full-stop band and this
        # priority live sport reads back `conservation_*`. 100 s is past the
        # live cadence and short of the 600 s conservation floor, so it polls
        # if and only if the mode failed to tighten.
        assert "basketball_nba" in QUOTA_GUARD_PRIORITY_SPORTS, (
            "this sport must survive the priority filter, or the zero below is "
            "bought by the filter and says nothing about the floor"
        )
        _result, service = await _run_poll(
            outer=(True, "ok_600000"), per_sport=(True, "conservation_9000"),
            last_poll_age_s=100.0,
        )
        assert service.get_odds.await_count == 0, (
            "a pass that began unconstrained crossed into the full-stop band "
            "and kept the flat live cadence instead of the conservation floor"
        )

    async def test_crossing_into_the_full_stop_band_denies_a_non_priority_sport(self):
        _result, service = await _run_poll(
            outer=(True, "ok_600000"), per_sport=(False, "full_stop_9000"),
            sport_key="americanfootball_ncaaf", last_poll_age_s=86_400.0,
        )
        assert service.get_odds.await_count == 0, (
            "a deny was only honoured inside an outer FULL_STOP"
        )

    #: 🔴 CERT-540. The readings that FOLLOW a full-stop DENY. `ok_*` is quota
    #: refilling (or a racing writer); `redis_error` and `no_redis` are
    #: `check_quota_guard`'s two fail-open escapes, which return True and say
    #: nothing about the band. All three used to reopen the pass, because the
    #: deny took `continue` before the latch ran.
    REOPENING_READS_AFTER_A_DENY = ["ok_600000", "redis_error", "no_redis"]

    @pytest.mark.parametrize("second", REOPENING_READS_AFTER_A_DENY)
    async def test_a_full_stop_DENY_still_constrains_the_next_sport(self, second):
        """🔴 CERT-540, and it is the sharpest ordering bug in the chain.

        A DENY is the reading that most certainly proves the breaker has
        tripped — and it was the one reading thrown away, because
        `if not sport_ok: continue` sat ABOVE the latch. Sport one reads
        `full_stop_9000`, skips itself, and tells the pass nothing. Sport two
        reads `ok`/`redis_error` and polls, after the task has already SEEN
        full stop.

        `icehockey_nhl` is deliberately NON-priority: if the latch works, the
        priority filter is what stops it, and if the latch does not run there
        is no filter to stop it with.
        """
        assert "icehockey_nhl" not in QUOTA_GUARD_PRIORITY_SPORTS
        _result, service = await _run_poll(
            outer=(True, "ok_600000"),
            per_sport={
                "soccer_epl": (False, "full_stop_9000"),
                "icehockey_nhl": (True, second),
            },
            sports=("soccer_epl", "icehockey_nhl"),
            last_poll_age_s=86_400.0,      # a day: no interval can be what gates it
        )
        assert service.guard_calls == ["soccer_epl", "icehockey_nhl"], (
            f"the pass did not reach the second sport at all: "
            f"{service.guard_calls} — this zero would be vacuous"
        )
        assert service.get_odds.await_count == 0, (
            f"a full-stop DENY was discarded before the latch, and a following "
            f"{second!r} reopened the pass and spent the Odds API"
        )

    async def test_a_later_ok_reading_cannot_reopen_what_an_earlier_one_closed(self):
        # Quota reads `conservation_*` on sport one and then — refill, or a
        # racing writer — `ok_*` on sport two. Sport two is a priority live
        # sport at 100 s: under the latch it stays on the 600 s floor.
        assert QUOTA_GUARD_PRIORITY_SPORTS.issuperset(
            {"basketball_nba", "baseball_mlb"}
        ), "both sports must survive the priority filter for this to test the floor"
        _result, service = await _run_poll(
            outer=(True, "ok_600000"),
            per_sport={
                "basketball_nba": (True, "conservation_9000"),
                "baseball_mlb": (True, "ok_600000"),
            },
            sports=("basketball_nba", "baseball_mlb"),
            last_poll_age_s=100.0,
        )
        assert service.get_odds.await_count == 0, (
            "a later ok reading widened the pass back out — a re-read may only "
            "ADD constraint, never remove it"
        )


class TestThePassesOwnLastCallCannotOutrunTheBreaker:
    """🔴 CERT-541. `absolute_stop_hit` could only be set by a guard read taken
    BEFORE an odds call — so if the LAST (or only) odds response is the one whose
    recorded `remaining` crosses the 500-unit absolute stop, there is no next
    sport left to observe it, and the scores loop spends anyway. **A one-sport
    pass leaked every single time.**

    The class again: the guard was upstream of the consuming path instead of ON
    it. `record_odds_api_quota` has written every response's reading by the time
    the loop exits, so one read at the boundary sees the whole pass including
    its own last call.
    """

    async def test_the_boundary_read_happens_at_all(self):
        # Control. If there is only ever ONE pass-wide guard read, every zero
        # below is bought by something else entirely.
        _result, service = await _run_poll(
            outer=(True, "ok_600000"), per_sport=(True, "ok_600000"),
            score_sports=("basketball_nba",),
        )
        assert service.passwide_guard_reads == 2, (
            f"expected the outer read AND the loop/scores boundary read, got "
            f"{service.passwide_guard_reads}"
        )

    async def test_scores_still_fire_when_the_boundary_read_is_clean(self):
        # The other control: the boundary read must not become a blanket "never
        # fetch scores". Quota is fine at both reads, so scores fetch.
        _result, service = await _run_poll(
            outer=(True, "ok_600000"), per_sport=(True, "ok_600000"),
            boundary=(True, "ok_599000"), score_sports=("basketball_nba",),
        )
        assert service.get_odds.await_count == 1
        assert service.get_scores.await_count == 1, (
            "the boundary read is refusing scores in the ordinary case"
        )

    async def test_a_one_sport_pass_whose_own_call_crosses_the_stop_skips_scores(self):
        # 🔴 The exact defect. The pass starts fine, makes its ONE odds call, and
        # that response is what records `remaining=400`. There is no second sport
        # to notice. Before CERT-541's repair, scores spent anyway.
        _result, service = await _run_poll(
            outer=(True, "ok_600000"), per_sport=(True, "ok_600000"),
            boundary=(False, "absolute_stop_400"),
            score_sports=("basketball_nba",),
        )
        assert service.get_odds.await_count == 1, (
            "the odds call never happened, so nothing could have crossed the "
            "stop and this test proves nothing"
        )
        assert service.get_scores.await_count == 0, (
            "the pass's own last odds response crossed the absolute stop and the "
            "independent scores fetch spent anyway"
        )

    async def test_the_same_holds_for_the_LAST_sport_of_a_multi_sport_pass(self):
        _result, service = await _run_poll(
            outer=(True, "ok_600000"), per_sport=(True, "ok_600000"),
            sports=("basketball_nba", "baseball_mlb"),
            boundary=(False, "absolute_stop_400"),
            score_sports=("icehockey_nhl",),
        )
        assert service.get_odds.await_count == 2, "both sports must have polled"
        assert service.get_scores.await_count == 0


class TestAScoreFetchCannotOutrunTheBreakerEither:
    """The same class one level down, closed rather than waited for.

    `get_scores` calls are Odds API calls and they record quota too, so a scores
    response can be the one that crosses the absolute stop — and every remaining
    score in the same pass would spend past it. A re-read placed only at the
    loop/scores boundary is upstream of THIS loop, which is the exact sentence
    that has now been written about this branch nine times.
    """

    async def test_two_score_sports_really_do_fetch_twice(self):
        # Control first: without it, "stopped at the second" is indistinguishable
        # from "there was never a second".
        _result, service = await _run_poll(
            outer=(True, "ok_600000"), per_sport=(True, "ok_600000"),
            score_sports=("baseball_mlb", "icehockey_nhl"),
        )
        assert service.get_scores.await_count == 2

    async def test_a_mid_scores_crossing_halts_the_remaining_fetches(self):
        # `per_sport` is keyed, so the SCORES loop's own re-read for the second
        # score sport returns the stop. The first score fetch has happened; the
        # second must not.
        _result, service = await _run_poll(
            outer=(True, "ok_600000"),
            per_sport={
                "basketball_nba": (True, "ok_600000"),   # the odds sport
                "baseball_mlb": (True, "ok_600000"),     # score sport 1
                "icehockey_nhl": (False, "absolute_stop_400"),   # score sport 2
            },
            score_sports=("baseball_mlb", "icehockey_nhl"),
        )
        assert service.get_scores.await_count == 1, (
            "a scores response crossed the absolute stop and the remaining "
            "score fetches spent past it"
        )


class TestAPerSportReReadDoesNotFloodTheBreakersOwnLog:
    """The cost of making the re-read unconditional, and the guard on paying it.

    `check_quota_guard` announces FULL_STOP at CRITICAL. Before CERT-535 that
    line fired at most once per pass plus once per priority sport; now the
    re-read runs for EVERY sport in EVERY mode, so a dozen sports at a 30 s beat
    is ~50,000 CRITICAL lines a day restating a state the pass announced once —
    a Sentry flood during the exact emergency an operator has to read.

    So the per-sport read passes `quiet=True`. The claim that has to hold is
    that `quiet` changes the LOG and nothing else: if it ever changed a return
    value it would be a fail-open breaker wearing a logging flag.
    """

    QUOTA_LOGGER = "app.tasks.redis_state"

    #: The whole reason ladder, as (remaining, sport_key). Every band, both
    #: sides of the priority split.
    LADDER = [
        (400, "basketball_nba"),        # absolute stop — no exceptions
        (400, "soccer_epl"),
        (9_000, "basketball_nba"),      # full-stop band, priority => conservation
        (9_000, "soccer_epl"),          # full-stop band, non-priority => deny
        (30_000, "basketball_nba"),     # live-only band
        (600_000, "basketball_nba"),    # ordinary
    ]

    @staticmethod
    def _guard(remaining, sport_key, quiet):
        from app.tasks import redis_state

        with patch.object(redis_state, "get_redis_client",
                          return_value=_FakeRedis(0, quota_hash={b"remaining":
                                                                str(remaining).encode()})):
            return redis_state.check_quota_guard(
                "poll_odds", sport_key=sport_key, quiet=quiet,
            )

    @pytest.mark.parametrize("remaining,sport_key", LADDER)
    def test_quiet_changes_the_log_and_never_the_verdict(self, remaining, sport_key):
        loud = self._guard(remaining, sport_key, quiet=False)
        quiet = self._guard(remaining, sport_key, quiet=True)
        assert loud == quiet, (
            f"`quiet` altered the breaker's verdict at {remaining} remaining "
            f"for {sport_key}: {loud} loud vs {quiet} quiet. A logging flag "
            f"that moves a boolean is a fail-open breaker in disguise."
        )

    def test_the_loud_path_really_does_emit_so_the_silence_below_means_something(
        self, caplog,
    ):
        with caplog.at_level(logging.CRITICAL, logger=self.QUOTA_LOGGER):
            self._guard(9_000, "soccer_epl", quiet=False)
        assert [r for r in caplog.records if r.levelno >= logging.CRITICAL], (
            "the instrument cannot see a CRITICAL at all, so every empty "
            "caplog below is vacuous"
        )

    @pytest.mark.parametrize("remaining,sport_key", LADDER)
    def test_a_quiet_read_says_nothing(self, remaining, sport_key, caplog):
        with caplog.at_level(logging.INFO, logger=self.QUOTA_LOGGER):
            self._guard(remaining, sport_key, quiet=True)
        assert not [r for r in caplog.records if r.name == self.QUOTA_LOGGER], (
            f"a quiet read logged anyway at {remaining} remaining: "
            f"{[r.getMessage() for r in caplog.records]}"
        )

    async def test_a_full_stop_pass_announces_the_breaker_once_not_once_per_sport(
        self, caplog,
    ):
        """The behavioural guard — it goes red if `quiet=True` is ever dropped
        from the call site, which no unit test of `check_quota_guard` can see."""
        from app.tasks import redis_state

        sports = ["soccer_epl", "soccer_uefa_champs_league", "icehockey_nhl"]
        assert not QUOTA_GUARD_PRIORITY_SPORTS.intersection(sports), (
            "these must all be NON-priority, or the guard's CRITICAL branch is "
            "never the one taken and the count proves nothing"
        )

        now_ts = time.time()
        quota = _FakeRedis(now_ts - 100.0, quota_hash={b"remaining": b"9000"})
        session = _FakeSession(
            [(k, datetime.now(timezone.utc) - timedelta(minutes=5), True)
             for k in sports],
            [],
        )
        service = MagicMock()
        service.get_odds = AsyncMock(return_value=[])
        service.get_scores = AsyncMock(return_value=[])
        service.close = AsyncMock()
        service.last_requests_remaining = None
        service.last_requests_used = None

        class _CM:
            async def __aenter__(self):
                return session

            async def __aexit__(self, *_a):
                return False

        with caplog.at_level(logging.CRITICAL, logger=self.QUOTA_LOGGER), \
                patch.object(redis_state, "get_redis_client", return_value=quota), \
                patch("app.tasks.odds_polling.OddsAPIService", return_value=service), \
                patch("app.tasks.odds_polling.get_redis_client", return_value=quota), \
                patch("app.tasks.odds_polling.get_task_session", return_value=_CM()), \
                patch("app.tasks.odds_polling.detect_and_close_stale_events",
                      # live/048 — see the note on the sibling patch above.
                      AsyncMock(return_value={"closed": 0, "suspended": 0})), \
                patch("app.tasks.odds_polling.update_poll_state", MagicMock()), \
                patch("app.tasks.excitement_index.update_live_ei",
                      AsyncMock(return_value=0)):
            await odds_polling._poll_all_odds()

        breaker_criticals = [
            r for r in caplog.records
            if r.name == self.QUOTA_LOGGER and r.levelno >= logging.CRITICAL
        ]
        assert len(breaker_criticals) == 1, (
            f"the breaker announced itself {len(breaker_criticals)} times for a "
            f"{len(sports)}-sport pass — the per-sport re-read is not quiet, and "
            f"at a 30 s beat that is tens of thousands of CRITICAL lines a day"
        )
        assert service.get_odds.await_count == 0, (
            "a non-priority sport polled during FULL_STOP"
        )


class TestTheShipSurvivesTheRepair:
    """LAT-P159 exists to make live odds fresh. The quota repair must not undo it."""

    async def test_an_ordinary_live_sport_still_polls_at_the_new_cadence(self):
        _result, service = await _run_poll(
            outer=(True, "ok_600000"), per_sport=(True, "ok_600000"),
            last_poll_age_s=LIVE_POLL_INTERVAL + 1,
        )
        assert service.get_odds.await_count == 1, (
            "the cadence ship regressed: a live sport past its interval did not poll"
        )

    async def test_a_live_sport_inside_the_new_cadence_still_waits(self):
        _result, service = await _run_poll(
            outer=(True, "ok_600000"), per_sport=(True, "ok_600000"),
            last_poll_age_s=LIVE_POLL_INTERVAL - 1,
        )
        assert service.get_odds.await_count == 0


class TestTheScoresLoopObeysTheOtherTwoQuotaBands:
    """#2368 — the breaker was half a breaker.

    The scores loop already re-read the guard, but acted on `absolute_stop`
    alone: the allow/deny boolean was `_score_ok`, discarded. So FULL_STOP — the
    state that skips every non-priority sport in the odds loop — reached this
    loop and did nothing, and scores kept fetching for every sport with a recent
    event at the moment quota is scarcest.

    `check_quota_guard("poll_odds", sport_key=...)` already encodes the tiering:
    (False, "full_stop_*") for a non-priority sport, (True, "conservation_*")
    for a priority one, allow under LIVE_ONLY. These stubs return exactly that
    contract (redis_state.py: the FULL_STOP band), so the arms model the real
    guard rather than a policy invented in the test.
    """

    NON_PRIORITY = "icehockey_nhl"     # not in QUOTA_GUARD_PRIORITY_SPORTS
    PRIORITY = "baseball_mlb"          # in QUOTA_GUARD_PRIORITY_SPORTS

    async def test_a_non_priority_sport_fetches_scores_when_quota_is_fine(self):
        # Control. Without it, every zero below is indistinguishable from "this
        # sport never fetches scores in the harness at all".
        _result, service = await _run_poll(
            outer=(True, "ok_600000"), per_sport=(True, "ok_600000"),
            score_sports=(self.NON_PRIORITY,),
        )
        assert service.get_scores.await_count == 1

    async def test_a_priority_sport_still_fetches_scores_under_FULL_STOP(self):
        # 🔴 THE CONTROL THAT MATTERS. The repair must refuse the long tail, not
        # switch scores off: a score fetch is what turns a `live` event into
        # `completed`, so a repair that silenced priority sports too would strand
        # exactly the games users watch. A green suite with this arm missing
        # cannot tell the fix from `sports_for_scores = []`.
        result, service = await _run_poll(
            outer=(False, "full_stop_9000"),
            per_sport={
                "basketball_nba": (True, "conservation_9000"),
                self.PRIORITY: (True, "conservation_9000"),
            },
            score_sports=(self.PRIORITY,),
        )
        assert service.get_scores.await_count == 1, (
            "FULL_STOP withheld scores from a PRIORITY sport — completion "
            "detection dies for the games that matter most"
        )
        # `.get` on purpose: a control must be green under BOTH arms, including
        # the un-repaired source that has no such counter. Asserting the key
        # here would turn the control into a second detector and cost it the one
        # job it has — proving the harness can still see a fetch.
        assert result.get("scores_skipped_quota", 0) == 0, result

    async def test_a_non_priority_sport_is_refused_under_FULL_STOP(self):
        # The defect itself.
        result, service = await _run_poll(
            outer=(False, "full_stop_9000"),
            per_sport={
                "basketball_nba": (True, "conservation_9000"),
                self.NON_PRIORITY: (False, "full_stop_9000"),
            },
            score_sports=(self.NON_PRIORITY,),
        )
        assert service.get_scores.await_count == 0, (
            "FULL_STOP skips this sport's ODDS and its SCORES spent anyway — "
            "get_scores is an Odds API call billed against the same quota"
        )
        assert result["scores_skipped_quota"] == 1, (
            f"the refusal was invisible to task-metrics: {result}"
        )

    async def test_LIVE_ONLY_still_allows_scores(self):
        # A deliberate allow, pinned so it cannot change silently. LIVE_ONLY is
        # the mild band (20k-50k); scores are the cheap half and they are the
        # completion signal, so cutting them here would strand events in `live`
        # long before the emergency the breaker exists for.
        _result, service = await _run_poll(
            outer=(True, "live_only_30000"),
            per_sport=(True, "live_only_30000"),
            score_sports=(self.NON_PRIORITY,),
        )
        assert service.get_scores.await_count == 1

    @pytest.mark.parametrize("reason", NON_CONSERVATION_ALLOW_REASONS)
    async def test_no_fail_open_reread_can_erode_a_known_FULL_STOP(self, reason):
        # CERT-528's defect, reachable through THIS loop: a transient
        # (True, "no_redis") in the scores loop must not erase the FULL_STOP the
        # pass already established. Monotonic — a re-read may only ADD constraint.
        result, service = await _run_poll(
            outer=(False, "full_stop_9000"),
            per_sport={
                "basketball_nba": (True, "conservation_9000"),
                self.NON_PRIORITY: (True, reason),
            },
            score_sports=(self.NON_PRIORITY,),
        )
        assert service.get_scores.await_count == 0, (
            f"the scores re-read {reason!r} cleared the FULL_STOP the pass had "
            f"already established and spent on a non-priority sport"
        )
        assert result["scores_skipped_quota"] == 1, result

    async def test_two_non_priority_score_sports_really_do_fetch_twice(self):
        # Control for the mid-loop latch below.
        result, service = await _run_poll(
            outer=(True, "ok_600000"),
            per_sport={
                "basketball_nba": (True, "ok_600000"),
                self.NON_PRIORITY: (True, "ok_600000"),
                "americanfootball_nfl": (True, "no_redis"),
            },
            score_sports=(self.NON_PRIORITY, "americanfootball_nfl"),
        )
        assert service.get_scores.await_count == 2
        assert result.get("scores_skipped_quota", 0) == 0, result  # control: see above

    async def test_a_mid_scores_FULL_STOP_constrains_the_REST_of_the_loop(self):
        # The pass starts unconstrained; the FIRST score sport's own re-read is
        # what discovers FULL_STOP. The second sport's read is fail-open, so only
        # the latch can stop it. Same inputs as the control above except the one
        # reason under test — so the zero is caused by the band, not the harness.
        result, service = await _run_poll(
            outer=(True, "ok_600000"),
            per_sport={
                "basketball_nba": (True, "ok_600000"),
                self.NON_PRIORITY: (False, "full_stop_9000"),
                "americanfootball_nfl": (True, "no_redis"),
            },
            score_sports=(self.NON_PRIORITY, "americanfootball_nfl"),
        )
        assert service.get_scores.await_count == 0, (
            "the scores loop discovered FULL_STOP on its first sport and kept "
            "spending on the rest of the pass"
        )
        assert result["scores_skipped_quota"] == 2, result

    async def test_the_refusal_counter_rides_out_with_the_run(self):
        # The counter's own detector, kept OUT of the controls above so they can
        # stay green under both arms. #2368's verification is "scores contribute
        # zero under FULL_STOP", and a refusal nobody can count from
        # `task-metrics` is only readable by grepping logs during the emergency.
        result, _service = await _run_poll(
            outer=(True, "ok_600000"), per_sport=(True, "ok_600000"),
            score_sports=(self.NON_PRIORITY,),
        )
        assert "scores_skipped_quota" in result, (
            f"the quota refusals never reach the run's own result: {result}"
        )
