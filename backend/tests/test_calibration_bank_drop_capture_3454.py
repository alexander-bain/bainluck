"""CAL-P1030 (#3454) — the bank wipe and the stop reason stop being invisible.

PILLAR: TRUTH. Rides the queued ship "the accuracy page's numbers start
refreshing again" (#1597, #3437).

What was wrong
--------------
The rebuild's most destructive event was the one event its telemetry could not
show. ``retain_planned_units``' CAL-P034 FAIL-CLOSED arm discards **every**
banked unit — building bank and serving bank both, *"Everything goes, and the
walk restarts"* — when any one banked unit is not in the current plan. Its only
signal is ``staged:units_dropped``, and ``calibration_beat_gauge_sampler``
captured neither that key nor any of the seven ``staged:*_stop:*`` reasons the
producer writes when a beat gives up early.

Measured 2026-09-06 over all 168 banked observations from
``GET /api/admin/calibration-beat-gauges?limit=16&full=true``: the substring
``drop`` does not occur once, and no ``*_stop:*`` key occurs once. Live
generation ``c1d6afbc16`` went 6 banked units → 0 between 03:16Z and 04:16Z with
every ``staged:cursor_reason:*`` at ``0`` — no recorded cause — and the one path
that produces exactly that shape was unobservable by construction.

The three classes of test here
------------------------------
1. **Capture.** A ledger carrying a drop and a stop reason surfaces both.
2. **Gotcha #53.** A drop of zero is distinguishable from a drop never written.
   The producer writes the key only inside ``if dropped:``, so absence is
   ambiguous on its own; the disambiguator is the cursor action, written
   unconditionally three lines above the call that can drop.
3. **Drift against the frozen writer.** ``precompute_calibration.py`` is
   D45/ruling-009 frozen, so the stop-key shape cannot be imported. These read
   its SOURCE and fail if the emitted literals move — CAL-P993's rule paid for
   differently, the same way ``test_calibration_cursor_decision_capture_1002.py``
   pays for ``CURSOR_PREFIX``.
4. **The capture-version gate (CERT-2051).** A capture rule changes what ABSENCE
   means, and this ring outlives the change.
5. **The real endpoint**, over one ring holding all three row classes at once.

What CERT-2051 blocked, and what classes 4 and 5 exist to stop coming back
---------------------------------------------------------------------------
The first version of this change derived the two new fields from ``r["gauges"]``
whenever the row did not carry them — which is exactly the 168 rows already
banked, and exactly where the derivation is unsound. Those rows' gauge maps had
the drop and stop keys discarded **at capture time**, while the cursor key
``bank_drop`` disambiguates against HAS been captured since CAL-P1002. So the
known 6-banked-units → 0 wipe row was served as ``units_dropped: 0``,
``units_dropped_measured: true``, ``stop_reasons: []``: a confident, wrong,
*measured* zero on the TRUTH surface added to end exactly that collapse.

The fix is that a row now says what its sampler could retain
(``gauge_capture_version``), one reader gates on it (``row_stop_and_drop``), and
a row below the floor answers ``null`` / ``false`` on every one of the fields.
``null`` and ``[]`` do not share a value domain here: ``[]`` is a measurement
("recorded no stop reason") and a legacy row never made it.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from app.tasks.calibration_beat_gauge_sampler import (
    DROP_AND_STOP_CAPTURE_VERSION,
    GAUGE_CAPTURE_VERSION,
    HISTORY_IDENTITY,
    HISTORY_SCHEMA,
    OPERATIONAL_GAUGES,
    STAGED_PREFIX,
    STOP_REASON_INFIX,
    UNVERSIONED_CAPTURE,
    bank_drop,
    build_observation,
    capture_version,
    is_stop_key,
    row_stop_and_drop,
    select_gauges,
    stop_reasons,
)

# Every stop stage the producer writes today, read once here and pinned against
# the source below so this list cannot quietly go stale.
_WINDOW_STOPS = (
    "staged:window_stop:deadline",
    "staged:window_stop:unit_too_large",
    "staged:window_stop:units_cancelling",
)
_REBUILD_STOPS = (
    "staged:rebuild_stop:interrupted",
    "staged:rebuild_stop:no_window_after_publish",
    "staged:rebuild_stop:overlap_lock",
    "staged:rebuild_stop:error",
)


# ---------------------------------------------------------------------------
# 1. capture
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("key", _WINDOW_STOPS + _REBUILD_STOPS)
def test_every_stop_reason_the_producer_writes_is_captured(key):
    """The regression in one line: none of these survived ``select_gauges``."""
    captured, _ = select_gauges({key: 0, "read:futures_generation": 226604})
    assert key in captured, f"{key} was dropped by the sampler"
    assert "read:futures_generation" not in captured


def test_the_two_stop_stems_are_both_reached_by_one_rule():
    """``window_stop`` and ``rebuild_stop`` share no prefix but ``staged:``.

    A prefix tuple would need one entry per stem and would silently miss the
    third — which is the omission this file has now recorded four times. The
    infix is what the producer's naming convention actually guarantees.
    """
    stages = {"staged:window_stop:deadline": 0, "staged:rebuild_stop:interrupted": 0}
    captured, _ = select_gauges(stages)
    assert set(captured) == set(stages)
    assert stop_reasons(captured) == ["rebuild_stop:interrupted", "window_stop:deadline"]


def test_a_stem_this_repo_has_never_written_is_still_captured():
    """The rule has to survive the NEXT stem, not just today's two."""
    captured, _ = select_gauges({"staged:publish_stop:something_new": 0})
    assert "staged:publish_stop:something_new" in captured
    assert stop_reasons(captured) == ["publish_stop:something_new"]


