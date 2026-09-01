"""CAL-P192 (#2052) — ``staged:beats_to_publish`` has THREE writers, and the
frozen one's ``-1`` catastrophe sentinel is clamped to ``0`` on the way in.

Report: ``artifacts/cal-p192/BEATS-TO-PUBLISH-HAS-THREE-WRITERS.md``.

CAL-P191 asked "two writers, one key — which one wins, and do they agree on what
it means?" of ``staged:units_this_beat`` and parked the answer. This file is the
SWEEP that question implies, run across every ``record_stage`` /
``record_gauge`` / ``record_stage_outcome`` call site under ``app/``. Forty-five
distinct keys; four with more than one writer; three of those real:

* ``staged:units_this_beat``  — 2 writers, DISAGREE (banked vs attempts). P191.
* ``staged:unit_ms_mean``     — 2 writers, DISAGREE by the same divisor, and for
  the same reason: the frozen writer divides by units that BANKED, the winner
  divides by units ATTEMPTED. Same defect instance as P191, one key over.
* ``staged:beats_to_publish`` — **3 writers**, and the new finding.

The three writers are:

1. ``precompute_calibration._record_convergence_projection`` (frozen, ruling
   009) at ``:4467`` — ``record_stage``, projection over the MIXED mean.
2. ``calibration_main_build._record_staged_rate`` at ``:1588`` —
   ``record_gauge(…, 0)`` when ``remaining == 0``, i.e. **it publishes this
   beat**.
3. the same function at ``:1621`` — ``record_gauge`` of the COMPLETED-mean
   projection, or ``-1``.

``-1`` is not "unknown". Three separate docstrings say so in the same words —
``calibration_main_build:1618``, ``calibration_phase_ledger.unit_projection``
(``beats_remaining``), and the frozen module at ``precompute_calibration:4465``
— it is "a whole beat cannot hold one unit", the worst fact the build can
report. But writer 1 emits it through ``record_stage``, whose first line is
``ms = max(0, int(duration_ms))``, because that primitive was built for
durations. **The sentinel becomes 0** — the exact integer writer 2 uses for
"nothing remains, it publishes now". The two most opposite states of the
rebuild render as the same number.

Why it has never been seen: writer 3 runs on the terminal path and lands LAST,
so it normally overwrites writer 1 before anyone reads. That ordering is
measurable on the live beat rather than assumed — see
``TestTheWinnerIsTheLastWriter``. The clamp is therefore LATENT, and reachable
exactly when ``_record_staged_rate`` returns before ``:1588``/``:1621``: the
durable convergence snapshot read failing, being stale, or raising
(``calibration_main_build:1400`` / ``:1404`` / ``:1408`` / ``:1418``). Those
paths are gauged (``staged:convergence_reason:*``) precisely because they
happen. On such a beat the ledger publishes ``beats_to_publish: 0`` while the
truth is ``-1``, and ``calibration_beat_gauge_sampler.OPERATIONAL_GAUGES``
carries that 0 to an operator.

The stale comment is worth recording too: ``precompute_calibration:4370`` says
the projection is skipped on every beat, "which is why ``staged:beats_to_publish``
is absent from every ledger". The live ledger's ``stage_counts`` says otherwise —
see ``TestTheFrozenWriterDidFire``. The loop now exits normally via the window
stop rather than throwing, so writer 1 fires every beat.

These tests CHARACTERIZE current behaviour. They do not assert it is right.
Choosing which writer owns the key, or giving ``record_stage`` a signed variant,
changes a gauge the sampler and five graders read — a fold's call under ruling
134, not a build lane's. Parked as ``P192-1``.

TEST-ONLY. Nothing under ``app/`` is touched, so ``_main_input_fingerprint()``
cannot move and this file is inert under the D-G deploy freeze
(``.claude/handoff/runner-inbox/calibration/960-calibration-deploy-freeze``).
"""

from __future__ import annotations

import ast
import collections
import pathlib
from importlib import import_module

import pytest

cmb = import_module("app.tasks.calibration_main_build")
cpl = import_module("app.utils.calibration_phase_ledger")
pc = import_module("app.tasks.precompute_calibration")
sampler = import_module("app.tasks.calibration_beat_gauge_sampler")

KEY = "staged:beats_to_publish"

