"""The rolling re-stage, driven through the REAL frozen loop (CAL-P078, #2007).

**Ruling 102 governs this file.** The mechanism it covers lives half in a pure
module this lane may edit and half in ``precompute_calibration._run_staged_futures``,
which ruling 009 freezes. Every decision is testable purely — and a suite that
only did that would prove nothing about whether the frozen loop, calling these
functions in the order it calls them, actually re-stages anything. That is the
exact shape of the failure ruling 102 was written for: 17,093 green tests over a
worker that had never run.

So :class:`TestTheFrozenLoopActuallyReStages` **starts the real coroutine** —
the unedited one, imported from the frozen module — over stub I/O, and steps it
beat by beat.

The bug being closed, stated once: ``is_complete`` was ``planned == committed``
over SLOT keys; every slot is planned every beat; so once 128 slots were banked
it was True forever, the loop skipped every unit it already ``has()``,
``units_this_beat`` went to 0 and stayed there, and the build republished a
frozen census every hour under a brand-new ``generated_at`` and
``availability: fresh``. 115 of 128 units drifted, six hours and counting.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.utils.calibration_staged_futures import (
    advance,
    collect_unit_results,
    decode_staged_cursor_detailed,
    is_complete,
    new_staged_cursor,
    plan_units,
    promote_if_complete,
    retain_planned_units,
    served_drift,
    stamp_served_at,
    top_up_served_digests,
    unit_key,
)

VERSION = "q268"
INPUT_FP = "fp-input"
OWNER = "beat-1"
BUCKETS = 8


def _roster(n: int, *, extra: list[tuple] = ()) -> list[SimpleNamespace]:
    rows = [
        SimpleNamespace(market_id=i, source="kalshi", vm_id=f"m:{i:04d}", is_grouped=False)
        for i in range(n)
    ]
    rows += [
        SimpleNamespace(market_id=m, source=s, vm_id=v, is_grouped=g) for (m, s, v, g) in extra
    ]
    return rows


def _population_row(*, bucket_idx: int, n: int = 3, winners: int = 1):
    """One bucket row shaped like the population statement's output.

    Only DECLARED columns: the fold refuses a column whose kind it was not told
    (``UndeclaredColumnError``), because a passthrough summed is double-counted
    and an additive broadcast is frozen at one chunk's mass.
    """
    return SimpleNamespace(
        bucket_idx=bucket_idx,
        source="kalshi",
        category="sports",
        price_moved=False,
        is_nonexclusive_bundle=False,
        n=n,
        winners=winners,
        sum_prob=1.5,
        sum_sq_err=0.25,
        avg_prob=0.5,
        published_questions=n,
        representative_tie_broken=0,
    )


def _plan_size(roster) -> int:
    """How many units the FROZEN loop will plan for this roster.

    It uses ``STAGED_FUTURES_BUCKETS`` (128), not this module's ``BUCKETS``, and
    empty slots are not planned — so the count is a property of the roster, not
    a constant. Deriving it here is the difference between a test that asserts
    the loop's behaviour and one that asserts a number I chose.
    """
    from app.tasks.calibration_main_build import STAGED_FUTURES_BUCKETS

    return len(plan_units(roster, buckets=STAGED_FUTURES_BUCKETS))


def _bucket_mass(merged) -> int:
    """Total ``n`` across the merged bucket rows, however they are shaped.

    ``merge_futures_rows`` returns row objects, not mappings; the null-keyed
    census carriers are excluded because they are not buckets.
    """
    total = 0
    for row in merged:
        mapping = dict(row._mapping) if hasattr(row, "_mapping") else dict(vars(row))
        if mapping.get("bucket_idx") is not None:
            total += int(mapping.get("n") or 0)
    return total


# =============================================================================
# The pure decisions
# =============================================================================


class TestThePromotion:
    def test_a_complete_bank_moves_to_the_serving_slot_and_the_builder_restarts(self):
        chunks = plan_units(_roster(200), buckets=BUCKETS)
        cursor = new_staged_cursor(
            population_version=VERSION,
            input_fingerprint=INPUT_FP,
            generation_fingerprint="gen",
            owner=OWNER,
            generation=1,
        )
        cursor, _ = retain_planned_units(cursor, chunks)
        for chunk in chunks:
            cursor = advance(
                cursor, chunk.key, [_population_row(bucket_idx=chunk.index + 1)],
                owner=OWNER, lease_expires_at=0.0,
            )
        assert set(cursor.served_units) == {c.key for c in chunks}
        assert cursor.committed_units == (), "the builder starts the next census empty"
        assert cursor.served_accumulator is not None
        assert cursor.accumulator is None

    def test_an_incomplete_bank_is_never_promoted(self):
        chunks = plan_units(_roster(200), buckets=BUCKETS)
        cursor = new_staged_cursor(
            population_version=VERSION, input_fingerprint=INPUT_FP,
            generation_fingerprint="gen", owner=OWNER, generation=1,
        )
        cursor, _ = retain_planned_units(cursor, chunks)
        for chunk in chunks[:-1]:
            cursor = advance(
                cursor, chunk.key, [_population_row(bucket_idx=chunk.index + 1)],
                owner=OWNER, lease_expires_at=0.0,
            )
        assert cursor.served_units == ()
        assert len(cursor.committed_units) == len(chunks) - 1
        assert not is_complete(cursor, chunks), "a partial census may never publish"

    def test_promotion_without_a_plan_is_refused_rather_than_guessed(self):
        """``planned_units`` is what makes 'complete' answerable. Absent, it is not."""
        chunks = plan_units(_roster(100), buckets=BUCKETS)
        cursor = new_staged_cursor(
            population_version=VERSION, input_fingerprint=INPUT_FP,
            generation_fingerprint="gen", owner=OWNER, generation=1,
        )
        for chunk in chunks:
            cursor = advance(
                cursor, chunk.key, [_population_row(bucket_idx=chunk.index + 1)],
                owner=OWNER, lease_expires_at=0.0,
            )
        assert cursor.planned_units == ()
        assert cursor.served_units == (), "no plan, no promotion"
        # ...and it is not stuck: is_complete still answers off the builder, so
        # every pre-CAL-P078 caller and test behaves exactly as it always did.
        assert is_complete(cursor, chunks)

    def test_promotion_is_idempotent(self):
        chunks = plan_units(_roster(80), buckets=BUCKETS)
        cursor = new_staged_cursor(
            population_version=VERSION, input_fingerprint=INPUT_FP,
            generation_fingerprint="gen", owner=OWNER, generation=1,
        )
        cursor, _ = retain_planned_units(cursor, chunks)
        for chunk in chunks:
            cursor = advance(
                cursor, chunk.key, [_population_row(bucket_idx=chunk.index + 1)],
                owner=OWNER, lease_expires_at=0.0,
            )
        once = promote_if_complete(cursor)
        twice = promote_if_complete(once)
        assert once.served_units == twice.served_units
        assert twice.served_accumulator == once.served_accumulator


class TestWhatIsServedWhileTheNextCensusBuilds:
    def _complete_bank(self, chunks):
        cursor = new_staged_cursor(
            population_version=VERSION, input_fingerprint=INPUT_FP,
            generation_fingerprint="gen", owner=OWNER, generation=1,
        )
        cursor, _ = retain_planned_units(cursor, chunks)
        for chunk in chunks:
            cursor = advance(
                cursor, chunk.key, [_population_row(bucket_idx=chunk.index + 1)],
                owner=OWNER, lease_expires_at=0.0,
            )
        return cursor

    def test_a_partial_rebuild_publishes_the_served_bank_not_a_blend(self):
        """THE property. A rebuild in progress must never take the curve dark,
        and must never publish half of one generation on top of half of another.
        """
        chunks = plan_units(_roster(200), buckets=BUCKETS)
        served = self._complete_bank(chunks)
        served_rows = collect_unit_results(served, chunks)

        # Two units of the NEXT census land. The curve keeps serving the old one.
        mid = served
        for chunk in chunks[:2]:
            mid = advance(
                mid, chunk.key, [_population_row(bucket_idx=chunk.index + 1, n=99)],
                owner=OWNER, lease_expires_at=0.0,
            )
        assert len(mid.committed_units) == 2, "the rebuild is genuinely under way"
        assert is_complete(mid, chunks), "the curve is still publishable"
        assert collect_unit_results(mid, chunks) == served_rows, (
            "a partial rebuild leaked into the published census"
        )

    def test_the_finished_rebuild_replaces_the_served_bank(self):
        chunks = plan_units(_roster(200), buckets=BUCKETS)
        served = self._complete_bank(chunks)
        before = collect_unit_results(served, chunks)

        nxt = served
        for chunk in chunks:
            nxt = advance(
                nxt, chunk.key, [_population_row(bucket_idx=chunk.index + 1, n=99)],
                owner=OWNER, lease_expires_at=0.0,
            )
        after = collect_unit_results(nxt, chunks)
        assert after != before, "a completed rebuild must actually take over"
        assert sum(r.n for r in after[0] if getattr(r, "bucket_idx", None) is not None) > sum(
            r.n for r in before[0] if getattr(r, "bucket_idx", None) is not None
        )

    def test_a_serving_bank_that_does_not_cover_the_plan_cannot_publish(self):
        chunks = plan_units(_roster(200), buckets=BUCKETS)
        served = self._complete_bank(chunks)
        wider = plan_units(_roster(200), buckets=BUCKETS * 2)
        assert not is_complete(served, wider), (
            "a census of a different partition is not a census of this one"
        )


class TestTheBankDatesItself:
    """#2007's acceptance criterion: the age of the ROWS, not of the serializer."""

    def _served(self):
        chunks = plan_units(_roster(120), buckets=BUCKETS)
        cursor = new_staged_cursor(
            population_version=VERSION, input_fingerprint=INPUT_FP,
            generation_fingerprint="gen", owner=OWNER, generation=1,
        )
        cursor, _ = retain_planned_units(cursor, chunks)
        for chunk in chunks:
            cursor = advance(
                cursor, chunk.key, [_population_row(bucket_idx=chunk.index + 1)],
                owner=OWNER, lease_expires_at=0.0,
            )
        return cursor, chunks

    def test_promotion_leaves_it_unstamped_and_the_persister_dates_it(self):
        cursor, _ = self._served()
        assert cursor.served_at == 0.0, "the pure module owns no clock"
        stamped = stamp_served_at(cursor, now=1_700_000_000.0)
        assert stamped.served_at == 1_700_000_000.0

    def test_re_persisting_can_never_make_an_old_census_look_new(self):
        """#2007's failure mode, arriving through its own fix. Refused."""
        cursor, _ = self._served()
        first = stamp_served_at(cursor, now=1_700_000_000.0)
        later = stamp_served_at(first, now=1_700_099_999.0)
        assert later.served_at == 1_700_000_000.0

    def test_an_empty_bank_is_not_dated(self):
        blank = new_staged_cursor(
            population_version=VERSION, input_fingerprint=INPUT_FP,
            generation_fingerprint="gen", owner=OWNER, generation=1,
        )
        assert stamp_served_at(blank, now=1_700_000_000.0).served_at == 0.0

    def test_served_drift_counts_the_served_bank_not_the_builder(self):
        cursor, chunks = self._served()
        moved = plan_units(
            _roster(120, extra=[(9_001, "polymarket", "e:77", True)]), buckets=BUCKETS
        )
        # A bank promoted by ``advance`` mid-beat carries no digest for the units
        # that beat banked, because ``advance`` is handed a key and never a
        # chunk. Here EVERY unit was banked that way, so the whole bank is
        # UNMEASURABLE for exactly one beat — and it reads 0 as UNKNOWN, which is
        # only safe to publish beside the uncheckable count.
        assert cursor.served_digests == {}
        assert served_drift(cursor, moved) == 0

        # The next beat's retention tops the baselines up, and from then on the
        # served bank's drift is a real measurement.
        nxt, _ = retain_planned_units(cursor, chunks)
        assert nxt.served_digests, "the gap must close on the following beat"
        assert served_drift(nxt, moved) == 1
        # The builder is empty, so it has no drift of its own to report — and
        # reporting the builder's number beside a served census is the confusion
        # this pair of counters exists to prevent.
        assert nxt.committed_units == ()
        assert nxt.roster_drift_units == 0

    def test_an_undigested_served_unit_reads_unknown_never_zero(self):
        """CAL-P069's find: six unmeasurable units published as ``drifted: 0``."""
        cursor, chunks = self._served()
        blind = replace(cursor, served_digests={})
        assert served_drift(blind, chunks) == 0
        # ...and the absence is still visible, which is what makes the 0 safe to
        # publish only alongside an uncheckable count.
        assert blind.served_digests == {}
        assert len(blind.served_units) == len(chunks)

    def test_the_top_up_never_overwrites_an_existing_baseline(self):
        cursor, chunks = self._served()
        # Give it real baselines first — the top-up's job is to fill gaps, and a
        # cursor with no baselines at all cannot show that it refuses to move one.
        based, _ = retain_planned_units(cursor, chunks)
        assert based.served_digests

        digests = {unit_key(c): "DIFFERENT" for c in chunks}
        topped = top_up_served_digests(based, digests)
        assert topped.served_digests == based.served_digests, (
            "re-baselining every beat makes drift read zero forever"
        )