def test_units_dropped_is_captured():
    captured, _ = select_gauges({"staged:units_dropped": 6})
    assert captured["staged:units_dropped"] == 6
    assert "staged:units_dropped" in OPERATIONAL_GAUGES


def test_the_infix_is_namespaced_so_it_cannot_sweep_a_foreign_key():
    """``_stop:`` alone would match anything. Only ``staged:`` keys qualify."""
    captured, _ = select_gauges({"diagnostics:worker_stop:sigterm": 0})
    assert captured == {}
    assert is_stop_key("diagnostics:worker_stop:sigterm") is False
    assert is_stop_key("staged:window_stop:deadline") is True
    # The infix must be BEYOND the namespace, not inside it.
    assert is_stop_key("staged:units_done") is False
    assert is_stop_key(None) is False


def test_the_live_wipe_beat_becomes_attributable():
    """The 2026-09-06 03:16Z→04:16Z shape, replayed.

    6 banked units → 0 with every cursor reason at zero. Before this change the
    banked row carried no ``drop`` substring anywhere, so the wipe was
    indistinguishable from a beat that simply banked nothing.
    """
    stages = {
        "staged:cursor_resume": 0,
        "staged:cursor_reason:generation_unchanged": 0,
        "staged:units_dropped": 6,
        "staged:units_done": 0,
        "staged:window_stop:deadline": 0,
        "staged:window_left_ms": 1150000,
    }
    observation = build_observation(
        generation=1757131234567,
        generated_at="2026-09-06T04:16:00+00:00",
        complete=True,
        payload={"stages": stages, "terminal": "partial"},
    )
    assert observation["units_dropped"] == 6
    assert observation["units_dropped_measured"] is True
    assert observation["stop_reasons"] == ["window_stop:deadline"]
    # And the raw key is still on the row, so the derivation stays replayable
    # against a future version of this reader rather than replacing it.
    assert observation["gauges"]["staged:units_dropped"] == 6


# ---------------------------------------------------------------------------
# 2. gotcha #53 — a zero drop is not an unwritten drop
# ---------------------------------------------------------------------------

def test_a_drop_of_zero_is_distinguishable_from_a_drop_never_written():
    """The producer writes the key only inside ``if dropped:``.

    So absence carries two facts, and the cursor action — written
    unconditionally three lines above the call that can drop — separates them.
    """
    reached = bank_drop({"staged:cursor_resume": 0})
    assert reached == {"units_dropped": 0, "measured": True}

    never_reached = bank_drop({"staged:units_done": 4})
    assert never_reached == {"units_dropped": None, "measured": False}

    # And the two must not collapse into the same rendered value.
    assert reached["units_dropped"] != never_reached["units_dropped"]


def test_a_refused_beat_reports_unknown_rather_than_zero():
    """``REFUSE`` returns BEFORE the ledger write, so the row has no cursor key.

    Reporting that as "dropped 0" would be the CAL-P028 collapse ("nothing
    dropped" vs "we never looked") arriving through the field added to end it.
    """
    assert bank_drop({})["measured"] is False
    assert bank_drop({})["units_dropped"] is None
    assert bank_drop(None)["units_dropped"] is None


