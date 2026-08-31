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
from app.tasks.redis_state import QUOTA_GUARD_CONSERVATION_INTERVAL


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
    def __init__(self, last_poll_ts):
        self.last_poll_ts = last_poll_ts

    def get(self, key):
        if key.startswith("bainluck:last_poll:"):
            return str(self.last_poll_ts).encode()
        return None                          # no 404 cache, no unchanged_count

    def hget(self, *_a, **_k):
        return None

    def set(self, *_a, **_k):
        return True

    def incr(self, *_a, **_k):
        return 1

    def expire(self, *_a, **_k):
        return True


async def _run_poll(*, outer, per_sport, sport_key="basketball_nba",
                    last_poll_age_s=100.0, score_sports=()):
    """Execute the real `_poll_all_odds` and hand back its Odds API ledger."""
    now_ts = time.time()
    session = _FakeSession(
        [(sport_key, datetime.now(timezone.utc) - timedelta(minutes=5), True)],
        list(score_sports),
    )

    service = MagicMock()
    service.get_odds = AsyncMock(return_value=[])
    service.get_scores = AsyncMock(return_value=[])
    service.close = AsyncMock()
    service.last_requests_remaining = None   # a MagicMock here is `is not None`
    service.last_requests_used = None        # and would hit the real recorder

    def _guard(_task_type, sport_key=None):
        return outer if sport_key is None else per_sport

    class _CM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_a):
            return False

    with patch("app.tasks.odds_polling.check_quota_guard", side_effect=_guard), \
            patch("app.tasks.odds_polling.OddsAPIService", return_value=service), \
            patch("app.tasks.odds_polling.get_redis_client",
                  return_value=_FakeRedis(now_ts - last_poll_age_s)), \
            patch("app.tasks.odds_polling.get_task_session", return_value=_CM()), \
            patch("app.tasks.odds_polling.detect_and_close_stale_events",
                  AsyncMock(return_value=0)), \
            patch("app.tasks.odds_polling.update_poll_state", MagicMock()), \
            patch("app.tasks.excitement_index.update_live_ei", AsyncMock(return_value=0)):
        result = await odds_polling._poll_all_odds()

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
