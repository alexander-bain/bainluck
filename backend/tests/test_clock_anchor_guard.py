"""The anchor guard's own control: every disclosed attack, and each must raise.

🔴 WHY THIS FILE EXISTS AT ALL. Four of the five certs that attacked the original
anchor found the ANCHOR fine and the GUARD hollow, and every one of them landed
on a **green** suite. A guard nobody has watched fail is a guard nobody knows the
shape of, and a broken redundant check is worse than no check because it is
counted as one.

So every known attack is pinned here as a source string. The list only grows — an
attack that has been closed still runs, because the cheapest way to reopen one is
to rewrite the guard for the next.

In memory, never on disk: ``scripts/evals/_mutation_guard.py`` says an in-process
harness that mutates a STRING is strictly the better design because it cannot
leave residue in a real file, and nothing here needs a file.
"""

from __future__ import annotations

import ast

import pytest

from tests.lib_clock_anchor import (
    assert_anchor_grammar,
    assert_anchor_is_clock_derived,
    assert_no_absolute_date_literals,
)

REAL = "NOW = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(microsecond=0)"
LITERAL = "NOW = datetime(2026, 8, 31, 12, 53, 0, tzinfo=timezone.utc)"

#: Every disclosed way a hardcoded instant has hidden from a guard that had
#: already seen a real clock call. Keyed by the cert that found it.
ATTACKS = {
    # CERT-568: swap the clock call for a timestamp that is fresh TODAY. This is
    # the one that proves a guard against hardcoding cannot itself be a check on
    # the value — any value test is satisfied by a value.
    "CERT-568 fresh literal replaces the clock call": LITERAL,
    # CERT-571: leave the clock call in place and override it below. Python uses
    # the LAST binding executed; a first-binding scan certifies a dead statement.
    "CERT-571 a later assignment shadows it": f"{REAL}\n{LITERAL}",
    "CERT-571 an annotated later assignment shadows it": (
        f"{REAL}\nNOW: datetime = datetime(2026, 8, 31, 12, 53, 0, tzinfo=timezone.utc)"
    ),
    # CERT-577: "module level" is a SCOPE, not a depth. Both of these execute at
    # module scope and both are invisible to a `tree.body` walk.
    "CERT-577 a rebinding nested under `if`": f"{REAL}\nif True:\n    {LITERAL}",
    "CERT-577 a rebinding nested under `try`": (
        f"{REAL}\ntry:\n    {LITERAL}\nexcept Exception:\n    pass"
    ),
    "CERT-577 a rebinding nested two levels down": (
        f"{REAL}\nif True:\n    if True:\n        {LITERAL}"
    ),
    # The same class through the other binding forms, which are stores rather
    # than assignment statements.
    "a `for` target rebinds it": (
        f"{REAL}\nfor NOW in [datetime(2026, 8, 31, tzinfo=timezone.utc)]:\n    pass"
    ),
    "a `with ... as` target rebinds it": (
        f"{REAL}\nimport contextlib\n"
        "with contextlib.nullcontext(datetime(2026, 8, 31, tzinfo=timezone.utc)) as NOW:"
        "\n    pass"
    ),
    # 🔴 CERT-581's class, and the reason the guard RUNS the anchor instead of
    # reading it. Every one of these is a single module-level plain assignment
    # whose right-hand side genuinely contains a `datetime.now(...)` call — and
    # in every one the call's result is thrown away and a constant binds. No
    # source scan can separate these from the real thing; evaluating them
    # against a moving clock separates them instantly.
    "CERT-581 an unreachable clock branch fronts a fixed value": (
        "NOW = datetime.now(timezone.utc) if False else "
        "datetime.fromtimestamp(1756645980, tz=timezone.utc)"
    ),
    "CERT-581 a short-circuit discards the clock call": (
        "NOW = datetime.fromtimestamp(1756645980, tz=timezone.utc) "
        "or datetime.now(timezone.utc)"
    ),
    "CERT-581 the clock call is an unused list element": (
        "NOW = [datetime.now(timezone.utc), "
        "datetime.fromtimestamp(1756645980, tz=timezone.utc)][1]"
    ),
    # The partial-derivation case: it moves with the clock but not by the clock's
    # own step, so it is not a fixed distance behind `now` and can still drift
    # across the bound. Grammatically LEGAL — the one the grammar cannot see and
    # only the runtime check kills.
    "only the date follows the clock, the time is pinned": (
        "NOW = datetime.now(timezone.utc).replace(year=2026, month=8, day=31)"
    ),
    # 🔴 CERT-583's move: recognise the calendar the oracle samples in. Behaviour
    # at N points is behaviour at N points.
    "CERT-583 a conditional gated on the sampled calendar": (
        "NOW = (datetime.now(timezone.utc) - timedelta(minutes=1)) "
        "if datetime.now(timezone.utc).year == 2031 "
        "else datetime(2026, 8, 31, 12, 53, 0, tzinfo=timezone.utc)"
    ),
    "CERT-583 a comparison selects between clock and constant": (
        "NOW = [datetime(2026, 8, 31, tzinfo=timezone.utc), "
        "datetime.now(timezone.utc)][datetime.now(timezone.utc).year == 2031]"
    ),
    "CERT-583 a dict lookup selects between clock and constant": (
        "NOW = {True: datetime.now(timezone.utc), "
        "False: datetime(2026, 8, 31, tzinfo=timezone.utc)}"
        "[datetime.now(timezone.utc).year > 2030]"
    ),
    "CERT-583 an unapproved call launders the constant": (
        "NOW = min(datetime.now(timezone.utc), datetime(2026, 8, 31, tzinfo=timezone.utc))"
    ),
    # 🔴 THE ONE THAT PROVES THE GRAMMAR IS WIRED IN, AND THE ONLY ENTRY HERE
    # THAT IS NOT ITSELF A BOMB. It tracks the clock perfectly, so the runtime
    # check passes it; the grammar refuses it because it SELECTS, and selection
    # is the mechanism every real attack above used. Without this entry, deleting
    # the `assert_anchor_grammar` call would leave this whole control GREEN — the
    # grammar has a test of its own below which calls it DIRECTLY and so cannot
    # see that the call site is gone. That is a containment check satisfied by a
    # sibling call site, and it is why a policy refusal has to be pinned at the
    # point the policy is APPLIED, not only where it is defined.
    "a benign-looking selection, refused on principle": (
        "NOW = [(datetime.now(timezone.utc) - timedelta(minutes=1)).replace(microsecond=0)][0]"
    ),
}