@pytest.mark.parametrize("action", ["fresh", "resume", "invalidate"])
def test_every_cursor_action_counts_as_having_reached_the_drop_path(action):
    """``record_stage(f"staged:cursor_{action}")`` is unconditional for all three."""
    assert bank_drop({f"staged:cursor_{action}": 0}) == {
        "units_dropped": 0,
        "measured": True,
    }


def test_an_explicit_zero_is_reported_as_measured():
    """If the writer's ``if dropped:`` guard is ever removed, a literal 0 must
    read as measured rather than falling through to the cursor inference."""
    assert bank_drop({"staged:units_dropped": 0}) == {
        "units_dropped": 0,
        "measured": True,
    }


def test_a_beat_that_recorded_no_stop_reason_answers_empty_not_unknown():
    assert stop_reasons({"staged:units_done": 128}) == []
    assert stop_reasons(None) == []


# ---------------------------------------------------------------------------
# 3. drift against the frozen writer
# ---------------------------------------------------------------------------

def _producer_source() -> str:
    from app.tasks import precompute_calibration

    return Path(inspect.getsourcefile(precompute_calibration)).read_text()


def test_every_stop_stage_in_the_frozen_writer_matches_the_infix_rule():
    """``precompute_calibration.py`` is frozen, so there is no constant to
    import. This reads its source and fails if a stop stage is ever emitted
    under a name the sampler's rule cannot reach.

    When the freeze lifts: promote these literals to imports and delete this.
    """
    src = _producer_source()
    emitted = set(re.findall(r'record_stage\(\s*f?"([^"{]*_stop:[^"{]*)', src))
    assert emitted, "the writer no longer records any *_stop:* stage"
    unreachable = sorted(name for name in emitted if not is_stop_key(name))
    assert not unreachable, (
        f"writer emits {unreachable}, which "
        f"{STAGED_PREFIX!r} + {STOP_REASON_INFIX!r} does not cover"
    )


def test_the_stop_stages_this_suite_names_are_the_ones_the_writer_writes():
    """The parametrised list above is a transcription, and a transcription that
    is never checked is how ``staged:units_done`` went missing in CAL-P083."""
    src = _producer_source()
    emitted = set(re.findall(r'record_stage\(\s*"(staged:[a-z_]+_stop:[a-z_]+)"', src))
    named = set(_WINDOW_STOPS + _REBUILD_STOPS)
    # ``staged:window_stop:{stop_reason}`` is interpolated, so ``deadline`` and
    # ``unit_too_large`` are not literals in the source and are excluded here.
    interpolated = {"staged:window_stop:deadline", "staged:window_stop:unit_too_large"}
    assert emitted <= named, f"writer emits stop stages this suite does not name: {emitted - named}"
    assert (named - interpolated) <= emitted, (
        f"this suite names stop stages the writer no longer writes: {named - interpolated - emitted}"
    )


def test_the_writer_still_records_units_dropped_under_that_name():
    """If the drop stage is renamed, capturing the old name is a silent no-op —
    exactly the shape of the defect this file closes."""
    assert 'record_stage("staged:units_dropped"' in _producer_source()


def test_the_writer_still_writes_the_cursor_action_before_it_can_drop():
    """``bank_drop``'s zero-vs-unknown split rests entirely on this ordering.

    If ``retain_planned_units`` ever moves above the cursor stage write, a beat
    that dropped nothing would report ``measured: false`` — degraded, not wrong,
    but this says so rather than letting the inference rot quietly.
    """
    src = _producer_source()
    cursor_at = src.index('record_stage(f"staged:cursor_{action}"')
    drop_at = src.index("cursor, dropped = retain_planned_units(")
    assert cursor_at < drop_at, (
        "the cursor action is no longer written before the drop path — "
        "bank_drop's zero-vs-unknown inference no longer holds"
    )


# ---------------------------------------------------------------------------
# 4. the capture-version gate — CERT-2051
# ---------------------------------------------------------------------------

