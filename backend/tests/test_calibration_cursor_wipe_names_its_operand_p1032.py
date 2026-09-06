"""CAL-P1032 (#3522) — the bank wipe stops accusing a compile-time constant.

``decode_staged_cursor_detailed`` classified both of its identity fields with
``raw.get(field) != expected``, and ``.get`` folds **absent** into **different**.
For ``input_fingerprint`` that is imprecise. For ``population_version`` it is
impossible: the expected value is ``CALIBRATION_POPULATION_VERSION``, a module
constant, so it cannot differ between two beats of one release — yet three of
the last eight beats on the live ring at 2026-09-06 11:56Z recorded
``cursor_reason: population_version_changed`` while it sat at ``q269``.

That token is the entire diagnosis of a curve that was 29 hours stale, and it
named the one thing that provably did not happen. These guards pin the split in
both directions, pin that the split changed no BEHAVIOUR, and pin the claim that
made the change safe to ship at all: editing this module cannot move
``staged_unit_fingerprint`` and therefore cannot wipe the bank it exists to save.
"""

import pytest

from app.tasks.calibration_beat_gauge_sampler import cursor_decision
from app.utils.calibration_phase_ledger import INVALIDATE, RESUME
from app.utils.calibration_staged_futures import (
    MAIN_BUILD_TASK,
    REASON_INPUT_FINGERPRINT,
    REASON_INPUT_FINGERPRINT_ABSENT,
    REASON_INPUT_FINGERPRINT_MALFORMED,
    REASON_LEGACY_FINGERPRINT_ACCEPTED,
    REASON_POPULATION_VERSION,
    REASON_POPULATION_VERSION_ABSENT,
    REASON_POPULATION_VERSION_MALFORMED,
    STAGED_FUTURES_SCHEMA,
    UNIT_KEY_VM_ID,
    classify_field_mismatch,
    decode_staged_cursor_detailed,
    encode_accumulator,
)

VERSION = "q267"
INPUT_FP = "fp-a"


def _raw(*, drop=(), **overrides):
    """A resumable cursor, with keys overridden AND — the new part — removable.

    The existing ``_raw`` in ``test_calibration_convergence_p024`` cannot express
    an absent key (``dict.update`` only sets), which is precisely why the absent
    branch went unguarded and shipped folded into ``changed``.
    """
    raw = {
        "schema": STAGED_FUTURES_SCHEMA,
        "task": MAIN_BUILD_TASK,
        "unit_key": UNIT_KEY_VM_ID,
        "population_version": VERSION,
        "input_fingerprint": INPUT_FP,
        "generation_fingerprint": "gen-a",
        "owner": "me",
        "lease_expires_at": 0.0,
        "committed_units": ["u1"],
        "accumulator": encode_accumulator([{"bucket_idx": 1, "n": 1}], []),
        "terminal": "partial",
    }
    raw.update(overrides)
    for key in drop:
        raw.pop(key, None)
    return raw


def _decode(raw, *, legacy=None):
    return decode_staged_cursor_detailed(
        raw,
        expected_population_version=VERSION,
        expected_input_fingerprint=INPUT_FP,
        expected_generation_fingerprint="gen-a",
        owner="me",
        generation=9,
        now=100.0,
        legacy_input_fingerprint=legacy,
    )


class TestAnAbsentFieldStopsReportingAsAChangedOne:
    """The finding. A missing value accuses the writer; a different one accuses a deploy."""

    def test_a_cursor_with_no_population_version_says_absent_not_changed(self):
        _c, action, reason = _decode(_raw(drop=("population_version",)))
        assert action == INVALIDATE
        assert reason == REASON_POPULATION_VERSION_ABSENT
        # The whole point, stated as its own assertion so a future fold fails
        # here with the sentence rather than on an opaque token comparison.
        assert reason != REASON_POPULATION_VERSION, (
            "a constant cannot change; reporting an absent field as a change "
            "sends the reader hunting a deploy that never happened"
        )

    def test_an_explicit_null_population_version_is_absent_too(self):
        """After a JSON round-trip, missing and ``null`` are one fact."""
        _c, _a, reason = _decode(_raw(population_version=None))
        assert reason == REASON_POPULATION_VERSION_ABSENT

    def test_a_cursor_with_no_input_fingerprint_says_absent_not_changed(self):
        _c, action, reason = _decode(_raw(drop=("input_fingerprint",)))
        assert action == INVALIDATE
        assert reason == REASON_INPUT_FINGERPRINT_ABSENT
        assert reason != REASON_INPUT_FINGERPRINT

    @pytest.mark.parametrize("bad", [123, True, [], {}, ""])
    def test_a_present_but_unusable_population_version_is_malformed(self, bad):
        """Not a string, or an empty one. ``new_staged_cursor`` writes neither."""
        _c, action, reason = _decode(_raw(population_version=bad))
        assert (action, reason) == (INVALIDATE, REASON_POPULATION_VERSION_MALFORMED)

    @pytest.mark.parametrize("bad", [123, True, [], {}, ""])
    def test_a_present_but_unusable_input_fingerprint_is_malformed(self, bad):
        _c, action, reason = _decode(_raw(input_fingerprint=bad))
        assert (action, reason) == (INVALIDATE, REASON_INPUT_FINGERPRINT_MALFORMED)