@pytest.mark.parametrize("label", sorted(ATTACKS))
def test_every_disclosed_attack_is_refused(label):
    with pytest.raises(AssertionError):
        assert_anchor_is_clock_derived(ATTACKS[label], "NOW")


def test_the_real_anchor_still_passes():
    """The control's control: without this, every `raises` above could be passing
    for an unrelated reason — a typo in the guard would refuse everything."""
    assert_anchor_is_clock_derived(REAL, "NOW")


def test_the_scope_rule_cuts_both_ways():
    """A binding inside a FUNCTION or CLASS is a local and must NOT trip the guard,
    or the next author cannot write a helper."""
    assert_anchor_is_clock_derived(f"{REAL}\ndef _helper():\n    NOW = 1\n    return NOW", "NOW")
    assert_anchor_is_clock_derived(f"{REAL}\nclass _C:\n    NOW = 2", "NOW")


@pytest.mark.parametrize(
    "src",
    [
        # 🔴 POSITIVE CONTROLS THAT PROVE IT IS NOT PATTERN-MATCHING `datetime.now`.
        # The original check accepted an anchor because the letters `now` appeared
        # in its AST; a replacement doing the same thing by another route would
        # reject these, which are all honestly clock-derived and none of which
        # spell `datetime.now(...)` in that shape.
        "NOW = datetime.fromtimestamp(time.time(), tz=timezone.utc)",
        "NOW = datetime.now(timezone.utc) - timedelta(hours=6)",
        "NOW = (datetime.utcnow() - timedelta(minutes=2)).replace(microsecond=0, tzinfo=timezone.utc)",
        "NOW = datetime.now(timezone.utc) + timedelta(seconds=-30)",
    ],
)
def test_honestly_derived_anchors_are_permitted(src):
    assert_anchor_is_clock_derived(src, "NOW")