# The 2026-09-01T16:32:11.447482Z production beat, read off
# ``durable_state_snapshots`` where ``identity='calibration:main:phase_ledger'``.
LIVE_STAGES_BEATS_TO_PUBLISH = 4
LIVE_STAGE_COUNTS_BEATS_TO_PUBLISH = 1
LIVE_ATTEMPTS = 7          # stage_counts['read:futures_unit']
LIVE_BANKED_THIS_BEAT = 5  # stages['staged:units_completed_this_beat']
LIVE_UNITS_THIS_BEAT = 7   # stages['staged:units_this_beat'] — the published one


def _ledger() -> cpl.PhaseLedger:
    return cpl.PhaseLedger(
        plan=cpl.derive_plan({}, floors={}),
        population_version="q268",
        owner="test",
        generation=1,
        input_fingerprint="fp",
    )


# ---------------------------------------------------------------------------
# 1. The sweep: which keys have more than one writer
# ---------------------------------------------------------------------------

WRITE_PRIMITIVES = frozenset(
    {"record_gauge", "record_stage", "record_stage_outcome"}
)

#: Every key written from more than one call site, and by which primitive.
#: A key appearing here is not by itself a defect — it is a place where two
#: authors had to agree on a meaning without a type to make them.
EXPECTED_MULTI_WRITER_KEYS = {
    "staged:units_this_beat": {"record_stage", "record_gauge"},
    "staged:unit_ms_mean": {"record_stage", "record_gauge"},
    "staged:beats_to_publish": {"record_stage", "record_gauge"},
}


#: Call sites that pass a bare variable through to a write primitive. These are
#: forwarders, not key sites — the key was chosen by their caller, which the
#: sweep sees separately. Counted rather than skipped, so that a NEW forwarder
#: (a real way to hide a writer) fails the sweep instead of vanishing from it.
EXPECTED_FORWARDER_SITES = 2


def _key_names(node: ast.expr) -> list[str]:
    """Every key a call site can write, as literals or f-string PATTERNS.

    ``[]`` means "this is a forwarder, the key comes from a caller".

    Raises on anything else. A source scan that silently skips what it does not
    understand reports "no new collisions" for a file it never read, which is
    the failure mode this whole file exists to catch one level down.
    """
    if isinstance(node, ast.Name):
        return []
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, ast.Constant):
                parts.append(str(value.value))
            else:
                parts.append("{?}")
        return ["".join(parts)]
    if isinstance(node, ast.IfExp):
        # ``record_gauge("a" if cond else "b", 1)`` — one site, two keys, both
        # statically known. Rendering only one of them would under-report.
        return _key_names(node.body) + _key_names(node.orelse)
    raise AssertionError(
        f"ledger write with an unrenderable key at line {node.lineno}: "
        f"{ast.dump(node)[:120]} — teach this scan to read it rather than "
        f"letting the sweep under-report"
    )


def _sweep_writers() -> tuple[dict[str, list[tuple[str, int, str]]], int]:
    """``({key: [(path, line, primitive), …]}, forwarder_count)``."""
    app_root = pathlib.Path(cpl.__file__).resolve().parent.parent
    assert app_root.name == "app", f"expected the app package, got {app_root}"

    writers: dict[str, list[tuple[str, int, str]]] = collections.defaultdict(list)
    forwarders = 0
    scanned = 0
    for path in sorted(app_root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text())
        except (SyntaxError, UnicodeDecodeError) as exc:
            raise AssertionError(f"cannot parse {path}: {exc}") from exc
        scanned += 1
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute):
                continue
            if func.attr not in WRITE_PRIMITIVES:
                continue
            if not node.args:
                # Keyword-only forwarding; no positional key to attribute.
                forwarders += 1
                continue
            names = _key_names(node.args[0])
            if not names:
                forwarders += 1
                continue
            for name in names:
                writers[name].append(
                    (str(path.relative_to(app_root.parent)), node.lineno, func.attr)
                )
    assert scanned > 100, f"the sweep only read {scanned} files — wrong root?"
    return dict(writers), forwarders