class TestThePersistedShape:
    def test_the_serving_bank_survives_a_round_trip(self):
        chunks = plan_units(_roster(90), buckets=BUCKETS)
        cursor = new_staged_cursor(
            population_version=VERSION, input_fingerprint=INPUT_FP,
            generation_fingerprint="gen", owner=OWNER, generation=1,
        )
        cursor, _ = retain_planned_units(cursor, chunks)
        for chunk in chunks:
            cursor = advance(
                cursor, chunk.key, [_population_row(bucket_idx=chunk.index + 1)],
                owner=OWNER, lease_expires_at=0.0,
            )
        cursor = stamp_served_at(cursor, now=1_700_000_000.0)

        back, action, _reason = decode_staged_cursor_detailed(
            cursor.as_payload(),
            expected_population_version=VERSION,
            expected_input_fingerprint=INPUT_FP,
            expected_generation_fingerprint="gen",
            owner=OWNER,
            generation=2,
            now=0.0,
        )
        assert set(back.served_units) == set(cursor.served_units)
        assert back.served_at == 1_700_000_000.0
        assert back.served_digests == cursor.served_digests
        assert is_complete(back, chunks), "the census survives the process that built it"

    def test_a_pre_cal_p078_cursor_promotes_on_its_first_beat(self):
        """THE DEPLOY CASE — and why no schema bump is owed.

        Production's live cursor has 128 banked units, a fold behind them, and
        none of the serving fields. It must decode, promote, and publish on the
        FIRST beat: a bump would have invalidated it and taken ``/api/calibration``
        dark for the ~5 beats of a full rebuild, to fix a staleness bug.
        """
        chunks = plan_units(_roster(90), buckets=BUCKETS)
        cursor = new_staged_cursor(
            population_version=VERSION, input_fingerprint=INPUT_FP,
            generation_fingerprint="gen", owner=OWNER, generation=1,
        )
        cursor, _ = retain_planned_units(cursor, chunks)
        for chunk in chunks:
            cursor = advance(
                cursor, chunk.key, [_population_row(bucket_idx=chunk.index + 1)],
                owner=OWNER, lease_expires_at=0.0,
            )
        # Rewind it to the old shape: units in the BUILDING slot, no serving bank.
        legacy = cursor.as_payload()
        legacy["committed_units"] = list(cursor.served_units)
        legacy["accumulator"] = cursor.served_accumulator
        legacy["unit_digests"] = dict(cursor.served_digests)
        for gone in (
            "served_accumulator", "served_units", "served_digests", "served_at",
            "planned_units", "served_drift_units",
        ):
            legacy.pop(gone)

        back, action, _reason = decode_staged_cursor_detailed(
            legacy,
            expected_population_version=VERSION,
            expected_input_fingerprint=INPUT_FP,
            expected_generation_fingerprint="gen",
            owner=OWNER,
            generation=2,
            now=0.0,
        )
        assert back.served_units == (), "the old shape has no serving bank"
        assert len(back.committed_units) == len(chunks)

        promoted, dropped = retain_planned_units(back, chunks)
        assert dropped == ()
        assert set(promoted.served_units) == {c.key for c in chunks}
        assert is_complete(promoted, chunks), "publishable on the first beat, no dark window"

    def test_a_serving_unit_list_with_no_fold_behind_it_is_refused(self):
        """Units claimed with no mass behind them — the bookkeeping error the
        building bank refuses two checks earlier. No better one bank over."""
        chunks = plan_units(_roster(50), buckets=BUCKETS)
        cursor = new_staged_cursor(
            population_version=VERSION, input_fingerprint=INPUT_FP,
            generation_fingerprint="gen", owner=OWNER, generation=1,
        )
        payload = cursor.as_payload()
        payload["served_units"] = [unit_key(c) for c in chunks]
        payload["served_accumulator"] = None

        back, _action, _reason = decode_staged_cursor_detailed(
            payload,
            expected_population_version=VERSION,
            expected_input_fingerprint=INPUT_FP,
            expected_generation_fingerprint="gen",
            owner=OWNER, generation=2, now=0.0,
        )
        assert back.served_units == ()
        assert not is_complete(back, chunks)


