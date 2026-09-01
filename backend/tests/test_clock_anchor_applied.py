"""The anchor guard, APPLIED to the real files LAT-P181 repaired.

🔴 WHY THIS FILE EXISTS, AND WHY IT IS SEPARATE FROM THE CONTROL BATTERY.

``tests/lib_clock_anchor.py`` is the guard and ``tests/test_clock_anchor_guard.py``
is its control — every disclosed attack, each proved to raise. Both were written
and both were green, and between them they protected **nothing**: measured with
a grep for call sites, the library had *zero* callers outside its own control.
A guard tested only against string literals it is handed is a guard with no
subject. Re-pinning ``NOW`` in any repaired file to ``datetime(2026, ...)`` would
have restored the exact bomb the repair removed, on a fully green suite.

That is the same shape as *"a containment check satisfied by a sibling call
site"*: the mechanism is exercised somewhere, so it looks covered, while the
place it is supposed to act is unguarded. This file is the call site. The battery
proves the guard *can* refuse; this proves the guard is *pointed at* the files.

🔴 WHAT THIS FILE DOES **NOT** COVER, STATED RATHER THAN DISCOVERED LATER.

``assert_no_absolute_date_literals`` is module-scope only, deliberately — a date
built inside a helper is that helper's business, and the battery pins that scope
rule in both directions. But one of the five repairs was exactly that shape:
``tests/integration/test_route_politics.py`` carried
``resolution_date=datetime(2027, 5, 31, ...)`` **inside** ``_georgia_specimen``,
and it was a real bomb (measured red on 2027-06-07). This guard cannot see that
class and must not be read as covering it.

The instrument that does see it is the oracle, not a scan:
``scripts/timebomb_confirm.py`` runs the file at future instants and asks whether
it changes its mind. Scope is invisible to a runtime check. The division is
deliberate — a static guard for the shape that is cheap to pin, an oracle for the
shape that is not — and the oracle is the one that found all five.
"""

from __future__ import annotations

import pathlib

import pytest

from tests.lib_clock_anchor import (
    assert_anchor_is_clock_derived,
    assert_no_absolute_date_literals,
)

_TESTS = pathlib.Path(__file__).resolve().parent


def _read(rel: str) -> str:
    path = _TESTS / rel
    # A guard that cannot find its subject must say so, not shrug. If one of
    # these files is renamed, this fails loudly rather than skipping quietly.
    assert path.is_file(), f"guarded file has moved or been deleted: {rel}"
    return path.read_text()


#: The module-level anchors LAT-P181 converted from a literal to a clock read.
#: ``rel`` -> the anchor name a re-pin would have to attack.
ANCHORS = {
    "test_gold_label_store_convergence.py": "NOW",
    "test_feed_concept_single_scan.py": "NOW",
    "test_golf_tour_badge_uxp185.py": "_FEED_NOW",
    # 🔴 THE ORIGINAL BURN, AND CERT-589's SHIP DELIVERED IN ONE LINE.
    #
    # This is the file whose literal `datetime(2026, 8, 1, 12, 0)` crossed
    # `SENTINEL_MAX_AGE_S` on 2026-08-31 and cost fifteen hours. `41b2479c`
    # (CERT-602) made its anchor clock-following and is on master; the ALLOWLIST
    # GRAMMAR that stops the next one being *written* was CERT-589's subject
    # (`cf97a474`), which has held a GREEN token, unmerged, since 17:19Z and
    # survived four integrator sweeps. INT-190 asked for it to be rebased.
    #
    # It does not need to be. `cf97a474` adds 588 lines to THIS ONE FILE, and
    # `tests/lib_clock_anchor.py` is that same grammar lifted out and generalised
    # over the anchor NAME — same refusals (IfExp/BoolOp/Compare/Subscript/
    # comprehension/lambda), same runtime tracking check, and a name parameter
    # `cf97a474` could not have because it was hardcoded to `NOW`.
    #
    # So the anchor stays as master has it and the grammar layers over it, which
    # is exactly the resolution INT-190 asked for — reached by adding this file
    # to the guard rather than by a conflict-prone rebase of a superseded
    # implementation. Disposition for CERT-589 is written up in CODEX-REPORT-2.md.
    "test_sentinel_durable_evidence_298.py": "NOW",
}

