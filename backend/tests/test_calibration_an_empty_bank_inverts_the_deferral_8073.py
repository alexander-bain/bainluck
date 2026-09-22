"""CAL-P1338 (#8073): with nothing banked, deferring a struck slot closes the
only two exits the build has, and production sat in the closed loop.

THE SPECIMEN, read off ``/api/admin/calibration-beat-gauges`` on 2026-09-22.
After the 12:36Z partition reset the accuracy build banked NOTHING for six
consecutive hourly beats::

    12:36 invalidate population_version_malformed  planned 128  banked 0
    13:38 invalidate population_version_malformed  planned 128  banked 0
    14:38 invalidate population_version_malformed  planned 128  banked 0
    15:37 fresh      nothing_banked                planned 128  banked 0
    16:37 fresh      nothing_banked                planned 128  banked 0
    17:37 fresh      nothing_banked                planned 128  banked 0
    18:37 fresh      nothing_banked                planned 128  banked 0

and the per-slot gauges say why, one pair of slots per beat, each at exactly ONE
strike, walking the plan in index order::

    15:37  staged:unit_cancels:128:2 = 1   staged:unit_cancels:128:3 = 1
    16:37  staged:unit_cancels:128:4 = 1   staged:unit_cancels:128:5 = 1
    17:37  staged:unit_cancels:128:6 = 1   staged:unit_cancels:128:7 = 1
    18:37  staged:unit_cancels:128:8 = 1   staged:unit_cancels:128:9 = 1
    every beat: staged:unit_cost_reason:no_unit_completed = 1

**THE CLOSED LOOP.** A unit is cut only by ``STAGED_UNIT_SPLIT_AFTER``, which
needs a reproduction on the SAME slot, or by ``cancellation_is_conclusive``,
which cuts on the first strike. Both were shut, at the same time, by the same
fact:

* ``attempt_order`` sorted ascending on recorded cancellations, so a struck slot
  went to the BACK and no slot could earn a second strike until all 128 held a
  first — 64 hourly beats at two cancellations a beat, and only then the first
  cut.
* ``cancellation_is_conclusive`` returns False when no unit has ever completed
  (ruling 075: nothing to outrun). Nothing completes at this granularity, so the
  first-strike exit declines precisely in the regime it exists for.

Refinement needed a completion and a completion needed refinement. That is not a
slow recovery; nothing in the loop ends it, and ``/api/calibration`` served a
bank 173 rebuilds stale while it ran.

**WHAT THIS FILE PINS**, in the two directions that can each fail alone:

* ``TestTheEmptyBankLeadsWithTheStruckSlot`` — nothing banked, so a slot holding
  a strike is attempted FIRST and takes its second on the next beat. Mutating
  the rank back to ascending restores the production order, which is the
  strawman: the assertion is on which slot LEADS, not merely that the order
  changed.
* ``TestAnUnrefinableSlotIsNotHammered`` — a slot at ``STAGED_UNIT_SPLIT_AFTER``
  has had its chance (it refined, or ``refine_unit`` refused it as
  ``SPLIT_ATOMIC``/``SPLIT_TOO_DEEP``) and goes to the BACK, behind the untried
  slots. Without this the inversion trades a 64-beat wait for a permanent one.
* ``TestTheHealthyRegimeIsUnchanged`` — one banked unit restores ascending order
  exactly, so CAL-P1301's own livelock fix (two slow slots at the head of a plan
  banking 31 of 128) is untouched. This is the guard that makes the blast radius
  a claim rather than a hope.

Every case asserts a full attempted ORDER, never a set and never a count: the
defect was an ordering and a test that checked membership would have passed
throughout the six frozen beats.

**And section 2 drives the real beat loop, because none of the above publishes
anything.** ``attempt_order`` reordering is the mechanism; "the accuracy page
starts updating again" is the ship, and only a BUILD can pay it. With all three
of this loop's refinement candidates live — the composition the heavy worker
runs — a frozen 16-slot build publishes on beat **25** against **29** deferred,
and a 32-slot build on **46** against **59**. The cut moves from ``N/2 + 1`` to
beat 3 at every size measured.

That direction is worth dwelling on, because the sibling isolation rig scores
this same change as publishing 1-4 beats LATER and that number nearly kept the
ship unoffered. The sibling holds the packing candidate OFF; with it live beside
the earlier refinement the two compound rather than compete. **A regression
measured in a rig that is missing one of production's three mechanisms is not
production's regression** — and the only way to know which it was, was to run
the composed loop.
"""