# =============================================================================
# Ruling 102 — drive the REAL frozen loop
# =============================================================================


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeDB:
    """Answers the two statements ``_run_staged_futures`` issues, and no others."""

    def __init__(self, roster, *, unit_n=3):
        self.roster = roster
        self.unit_n = unit_n
        self.unit_reads = 0

    async def execute(self, statement, params=None):
        if params is None:
            return _FakeResult(self.roster)
        # The per-chunk population statement. One bucket row per unit, tagged
        # with the generation's payload size so a re-stage is VISIBLE in the
        # merged output rather than merely asserted about.
        self.unit_reads += 1
        return _FakeResult([_population_row(bucket_idx=1, n=self.unit_n, winners=1)])


class _FakeLedger:
    def __init__(self, window_ms):
        self.window_ms = window_ms
        self.stages: dict[str, int] = {}
        self.gauges: dict[str, int] = {}

    def record_stage(self, name, duration_ms=0):
        self.stages[name] = self.stages.get(name, 0) + int(duration_ms)

    def record_gauge(self, name, value):
        self.gauges[name] = int(value)

    def remaining_ms(self, *, elapsed_ms=0):
        return self.window_ms - elapsed_ms


class _FakeStage:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeRunner:
    """The PhaseRunner surface ``_run_staged_futures`` actually touches."""

    def __init__(self, *, window_ms, generation=1):
        self.ledger = _FakeLedger(window_ms)
        self.population_version = VERSION
        self.fingerprint = INPUT_FP
        self.owner = OWNER
        self.generation = generation
        self._elapsed = 0

    def stage(self, _name):
        # Each unit read costs a slice of the window, which is what makes the
        # per-beat bound real rather than simulated.
        self._elapsed += 100
        return _FakeStage()

    def elapsed_ms(self):
        return self._elapsed

    async def commit(self, _db):
        return None

    async def apply_statement_timeout(self, _db, _phase):
        return None

    # CAL-P081 (#2052): the loop's runner protocol grew a unit-scoped timeout and
    # a carried unit cost. A fake must implement the protocol its subject uses
    # (CAL-P076's banked lesson); ``None`` here means "no carried measurement",
    # which leaves every re-stage assertion in this file measuring what it did.
    def measured_unit_ms(self, _phase):
        return None

    async def apply_unit_statement_timeout(self, _db, _phase, *, unit_ms=None):
        return None


