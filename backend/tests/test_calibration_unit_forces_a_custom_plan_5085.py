"""#5085 — every unit statement re-plans, so the sixth one stops falling off a cliff.

**The measurement, from three consecutive production beats (2026-09-11).** Sampled
from `calibration:main:phase_ledger` once per beat — the beat ring drops the fence
keys (#5081, parked), the ledger does not:

===========  =========  =========  ==================  ===========  ========
beat (gen)   attempted  completed  cancelled slots     fence        wasted
===========  =========  =========  ==================  ===========  ========
04:15Z       7          5 (15-19)  **20, 21**          452,028 ms   64.3%
05:15Z       6          5 (20-24)  **25**              632,404 ms   51.9%
06:15Z       7          5 (25-29)  **30, 31**          306,064 ms   56.8%
===========  =========  =========  ==================  ===========  ========

Two things fall out and neither is the fence:

1. **Every cancelled slice completed on the very next beat**, as that beat's first
   or second attempt, in 80-165 s. Slots 20, 21, 25 all did. So no slice is too
   large, and the 128-way partition converges.
2. Beat 3's fence was **less than half** beat 2's and it still banked exactly five
   and still cancelled at attempt six. A cause that does not move when the fence
   halves is not the fence.

**The cause.** ``chunk_sql`` is built once outside the unit loop
(``precompute_calibration.py:5106``) and executed once per unit on one pooled
asyncpg connection, so a beat's units are executions 1..N of ONE prepared
statement. Production runs ``plan_cache_mode = auto`` (``pg_settings``:
``boot_val = reset_val = auto``, recorded in
``test_last_match_arm_custom_plan_4506``), under which Postgres uses a custom plan
for the first five executions and then pins the generic one. The unit statement
takes three array parameters whose length and selectivity vary per slice, and a
generic plan cannot see into them — the same estimate collapse #4506 measured on
``_last_match_query`` (811 estimated rows against a real 0; 618 ms median against
1-3 ms with literals). A new beat is a new task run on a new connection, so the
execution counter resets, which is why the same slice is fast an hour later and
why no per-slice census could ever have found this.

**What this suite pins:**

1. the arm is issued, per unit, with the mode #4506 established;
2. arming cannot fail the beat, and a failure is recorded rather than swallowed —
   "the arm never took" and "the diagnosis was wrong" are different findings
   (#4506's own read-back argument);
3. **the population fingerprint does not move.** This is the load-bearing one. The
   fingerprint hashes four functions in ``precompute_calibration.py`` and
   ``inspect.getsource`` never returns a callee's text, so a change in
   ``calibration_main_build.py`` must not re-key the cursor. If it did, deploying
   this would discard every banked unit — 30 of 128 at the time of writing, on a
   page already frozen — which is the opposite of the ship.
"""

from __future__ import annotations

import pytest

import app.tasks.precompute_calibration as pc
from app.tasks.calibration_main_build import UNIT_PLAN_CACHE_MODE