#: The row the grader reproduced against the live ring: the 2026-09-06 04:16Z
#: beat that went 6 banked units → 0, **as it is actually banked**. It has a
#: cursor key, because CAL-P1002 captured those. It has no drop key and no stop
#: key, because the sampler of the day discarded both — NOT because the beat did
#: not drop. And it carries no ``gauge_capture_version``, because nothing did.
#:
#: This is the one fixture in the file that is a legacy row rather than a future
#: one, and every assertion about it is about refusing to answer.
LEGACY_WIPE_ROW = {
    "generation": 1757131234567,
    "generated_at": "2026-09-06T04:16:00+00:00",
    "tolerance_pp": 4.0,
    "terminal": "partial",
    "measured": True,
    "gauges": {
        "staged:cursor_resume": 0,
        "staged:cursor_reason:generation_unchanged": 0,
        "staged:units_done": 0,
        "staged:units_banked": 0,
        "staged:window_left_ms": 1150000,
    },
    "disclosure": {"measured": True, "units_banked": 0},
}


def test_a_new_observation_stamps_what_its_capture_could_retain():
    observation = build_observation(
        generation=1757131234567,
        generated_at="2026-09-06T04:16:00+00:00",
        complete=True,
        payload={"stages": {"staged:cursor_resume": 0}, "terminal": "partial"},
    )
    assert observation["gauge_capture_version"] == GAUGE_CAPTURE_VERSION
    assert GAUGE_CAPTURE_VERSION >= DROP_AND_STOP_CAPTURE_VERSION, (
        "the sampler stamps a version below its own drop/stop floor, so every "
        "row it banks from now on reads as unable to answer"
    )


@pytest.mark.parametrize(
    "row",
    [
        {},
        {"gauge_capture_version": None},
        # ``isinstance(True, int)`` is True, so a bool would sail through as 1.
        {"gauge_capture_version": True},
        {"gauge_capture_version": "2"},
        {"gauge_capture_version": 2.0},
        None,
        "not a row",
    ],
)
def test_a_row_that_does_not_plainly_say_its_version_is_unversioned(row):
    """Unproven capture support is unknown, never a number."""
    assert capture_version(row) == UNVERSIONED_CAPTURE
    assert UNVERSIONED_CAPTURE < DROP_AND_STOP_CAPTURE_VERSION


def test_the_legacy_wipe_row_answers_unknown_rather_than_a_measured_zero():
    """CERT-2051 in one test. This is the exact false statement it blocked.

    The bare readers, called on this row's gauge map, still say ``0``/``[]`` —
    that is what they are for, over a map that could have held the keys — so the
    assertion that matters is that the GATE does not let them near it.
    """
    assert bank_drop(LEGACY_WIPE_ROW["gauges"]) == {"units_dropped": 0, "measured": True}
    assert stop_reasons(LEGACY_WIPE_ROW["gauges"]) == []

    gated = row_stop_and_drop(LEGACY_WIPE_ROW)
    assert gated["capture_version"] == UNVERSIONED_CAPTURE
    assert gated["units_dropped"] is None
    assert gated["units_dropped_measured"] is False
    assert gated["stop_reasons"] is None
    assert gated["stop_reasons_measured"] is False


def test_no_stop_reason_and_could_not_have_seen_one_are_different_values():
    """``[]`` is a measurement; a legacy row never made it. gotcha #53's shape.

    If these two ever collapse into one value the gate is decorative — a reader
    cannot tell "this beat ran to the end" from "this row predates the capture".
    """
    ran_to_the_end = row_stop_and_drop(
        {"gauge_capture_version": GAUGE_CAPTURE_VERSION, "gauges": {"staged:units_done": 128}}
    )
    could_not_say = row_stop_and_drop(LEGACY_WIPE_ROW)

    assert ran_to_the_end["stop_reasons"] == []
    assert could_not_say["stop_reasons"] is None
    assert ran_to_the_end["stop_reasons"] != could_not_say["stop_reasons"]
    assert ran_to_the_end["stop_reasons_measured"] is True
    assert could_not_say["stop_reasons_measured"] is False


def test_a_versioned_row_is_read_off_its_own_banked_fields():
    row = {
        "gauge_capture_version": GAUGE_CAPTURE_VERSION,
        "stop_reasons": ["rebuild_stop:overlap_lock"],
        "units_dropped": 6,
        "units_dropped_measured": True,
        # Deliberately EMPTY, to prove the banked fields are preferred to a
        # re-derivation: a row is not re-litigated against a map it already
        # reduced.
        "gauges": {},
    }
    assert row_stop_and_drop(row) == {
        "capture_version": GAUGE_CAPTURE_VERSION,
        "stop_reasons": ["rebuild_stop:overlap_lock"],
        "stop_reasons_measured": True,
        "units_dropped": 6,
        "units_dropped_measured": True,
    }