class TestTheFrozenLoopActuallyReStages:
    """RULING 102. The unedited coroutine, started, over stubs.

    Everything above tests decisions. This tests that the frozen caller, calling
    those decisions in the order it calls them, re-stages anything at all —
    which is the only question #2007 actually asks.
    """

    @pytest.fixture
    def wiring(self, monkeypatch):
        from app.tasks import calibration_main_build as mb
        from app.tasks import precompute_calibration as pc

        store: dict[str, object] = {"cursor": None}

        async def fake_load(**kwargs):
            from app.utils.calibration_phase_ledger import FRESH

            raw = store["cursor"]
            if raw is None:
                return (
                    new_staged_cursor(
                        population_version=kwargs["population_version"],
                        input_fingerprint=kwargs["input_fingerprint"],
                        generation_fingerprint=kwargs["generation_fingerprint"],
                        owner=kwargs["owner"],
                        generation=kwargs["generation"],
                    ),
                    FRESH,
                    "absent",
                )
            cursor, action, reason = decode_staged_cursor_detailed(
                raw,
                expected_population_version=kwargs["population_version"],
                expected_input_fingerprint=kwargs["input_fingerprint"],
                expected_generation_fingerprint=kwargs["generation_fingerprint"],
                owner=kwargs["owner"],
                generation=kwargs["generation"],
                now=0.0,
            )
            return cursor, action, reason

        saves = {"n": 0}

        async def fake_save(cursor, *, terminal):
            saves["n"] += 1
            # The real persister stamps the clock here. Keep that in the path so
            # the dating is exercised by the loop, not only by its own unit test.
            store["cursor"] = stamp_served_at(cursor, now=1_700_000_000.0).as_payload()
            return True

        monkeypatch.setattr(mb, "load_staged_cursor", fake_load)
        monkeypatch.setattr(mb, "save_staged_cursor", fake_save)
        monkeypatch.setattr(mb, "staged_lease", lambda: 0.0)
        monkeypatch.setattr(pc, "_futures_generation_sql", lambda: "SELECT 1")
        return pc, store, saves

    @staticmethod
    async def _beat(pc, *, roster, window_ms, unit_n=3, generation=1):
        db = _FakeDB(roster, unit_n=unit_n)
        runner = _FakeRunner(window_ms=window_ms, generation=generation)
        merged = await pc._run_staged_futures(db, runner, lambda frozen: "SELECT 2")
        return merged, runner, db

    @pytest.mark.asyncio
    async def test_a_bank_that_is_already_complete_keeps_re_staging(self, wiring):
        """THE BUG, and the whole point of the queue.

        Before CAL-P078 the second beat here banked ZERO units and republished
        the first beat's census forever. ``units_this_beat: 0``, every hour, over
        a moving population, under ``availability: fresh``.
        """
        pc, store, _saves = wiring
        roster = _roster(60)

        first, runner1, db1 = await self._beat(pc, roster=roster, window_ms=10_000_000)
        assert first is not None, "beat 1 must complete a census and publish it"
        assert db1.unit_reads > 0

        # Beat 2, same complete bank, nothing changed about the population.
        second, runner2, db2 = await self._beat(pc, roster=roster, window_ms=10_000_000)
        assert db2.unit_reads > 0, (
            "the frozen loop re-staged NOTHING — this is #2007 reproducing"
        )
        assert runner2.ledger.stages.get("staged:units_this_beat", 0) > 0
        assert second is not None, "and it must still publish while it rebuilds"

    @pytest.mark.asyncio
    async def test_the_curve_keeps_publishing_through_a_partial_rebuild(self, wiring):
        """A beat too small to finish a census must still serve the last one."""
        pc, store, _saves = wiring
        roster = _roster(60)

        first, _r, _d = await self._beat(pc, roster=roster, window_ms=10_000_000)
        assert first is not None

        # A window that admits only a couple of units before it closes.
        partial, runner, db = await self._beat(pc, roster=roster, window_ms=250)
        assert 0 < db.unit_reads < _plan_size(roster), "the beat must stop early, not finish"
        assert partial is not None, "a partial rebuild took the curve dark"

    @pytest.mark.asyncio
    async def test_a_finished_rebuild_takes_over_and_the_payload_changes(self, wiring):
        """The re-stage is not decorative: new rows reach the published census."""
        pc, store, _saves = wiring
        roster = _roster(60)

        first, _r1, _d1 = await self._beat(pc, roster=roster, window_ms=10_000_000)
        firstn = _bucket_mass(first)

        second, _r2, _d2 = await self._beat(
            pc, roster=roster, window_ms=10_000_000, unit_n=50
        )
        secondn = _bucket_mass(second)
        assert secondn > firstn, (
            "a completed rebuild did not reach the published payload — the bank "
            "is still frozen, just with two of them"
        )

    @pytest.mark.asyncio
    async def test_the_served_bank_carries_a_date_after_a_real_beat(self, wiring):
        pc, store, _saves = wiring
        await self._beat(pc, roster=_roster(60), window_ms=10_000_000)
        assert store["cursor"] is not None
        assert store["cursor"]["served_at"] == 1_700_000_000.0
        assert len(store["cursor"]["served_units"]) == _plan_size(_roster(60))

    @pytest.mark.asyncio
    async def test_a_full_multi_beat_cycle(self, wiring):
        """THE END-TO-END SHAPE, on a window too small to finish in one beat —
        which is production's shape (128 units, ~25 per beat).

        Traced through the real frozen loop with a window that admits ~12 units:

            beat 1  ran=12  published=False  served= 0  building=12
            beat 2  ran=12  published=False  served= 0  building=24
            beat 3  ran=12  published=False  served= 0  building=36
            beat 4  ran=10  published=True   served=46  building= 0   <- promotion
            beat 5  ran=12  published=True   served=46  building=12
            beat 6  ran=12  published=True   served=46  building=24

        Three properties, and the third is the one #2007 is about:

        * a cold start publishes NOTHING until a census is complete — partial is
          still not done;
        * the beat that completes one PUBLISHES it, not the beat after;
        * once serving, the curve keeps publishing through every subsequent
          partial rebuild. It never goes dark and it never serves a blend.
        """
        pc, store, _saves = wiring
        roster = _roster(60)
        plan = _plan_size(roster)
        seen = []
        for _ in range(6):
            db = _FakeDB(roster)
            runner = _FakeRunner(window_ms=1300)
            merged = await pc._run_staged_futures(db, runner, lambda frozen: "SELECT 2")
            cursor = store["cursor"]
            seen.append(
                {
                    "ran": db.unit_reads,
                    "published": merged is not None,
                    "served": len(cursor["served_units"]),
                    "building": len(cursor["committed_units"]),
                    "served_at": cursor["served_at"],
                }
            )

        assert all(b["ran"] > 0 for b in seen), "every beat must re-stage something"
        assert not seen[0]["published"], "a partial first census may not publish"

        first_publish = next(i for i, b in enumerate(seen) if b["published"])
        assert seen[first_publish]["served"] == plan, (
            "the beat that COMPLETES a census is the beat that publishes it"
        )
        assert seen[first_publish]["served_at"] > 0, "and it is dated on that beat"

        # From the promotion onward the curve never goes dark, however partial
        # the rebuild behind it gets.
        tail = seen[first_publish:]
        assert all(b["published"] for b in tail)
        assert all(b["served"] == plan for b in tail)
        assert any(0 < b["building"] < plan for b in tail), (
            "a rebuild must actually be in progress underneath a serving bank"
        )
        # The census ages until the NEXT promotion — it does not silently
        # re-date itself every beat, which is the bug this queue closes.
        assert len({b["served_at"] for b in tail}) == 1

    @pytest.mark.asyncio
    async def test_an_empty_population_still_publishes_and_does_not_promote(self, wiring):
        """An empty roster is a real answer, and it must not mint a dated bank."""
        pc, store, _saves = wiring
        merged, _runner, db = await self._beat(pc, roster=[], window_ms=10_000_000)
        assert merged == []
        assert db.unit_reads == 0


