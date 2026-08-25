"""CAL-P092 — the publisher→after-read guard, and the mutation that must stay red.

Consumes ``C-APPLY-PRE-1912-R3-R3`` [P1]:

    "the census counts prose, not a publisher-to-reader relationship, so its
    claimed structural closure is false … replace source-string equality with an
    AST/callgraph rule that identifies every publisher call's enclosing function
    and requires a consumer-facing read on every successful return path, plus
    retain the injected-fifth-site mutation as a red test."

Both halves are here. :class:`TestTheRailIsProved` is the guard; everything below
it is the guard's own oracle — the shapes it MUST reject, headed by the cert's
own mutation, so this file can never again pass by counting a comment.

The rule and its stated limits live in ``tests/lib_publisher_after_read.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.lib_publisher_after_read import (
    PUBLISHER_NAMES,
    READER_NAMES,
    audit_module,
    describe,
    reader_reaching_functions,
)

RAIL = Path(__file__).resolve().parents[1] / "app" / "tasks" / "repair_pm_never_graded.py"

#: The four durability writers as of CAL-P085. A census, not a threshold: if a
#: fifth arrives it must arrive WITH a read, and this list must be widened
#: deliberately rather than the assertion loosened.
KNOWN_PUBLISHER_FUNCTIONS = {
    "_save_plan",
    "_save_obligation",
    "_raise_wave_halt",
    "_save_progress",
}


@pytest.fixture(scope="module")
def rail_source() -> str:
    return RAIL.read_text()


class TestTheRailIsProved:
    """The shipping rail, under the real rule."""

    def test_every_publisher_call_has_a_dominating_consumer_read(self, rail_source):
        result = audit_module(rail_source, filename=str(RAIL))
        assert result["violations"] == [], (
            "a durable write acknowledges and returns success without reading it "
            "back:\n" + describe(result["violations"])
        )
        assert result["sites"], "no publisher call found at all — the seam moved"

    def test_the_publisher_census_is_the_four_known_writers(self, rail_source):
        result = audit_module(rail_source, filename=str(RAIL))
        assert set(result["publisher_functions"]) == KNOWN_PUBLISHER_FUNCTIONS, (
            "the publisher census moved. A NEW writer is not a reason to edit this "
            "set until it passes the rule above; a REMOVED one is not a reason to "
            "lower it. Re-derive it, do not relax it."
        )

    def test_the_reader_is_reached_transitively_not_inlined(self, rail_source):
        """`_save_plan` calls `_load_plan` calls `read_snapshot_standalone`.

        Recorded as a fact about the rail, because it is the reason the rule is a
        callgraph closure and not a one-hop check.
        """
        reaching = reader_reaching_functions(ast.parse(rail_source))
        for helper in ("_load_plan", "_load_obligation", "_wave_halt_state", "_load_progress"):
            assert helper in reaching, f"{helper} no longer reaches a durable read"


# =============================================================================
# The guard's oracle — the shapes it must REJECT
# =============================================================================


def _module(body: str) -> str:
    return "from app.services.durable_snapshots import (\n" \
           "    publish_snapshot_standalone,\n    read_snapshot_standalone,\n)\n" + body


#: The cert's mutation, reproduced in the shape the old census was proved to
#: bless: a fifth publisher call formatted so ``count("publish_snapshot_standalone(\n")``
#: sees it, no read of any kind, and one ``# after-read proved`` comment.
CERT_FIFTH_SITE = '''

async def _save_fifth_thing(payload):
    result = await publish_snapshot_standalone(
        payload
    )
    if result.get("status") not in ("ok", "superseded"):
        return False, "fifth persist rejected"
    # after-read proved
    return True, "ok"
'''


class TestACommentCanNeverSatisfyTheGuardAgain:
    """The permanent red test. Deleting it re-opens the exact hole R3-R3 found."""

    def test_the_injected_fifth_site_is_rejected(self, rail_source):
        mutated = rail_source + CERT_FIFTH_SITE
        result = audit_module(mutated, filename="mutated")

        assert "_save_fifth_thing" in result["publisher_functions"]
        offenders = {v.function for v in result["violations"]}
        assert offenders == {"_save_fifth_thing"}, (
            "the AST rule must reject the acknowledgement-only fifth writer and "
            "nothing else:\n" + describe(result["violations"])
        )
        assert result["violations"][0].kind == "no_dominating_read"

    def test_the_old_string_census_would_have_passed_it(self, rail_source):
        """The reason this file exists, asserted rather than remembered.

        This reproduces the RETIRED guard inline and proves it green on the very
        mutation the new rule rejects. If a future edit ever swaps the AST rule
        back for a source count, this test is the receipt that the swap is a
        regression and not a simplification.
        """
        mutated = rail_source + CERT_FIFTH_SITE
        publishes = mutated.count("publish_snapshot_standalone(\n")
        proved = mutated.count("after-read proved")

        assert publishes >= 4
        assert proved == publishes, (
            "the retired census no longer reproduces its own failure mode — "
            "re-derive the mutation so the comparison stays honest"
        )
        # ...and the real rule disagrees with it.
        assert audit_module(mutated)["violations"], (
            "the string census passes this mutation and the AST rule must not"
        )

    def test_adding_a_real_read_makes_the_same_site_pass(self, rail_source):
        """The control. A guard that rejects everything proves nothing."""
        fixed = rail_source + '''

async def _save_fifth_thing(payload):
    result = await publish_snapshot_standalone(
        payload
    )
    if result.get("status") not in ("ok", "superseded"):
        return False, "fifth persist rejected"
    stored = await read_snapshot_standalone("fifth")
    if stored is None:
        return False, "fifth persist UNPROVED"
    return True, "ok (after-read proved)"
'''
        assert audit_module(fixed)["violations"] == []


class TestTheDominanceRuleIsRealDominance:
    """"Somewhere in the function" is not the rule — these are the differences."""

    def test_a_read_in_only_one_branch_does_not_prove_the_other(self):
        source = _module('''
async def _save(payload, verify):
    await publish_snapshot_standalone(payload)
    if verify:
        stored = await read_snapshot_standalone("x")
        if stored is None:
            return False, "unproved"
    return True, "ok"
''')
        violations = audit_module(source)["violations"]
        assert [v.kind for v in violations] == ["no_dominating_read"]

    def test_a_read_in_both_branches_does_prove_it(self):
        source = _module('''
async def _save(payload, verify):
    await publish_snapshot_standalone(payload)
    if verify:
        stored = await read_snapshot_standalone("x")
    else:
        stored = await read_snapshot_standalone("y")
    if stored is None:
        return False, "unproved"
    return True, "ok"
''')
        assert audit_module(source)["violations"] == []

    def test_a_read_inside_a_loop_never_dominates(self):
        """A loop may run zero times, so its body proves nothing about the exit."""
        source = _module('''
async def _save(payload, keys):
    await publish_snapshot_standalone(payload)
    for key in keys:
        await read_snapshot_standalone(key)
    return True, "ok"
''')
        assert [v.kind for v in audit_module(source)["violations"]] == [
            "no_dominating_read"
        ]

    def test_a_read_in_a_try_whose_handler_swallows_does_not_dominate(self):
        """The handler falls through to the success return with nothing read."""
        source = _module('''
async def _save(payload):
    await publish_snapshot_standalone(payload)
    try:
        await read_snapshot_standalone("x")
    except Exception:
        pass
    return True, "ok"
''')
        assert [v.kind for v in audit_module(source)["violations"]] == [
            "no_dominating_read"
        ]

    def test_a_read_in_a_try_whose_handler_returns_does_dominate(self):
        """The rail's real shape: the handler cannot reach the success return."""
        source = _module('''
async def _save(payload):
    await publish_snapshot_standalone(payload)
    try:
        stored = await read_snapshot_standalone("x")
    except Exception:
        return False, "after-read raised"
    if stored is None:
        return False, "unproved"
    return True, "ok"
''')
        assert audit_module(source)["violations"] == []

    def test_a_read_BEFORE_the_publisher_does_not_count(self):
        """It is an AFTER-read. A stale read proves the write happened to nothing."""
        source = _module('''
async def _save(payload):
    stored = await read_snapshot_standalone("x")
    await publish_snapshot_standalone(payload)
    return True, "ok"
''')
        assert [v.kind for v in audit_module(source)["violations"]] == [
            "no_dominating_read"
        ]