def test_a_versioned_row_missing_its_derived_fields_falls_back_to_its_gauges():
    """Sound at this version, and only at this version: the capture retained the
    keys, so their absence from the map is a fact about the beat."""
    row = {
        "gauge_capture_version": GAUGE_CAPTURE_VERSION,
        "gauges": {"staged:cursor_fresh": 0, "staged:window_stop:deadline": 0},
    }
    gated = row_stop_and_drop(row)
    assert gated["units_dropped"] == 0
    assert gated["units_dropped_measured"] is True
    assert gated["stop_reasons"] == ["window_stop:deadline"]


def test_a_versioned_row_may_still_report_an_unknown_drop():
    """``units_dropped: null`` is a legitimate banked value — the beat refused
    before reaching the drop path — so presence of the KEY is the test, not
    truthiness. A null read as "absent" would send this row down the fallback."""
    row = {
        "gauge_capture_version": GAUGE_CAPTURE_VERSION,
        "stop_reasons": [],
        "units_dropped": None,
        "units_dropped_measured": False,
        # Would re-derive to a MEASURED ZERO if the banked null were skipped.
        "gauges": {"staged:cursor_invalidate": 0},
    }
    gated = row_stop_and_drop(row)
    assert gated["units_dropped"] is None
    assert gated["units_dropped_measured"] is False


def test_the_ring_schema_is_not_bumped_to_describe_a_row_field():
    """``HISTORY_SCHEMA`` is the envelope's ``expected_version``.

    Bumping it to announce ``gauge_capture_version`` would make the entire banked
    ring unreadable in one deploy — the endpoint would answer
    ``history_unreadable`` — and throw away the seven days of history the version
    marker exists to keep readable. Row shape is versioned per row instead.
    """
    assert HISTORY_SCHEMA == "calibration-beat-gauge-history/v1"


# ---------------------------------------------------------------------------
# 5. the real endpoint, over a ring holding all three row classes
# ---------------------------------------------------------------------------

def _banked(generation, generated_at, stages):
    """A ring row built by the PRODUCER, from raw stages.

    Not a hand-written dict. Every field the endpoint reads — including the
    capture version and the two derived fields — is whatever
    ``build_observation`` actually writes, so a fixture cannot agree with
    production by construction and the version stamp cannot go missing behind a
    literal that keeps asserting it is there.
    """
    return build_observation(
        generation=generation,
        generated_at=generated_at,
        complete=True,
        payload={"stages": stages, "terminal": "partial"},
    )


#: A beat banked by THIS sampler that reached the drop path and dropped nothing:
#: a cursor action, no drop key, no stop key. The shape ``LEGACY_WIPE_ROW`` was
#: wrongly given.
NEW_ZERO_DROP_ROW = _banked(
    1757134800000,
    "2026-09-06T05:16:00+00:00",
    {"staged:cursor_resume": 0, "staged:units_done": 12},
)

#: The same wipe as ``LEGACY_WIPE_ROW``, as it will be banked from now on.
NEW_WIPE_ROW = _banked(
    1757138400000,
    "2026-09-06T06:16:00+00:00",
    {
        "staged:cursor_resume": 0,
        "staged:units_dropped": 6,
        "staged:window_stop:deadline": 0,
    },
)


async def _serve(monkeypatch, rows):
    """The real endpoint over a ring of ``rows``, with only the read stubbed."""
    from datetime import datetime, timezone

    from app.routes import admin_cohort
    from app.utils.durable_state import DurableEnvelope, EnvelopeRead

    payload = {
        "schema": HISTORY_SCHEMA,
        "limit": 168,
        "observations": rows,
        "summary": {"observations": len(rows)},
    }
    envelope = DurableEnvelope.build(
        identity=HISTORY_IDENTITY,
        schema_version=HISTORY_SCHEMA,
        payload=payload,
        complete=True,
        source="calibration_beat_gauge_sampler",
        generated_at=datetime(2026, 9, 6, 7, 0, tzinfo=timezone.utc),
    )

    async def _fake_read(identity, *, expected_version=None, max_age_s=None):
        assert identity == HISTORY_IDENTITY
        assert expected_version == HISTORY_SCHEMA
        return EnvelopeRead(status="fresh", tier="durable", envelope=envelope)

    import app.services.durable_snapshots as ds

    monkeypatch.setattr(admin_cohort, "_check_admin_secret", lambda **kw: None)
    monkeypatch.setattr(ds, "read_snapshot_standalone", _fake_read)
    return await admin_cohort.calibration_beat_gauges(request=None, limit=24)