class TestTheSweep:
    def test_exactly_these_keys_have_more_than_one_writer(self):
        """A fourth colliding key must fail this test, not go unnoticed.

        ``<DYNAMIC>`` is excluded: those are f-string keys whose pattern differs
        per call site, so sharing the rendered stem is not a collision.
        """
        writers, forwarders = _sweep_writers()
        assert forwarders == EXPECTED_FORWARDER_SITES, (
            "a new forwarding write site appeared. A forwarder hides which key "
            "gets written, so it is the one way a fourth collision could enter "
            "without this sweep seeing it — read it before raising the count."
        )
        multi = {
            key: {prim for _, _, prim in sites}
            for key, sites in writers.items()
            if len(sites) > 1 and "{?}" not in key
        }
        assert multi == EXPECTED_MULTI_WRITER_KEYS, (
            "the set of multi-writer ledger keys moved. Every entry is a place "
            "two modules must agree on a meaning with nothing enforcing it — "
            "read the new one before updating this expectation."
        )

    def test_beats_to_publish_has_three_writers_across_two_modules(self):
        sites = _sweep_writers()[0][KEY]
        assert len(sites) == 3, sites

        by_module = collections.Counter(path for path, _, _ in sites)
        assert by_module == {
            "app/tasks/calibration_main_build.py": 2,
            "app/tasks/precompute_calibration.py": 1,
        }, by_module

    def test_every_multi_writer_key_mixes_the_two_write_rules(self):
        """The collision is always accumulate-vs-overwrite, never like-for-like.

        That is what makes the order load-bearing: two ``record_gauge`` writers
        would merely disagree on a value, but a ``record_stage`` landing after a
        ``record_gauge`` SUMS them into a number neither writer computed.
        """
        for key, primitives in EXPECTED_MULTI_WRITER_KEYS.items():
            assert primitives == {"record_stage", "record_gauge"}, (key, primitives)


# ---------------------------------------------------------------------------
# 2. The mechanism: record_stage cannot carry a negative
# ---------------------------------------------------------------------------


class TestTheSentinelDoesNotSurviveRecordStage:
    def test_record_stage_clamps_minus_one_to_zero(self):
        """``ms = max(0, int(duration_ms))`` — right for durations, fatal here."""
        led = _ledger()
        led.record_stage(KEY, -1)
        assert led.stages[KEY] == 0, (
            "if this ever returns -1 the clamp has been removed and the frozen "
            "writer's sentinel now survives — a real improvement, and this "
            "test is the place to notice it"
        )

    def test_record_gauge_preserves_minus_one(self):
        """The winner's sentinel is intact, which is why nobody has seen this."""
        led = _ledger()
        led.record_gauge(KEY, -1)
        assert led.stages[KEY] == -1

    def test_the_clamped_sentinel_is_indistinguishable_from_publishing_now(self):
        """The two most opposite states of the rebuild share one integer.

        Writer 2 (``calibration_main_build:1588``) writes 0 for ``remaining ==
        0`` — the build finished and publishes this beat. Writer 1's clamped
        ``-1`` means a whole beat cannot hold one unit, i.e. it never finishes.
        """
        never_converges = _ledger()
        never_converges.record_stage(KEY, -1)  # writer 1, catastrophe

        publishes_now = _ledger()
        publishes_now.record_gauge(KEY, 0)  # writer 2, success

        assert never_converges.stages[KEY] == publishes_now.stages[KEY] == 0
        # And nothing else in the payload separates them either.
        assert KEY not in never_converges.as_payload().get("floors", {})

    def test_the_emission_count_is_the_only_survivor(self):
        """``stage_counts`` shows writer 1 fired; it does not show what it said."""
        led = _ledger()
        led.record_stage(KEY, -1)
        payload = led.as_payload()
        assert payload["stages"][KEY] == 0
        assert payload["stage_counts"][KEY] == 1


# ---------------------------------------------------------------------------
# 3. Order is load-bearing, and it is measurable on the live beat
# ---------------------------------------------------------------------------


class TestTheWinnerIsTheLastWriter:
    def test_gauge_after_stage_overwrites(self):
        led = _ledger()
        led.record_stage(KEY, 9)
        led.record_gauge(KEY, 4)
        assert led.stages[KEY] == 4

    def test_stage_after_gauge_SUMS_into_a_number_neither_writer_computed(self):
        """The hazard if the call order ever inverts.

        Neither 4 nor 9 is wrong on its own; 13 is not a projection at all.
        """
        led = _ledger()
        led.record_gauge(KEY, 4)
        led.record_stage(KEY, 9)
        assert led.stages[KEY] == 13

    def test_the_live_beat_proves_the_gauge_writer_landed_last(self):
        """Measured, not assumed — via the sibling key that has both writers.

        ``staged:units_this_beat`` published 7 on the live beat. The frozen
        writer contributes the banked count (5) through ``record_stage``; the
        terminal writer sets attempts (7) through ``record_gauge``. Had the
        frozen writer landed second the stored value would be 5 + 7 = 12.
        Seeing 7 fixes the order for both keys, since the two writes sit in the
        same pair of functions.
        """
        assert LIVE_UNITS_THIS_BEAT == LIVE_ATTEMPTS
        would_be_if_frozen_writer_landed_second = (
            LIVE_ATTEMPTS + LIVE_BANKED_THIS_BEAT
        )
        assert LIVE_UNITS_THIS_BEAT != would_be_if_frozen_writer_landed_second

        led = _ledger()
        led.record_stage("staged:units_this_beat", LIVE_BANKED_THIS_BEAT)
        led.record_gauge("staged:units_this_beat", LIVE_ATTEMPTS)
        assert led.stages["staged:units_this_beat"] == LIVE_UNITS_THIS_BEAT