class TestTheGuardFailsClosedOnWhatItCannotRead:
    """An exemption for the unrecognised shape is how the sixth site gets in."""

    def test_an_unclassifiable_return_is_a_violation_not_a_pass(self):
        source = _module('''
def _ok():
    return True, "ok"


async def _save(payload):
    await publish_snapshot_standalone(payload)
    return _ok()
''')
        violations = audit_module(source)["violations"]
        assert [v.kind for v in violations] == ["unclassifiable_return"]

    def test_a_nested_helper_return_is_not_the_outer_functions_return(self):
        """`_save_progress` has an inner `return int(v)`; it is not a success path."""
        source = _module('''
async def _save(payload):
    await publish_snapshot_standalone(payload)

    def _coerce(v):
        return int(v)

    stored = await read_snapshot_standalone("x")
    if stored is None:
        return False, "unproved"
    return True, _coerce(1)
''')
        assert audit_module(source)["violations"] == []

    def test_a_nested_def_that_reads_has_not_read_anything(self):
        """Defining a reader is not calling one."""
        source = _module('''
async def _save(payload):
    await publish_snapshot_standalone(payload)

    async def _verify():
        return await read_snapshot_standalone("x")

    return True, "ok"
''')
        assert [v.kind for v in audit_module(source)["violations"]] == [
            "no_dominating_read"
        ]

    def test_a_publisher_reached_through_a_helper_is_still_the_helpers_site(self):
        """Attribution follows the CALL, so the rule lands on the function that writes."""
        source = _module('''
async def _write(payload):
    await publish_snapshot_standalone(payload)
    return True, "ok"


async def _save(payload):
    return await _write(payload)
''')
        result = audit_module(source)
        assert set(result["publisher_functions"]) == {"_write"}
        assert [v.function for v in result["violations"]] == ["_write"]


class TestTheSeamsAreNamedNotInferred:
    def test_the_publisher_and_reader_names_are_disjoint_and_nonempty(self):
        assert PUBLISHER_NAMES and READER_NAMES
        assert not (PUBLISHER_NAMES & READER_NAMES)

    def test_a_function_local_import_is_still_seen(self, rail_source):
        """The rail imports the publisher INSIDE each function.

        A module-level import census would have found zero call sites and
        reported the rail clean — the failure mode this rule had to avoid.
        """
        tree = ast.parse(rail_source)
        module_level = {
            alias.name
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        assert not (module_level & PUBLISHER_NAMES)
        assert audit_module(rail_source)["sites"]