#: The value this tree's population chain hashes to.
#:
#: It began as the live production value at 2026-09-11T06:15Z, read from the
#: phase ledger's ``input_fingerprint`` — not a golden string invented here — so
#: that #5085 could prove it did NOT re-key the bank.
#:
#: RE-ANCHORED by #5401 (CAL-P1119), which does re-key it, on purpose:
#: ``cf030934…`` -> ``634f4e35…``. The writer-bar exclusion edits
#: ``_calibration_population_ctes``, one of the four functions
#: ``_main_input_fingerprint`` hashes, and it MUST — the fingerprint's whole job
#: is to notice when the set of qualifying rows changes, and this ship changes
#: it. Any predicate change lands here; that is the design, not a surprise.
#:
#: THE COST, stated rather than discovered on deploy: re-keying discards the
#: 128-unit staged-futures bank, so the first build after this ships climbs from
#: zero — measured at q269's bump as ~3.3 h of build, or ceil(128/13) = 10
#: hourly beats unassisted. It is the same bill the q269 bump paid, and it is
#: why this ship is batched with the q270 version bump rather than landing on
#: its own: paying it twice for one methodology change would be waste.
#:
#: The guard still earns its place after the re-anchor. #5085's actual claim is
#: that a change confined to ``calibration_main_build.py`` cannot re-key the
#: cursor, and that is proved independently and structurally by
#: ``test_the_new_helper_is_not_inside_the_hashed_source`` below. This constant
#: is the tripwire for an UNINTENDED move: if you did not mean to change which
#: rows qualify and this test is red, you have moved the population.
#:
#: RE-ANCHORED for #5401 (CAL-P1121). The move is NOT a population
#: change: the edit that caused it adds two payload-only transparency
#: counts (`writer_bar_included` / `writer_bar_excluded`) to
#: `liq_summary`, which no row qualifies or fails on. It moves anyway
#: because the hash covers the SOURCE of `_main_futures_sql` wholesale,
#: not just its population predicates — a known imprecision, and a
#: deliberately conservative one. It costs nothing here: the writer-bar
#: exclusion in the same commit re-keys the cursor on its own account,
#: so the rebuild is paid once, not twice.
#:
#: RE-ANCHORED AGAIN for CAL-P1137 (the q270 recount): ``b1126a29…`` ->
#: ``6ae47375…``. Two of this bump's three edits are meant to land here — the
#: threshold-ladder arm (#5305) edits ``_calibration_population_ctes`` and
#: ``CALIBRATION_POPULATION_VERSION`` is itself a hashed input — so an UNMOVED
#: fingerprint would have been the bug. The rebuild is the one the version bump
#: already pays for; nothing extra is spent by these two riding along.
#:
#: RE-ANCHORED AGAIN for CAL-P1138 (q271, D112 #997): ``6ae47375…`` -> ``66179356…``.
#: Same reasoning, and the move is again the EXPECTED one rather than a
#: surprise to be papered over — which is worth saying explicitly, because
#: re-anchoring a pin is how a rig starts agreeing with whatever it is given.
#: Two hashed inputs changed on purpose: ``_calibration_population_ctes`` now
#: renders the lone-claim admission in ``ranked_outcomes``, and
#: ``CALIBRATION_POPULATION_VERSION`` moved q270 -> q271. An UNMOVED fingerprint
#: would have meant the widening never reached the population SQL. The bank is
#: discarded either way by the version bump, so the re-key costs nothing extra.
#: RE-ANCHORED for #6275 (the identity quarantine, Alex ruling queue 363 item 4):
#: ``66179356…`` -> ``c0a825a6…``. The move is again the EXPECTED one — two hashed
#: inputs changed on purpose: ``_calibration_population_ctes`` now renders the
#: quarantine chain, and ``identity_quarantine_ctes`` was ADDED to the hash list
#: (it lives in another module, so the population root could never have covered
#: the SQL it returns).
#:
#: THIS RE-ANCHOR IS NOT LIKE THE THREE ABOVE, and the difference is the whole
#: reason to read this note. Each of those rode a ``CALIBRATION_POPULATION_VERSION``
#: bump, so they could say "the bank is discarded either way by the version bump,
#: so the re-key costs nothing extra". This change does NOT bump the version, so
#: the re-key is NOT already paid for: deploying it discards every banked unit and
#: restarts a multi-hour convergence. Whether it should instead ride the combined
#: invalidation window ruling 024 describes — with the version bump and its
#: published before/after census — is an ACTIVATION decision that was explicitly
#: withheld from the lane that made this change (#6275, coordinator note
#: 2026-09-14 18:37 PDT: "production fingerprint reset/rebuild/enable not yet
#: authorized"). Re-anchoring the pin RECORDS the move; it does not decide when
#: to pay for it.
#:
#: RE-ANCHORED WITHIN #6275 for CERT-2902's required repair: ``c0a825a6…`` ->
#: ``80a180b0…``. Not a second rebuild — the branch it sits on has never been
#: deployed, so this supersedes the anchor above rather than adding to it, and
#: the cost paragraph above is unchanged and still the operative one. The move
#: is again the EXPECTED one: the repair edits ``_calibration_population_ctes``
#: (``market_info`` now carries the LINKED EVENT's start and the quarantine is
#: pointed at it) AND ``identity_quarantine_ctes`` (``commence_time_col`` is no
#: longer defaulted), and both are hashed inputs. An UNMOVED fingerprint here
#: would have meant the repair never reached the population SQL — which is
#: precisely the shape of the defect CERT-2902 found, so it is worth saying that
#: this pin moving is evidence and not paperwork.
#: RE-ANCHORED for CAL-P1300, the #6275 cost repair: ``80a180b0…`` ->
#: ``1a1d9a91…``. One hashed input moved and it is a single keyword:
#: ``identity_quarantine_ctes`` now emits ``identity_disputed_markets AS
#: MATERIALIZED (``. The predicate, the population and the published rows are
#: byte-for-byte what ``80a180b0…`` produced — this move is a PLAN change and
#: nothing else — which is why the re-anchor is recorded here rather than
#: treated as a population edit.
#:
#: WHAT THIS RE-KEY COSTS, WHICH IS THE QUESTION THE NOTE ABOVE INSISTS ON
#: ASKING. Nominally it discards a 52/128 bank. Measured, it discards nothing
#: that was going to finish: since ``80a180b0…`` reached ``bainluck-heavy`` at
#: 11:48:44Z on 2026-09-15 the bank has been pinned at exactly 52 across every
#: beat, two units attempted and ZERO completed each time, both cancelled at the
#: 483,000 ms fence (``calibration:beat_gauge_history``; the 24 beats before it
#: completed 6-10 units apiece at a 116-165 s mean). The inlined chain is why —
#: see the gate. So the choice is not "keep 52 units or pay for a rebuild"; it
#: is "keep a bank that cannot advance, or re-key one that can". The version is
#: NOT bumped: the published population is unchanged, so there is nothing for a
#: reader to be told and q271 still names the right rows.
LIVE_INPUT_FINGERPRINT = "1a1d9a914a4824381d8132498197bb34"