from __future__ import annotations

import pytest

from app.utils import calibration_staged_futures as sf
from app.utils.calibration_phase_ledger import (
    STAGED_UNIT_MAX_CANCELLATIONS,
    STAGED_UNIT_SPLIT_AFTER,
)

# Section 2 only. Everything above it measures ``attempt_order`` as a function,
# which is where the mechanism lives but NOT where the ship's claim lives: "the
# accuracy page starts updating again" is a statement about a BUILD publishing,
# and a function cannot publish. Importing ``staged_beat_loop`` registers the
# sibling's rig as a fixture here. Its own ``drive`` is deliberately NOT
# imported — that one holds this mechanism off (see its docstring), and section
# 2 needs all three candidates live, because the loop production runs has all
# three in it.
from tests.test_calibration_oversized_slot_is_cut_on_its_proof_6599 import (  # noqa: E501,F401
    staged_beat_loop,
)


def chunk(index: int, *, buckets: int = 128) -> sf.UnitChunk:
    """One planned slot, with enough virtual questions to be refinable.

    Two ``vm_ids`` is the minimum ``refine_unit`` will cut (``SPLIT_ATOMIC``
    below that), so this is the ordinary case the production slots are in.
    """
    return sf.UnitChunk(
        index=index,
        vm_ids=(f"m:{index}a", f"m:{index}b"),
        market_ids=(index * 10, index * 10 + 1),
        buckets=buckets,
    )


def cursor_with(
    *, cancels: dict[str, int], committed: tuple[str, ...] = ()
) -> sf.StagedFuturesCursor:
    base = sf.new_staged_cursor(
        population_version="q271",
        input_fingerprint="if",
        generation_fingerprint="gf",
        owner="test",
        generation=1,
    )
    return sf.replace(
        base, unit_cancels=dict(cancels), committed_units=tuple(committed)
    )


def order(chunks, cursor) -> list[str]:
    return [sf.slot_ref(c) for c in sf.attempt_order(chunks, cursor)]


class TestTheEmptyBankLeadsWithTheStruckSlot:
    """Nothing banked: the slot one cut away is attempted first, not last."""

    def test_the_production_specimen_leads_with_a_struck_slot(self):
        # The 18:37Z state: slots 0-9 hold one strike each, 118 hold none.
        chunks = [chunk(i) for i in range(12)]
        cursor = cursor_with(cancels={f"128:{i}": 1 for i in range(10)})

        attempted = order(chunks, cursor)

        # The ten struck slots lead, in plan order, so the beat's two-cancellation
        # budget lands a SECOND strike on 128:0 and 128:1 — a cut on the next
        # beat rather than the sixty-fourth.
        assert attempted[:10] == [f"128:{i}" for i in range(10)]
        assert attempted[10:] == ["128:10", "128:11"]

    def test_the_untouched_ascending_order_is_the_strawman(self):
        """The pre-fix rule on the same specimen, spelled out.

        Ascending on cancellations puts the two UNTRIED slots first, so the
        budget is spent on fresh strikes and 128:0 is never reproduced. Pinned
        as an explicit expectation so the fix cannot be reverted silently: this
        list is what the six frozen beats actually did.
        """
        chunks = [chunk(i) for i in range(12)]
        cursor = cursor_with(cancels={f"128:{i}": 1 for i in range(10)})

        stalled = sorted(
            chunks, key=lambda c: (int(cursor.unit_cancels.get(sf.slot_ref(c), 0)),
                                   c.buckets, c.index)
        )
        assert [sf.slot_ref(c) for c in stalled][:2] == ["128:10", "128:11"]
        assert order(chunks, cursor)[:2] == ["128:0", "128:1"]

    def test_a_slot_at_one_strike_outranks_every_untried_slot(self):
        """Even when the struck slot is last in plan order."""
        chunks = [chunk(i) for i in range(6)]
        cursor = cursor_with(cancels={"128:5": 1, "128:4": 1, "128:3": 1})

        assert order(chunks, cursor)[:3] == ["128:3", "128:4", "128:5"]

    def test_no_slot_is_dropped_by_the_inversion(self):
        """The deferral defers; it has never skipped, and neither does this."""
        chunks = [chunk(i) for i in range(20)]
        cursor = cursor_with(
            cancels={"128:3": 1, "128:5": 1, "128:9": 1,
                     "128:17": STAGED_UNIT_SPLIT_AFTER}
        )

        attempted = order(chunks, cursor)

        assert len(attempted) == 20
        assert set(attempted) == {f"128:{i}" for i in range(20)}