@pytest.mark.asyncio
async def test_the_endpoint_tells_the_three_row_classes_apart_in_one_call(monkeypatch):
    """The regression CERT-2051 named, on the surface it named.

    One ring, three rows, one request — because the finding was never that the
    readers are wrong, it was that the endpoint applied them to rows they do not
    describe. Only serving all three together shows the gate discriminating
    rather than simply nulling everything.
    """
    out = await _serve(monkeypatch, [LEGACY_WIPE_ROW, NEW_ZERO_DROP_ROW, NEW_WIPE_ROW])
    legacy, zero, wipe = out["observations"]

    # The row that cannot speak, and the false statement that was shipped here.
    assert legacy["capture_version"] == UNVERSIONED_CAPTURE
    assert legacy["units_dropped"] is None
    assert legacy["units_dropped_measured"] is False
    assert legacy["stop_reasons"] is None
    assert legacy["stop_reasons_measured"] is False
    # It still reports everything it CAN: the gate withholds two answers, it does
    # not blank the row.
    assert legacy["cursor_action"] == "resume"
    assert legacy["cursor_reason"] == "generation_unchanged"
    assert legacy["tolerance_pp"] == 4.0

    # A measured zero, which is the value the legacy row was wrongly given.
    assert zero["units_dropped"] == 0
    assert zero["units_dropped_measured"] is True
    assert zero["stop_reasons"] == []
    assert zero["stop_reasons_measured"] is True

    # And the wipe, once the capture can see it.
    assert wipe["units_dropped"] == 6
    assert wipe["units_dropped_measured"] is True
    assert wipe["stop_reasons"] == ["window_stop:deadline"]

    assert out["observations_returned"] == 3


@pytest.mark.asyncio
async def test_the_endpoint_never_renders_an_unmeasured_drop_as_a_number(monkeypatch):
    """The single assertion a reader of this surface depends on: any row whose
    ``units_dropped_measured`` is false carries ``null``, never ``0``.

    The counts are asserted FIRST and on purpose. A loop over "every unmeasured
    row" is vacuously green on a payload with no unmeasured rows — which is
    precisely what the defect produced, since it declared the legacy row
    measured. So the control is the finding: exactly one of these three rows must
    be unable to answer.
    """
    out = await _serve(monkeypatch, [LEGACY_WIPE_ROW, NEW_ZERO_DROP_ROW, NEW_WIPE_ROW])
    rows = out["observations"]

    assert sum(1 for r in rows if not r["units_dropped_measured"]) == 1
    assert sum(1 for r in rows if not r["stop_reasons_measured"]) == 1

    for row in rows:
        if not row["units_dropped_measured"]:
            assert row["units_dropped"] is None
        if not row["stop_reasons_measured"]:
            assert row["stop_reasons"] is None


@pytest.mark.asyncio
async def test_the_full_view_hands_back_the_row_verbatim(monkeypatch):
    """``full=true`` is the replayable form and must not acquire a derived field.

    A legacy row there carries NO drop or stop key at all, which is honest — the
    danger was only ever in the default view's re-derivation.
    """
    from app.routes import admin_cohort
    from app.utils.durable_state import DurableEnvelope, EnvelopeRead
    from datetime import datetime, timezone

    envelope = DurableEnvelope.build(
        identity=HISTORY_IDENTITY,
        schema_version=HISTORY_SCHEMA,
        payload={"schema": HISTORY_SCHEMA, "observations": [LEGACY_WIPE_ROW]},
        complete=True,
        source="calibration_beat_gauge_sampler",
        generated_at=datetime(2026, 9, 6, 7, 0, tzinfo=timezone.utc),
    )

    async def _fake_read(identity, *, expected_version=None, max_age_s=None):
        return EnvelopeRead(status="fresh", tier="durable", envelope=envelope)

    import app.services.durable_snapshots as ds

    monkeypatch.setattr(admin_cohort, "_check_admin_secret", lambda **kw: None)
    monkeypatch.setattr(ds, "read_snapshot_standalone", _fake_read)
    out = await admin_cohort.calibration_beat_gauges(request=None, full=True)

    assert out["observations"] == [LEGACY_WIPE_ROW]
    assert "units_dropped" not in out["observations"][0]
