"""The specimen helper actually moves the gate — #4564, substrate for #4436.

These test the WIRING, not `flip_permitted`'s logic. The gate's own branches are
covered in `test_authority_flip_switch.py`; what can silently fail here is the
patch not landing where the gate reads, which would leave every specimen test
quietly measuring the real config and passing for that reason. So the assertions
are: the specimen is invisible before registration, the branch it selects is the
branch that answers, and the real config is intact afterwards.

The two cases at the bottom — a RULED key with no shadow stamper, and a RULED key
with no discovery pass — are #4436's stated acceptance guards, and neither can be
written with a real sport: every ruled sport has both.
"""

from __future__ import annotations

import pytest

from app.config import authority_by_sport as gate
from app.config.authority_by_sport import flip_permitted
from app.utils.authority_agreement import GATE_MEETS

from tests.authority_specimens import (
    GATE_GLOBALS,
    _bindings,
    _patch_everywhere,
    register_specimen,
)

#: A key no real sport uses. Deliberately not sport-shaped: a specimen that read
#: like `basketball_wnba` would invite someone to "fix" it into a real league.
SPECIMEN = "specimen_4564"


def _run_of(n: int, state: str = GATE_MEETS) -> list[dict]:
    """`n` consecutive ledger days, newest last, in the two fields the walk reads."""
    return [{"day": f"2026-09-{day:02d}", "state": state} for day in range(1, n + 1)]


def test_the_specimen_does_not_exist_until_it_is_registered():
    """The negative control for every test below.

    If this ever fails, `SPECIMEN` has leaked into the real config and every
    other assertion in this file is measuring something it did not build.
    """
    permitted, why = flip_permitted(SPECIMEN, _run_of(10))
    assert not permitted
    assert "no shadow stamper" in why


def test_a_default_specimen_is_refused_on_the_clock(monkeypatch):
    """Fully structural and unruled — the state `icehockey_nhl` is the last of.

    This is the branch the pool is losing: the specimen must be refused on the
    STREAK, not on any structural branch, or it is not standing in for the NHL.
    """
    register_specimen(monkeypatch, SPECIMEN)

    permitted, why = flip_permitted(SPECIMEN, _run_of(6))
    assert not permitted
    assert "6/7 consecutive days" in why, why
    assert "a wait, not a defect" in why


def test_a_default_specimen_permits_at_seven(monkeypatch):
    register_specimen(monkeypatch, SPECIMEN)

    permitted, _ = flip_permitted(SPECIMEN, _run_of(7))
    assert permitted


def test_governing_none_is_refused_on_d63_which_is_what_4436_takes(monkeypatch):
    """What `baseball_mlb` demonstrates today, and is about to stop demonstrating."""
    register_specimen(monkeypatch, SPECIMEN, governing=None)

    permitted, why = flip_permitted(SPECIMEN, _run_of(10))
    assert not permitted
    assert "no governing identity number (D63)" in why
    assert "not more days" in why


def test_stamper_false_is_refused_as_a_build_not_a_wait(monkeypatch):
    register_specimen(monkeypatch, SPECIMEN, stamper=False)

    permitted, why = flip_permitted(SPECIMEN, _run_of(10))
    assert not permitted
    assert "no shadow stamper" in why
    assert "not a wait" in why


def test_discovery_false_is_refused_before_the_ledger_is_read(monkeypatch):
    register_specimen(monkeypatch, SPECIMEN, discovery=False)

    permitted, why = flip_permitted(SPECIMEN, _run_of(10))
    assert not permitted
    assert "no working StatPal discovery pass" in why


def test_a_ruled_specimen_is_permitted_with_no_ledger_at_all(monkeypatch):
    """D104: the ruling retires the wait, so an empty ledger is not a refusal."""
    register_specimen(monkeypatch, SPECIMEN, ruled=True)

    permitted, why = flip_permitted(SPECIMEN, [])
    assert permitted
    assert "without a certification streak" in why
    assert "D104" in why


# ── #4436's acceptance guards: the ruling must not skip the structural refusals ──
# Neither of these can be written with a real sport, which is the whole reason
# this helper exists: every sport in FLIP_RULED_WITHOUT_STREAK has a stamper and
# a discovery pass, so borrowing one could only ever demonstrate the permit.


def test_a_ruled_key_with_no_shadow_stamper_still_refuses(monkeypatch):
    register_specimen(monkeypatch, SPECIMEN, ruled=True, stamper=False)

    permitted, why = flip_permitted(SPECIMEN, _run_of(10))
    assert not permitted, "D104 must not be readable as a way past step 2"
    assert "no shadow stamper" in why


def test_a_ruled_key_with_no_discovery_pass_still_refuses(monkeypatch):
    register_specimen(monkeypatch, SPECIMEN, ruled=True, discovery=False)

    permitted, why = flip_permitted(SPECIMEN, _run_of(10))
    assert not permitted, "D104 must not be readable as a way past step 3"
    assert "no working StatPal discovery pass" in why


# ────────────────────────── the wiring itself ──────────────────────────


def test_the_patch_lands_on_the_module_the_gate_reads_not_the_one_that_defines():
    """The trap this helper centralises.

    `SHADOW_STAMPERS` is defined in `authority_agreement` and read as a global of
    `authority_by_sport`. A patch that reached only the definer would leave the
    gate reading the original — and a specimen test would pass on the real config
    without saying so.
    """
    assert gate in _bindings("SHADOW_STAMPERS"), (
        "the gate's own module must be among the patch targets, or "
        "flip_permitted never sees a specimen"
    )

    with pytest.MonkeyPatch.context() as patcher:
        register_specimen(patcher, SPECIMEN)
        assert SPECIMEN in gate.SHADOW_STAMPERS
        assert SPECIMEN in gate.DISCOVERY_SCHEDULED_SPORTS
        assert SPECIMEN in gate.GOVERNING_IDENTITY_NUMBERS


def test_every_gate_global_is_bound_by_at_least_one_module():
    """A renamed global must fail here rather than no-op inside a specimen.

    `_patch_everywhere` raises on an unbound name; this proves the names in
    `GATE_GLOBALS` are the ones the code actually has, so that raise stays a
    tripwire for a rename instead of firing on every test.
    """
    for name in GATE_GLOBALS:
        assert _bindings(name), f"{name} is in GATE_GLOBALS but nothing binds it"


def test_patching_an_unbound_name_raises_rather_than_silently_doing_nothing(
    monkeypatch,
):
    with pytest.raises(LookupError, match="silently measure the real config"):
        _patch_everywhere(monkeypatch, "NO_SUCH_GATE_GLOBAL_4564", {})


def test_a_specimen_may_not_shadow_a_real_sport(monkeypatch):
    """Otherwise a refusal it 'demonstrates' could be the real config's."""
    with pytest.raises(ValueError, match="already in"):
        register_specimen(monkeypatch, "baseball_mlb")


def test_the_real_config_is_intact_after_a_specimen_is_registered():
    """Registration is scoped to one test; the next one must see the real config."""
    before = dict(gate.SHADOW_STAMPERS)

    with pytest.MonkeyPatch.context() as patcher:
        register_specimen(patcher, SPECIMEN)
        assert SPECIMEN in gate.SHADOW_STAMPERS

    assert gate.SHADOW_STAMPERS == before
    assert SPECIMEN not in gate.SHADOW_STAMPERS