class TestAnUnrefinableSlotIsNotHammered:
    """A slot that has had its cut goes to the back, or the wait is permanent."""

    def test_a_slot_at_the_split_threshold_sorts_behind_untried_slots(self):
        chunks = [chunk(i) for i in range(6)]
        cursor = cursor_with(
            cancels={"128:0": STAGED_UNIT_SPLIT_AFTER, "128:1": 1, "128:2": 1}
        )

        attempted = order(chunks, cursor)

        # struck (1,2) lead, untried (3,4,5) follow, the spent slot 0 is last.
        assert attempted == ["128:1", "128:2", "128:3", "128:4", "128:5", "128:0"]

    def test_an_atomic_slot_refused_by_refine_unit_stops_leading(self):
        """The real refusal, driven through ``refine_unit``, not asserted about.

        A single-``vm_id`` slot cannot be cut. If the inversion kept promoting it
        the build would spend every beat's budget on the one slot that can never
        progress — the same zero as before, reached faster.
        """
        atomic = sf.UnitChunk(
            index=0, vm_ids=("m:only",), market_ids=(1,), buckets=128
        )
        others = [chunk(i) for i in range(1, 5)]
        cursor = cursor_with(cancels={"128:0": 1, "128:1": 1, "128:2": 1})

        # It leads while it is still worth a reproduction...
        assert order([atomic, *others], cursor)[0] == "128:0"

        # ...and the reproduction refuses, which is what banks the second strike.
        after, outcome = sf.refine_unit(cursor, atomic, factor=4)
        assert outcome == sf.SPLIT_ATOMIC
        struck = sf.replace(
            after, unit_cancels={**after.unit_cancels, "128:0": STAGED_UNIT_SPLIT_AFTER}
        )

        assert order([atomic, *others], struck)[-1] == "128:0"

    def test_a_refined_slots_children_are_untried_and_lead_nothing(self):
        """Children carry no strikes, so they sort as ordinary untried work."""
        cursor = cursor_with(
            cancels={"128:0": STAGED_UNIT_SPLIT_AFTER, "128:1": 1, "128:2": 1},
            committed=(),
        )
        children = [chunk(0, buckets=512), chunk(128, buckets=512)]
        coarse = [chunk(1), chunk(2), chunk(3)]

        attempted = order([*children, *coarse], cursor)

        # The refined parent 128:0 is no longer planned at all — plan_units
        # replaced it with these children. Struck coarse slots lead (one cut
        # away), then the FINEST untried work: the children, the only units
        # small enough to have a new chance of completing.
        assert attempted == ["128:1", "128:2", "512:0", "512:128", "128:3"]


