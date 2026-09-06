"""No row is created from a provider id we made up. #2963.

PILLAR: MATCHING. SHIP: nothing goes blank when ESPN does — but only if the
StatPal side of the join is real. `events.statpal_fixture_id` is what ~11 readers
test to decide "is this event linked to StatPal?", and it is the column the NFL
flip gate's `polluted_column` count is taken over.

THE DEFECT, as it shipped
═════════════════════════
`_sync_statpal_schedules` created events for live fixtures with:

    claim_id = live_fix.fixture_id or f"statpal_live_{home}_{away}"

That `or` fabricated a provider id out of two team names whenever StatPal served
a fixture without one. Measured on production 2026-09-06: **48 NFL rows**, every
row this path has ever created, created between 2026-05-15 and 2026-08-26. The
cause was upstream — NFL keys its id `contestid` and the parser read only `id`,
so `fixture_id` was `''` and falsy — but the `or` is what turned a parser gap
into a written lie.

WHY A FABRICATED ID IS WORSE THAN NO ROW
════════════════════════════════════════
* `EventClaim.anchor_source_id` is documented as *"the id an anchor key must be
  built from — the provider's, never ours"* and returns `provider_id or
  source_id`. A synthesized `source_id` with no `provider_id` hands the anchor
  channel a game key made of team names — the one shape that can merge two real
  fixtures (gotcha #32, ruling 048).
* It is unrepairable in place: `stamp_nfl_statpal_fixtures.classify_fixture`
  returns `POLLUTED_COLUMN` for such a row and refuses to write, so the row can
  never receive its real contest id while the fabricated value sits there.

So the rule is: **no id, no row, and count the refusal.**

WHAT THESE GUARDS ARE FOR
═════════════════════════
The behavioural half pins the predicate. The structural half pins the *shape* of
the call site, because the defect was a single `or` and a future edit that
reintroduces one would satisfy every behavioural test written against a fixture
that happens to carry an id. A structural guard is only worth having if it fires
on the real historical code, so `TestTheGuardFiresOnTheCodeThatShipped` runs the
same detector over the verbatim shipped expression and requires a hit.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from app.tasks.statpal_sync import statpal_provided_an_id

SOURCE_PATH = (
    pathlib.Path(__file__).resolve().parents[1] / "app/tasks/statpal_sync.py"
)

#: The expression as production ran it, verbatim. This is the control's input.
SHIPPED_EXPRESSION = (
    'claim_id = live_fix.fixture_id or '
    'f"statpal_live_{live_fix.home_team}_{live_fix.away_team}"'
)


def fabricated_id_offenders(source: str) -> list[str]:
    """Assignments that build an id out of anything but the provider's own field.

    Structural, not textual: it walks assignments and flags any whose value is a
    BoolOp (`a or b`) or an f-string. Text matching on `statpal_live_` would be
    defeated by the next fabrication choosing a different prefix — and the prefix
    is the least interesting thing about the bug.
    """
    offenders: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(t, ast.Name) and t.id in ("claim_id", "source_id", "provider_id")
            for t in node.targets
        ):
            continue
        value = node.value
        if isinstance(value, ast.BoolOp) and isinstance(value.op, ast.Or):
            offenders.append(f"line {node.lineno}: `or` fallback builds the id")
        elif isinstance(value, ast.JoinedStr):
            offenders.append(f"line {node.lineno}: f-string builds the id")
    return offenders


class TestThePredicate:
    """`statpal_provided_an_id` — the judgement, driven directly."""

    @pytest.mark.parametrize("value", [None, "", "   ", "\t\n"])
    def test_nothing_is_not_an_id(self, value):
        """`''` is the one that matters: it is what the parser produces when it
        recognises no id key, and 8,272 rows once carried it as a linkage."""
        assert statpal_provided_an_id(value) is False

    @pytest.mark.parametrize("value", ["280500", "1329192542", "2631673"])
    def test_a_real_statpal_id_is_an_id(self, value):
        """Real ids measured across the four id spaces — NFL 6-digit contestid,
        MLB 10-digit, tennis 7-digit. THE CONTROL: without this the predicate
        could return False for everything and every other test would still pass."""
        assert statpal_provided_an_id(value) is True

    def test_it_does_not_judge_the_shape_of_the_id(self):
        """Deliberately not a digit check. D55 removed digit-counting from anchor
        keys because a length rule gives a confident wrong answer the moment a new
        sport arrives; this predicate answers "did they give us one", nothing more."""
        assert statpal_provided_an_id("abc-123") is True


class TestTheCallSite:
    """The shape of the shipping code, not just its behaviour on one input."""

    def test_no_assignment_fabricates_an_id(self):
        offenders = fabricated_id_offenders(SOURCE_PATH.read_text())
        assert offenders == [], (
            f"{offenders} — an id assigned from an `or` fallback or an f-string is "
            "an id we invented. `EventClaim.anchor_source_id` must be the "
            "provider's, never ours (#2963). If StatPal served no id, refuse the "
            "create and count it; do not synthesize one."
        )

    @pytest.mark.parametrize(
        "counter",
        ["live_created_refused_no_provider_id", "schedule_created_refused_no_provider_id"],
    )
    def test_each_refusal_is_counted_and_always_reported(self, counter):
        """0 must be a reading, not an absence (gotcha #53). An absent key makes
        "the fabricator is unreachable" indistinguishable from "nobody looked"."""
        src = SOURCE_PATH.read_text()
        assert f"{counter} = 0" in src
        assert f'"{counter}": {counter},' in src

    @pytest.mark.parametrize(
        "call", ["live_fix.fixture_id", "fixture.fixture_id"],
    )
    def test_both_create_branches_consult_the_predicate(self, call):
        """BOTH paths, and the second one is the reason this guard is structural.
        The live path was the one with 48 rows behind it and the one a textual
        `statpal_live_` scan would have found; the schedule path fabricated under a
        different prefix and was found only by walking the assignments."""
        assert f"if not statpal_provided_an_id({call}):" in SOURCE_PATH.read_text()


class TestTheGuardFiresOnTheCodeThatShipped:
    """THE CONTROL. A structural guard that cannot catch the real defect is a
    test that passes because it is toothless, and this file would be worthless
    without it."""

    def test_the_shipped_or_fallback_is_caught(self):
        offenders = fabricated_id_offenders(SHIPPED_EXPRESSION)
        assert offenders, (
            "The detector did not fire on the exact expression that produced 48 "
            f"fabricated NFL ids:\n    {SHIPPED_EXPRESSION}"
        )

    def test_a_bare_fstring_id_is_caught_too(self):
        """The next fabrication need not use `or`, and need not use this prefix."""
        assert fabricated_id_offenders('claim_id = f"{home}_{away}"')

    def test_reading_the_providers_field_is_not_an_offence(self):
        """The counter-case. A guard that reds the correct code gets the guard
        deleted, not the code fixed."""
        assert fabricated_id_offenders("claim_id = live_fix.fixture_id") == []