#: Module-scope instants that are genuinely calendar FACTS rather than fixtures
#: measured against a rolling bound. An exemption is per-date and per-file; the
#: battery pins that an exemption for one date does not wave through another.
ALLOWED_LITERALS = {
    # `NOW` here is frozen on purpose — the file asks what the majors calendar
    # says at a fixed point between the 2026 and 2027 editions, which is a
    # question about a static config file and not about how far away "now" is.
    # The one assertion in this file that DID measure against the moving clock
    # was the Masters `next_edition` date, and LAT-P181 moved that reminder out
    # to `horizon_sentinel` where it files an issue instead of blocking deploys.
    "test_competition_identity.py": ("2026, 8, 12, 17, 0",),
}

_LITERAL_GUARDED = sorted(set(ANCHORS) | set(ALLOWED_LITERALS))


@pytest.mark.parametrize("rel", sorted(ANCHORS))
def test_each_repaired_anchor_is_still_clock_derived(rel):
    """The repair itself, pinned in the file it was made in."""
    assert_anchor_is_clock_derived(_read(rel), ANCHORS[rel])


@pytest.mark.parametrize("rel", _LITERAL_GUARDED)
def test_no_guarded_file_regrows_a_module_scope_instant(rel):
    """The FIELD half — measured as the more common of the two shapes.

    `test_feed_concept_single_scan.py` derived its anchor from the clock
    perfectly and still had a fuse, because one row of its specimen carried a
    hardcoded `resolution_date`. An anchor check alone would have passed it.
    """
    assert_no_absolute_date_literals(_read(rel), allow=ALLOWED_LITERALS.get(rel, ()))


# --- Negative controls ---------------------------------------------------------
#
# 🔴 EACH ONE RE-INTRODUCES THE EXACT LITERAL THE REPAIR REMOVED, into the REAL
# file's real text, and requires the guard to refuse it. Three cycles running,
# this lane's negative controls have caught the author rather than the code, so
# these are not optional and they assert their own substitution landed: a
# `replace()` that matched nothing would leave the source already-good and the
# `pytest.raises` would fail for a reason that has nothing to do with the guard.

#: ``rel`` -> (the string as it stands today, the literal that used to be there).
RE_PINS = {
    "test_gold_label_store_convergence.py": (
        "NOW = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(microsecond=0)",
        "NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)",
    ),
    "test_golf_tour_badge_uxp185.py": (
        "_FEED_NOW = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(microsecond=0)",
        "_FEED_NOW = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)",
    ),
    # The literal that actually detonated on 2026-08-31, restored verbatim. If
    # any control in this file has to keep working, it is this one.
    "test_sentinel_durable_evidence_298.py": (
        "NOW = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(microsecond=0)",
        "NOW = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)",
    ),
}


@pytest.mark.parametrize("rel", sorted(RE_PINS))
def test_re_pinning_a_real_anchor_is_refused(rel):
    current, historical = RE_PINS[rel]
    src = _read(rel)
    assert src.count(current) == 1, (
        f"{rel}: the anchor this control mutates is not present exactly once — "
        "the control is not testing what it claims. Re-read the file and update "
        "RE_PINS rather than deleting this assertion."
    )
    mutated = src.replace(current, historical)
    assert mutated != src, "the mutation did not apply"
    with pytest.raises(AssertionError):
        assert_anchor_is_clock_derived(mutated, ANCHORS[rel])


def test_re_pinning_a_real_specimen_FIELD_is_refused():
    """The field half's control, on the file that actually had this bug."""
    rel = "test_feed_concept_single_scan.py"
    current = '"resolution_date": CYCLING_RESOLUTION,'
    historical = '"resolution_date": datetime(2026, 9, 14, tzinfo=timezone.utc),'
    src = _read(rel)
    assert src.count(current) == 1, f"{rel}: specimen field not found exactly once"
    mutated = src.replace(current, historical)
    assert mutated != src, "the mutation did not apply"
    with pytest.raises(AssertionError, match="2026, 9, 14"):
        assert_no_absolute_date_literals(mutated)
    # ...and the anchor check must NOT be what catches it, or this control is
    # really the previous one wearing a different name.
    assert_anchor_is_clock_derived(mutated, "NOW")


def test_the_exemption_list_is_not_a_blanket():
    """An allow-list entry must exempt its own date and nothing else.

    Without this, `ALLOWED_LITERALS` could quietly grow into "this file is not
    checked", which is how an exemption becomes a hole.
    """
    rel = "test_competition_identity.py"
    src = _read(rel)
    planted = src + "\n_PLANTED = datetime(2029, 3, 1, tzinfo=timezone.utc)\n"
    with pytest.raises(AssertionError, match="2029, 3, 1"):
        assert_no_absolute_date_literals(planted, allow=ALLOWED_LITERALS[rel])