class TestTheHealthyRegimeIsUnchanged:
    """One banked unit restores CAL-P1301's order exactly."""

    def test_a_single_banked_unit_restores_the_ascending_deferral(self):
        chunks = [chunk(i) for i in range(6)]
        cancels = {"128:0": 1, "128:1": 1}

        cancels = {**cancels, "128:2": 1}
        empty = cursor_with(cancels=cancels)
        banked = cursor_with(cancels=cancels, committed=("anything",))

        assert order(chunks, empty)[:3] == ["128:0", "128:1", "128:2"]
        # The CAL-P1301 shape: struck slots last, healthy work first.
        assert order(chunks, banked) == [
            "128:3", "128:4", "128:5", "128:0", "128:1", "128:2",
        ]

    def test_the_31_of_128_livelock_keeps_its_fix(self):
        """CAL-P1301's own specimen: two stuck heads, 31 banked, 95 starving.

        The generation has progressed, so the empty-bank branch must not touch
        it — the stuck heads still go last and the tail is still reached.
        """
        chunks = [chunk(i) for i in range(8)]
        cursor = cursor_with(
            cancels={"128:0": 1, "128:1": 1},
            committed=tuple(f"unit-{i}" for i in range(31)),
        )

        attempted = order(chunks, cursor)

        assert attempted[-2:] == ["128:0", "128:1"]
        assert attempted[0] == "128:2"

    @pytest.mark.parametrize("committed", [(), ("one",)])
    def test_a_plan_with_no_cancellations_is_plan_order_either_way(self, committed):
        """The clause every existing beat, test and cursor takes."""
        chunks = [chunk(i) for i in range(5)]
        cursor = cursor_with(cancels={}, committed=committed)

        assert order(chunks, cursor) == [f"128:{i}" for i in range(5)]

    def test_a_missing_cursor_is_plan_order(self):
        chunks = [chunk(i) for i in range(4)]

        assert order(chunks, None) == [f"128:{i}" for i in range(4)]


class TestTheSecondClauseBoundary:
    """``> STAGED_UNIT_MAX_CANCELLATIONS``, asserted AT the boundary.

    The scenario tests above show the young build keeps its deferral, but a
    scenario cannot say where the line is, and this clause is the whole reason
    the inversion does not reintroduce CAL-P1301's livelock. One beat can strike
    at most ``STAGED_UNIT_MAX_CANCELLATIONS`` slots, so that many struck slots is
    consistent with a SINGLE bad beat and must not trip the inversion; one more
    means two beats tried different slots and neither completed, which is a
    statement about the partition.

    Both sides are asserted off the constant rather than off a literal, so that
    raising the cancellation budget moves this test with it instead of silently
    shifting the regime boundary out from under it. Mutating ``>`` to ``>=``
    fails the first case alone, which is the point of testing the pair.
    """

    def test_exactly_one_beats_worth_of_strikes_keeps_the_deferral(self):
        n = STAGED_UNIT_MAX_CANCELLATIONS
        chunks = [chunk(i) for i in range(n + 3)]
        cursor = cursor_with(cancels={f"128:{i}": 1 for i in range(n)})

        assert not sf.bank_is_frozen(cursor, cursor.unit_cancels)
        # Ascending: the untried slots lead, exactly as CAL-P1301 wrote it.
        assert order(chunks, cursor)[:3] == [
            f"128:{i}" for i in (n, n + 1, n + 2)
        ]

    def test_one_more_than_a_beats_worth_inverts(self):
        n = STAGED_UNIT_MAX_CANCELLATIONS + 1
        chunks = [chunk(i) for i in range(n + 3)]
        cursor = cursor_with(cancels={f"128:{i}": 1 for i in range(n)})

        assert sf.bank_is_frozen(cursor, cursor.unit_cancels)
        assert order(chunks, cursor)[:n] == [f"128:{i}" for i in range(n)]

    def test_a_banked_unit_beats_the_clause_however_many_are_struck(self):
        """The first clause is not redundant with the second.

        Fifty struck slots is far past the boundary, but one banked unit means
        the generation IS progressing and the deferral is the right rule again.
        Without this, the pair above would pass with the bank check deleted.
        """
        n = STAGED_UNIT_MAX_CANCELLATIONS + 48
        chunks = [chunk(i) for i in range(n + 2)]
        cursor = cursor_with(
            cancels={f"128:{i}": 1 for i in range(n)}, committed=("one",)
        )

        assert not sf.bank_is_frozen(cursor, cursor.unit_cancels)
        assert order(chunks, cursor)[:2] == [f"128:{n}", f"128:{n + 1}"]