# =============================================================================
# The disclosure — the two readings the rolling re-stage invalidated
# =============================================================================


class TestTheDisclosureDescribesTheServedBank:
    """CAL-P078 breaks two of CAL-P076's inputs, and both fail toward comfort.

    1. The durable row's write time used to BE the instant the bank advanced,
       because a beat that banked nothing never rewrote it. Now every beat
       re-stages, so it advances hourly over a census that may be five beats
       old — a fresh timestamp back on a stale curve, which is #2007 verbatim.
    2. ``bank_advanced_this_beat`` used to be evidence the served census had
       moved. The BUILDER always advances now, so as a freeze verdict it would
       read "not frozen" forever.

    Left alone, this queue's fix would have re-manufactured the bug it closes.
    """

    @staticmethod
    def _stages(**over):
        base = {
            "staged:units_banked": 12,
            "staged:units_this_beat": 12,
            "staged:units_drifted": 0,
            "staged:units_drift_checkable": 128,
            "staged:units_drift_uncheckable": 0,
            "staged:served_units": 128,
            "staged:served_drifted": 115,
            "staged:served_drift_uncheckable": 0,
            "staged:served_at": 1_700_000_000,
        }
        base.update(over)
        return base

    def test_the_age_is_the_served_census_not_the_last_write(self):
        from datetime import datetime, timezone

        from app.utils.calibration_staged_disclosure import build_disclosure

        # The durable row was written SECONDS ago; the census is 6 hours old.
        just_now = datetime(2026, 8, 20, 6, 0, 0, tzinfo=timezone.utc)
        block = build_disclosure(
            ledger_stages=self._stages(),
            staged_generated_at=just_now,
            now=datetime.fromtimestamp(1_700_021_600, tz=timezone.utc),
        )
        assert block["measured"] is True
        assert block["staged_age_s"] == 21_600, "the ROWS are six hours old"
        assert block["units_banked"] == 128, "the served census, not the rebuild"
        assert block["units_drifted"] == 115

    def test_a_busy_rebuild_does_not_make_a_drifted_bank_read_honest(self):
        from datetime import datetime, timezone

        from app.utils.calibration_staged_disclosure import (
            availability_floor,
            build_disclosure,
        )

        block = build_disclosure(
            ledger_stages=self._stages(**{"staged:units_this_beat": 25}),
            staged_generated_at=datetime(2026, 8, 20, 6, 0, 0, tzinfo=timezone.utc),
            now=datetime.fromtimestamp(1_700_021_600, tz=timezone.utc),
        )
        assert block["frozen_over_drift"] is True, (
            "a busy builder is not evidence about the census being served"
        )
        assert availability_floor(block) == "stale"
        # The builder's progress is still published — beside the served figures,
        # under its own name, so a reader can see the rebuild is alive.
        assert block["rebuild_units_this_beat"] == 25
        assert block["rebuild_units_banked"] == 12
        assert block["rolling_restage"] is True

    def test_a_freshly_promoted_undrifted_bank_reads_fresh(self):
        from datetime import datetime, timezone

        from app.utils.calibration_staged_disclosure import (
            availability_floor,
            build_disclosure,
        )

        block = build_disclosure(
            ledger_stages=self._stages(**{"staged:served_drifted": 0}),
            staged_generated_at=datetime(2026, 8, 20, 6, 0, 0, tzinfo=timezone.utc),
            now=datetime.fromtimestamp(1_700_000_060, tz=timezone.utc),
        )
        assert block["frozen_over_drift"] is False
        assert availability_floor(block) is None, "no downgrade is owed"

    def test_an_undated_serving_bank_is_unmeasured_not_backfilled(self):
        """The tempting fallback is the durable write time. It is the publish
        clock wearing the census's name, and substituting it IS the bug."""
        from datetime import datetime, timezone

        from app.utils.calibration_staged_disclosure import (
            availability_floor,
            build_disclosure,
        )

        stages = self._stages()
        del stages["staged:served_at"]
        block = build_disclosure(
            ledger_stages=stages,
            staged_generated_at=datetime(2026, 8, 20, 6, 0, 0, tzinfo=timezone.utc),
        )
        assert block["measured"] is False
        assert block["reason"] == "served_at_absent"
        assert availability_floor(block) == "stale"

    def test_an_unmeasurable_served_unit_is_never_folded_into_a_zero(self):
        """CAL-P069's find, carried across to the serving bank."""
        from datetime import datetime, timezone

        from app.utils.calibration_staged_disclosure import build_disclosure

        block = build_disclosure(
            ledger_stages=self._stages(
                **{"staged:served_drifted": 0, "staged:served_drift_uncheckable": 6}
            ),
            staged_generated_at=datetime(2026, 8, 20, 6, 0, 0, tzinfo=timezone.utc),
            now=datetime.fromtimestamp(1_700_000_060, tz=timezone.utc),
        )
        assert block["units_drift_unknown"] == 6
        assert block["frozen_over_drift"] is True, (
            "zero drift only counts when every banked unit was checkable"
        )

    def test_a_pre_cal_p078_ledger_behaves_exactly_as_before(self):
        """No served gauges — a payload from before this deploy. Unchanged."""
        from datetime import datetime, timezone

        from app.utils.calibration_staged_disclosure import build_disclosure

        stages = {
            "staged:units_banked": 128,
            "staged:units_this_beat": 0,
            "staged:units_drifted": 115,
            "staged:units_drift_checkable": 127,
            "staged:units_drift_uncheckable": 1,
        }
        written = datetime(2026, 8, 19, 17, 16, 31, tzinfo=timezone.utc)
        block = build_disclosure(
            ledger_stages=stages,
            staged_generated_at=written,
            now=datetime(2026, 8, 19, 23, 16, 31, tzinfo=timezone.utc),
        )
        assert block["measured"] is True
        assert block["staged_age_s"] == 21_600
        assert block["units_banked"] == 128
        assert block["frozen_over_drift"] is True
        assert "rolling_restage" not in block