# ---------------------------------------------------------------------------
# 4. The frozen writer is NOT dead, whatever its comment says
# ---------------------------------------------------------------------------


class TestTheFrozenWriterDidFire:
    def test_live_stage_counts_records_one_emission(self):
        """``precompute_calibration:4370`` claims the key is absent from every
        ledger because the projection is skipped. The live beat has it, with an
        emission count of exactly 1 — and ``record_gauge`` never touches
        ``stage_counts``, so that 1 can only be the frozen writer.
        """
        assert LIVE_STAGE_COUNTS_BEATS_TO_PUBLISH == 1
        assert LIVE_STAGES_BEATS_TO_PUBLISH == 4

        led = _ledger()
        led.record_gauge(KEY, LIVE_STAGES_BEATS_TO_PUBLISH)
        assert KEY not in led.stage_counts, (
            "record_gauge must not count emissions — if it starts to, the live "
            "stage_counts reading stops being attributable to the frozen writer"
        )

    def test_record_gauge_alone_cannot_produce_the_live_pair(self):
        """(stages=4, stage_counts=1) is only reachable with BOTH writers."""
        gauge_only = _ledger()
        gauge_only.record_gauge(KEY, 4)
        assert gauge_only.stage_counts.get(KEY, 0) == 0

        both = _ledger()
        both.record_stage(KEY, 11)  # whatever the mixed-mean projection said
        both.record_gauge(KEY, 4)
        assert both.stages[KEY] == LIVE_STAGES_BEATS_TO_PUBLISH
        assert both.stage_counts[KEY] == LIVE_STAGE_COUNTS_BEATS_TO_PUBLISH


# ---------------------------------------------------------------------------
# 5. Blast radius: the clamped value reaches an operator
# ---------------------------------------------------------------------------


class TestTheSamplerQuotesIt:
    def test_beats_to_publish_is_an_operational_gauge(self):
        assert KEY in sampler.OPERATIONAL_GAUGES

    @pytest.mark.parametrize("sibling", ["staged:unit_ms_mean"])
    def test_the_other_disagreeing_key_is_quoted_too(self, sibling):
        """``unit_ms_mean`` is swept up in the same sampler tuple, and it is the
        second key whose two writers disagree on a divisor (P191's finding, one
        key over: the frozen writer divides by banked, the winner by attempts).
        """
        assert sibling in sampler.OPERATIONAL_GAUGES
        assert sibling in EXPECTED_MULTI_WRITER_KEYS


# ---------------------------------------------------------------------------
# 6. The -1 convention is asserted in three docstrings and enforced in none
# ---------------------------------------------------------------------------


class TestTheConventionIsProseOnly:
    def test_three_sites_promise_the_same_sentinel(self):
        import inspect

        promises = [
            inspect.getsource(cmb._record_staged_rate),
            inspect.getsource(pc._record_convergence_projection),
            inspect.getsource(cpl.PhasePlan.unit_projection),
        ]
        for source in promises:
            assert "-1" in source
            assert "unknown" in source, (
                "each site states the convention as 'NOT unknown' — if that "
                "wording goes, re-read whether the convention went with it"
            )

    def test_nothing_validates_a_written_value_against_it(self):
        """``record_gauge`` accepts any int; ``record_stage`` accepts none < 0.

        There is no shared writer for this key that could enforce the
        convention, which is the structural reason the clamp went unnoticed.
        """
        led = _ledger()
        for value in (-99, -1, 0, 4):
            led.record_gauge(KEY, value)
            assert led.stages[KEY] == value