class _Db:
    """Records the SQL it is handed. Optionally refuses the planner GUC."""

    def __init__(self, *, fail_on_plan_cache: bool = False):
        self.executed: list[str] = []
        self._fail = fail_on_plan_cache

    async def execute(self, statement, *_args, **_kwargs):
        sql = str(statement)
        if self._fail and "plan_cache_mode" in sql:
            raise RuntimeError("permission denied to set parameter")
        self.executed.append(sql)
        return None


class _Ledger:
    def __init__(self):
        self.gauges: dict = {}

    def record_gauge(self, name, value):
        self.gauges[name] = value


class _Runner:
    """Just enough of the runner to exercise the arm in isolation."""

    def __init__(self, **kw):
        self.ledger = _Ledger()

    _force_custom_plan = None  # bound below


@pytest.fixture()
def runner():
    from app.tasks.calibration_main_build import PhaseRunner

    obj = _Runner()
    obj._force_custom_plan = PhaseRunner._force_custom_plan.__get__(obj, _Runner)
    return obj


class TestTheArm:
    async def test_it_issues_set_local_plan_cache_mode(self, runner):
        db = _Db()

        await runner._force_custom_plan(db)

        assert len(db.executed) == 1
        sql = db.executed[0]
        assert "SET LOCAL" in sql
        assert "plan_cache_mode" in sql
        assert "force_custom_plan" in sql

    async def test_it_uses_the_mode_4506_established(self):
        """Pinned against the precedent rather than restated as a literal."""
        from app.routes.events import _LAST_MATCH_PLAN_CACHE_MODE

        assert UNIT_PLAN_CACHE_MODE == _LAST_MATCH_PLAN_CACHE_MODE == "force_custom_plan"

    async def test_it_is_local_so_it_dies_with_the_units_transaction(self, runner):
        """A bare ``SET`` would leak the replan cost onto every later statement
        on this pooled connection, which is what #4506's disarm exists to avoid.
        ``SET LOCAL`` ends at the unit's own commit, so there is nothing to
        disarm — but only while it really is LOCAL."""
        db = _Db()

        await runner._force_custom_plan(db)

        assert db.executed[0].strip().startswith("SET LOCAL")

    async def test_arming_is_recorded(self, runner):
        db = _Db()

        await runner._force_custom_plan(db)

        assert runner.ledger.gauges.get("staged:unit_plan_cache_mode_armed") == 1


class TestArmingNeverFailsTheBeat:
    async def test_a_refused_guc_does_not_raise(self, runner):
        db = _Db(fail_on_plan_cache=True)

        await runner._force_custom_plan(db)  # must not raise

    async def test_a_refused_guc_is_named_rather_than_swallowed(self, runner):
        """#4506's point: "the arm never took" and "the diagnosis was wrong" are
        two findings and must not read alike."""
        db = _Db(fail_on_plan_cache=True)

        await runner._force_custom_plan(db)

        assert runner.ledger.gauges.get("staged:unit_plan_cache_reason:not_armed") == 1
        assert "staged:unit_plan_cache_mode_armed" not in runner.ledger.gauges


class TestTheBankSurvivesThisChange:
    """The load-bearing property: deploying this must not re-key the cursor."""

    def test_the_population_fingerprint_is_unmoved(self):
        assert pc._main_input_fingerprint() == LIVE_INPUT_FINGERPRINT

    def test_the_new_helper_is_not_inside_the_hashed_source(self):
        """``getsource`` returns a function's own text, never its callees'.

        The same rule CAL-P081 relied on, asserted for this change: every line
        #5085 adds lives in ``calibration_main_build.py``, which is not on the
        hash list at all.
        """
        import inspect

        hashed = (
            inspect.getsource(pc.compute_calibration_payload)
            + inspect.getsource(pc._calibration_population_ctes)
            + inspect.getsource(pc._virtual_market_ctes)
            + inspect.getsource(pc._main_futures_sql)
        )

        assert "def _force_custom_plan" not in hashed
        assert "plan_cache_mode" not in hashed