# =============================================================================
# 2. THE COMPOSED LOOP — the build production runs, in the regime it froze in
# =============================================================================


class TestTheFrozenBuildRecoversInTheComposedLoop:
    """The ship's claim, measured on a BUILD rather than on ``attempt_order``.

    Section 1 proves the function reorders. That is not the same statement as
    "the accuracy page starts updating again", and the gap between them is where
    a ranking fix normally dies — so this section drives the real beat loop with
    **all three refinement candidates live**, which is the loop the heavy worker
    runs, and reads the beat a build PUBLISHES on.

    **Reproducing production's regime needs the ring erased, and that is not a
    detail.** A wholly oversized plan on its own does not freeze: with a legible
    ring ``cancellation_is_conclusive`` cuts on the FIRST strike and the build
    recovers on beat 1 whatever ``attempt_order`` does — measured, both arms
    identical. The freeze needs the other half of ruling 075, which is what
    production actually had after the 12:36Z partition reset: nothing completed,
    so nothing in the ring to outrun, so the first-strike exit declines. Only
    then are both exits shut at once, and only then is the wait closed rather
    than merely long. ``withdrawn=True, ring_readable=False`` is that state, and
    it is the same configuration CERT-3051 read fourteen hours of production in.

    **The headline is that publish gets SOONER, and this had to be measured
    rather than argued.** The sibling's isolation rig — which holds the packing
    candidate off — scores this change as publishing 1-4 beats LATER, and that
    number was nearly the reason this ship was not offered. It is an artifact of
    measuring a loop production does not run: with the packing cut live beside
    it, the earlier refinement compounds instead of competing, and the build
    publishes 4 beats sooner at 16 slots and 13 sooner at 32. A cost measured in
    a rig missing one of production's three mechanisms is not production's cost.

    **Read the ship on 128, not on 16.** Those two sizes are cheap, not
    representative, and quoting them was how an earlier revision of this file
    came to assert that 128 was hopeless — a guess about monotonicity that the
    measurement below refutes. At production's own partition the inversion takes
    publish from beat **230 to beat 167**, which is ~2.6 days of staleness off
    the accuracy page. The 4-and-13 figures are the same effect seen through a
    smaller plan; 63 is the one a reader should carry.

    **Every number here is beats-to-publish in THIS rig, which is a relative
    measure and not a production ETA.** The rig's population scales with the
    plan (``_roster(buckets * VMS_PER_SLOT)``, every oversized slot a flat
    ``OVERSIZED_SLOT_MS``), so a 128-slot run carries eight times the WORK of a
    16-slot one rather than the same work cut finer. That is the right shape for
    "N slots, each too big for the window", and it is what makes both-arms
    comparisons at a fixed size sound — but it means no row here answers "how
    many hours until production publishes". A claim of that kind needs a rig
    that holds the corpus fixed while the granularity varies, which this one
    cannot express.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "buckets, deferred_cut, deferred_publish, inverted_publish",
        [(16, 9, 29, 25), (32, 17, 59, 46)],
    )
    async def test_the_build_publishes_sooner_not_later(
        self,
        staged_beat_loop,
        buckets,
        deferred_cut,
        deferred_publish,
        inverted_publish,
    ):
        """Both arms, same population, same rig — only the predicate differs."""
        deferred = await staged_beat_loop(
            buckets=buckets,
            oversized_slots=buckets,
            max_beats=80,
            withdrawn=True,
            ring_readable=False,
            empty_bank_inversion=False,
        )
        inverted = await staged_beat_loop(
            buckets=buckets,
            oversized_slots=buckets,
            max_beats=80,
            withdrawn=True,
            ring_readable=False,
            empty_bank_inversion=True,
        )

        assert deferred.first_split_beat == deferred_cut, (
            f"{buckets} slots: the BEFORE arm must still show the N/2+1 wait "
            f"({deferred_cut}); got {deferred.first_split_beat}. If this moves, "
            "the two arms are no longer a comparison"
        )
        assert inverted.first_split_beat == 3, (
            f"{buckets} slots: the cut must land on beat 3 regardless of N; got "
            f"{inverted.first_split_beat}"
        )

        assert (deferred.completed_at, inverted.completed_at) == (
            deferred_publish,
            inverted_publish,
        ), (
            f"{buckets} slots: the build must PUBLISH, and sooner — expected "
            f"{deferred_publish} then {inverted_publish}, got "
            f"{deferred.completed_at} then {inverted.completed_at}"
        )
        assert inverted.completed_at < deferred.completed_at, (
            "the direction is the claim: an earlier refinement must not buy the "
            "cut at the price of the publish"
        )

    @pytest.mark.asyncio
    async def test_at_productions_own_128_slots_the_build_publishes_63_sooner(
        self, staged_beat_loop
    ):
        """The claim at the ONE partition size production actually runs.

        Sections above stop at 32 because they are cheap. That left the ship's
        headline resting on sizes nobody runs, and an earlier revision of this
        file went further and asserted the opposite of what is true here — it
        read the 64-slot stall below, assumed beats-to-publish rises with the
        plan, and wrote that 128 was "above even this" and hopeless. Measured,
        it is not: **128 publishes in both arms**, and the inversion takes it
        from beat 230 to beat 167.

        Sixty-three hourly beats is ~2.6 days of staleness off the accuracy
        page, at the size the ring showed after the 12:36Z partition reset. That
        is the number this ship should be read on, and it is the reason the
        monotonicity guess had to be replaced with a measurement rather than
        argued about: the behaviour is NOT monotone in the plan size (see the
        stall below, which sits at 64 and is gone again by 66).

        The floor makes the result readable. A wholly oversized plan is
        ``buckets`` slots of ``OVERSIZED_SLOT_MS`` against a window of
        ``WINDOW_MS`` per beat, so no cutting strategy of any kind can publish
        128 slots before ``ceil(128 * 1_400_000 / 1_350_000)`` = **133 beats**.
        167 is 1.25x that floor; 230 is 1.73x. The inversion is not buying a
        constant, it is buying back most of the distance to the arithmetic
        limit — and a reader who finds 167 and calls it slow should compare it
        against 133, not against zero.
        """
        deferred = await staged_beat_loop(
            buckets=128,
            oversized_slots=128,
            max_beats=260,
            withdrawn=True,
            ring_readable=False,
            empty_bank_inversion=False,
        )
        inverted = await staged_beat_loop(
            buckets=128,
            oversized_slots=128,
            max_beats=260,
            withdrawn=True,
            ring_readable=False,
            empty_bank_inversion=True,
        )

        assert (deferred.completed_at, inverted.completed_at) == (230, 167), (
            "at production's 128 slots BOTH arms publish and the inversion is "
            f"63 beats sooner — expected 230 then 167, got "
            f"{deferred.completed_at} then {inverted.completed_at}. If the "
            "first of these becomes None the plan stopped recovering at all; "
            "that is a different defect from this one moving"
        )
        assert (deferred.first_split_beat, inverted.first_split_beat) == (65, 3), (
            "and the first cut is what moves it: beat 65 is 128/2+1, beat 3 is "
            f"not a function of 128 at all; got {deferred.first_split_beat} "
            f"then {inverted.first_split_beat}"
        )
        assert inverted.completed_at < deferred.completed_at, (
            "the direction is the claim at the only size production runs"
        )

    @pytest.mark.asyncio
    async def test_the_64_slot_stall_is_in_BOTH_arms_so_it_is_not_this_ships(
        self, staged_beat_loop
    ):
        """The honest gap — and the control proving this ship did not open it.

        At 64 wholly oversized slots neither arm reaches a published census,
        here inside 200 beats (3x its own 67-beat floor) and separately measured
        to 1500. **Both arms**, which is the whole point of asserting it: the
        stall is pre-existing, the deferral has it too, and this change neither
        causes it nor rescues it. Without this control a later reader finding a
        frozen 64-slot build would have CAL-P1338 as the obvious suspect.

        It is also not "large plans are hard" — 56, 60, 62, 66, 80, 96, 112, 128
        and 256 all publish at ~1.25x their floor with the inversion live. 64,
        68 and 72 do not, in either arm. The measured mechanism is a SECOND
        closed loop one level up from the one this ship opens: the packing sweep
        only runs on a slot DECLINED for packing, and reaches plan scope only
        when the reference came from a unit that beat actually ran. At 64 a
        single unit banks on beat 5, the sweep never runs again
        (``staged:unit_packing_scope`` absent on every later beat),
        ``cancellation_is_conclusive`` has no completion to outrun, and the
        refinement map freezes at five entries for 400+ beats. Two completions
        are needed to widen the sweep and the regime produces one.

        That is #8074 and it wants its own discriminator; it is recorded here
        because the specimen is in hand, not because this ship addresses it.
        """
        deferred = await staged_beat_loop(
            buckets=64,
            oversized_slots=64,
            max_beats=200,
            withdrawn=True,
            ring_readable=False,
            empty_bank_inversion=False,
        )
        inverted = await staged_beat_loop(
            buckets=64,
            oversized_slots=64,
            max_beats=200,
            withdrawn=True,
            ring_readable=False,
            empty_bank_inversion=True,
        )

        assert deferred.completed_at is None and inverted.completed_at is None, (
            "the 64-slot stall must be present in BOTH arms — if the deferral "
            "arm starts publishing here this control has stopped being a "
            "control and the stall would read as this ship's regression; got "
            f"{deferred.completed_at} then {inverted.completed_at}"
        )
        assert (deferred.first_split_beat, inverted.first_split_beat) == (33, 3), (
            "and the wait is still what moves, even where the build does not "
            "go on to publish: beat 33 is 64/2+1, beat 3 is not a function of "
            f"64 at all; got {deferred.first_split_beat} then "
            f"{inverted.first_split_beat}"
        )

    @pytest.mark.asyncio
    async def test_a_legible_ring_freezes_nothing_so_the_arms_agree(
        self, staged_beat_loop
    ):
        """The control that makes the three tests above readable.

        Same wholly oversized plan, ring READABLE. ``cancellation_is_conclusive``
        now has a completion to outrun, cuts on the first strike, and the two
        arms reach the cut on the same beat — so the sections above are measuring
        the closed loop specifically, not "the inversion is faster at everything".
        Without this, a reader could not tell those apart.
        """
        deferred = await staged_beat_loop(
            buckets=16,
            oversized_slots=16,
            max_beats=60,
            empty_bank_inversion=False,
        )
        inverted = await staged_beat_loop(
            buckets=16,
            oversized_slots=16,
            max_beats=60,
            empty_bank_inversion=True,
        )

        assert deferred.first_split_beat == inverted.first_split_beat == 1, (
            "with the ring legible the first-strike exit is open and BOTH arms "
            "cut on beat 1 — the deferral was never the binding constraint here"
        )
        assert inverted.completed_at <= deferred.completed_at, (
            "and the inversion must not make the unfrozen case worse; got "
            f"{inverted.completed_at} against {deferred.completed_at}"
        )