def test_the_guard_is_generalised_over_the_NAME():
    """The whole reason this is a shared module: five files, five anchor names.

    A guard hardcoded to `NOW` silently passes a file whose anchor is called
    `_FEED_NOW` — it would report "binding not found", and a guard that cannot
    find its subject must say so rather than shrug.
    """
    assert_anchor_is_clock_derived(REAL.replace("NOW", "_FEED_NOW"), "_FEED_NOW")
    with pytest.raises(AssertionError, match="binding not found"):
        assert_anchor_is_clock_derived(REAL, "_FEED_NOW")


def test_the_GRAMMAR_half_can_actually_FAIL():
    """The grammar gets its own control, because the combined one cannot give it one.

    🔴 THIS EXISTS BECAUSE THE OBVIOUS CONTROL WAS VACUOUS. Deleting
    `assert_anchor_grammar` from `assert_anchor_is_clock_derived` left the attack
    battery **green**: every attack there is also caught by the runtime tracking
    check, so the grammar's failure path was never executed by anything.
    """
    def rhs(src):
        return ast.parse(src).body[0].value

    refused = {
        "conditional": "x = a if c else b",
        "boolean short-circuit": "x = datetime.now(timezone.utc) or b",
        "subscript": "x = [datetime.now(timezone.utc)][0]",
        "comparison": "x = datetime.now(timezone.utc).year == 2031",
        "comprehension": "x = [datetime.now(timezone.utc) for _ in (1,)][0]",
        "lambda": "x = (lambda: datetime.now(timezone.utc))()",
        "unapproved call": "x = min(datetime.now(timezone.utc), b)",
        "bare datetime constructor": "x = datetime(2026, 8, 31, tzinfo=timezone.utc)",
        "no clock read at all": "x = timedelta(minutes=1)",
    }
    for label, src in refused.items():
        with pytest.raises(AssertionError):
            assert_anchor_grammar(rhs(src), label)

    # And the shapes a real anchor needs must survive, or the grammar is
    # rejecting the thing it exists to permit.
    for src in (
        "x = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(microsecond=0)",
        "x = datetime.now(timezone.utc)",
        "x = datetime.fromtimestamp(time.time(), tz=timezone.utc)",
        "x = (datetime.utcnow() - timedelta(minutes=2)).replace(tzinfo=timezone.utc)",
        "x = datetime.now(timezone.utc) + timedelta(seconds=-30)",
    ):
        assert_anchor_grammar(rhs(src))


# --- The fixture-literal half -------------------------------------------------


def test_a_literal_in_a_FIELD_is_caught_even_when_the_anchor_is_honest():
    """Measured as the MORE common shape of the two.

    `tests/test_feed_concept_single_scan.py` derived its anchor from the clock
    correctly and still had a fuse, because one row of its specimen carried
    `datetime(2026, 9, 14)` as a resolution date. The anchor guard cannot see
    that; nothing binds it to a name it is asked about.
    """
    src = (
        f"{REAL}\n"
        "MARKETS = ({'commence_time': NOW, "
        "'resolution_date': datetime(2026, 9, 14, tzinfo=timezone.utc)},)"
    )
    assert_anchor_is_clock_derived(src, "NOW")  # the anchor really is fine
    with pytest.raises(AssertionError, match="2026, 9, 14"):
        assert_no_absolute_date_literals(src)


def test_offsets_from_the_anchor_are_permitted():
    src = (
        f"{REAL}\n"
        "MARKETS = ({'commence_time': NOW + timedelta(days=2), "
        "'resolution_date': NOW + timedelta(days=13)},)"
    )
    assert_no_absolute_date_literals(src)


def test_a_literal_inside_a_FUNCTION_is_not_module_scope():
    """Scope, again. A date built inside a helper is that helper's business."""
    assert_no_absolute_date_literals(
        f"{REAL}\ndef _historical():\n    return datetime(1997, 4, 13, tzinfo=timezone.utc)"
    )


def test_the_allow_list_is_an_exemption_not_a_hole():
    src = f"{REAL}\nMASTERS_1997 = datetime(1997, 4, 13, tzinfo=timezone.utc)"
    with pytest.raises(AssertionError):
        assert_no_absolute_date_literals(src)
    assert_no_absolute_date_literals(src, allow=("1997, 4, 13",))
    # ...and an exemption for one date must not wave through a different one.
    with pytest.raises(AssertionError):
        assert_no_absolute_date_literals(
            f"{src}\nOTHER = datetime(2026, 9, 14, tzinfo=timezone.utc)",
            allow=("1997, 4, 13",),
        )