class TestTheRealChangeStillReportsAsAChange:
    """The other direction. A split that swallowed the true positive would be worse
    than the fold it replaced: ``input_fingerprint_changed`` is the token that
    correctly convicted the 2026-08-09 deploy, and it must still fire."""

    def test_a_different_population_version_is_still_changed(self):
        _c, action, reason = _decode(_raw(population_version="q999"))
        assert (action, reason) == (INVALIDATE, REASON_POPULATION_VERSION)

    def test_a_different_input_fingerprint_is_still_changed(self):
        _c, action, reason = _decode(_raw(input_fingerprint="deployed-new-sql"))
        assert (action, reason) == (INVALIDATE, REASON_INPUT_FINGERPRINT)

    def test_a_healthy_cursor_still_resumes(self):
        """The split sits on the failure path only; the happy path is untouched."""
        cursor, action, _reason = _decode(_raw())
        assert action == RESUME
        assert cursor.committed_units == ("u1",)


class TestTheLegacyCutoverIsNotBrokenByTheSplit:
    """CAL-P205 layer 1 accepts a cursor stamped with the WIDE digest. That branch
    is checked BEFORE the new classification and must keep winning — otherwise
    this change costs the bank the cutover was written to protect."""

    def test_the_legacy_digest_is_still_accepted_not_classified(self):
        _c, action, reason = _decode(_raw(input_fingerprint="wide-fp"), legacy="wide-fp")
        assert action == RESUME
        assert reason == REASON_LEGACY_FINGERPRINT_ACCEPTED

    def test_an_absent_digest_is_not_smuggled_through_the_legacy_branch(self):
        """``None == legacy`` is False for any real legacy digest, and this pins
        it: an absent fingerprint is absent, never a legacy acceptance."""
        _c, action, reason = _decode(_raw(drop=("input_fingerprint",)), legacy="wide-fp")
        assert (action, reason) == (INVALIDATE, REASON_INPUT_FINGERPRINT_ABSENT)


class TestBehaviourIsUnchanged:
    """CAL-P1032 makes the wipe legible. It does not weaken it, and a later queue
    that decides to weaken it should have to delete an assertion saying so."""

    @pytest.mark.parametrize(
        "raw",
        [
            _raw(drop=("population_version",)),
            _raw(population_version=""),
            _raw(population_version="q999"),
            _raw(drop=("input_fingerprint",)),
            _raw(input_fingerprint=""),
            _raw(input_fingerprint="other"),
        ],
    )
    def test_every_one_of_the_six_still_invalidates(self, raw):
        _c, action, _reason = _decode(raw)
        assert action == INVALIDATE

    def test_the_six_tokens_are_all_distinct(self):
        tokens = [
            REASON_POPULATION_VERSION,
            REASON_POPULATION_VERSION_ABSENT,
            REASON_POPULATION_VERSION_MALFORMED,
            REASON_INPUT_FINGERPRINT,
            REASON_INPUT_FINGERPRINT_ABSENT,
            REASON_INPUT_FINGERPRINT_MALFORMED,
        ]
        assert len(set(tokens)) == 6

    def test_no_new_token_collides_with_an_existing_reason(self):
        """A token that duplicates another module constant would rebuild the fold
        one level up, where nothing here would catch it."""
        from app.utils import calibration_staged_futures as mod

        values = [
            getattr(mod, name)
            for name in dir(mod)
            if name.startswith("REASON_") and isinstance(getattr(mod, name), str)
        ]
        assert len(values) == len(set(values)), sorted(values)


class TestTheClassifierItself:
    """Unit-level, because the two call sites share it and a drift here is silent."""

    @pytest.mark.parametrize(
        "stored,expected",
        [
            (None, "A"),
            ("", "M"),
            (0, "M"),
            (False, "M"),
            ([], "M"),
            ("something", "C"),
            ("0", "C"),
        ],
    )
    def test_the_three_way_split(self, stored, expected):
        assert (
            classify_field_mismatch(stored, changed="C", absent="A", malformed="M")
            == expected
        )


class TestTheNewTokensReachTheReader:
    """A split the ring cannot show is a split nobody has. The sampler banks these
    by the ``staged:cursor_`` prefix and ``cursor_decision`` takes the suffix
    verbatim, so the tokens should arrive with no per-token registration — this
    proves it rather than assuming it."""

    @pytest.mark.parametrize(
        "token",
        [
            REASON_POPULATION_VERSION_ABSENT,
            REASON_POPULATION_VERSION_MALFORMED,
            REASON_INPUT_FINGERPRINT_ABSENT,
            REASON_INPUT_FINGERPRINT_MALFORMED,
        ],
    )
    def test_the_projection_reports_the_new_reason(self, token):
        decision = cursor_decision(
            {"staged:cursor_invalidate": 0, f"staged:cursor_reason:{token}": 0}
        )
        assert decision == {"action": "invalidate", "reason": token}


class TestEditingThisModuleCannotWipeTheBank:
    """The claim that made CAL-P1032 shippable at all, as a test rather than a
    paragraph. ``staged_unit_fingerprint`` governs whether banked units survive a
    deploy; if this module's source reached it, the fix for throwing the bank
    away would itself throw the bank away.

    Two arms on purpose. The null arm alone proves nothing — a fingerprint that
    never moves for any reason would pass it — so the control arm moves an input
    that IS hashed and shows the digest reacts.
    """

    def test_moving_a_constant_in_this_module_does_not_move_the_digest(
        self, monkeypatch
    ):
        from app.tasks.precompute_calibration import staged_unit_fingerprint
        from app.utils import calibration_staged_futures as mod

        before = staged_unit_fingerprint()
        monkeypatch.setattr(mod, "REASON_POPULATION_VERSION", "totally-different")
        monkeypatch.setattr(mod, "REASON_POPULATION_VERSION_ABSENT", "also-different")
        assert staged_unit_fingerprint() == before

    def test_control_moving_a_hashed_input_does_move_the_digest(self, monkeypatch):
        from app.tasks import precompute_calibration as pc

        before = pc.staged_unit_fingerprint()
        monkeypatch.setattr(pc, "CALIBRATION_POPULATION_VERSION", "q-nope")
        assert pc.staged_unit_fingerprint() != before
