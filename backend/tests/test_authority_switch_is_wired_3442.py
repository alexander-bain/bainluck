"""What reading the authority switch actually does, kept true by a tree walk.

#3442, amended by #3473. `AUTHORITY_BY_SPORT` is the one-line-per-sport flip
described by program step 6. When this file was written **exactly one module
under `app/` read it: the admin route that reports its own value** — so changing
a line changed one string on an admin page and nothing else, and the row said so
in a derived `INERT` note.

That was not a defect; a dark switch is what step 6 built. The note existed
because of WHEN it would stop being harmless. NFL, NBA and NHL all read gate
`MEETS` at day 2 of 7 on production (2026-09-06 05:44Z), so the earliest a
genuine seven exists is around 2026-09-11 — and on that day someone would read a
YOUR-TURN entry, edit one line, see the row change from `espn` to `statpal`, and
reasonably conclude the site now ran on StatPal for that sport.

**THE NOTE HAS NOW BEEN RETIRED BY THE THING IT WAS WAITING FOR.** Program step
7 (#3473) wired `app.utils.authority_failover`, which reads `authority_for` to
decide who serves a sport on a pass where ESPN went silent. The docstring above
used to end "wiring a real consumer fails these tests — that is the intended
cost"; this is that cost being paid, in the same diff as the wiring, which is
the whole point of a derived disclosure. What each test asserts about *today*
moved; what the file guards did not:

  * the declared set and the tree must agree, in both directions;
  * the published note is DERIVED from the set, never written twice;
  * `switch_is_wired` still answers False for a tree of reporters only, so the
    predicate has not simply become "return True".

The walk uses the `ast` module and never a grep, because a
`from app.config.authority_by_sport import (\\n    authority_for,\\n)` wrapped
across lines defeats a substring scan, and an import written that way is what
the linter produces.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.config.authority_by_sport import (
    AUTHORITY_BY_SPORT,
    DEFAULT_AUTHORITY,
    ESPN,
    FLIP_EVIDENCE,
    FLIP_RULED_WITHOUT_STREAK,
    STATPAL,
    SWITCH_ACTOR_SERVES,
    SWITCH_CONSUMERS,
    SWITCH_IS_WIRED,
    SWITCH_REPORTERS,
    SWITCH_WIRING_NOTE,
    switch_is_wired,
    switch_wiring_note,
)

APP = Path(__file__).resolve().parent.parent / "app"

#: The task that acts on the switch, and the function inside it that decides
#: what a flipped sport gets. Named here rather than inline so the walk below
#: fails loudly if either is renamed, instead of finding nothing and passing.
ACTOR_PATH = APP / "tasks" / "espn_sync.py"
ACTOR_FUNCTION = "_act_on_failovers"

#: The prefix every StatPal-serving helper in `espn_sync` shares
#: (`_serve_schedule_from_statpal`, `_serve_live_from_statpal`). A prefix rather
#: than the two names, so adding a third writer to the branch keeps reading as
#: serving without anyone having to update this file.
WRITER_PREFIX = "_serve_"

#: The LIVE half specifically, and it needs its own name because `WRITER_PREFIX`
#: cannot tell the two writers apart (CERT-2552's non-blocking follow-up).
#: `_serve_live_from_statpal` is the only writer under it; a prefix keeps a
#: rename of the `_from_statpal` suffix from silently finding nothing, and a
#: rename of `_serve_live` itself reads as NOT reaching, which fails loudly
#: against the declaration rather than passing vacuously.
LIVE_WRITER_PREFIX = "_serve_live"

CONFIG_MODULE = "app.config.authority_by_sport"

#: The names that, imported from the config, mean "this module reads the switch".
#: `ESPN`/`STATPAL` are excluded on purpose: they are string constants a module
#: may compare against without consulting the switch at all.
SWITCH_NAMES = frozenset({"AUTHORITY_BY_SPORT", "DEFAULT_AUTHORITY", "authority_for"})


def _module_name(path: Path) -> str:
    return "app." + ".".join(path.relative_to(APP).with_suffix("").parts)


def _reads_the_switch(tree: ast.AST) -> bool:
    """Does this module import a switch-reading name from the config?

    An AST walk, so it sees a multi-line import, an aliased one (`authority_for
    as af`) and one nested inside a function — which is how the admin route
    writes it — identically. A regex over the source sees the first and third
    only if the author happened to keep them on one line.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == CONFIG_MODULE and any(
                alias.name in SWITCH_NAMES for alias in node.names
            ):
                return True
        elif isinstance(node, ast.Import):
            # `import app.config.authority_by_sport` — reaches every name.
            if any(alias.name == CONFIG_MODULE for alias in node.names):
                return True
    return False


def _tests_standing_statpal(test: ast.AST) -> bool:
    """Is this `if`/`elif` the branch for an already-flipped sport?

    Matches `decision.code == STANDING_STATPAL` written either way round, and
    an `in {STANDING_STATPAL, ...}` form, because which of those the author
    picks is a style choice and none of them changes what the branch means.
    """
    if not isinstance(test, ast.Compare):
        return False
    for node in [test.left, *test.comparators]:
        for name in ast.walk(node):
            if isinstance(name, ast.Name) and name.id == "STANDING_STATPAL":
                return True
    return False


def _call_name(node: ast.Call) -> str:
    """The bare name a call is made through — `f()` and `obj.f()` alike."""
    func = node.func
    return (
        func.id if isinstance(func, ast.Name)
        else func.attr if isinstance(func, ast.Attribute)
        else ""
    )


def _dispatches_a_writer(body: list[ast.stmt]) -> bool:
    """Does this branch body call one of the StatPal-serving helpers?

    Takes the branch's `body` alone. An `elif` is a nested `If` in the previous
    branch's `orelse`, so the standing branch's own `orelse` holds everything
    that comes AFTER it in the chain — the uncovered arm and the final `else`.
    Walking the `If` node instead of its body would count a writer called in
    one of those as if the standing branch had called it, which is the reading
    that lets this guard pass while a flipped sport is served by nothing.
    """
    for statement in body:
        for node in ast.walk(statement):
            if isinstance(node, ast.Call) and _call_name(node).startswith(
                WRITER_PREFIX
            ):
                return True
    return False


def _actor_function(tree: ast.AST) -> ast.AST | None:
    """The named actor, or None — never "the first function that looks right"."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == ACTOR_FUNCTION:
                return node
    return None


def _standing_branch(function: ast.AST) -> ast.If | None:
    for node in ast.walk(function):
        if isinstance(node, ast.If) and _tests_standing_statpal(node.test):
            return node
    return None


def _accumulators_appended_to(body: list[ast.stmt]) -> set[str]:
    """The names `x` for which this branch body calls `x.append(...)`.

    The standing branch does not call the live writer; it puts the sport into a
    list that a single call after the loop consumes. That indirection is the
    whole reason `_dispatches_a_writer` cannot see the live half.
    """
    found: set[str] = set()
    for statement in body:
        for node in ast.walk(statement):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "append":
                if isinstance(func.value, ast.Name):
                    found.add(func.value.id)
    return found


def _subtree_ids(node: ast.AST) -> set[int]:
    return {id(child) for child in ast.walk(node)}


def _chain_root(function: ast.AST, branch: ast.If) -> ast.If:
    """The outermost `If` of the chain the standing branch belongs to.

    An `elif` is an `If` inside the previous arm's `orelse`, so the whole
    if/elif/else chain is one nested node and the standing branch sits some way
    down it. Everything arm-conditional lives inside this root; the coalesced
    call we are looking for is a sibling of the loop, outside it.
    """
    root = branch
    largest = len(_subtree_ids(branch))
    for node in ast.walk(function):
        if not isinstance(node, ast.If):
            continue
        ids = _subtree_ids(node)
        if id(branch) in ids and len(ids) > largest:
            root, largest = node, len(ids)
    return root


def _standing_branch_dispatches_schedule(tree: ast.AST) -> bool:
    """Does the actor's standing-sport branch call a writer directly? (#4947)

    The question `SWITCH_CONSUMERS` cannot ask. That set is built from imports,
    so it answers the same before and after #4434 — what moved was the body of
    one `elif`, and an import walk is blind to a body.
    """
    function = _actor_function(tree)
    if function is None:
        return False
    branch = _standing_branch(function)
    return branch is not None and _dispatches_a_writer(branch.body)


def _standing_branch_reaches_live(tree: ast.AST) -> bool:
    """Does a flipped sport reach the LIVE writer? (CERT-2552 follow-up)

    **The half the direct-dispatch walk above is structurally blind to.** The
    schedule writer takes a sport key and is called inside the branch, so a walk
    of the branch body finds it. The livescore writer takes none, covers every
    live sport in one call, and is therefore called ONCE after the loop with the
    list the branch appended to (`_serve_live_from_statpal`, CERT-2052's
    coalescing). Nothing in the standing branch names it.

    So `_dispatches_a_writer` stays True with `served.append(sport_key)`
    deleted, and what this FILE claims about the tree stops being true.

    **AND CI WOULD STILL GO RED, WHICH IS THE HONEST BOUNDARY OF THIS GUARD.**
    `test_standing_statpal_is_a_serving_state_4434
    ::test_a_standing_sport_dispatches_the_writers_counted_apart` runs the real
    actor against a standing sport and asserts BOTH writers fired; it was
    measured killing exactly this mutation ("the standing sport's writers did
    not run: ['schedule:americanfootball_nfl']"). #4434 shipped its own
    behavioural cover and the containment is older than this walk. So what is
    bought here is not a hole a defect could reach production through — it is
    that `SWITCH_ACTOR_SERVES`, the declared fact the operator's sentence is
    derived from, is now derived from both halves rather than one. A file whose
    whole subject is a disclosure staying true to the tree should not itself
    hold a claim only half-checked.

    The link asserted is the real one: the branch appends the sport to some
    accumulator, and that same accumulator is what a `_serve_live*` call outside
    the if/elif chain is passed. Both halves are needed — an append nothing
    consumes serves no one, and a live call passed something else never sees
    this sport.
    """
    function = _actor_function(tree)
    if function is None:
        return False
    branch = _standing_branch(function)
    if branch is None:
        return False

    accumulators = _accumulators_appended_to(branch.body)
    if not accumulators:
        return False

    # Everything inside the chain is arm-conditional: a live call in the
    # uncovered arm or the final `else` is not one the standing branch reaches,
    # and the chain root is what puts all of those out of scope at once.
    arm_conditional = _subtree_ids(_chain_root(function, branch))

    for node in ast.walk(function):
        if not isinstance(node, ast.Call) or id(node) in arm_conditional:
            continue
        if not _call_name(node).startswith(LIVE_WRITER_PREFIX):
            continue
        passed = [*node.args, *(keyword.value for keyword in node.keywords)]
        for argument in passed:
            for name in ast.walk(argument):
                if isinstance(name, ast.Name) and name.id in accumulators:
                    return True
    return False


def _standing_branch_serves(tree: ast.AST) -> bool:
    """BOTH writers, because the served sentence says "writers RUN", plural.

    `SWITCH_ACTOR_SERVES` publishes one claim and it is a claim about two
    writers: a flipped sport gets its fixtures AND its scores. Requiring both
    here is what makes the plural in the note true rather than half-true.
    """
    return _standing_branch_dispatches_schedule(tree) and (
        _standing_branch_reaches_live(tree)
    )


def _consumers() -> set[str]:
    found = set()
    for path in sorted(APP.rglob("*.py")):
        module = _module_name(path)
        if module == CONFIG_MODULE:
            continue
        if _reads_the_switch(ast.parse(path.read_text(), filename=str(path))):
            found.add(module)
    return found


def test_the_switch_names_every_module_that_reads_it():
    """The guard. Wiring a consumer fails here until the declared set — and the
    `INERT` note derived from it — are brought into line with the tree."""
    found = _consumers()

    unlisted = found - set(SWITCH_CONSUMERS)
    assert not unlisted, (
        f"{sorted(unlisted)} read the authority switch and are not in "
        "`SWITCH_CONSUMERS`. If one of them ACTS on the answer, the row's "
        "`switch_note` no longer describes reality — update the set and the "
        "note together"
    )

    stale = set(SWITCH_CONSUMERS) - found
    assert not stale, (
        f"{sorted(stale)} are declared as switch consumers and no longer read "
        "it; a declared set that over-claims is the same rot in the other "
        "direction"
    )


def test_the_walk_finds_the_consumers_we_know_about():
    """The guard would pass vacuously if the walk found nothing at all — an
    import-detection bug and a genuinely unread switch look identical from the
    assertion above.

    Two, since #3473: the route that REPORTS the switch and the failover that
    ACTS on it. They are named individually rather than counted, because the
    difference between the two kinds is what the whole disclosure turns on.
    """
    assert _consumers() == {
        "app.routes.admin_providers",
        "app.utils.authority_failover",
    }


def test_the_walk_sees_an_import_a_substring_scan_would_miss(tmp_path):
    """Why this is an AST walk. The admin route writes its import inside a
    function AND across four lines; either alone defeats a grep for
    `from app.config.authority_by_sport import authority_for`."""
    source = (
        "def handler():\n"
        "    from app.config.authority_by_sport import (\n"
        "        STATPAL,\n"
        "        authority_for,\n"
        "    )\n"
        "    return authority_for('x')\n"
    )
    assert _reads_the_switch(ast.parse(source))

    # The control: the same shape importing only the string constants is NOT a
    # read of the switch, and must not be counted as one.
    constants_only = (
        "from app.config.authority_by_sport import (\n    ESPN,\n    STATPAL,\n)\n"
    )
    assert not _reads_the_switch(ast.parse(constants_only))


def test_a_bare_module_import_counts_as_a_read():
    """`import app.config.authority_by_sport` reaches every name in the module,
    so a walk that only understood `from ... import` would miss a real consumer
    and keep serving `INERT` after it stopped being true."""
    assert _reads_the_switch(ast.parse("import app.config.authority_by_sport"))


def test_the_note_no_longer_says_inert_because_the_switch_is_wired():
    """The published sentence, checked against the derived fact rather than
    written twice.

    This is the assertion #3442 wrote knowing it would one day have to change,
    and #3473 is the change. `INERT` had to stop being served the same day it
    stopped being true, and the only way to be sure of that is to derive it —
    which is why this test reads `SWITCH_IS_WIRED` rather than a literal.
    """
    assert SWITCH_IS_WIRED is True
    assert "INERT" not in SWITCH_WIRING_NOTE
    assert "WIRED" in SWITCH_WIRING_NOTE

    # The note must still tell an operator the ONE thing a flip does not do,
    # because that is now the easiest wrong conclusion available to them.
    assert "event_registry" in SWITCH_WIRING_NOTE


def test_the_standing_branch_serves_and_the_note_says_so():
    """The #4947 guard: the declared fact, the tree, and the served sentence.

    `SWITCH_CONSUMERS`' walk asks whether anything READS the switch and could
    not catch #4434, which changed what the reader DOES. For a day the row told
    an operator that a flip only moved a counter, while a flipped sport's
    schedule and livescore writers were running on every ESPN-dark pass.

    Both directions, because the sentence is wrong either way round: strip the
    dispatch out of the standing branch and a note promising writers is a lie;
    add one and a note omitting it is the lie we actually shipped.

    **BOTH WRITERS SINCE CERT-2552's FOLLOW-UP, and the two halves are asserted
    apart so the failure names which one went.** The note's promise is plural.
    The first cut pinned only the direct dispatch; the live writer is named
    nowhere in the branch, so deleting `served.append(sport_key)` left this
    test green. Scope, stated so nobody reads more into it than it does:
    #4434's behavioural test kills that mutation and always did, so this is the
    declared fact being made to match its own sentence, not a hole being shut.
    """
    tree = ast.parse(ACTOR_PATH.read_text(), filename=str(ACTOR_PATH))
    schedule_in_tree = _standing_branch_dispatches_schedule(tree)
    live_in_tree = _standing_branch_reaches_live(tree)
    serves_in_tree = _standing_branch_serves(tree)

    assert schedule_in_tree is SWITCH_ACTOR_SERVES, (
        f"`{ACTOR_FUNCTION}`'s STANDING_STATPAL branch "
        f"{'dispatches' if schedule_in_tree else 'does not dispatch'} a "
        f"`{WRITER_PREFIX}*` writer, but `SWITCH_ACTOR_SERVES` is "
        f"{SWITCH_ACTOR_SERVES}. Update the declaration and the served "
        "`switch_note` together — an operator reads that sentence immediately "
        "before flipping a sport (#4947)"
    )

    assert live_in_tree is SWITCH_ACTOR_SERVES, (
        f"`{ACTOR_FUNCTION}`'s STANDING_STATPAL branch "
        f"{'reaches' if live_in_tree else 'does not reach'} a "
        f"`{LIVE_WRITER_PREFIX}*` writer, but `SWITCH_ACTOR_SERVES` is "
        f"{SWITCH_ACTOR_SERVES}. The branch reaches the live half ONLY by "
        "appending the sport to the list the coalesced post-loop call is "
        "passed, so the schedule dispatch above can stay green while a "
        "flipped sport gets fixtures and no score, clock or status — which is "
        "the half `switch_note`'s plural promises (CERT-2552 follow-up)"
    )

    # And the composite the declaration actually stands for, so a future
    # rewrite cannot satisfy the two halves separately and neither together.
    assert serves_in_tree is SWITCH_ACTOR_SERVES

    if SWITCH_ACTOR_SERVES:
        # The two facts the accounting-only sentence omitted, and the reason
        # they matter: a flip changes what is WRITTEN, and a flip that cannot
        # be covered is not quietly reported as covered.
        assert "SERVES" in SWITCH_WIRING_NOTE
        assert "writers RUN" in SWITCH_WIRING_NOTE
        assert "UNCOVERED" in SWITCH_WIRING_NOTE
        assert "ONE thing changes" not in SWITCH_WIRING_NOTE
    else:
        assert "writers RUN" not in SWITCH_WIRING_NOTE


def test_the_serving_walk_can_tell_a_dispatch_from_a_log_line():
    """The positive control, without which the guard above passes vacuously.

    A walk that returned True for any standing branch — or False because it
    never found the function — would agree with today's answer for the wrong
    reason. Both arms are synthetic, so this stays honest when the real file
    changes shape.

    Scoped to the DIRECT-dispatch half since CERT-2552's follow-up: every arm
    below is a statement about what the branch body names, which is the only
    thing this predicate now claims to see. The live half has its own control.
    """
    dispatching = (
        "async def _act_on_failovers(decisions, stats):\n"
        "    for k in decisions:\n"
        "        if decision.code in FAILOVER_CODES:\n"
        "            await _serve_schedule_from_statpal(k, stats)\n"
        "        elif decision.code == STANDING_STATPAL:\n"
        "            await _serve_schedule_from_statpal(k, stats)\n"
    )
    assert _standing_branch_dispatches_schedule(ast.parse(dispatching)) is True

    # The pre-#4434 shape: the branch exists and only accounts. The FAILOVER
    # branch above it still calls the writer, so a walk that read the whole
    # if/elif chain as one body would call this serving. It is not.
    accounting_only = (
        "async def _act_on_failovers(decisions, stats):\n"
        "    for k in decisions:\n"
        "        if decision.code in FAILOVER_CODES:\n"
        "            await _serve_schedule_from_statpal(k, stats)\n"
        "        elif decision.code == STANDING_STATPAL:\n"
        "            stats['standing_serving'] = 1\n"
        "            logger.info('standing')\n"
    )
    assert _standing_branch_dispatches_schedule(ast.parse(accounting_only)) is False

    # The branch accounts, and a LATER arm serves. An `elif` lives in the
    # previous branch's `orelse`, so everything below the standing branch is
    # inside its subtree — a walk of the `If` node rather than its `body` reads
    # this as serving, and would bless a note promising writers to a flipped
    # sport that gets none.
    served_by_a_later_arm = (
        "async def _act_on_failovers(decisions, stats):\n"
        "    for k in decisions:\n"
        "        if decision.code in FAILOVER_CODES:\n"
        "            stats['failover_serving'] = 1\n"
        "        elif decision.code == STANDING_STATPAL:\n"
        "            stats['standing_serving'] = 1\n"
        "        else:\n"
        "            await _serve_schedule_from_statpal(k, stats)\n"
    )
    later_arm = ast.parse(served_by_a_later_arm)
    assert _standing_branch_dispatches_schedule(later_arm) is False

    # And a tree with no such branch at all — the #3473 state — is not serving.
    no_branch = (
        "async def _act_on_failovers(decisions, stats):\n"
        "    for k in decisions:\n"
        "        if decision.code in FAILOVER_CODES:\n"
        "            await _serve_schedule_from_statpal(k, stats)\n"
    )
    assert _standing_branch_dispatches_schedule(ast.parse(no_branch)) is False

    # A renamed actor must read as not-serving rather than silently passing:
    # that is the failure mode where the guard finds nothing and says nothing.
    renamed = dispatching.replace(ACTOR_FUNCTION, "_act_on_failovers_v2")
    assert _standing_branch_dispatches_schedule(ast.parse(renamed)) is False


def test_the_live_walk_needs_the_append_AND_the_call_that_consumes_it():
    """The control for the half the dispatch walk cannot see (CERT-2552).

    Every arm here is a shape that leaves the SCHEDULE dispatch intact, so each
    one is a mutation this FILE was blind to before — the branch keeps calling
    `_serve_schedule_from_statpal` and only the live half goes. Blind to, not
    unguarded: #4434's behavioural test catches them, and saying so is the
    difference between defence in depth and a discovered defect.
    """
    real_shape = (
        "async def _act_on_failovers(decisions, stats):\n"
        "    served = []\n"
        "    for k in decisions:\n"
        "        if decision.code in FAILOVER_CODES:\n"
        "            served.append(k)\n"
        "            await _serve_schedule_from_statpal(k, stats)\n"
        "        elif decision.code == STANDING_STATPAL:\n"
        "            served.append(k)\n"
        "            await _serve_schedule_from_statpal(k, stats)\n"
        "    if served:\n"
        "        await _serve_live_from_statpal(served, stats)\n"
    )
    assert _standing_branch_reaches_live(ast.parse(real_shape)) is True
    # The schedule half is unmoved in every arm below — that is the point.
    assert _standing_branch_dispatches_schedule(ast.parse(real_shape)) is True

    # THE MUTATION THIS EXISTS FOR: the append alone is gone. The failover arm
    # still appends, so `served` is still truthy and the live writer still
    # runs — for the sports in an outage, and not for the flipped one.
    no_append = real_shape.replace(
        "        elif decision.code == STANDING_STATPAL:\n"
        "            served.append(k)\n",
        "        elif decision.code == STANDING_STATPAL:\n",
    )
    assert _standing_branch_reaches_live(ast.parse(no_append)) is False
    assert _standing_branch_dispatches_schedule(ast.parse(no_append)) is True

    # The call is gone: an accumulator nothing consumes serves nobody.
    no_call = real_shape.replace(
        "    if served:\n        await _serve_live_from_statpal(served, stats)\n", ""
    )
    assert _standing_branch_reaches_live(ast.parse(no_call)) is False

    # The call is there and is passed something else. `served` is still built
    # and still appended to, so a walk that only asked "does an append exist
    # and is a live writer called" reads this as covered.
    wrong_list = real_shape.replace(
        "await _serve_live_from_statpal(served, stats)",
        "await _serve_live_from_statpal(failed_over, stats)",
    )
    assert _standing_branch_reaches_live(ast.parse(wrong_list)) is False

    # The branch appends to a DIFFERENT list from the one the call consumes —
    # the same defect wearing a rename, which is how it would really arrive.
    other_accumulator = real_shape.replace(
        "        elif decision.code == STANDING_STATPAL:\n"
        "            served.append(k)\n",
        "        elif decision.code == STANDING_STATPAL:\n"
        "            standing.append(k)\n",
    )
    assert _standing_branch_reaches_live(ast.parse(other_accumulator)) is False

    # Arm-conditional and therefore not reached: the live call sits in the
    # `else`, which is inside the standing branch's own `orelse` subtree.
    live_in_a_later_arm = (
        "async def _act_on_failovers(decisions, stats):\n"
        "    served = []\n"
        "    for k in decisions:\n"
        "        if decision.code in FAILOVER_CODES:\n"
        "            await _serve_schedule_from_statpal(k, stats)\n"
        "        elif decision.code == STANDING_STATPAL:\n"
        "            served.append(k)\n"
        "            await _serve_schedule_from_statpal(k, stats)\n"
        "        else:\n"
        "            await _serve_live_from_statpal(served, stats)\n"
    )
    assert _standing_branch_reaches_live(ast.parse(live_in_a_later_arm)) is False

    # A renamed actor reads as not reaching rather than passing vacuously,
    # exactly as the dispatch walk does.
    renamed_actor = real_shape.replace(ACTOR_FUNCTION, "_act_on_failovers_v2")
    assert _standing_branch_reaches_live(ast.parse(renamed_actor)) is False

    # And a keyword-passed accumulator still counts: `sports=served` is the
    # same wiring, and a positional-only walk would call the real thing broken
    # the first time someone spelled the call out.
    by_keyword = real_shape.replace(
        "_serve_live_from_statpal(served, stats)",
        "_serve_live_from_statpal(sports=served, stats=stats)",
    )
    assert _standing_branch_reaches_live(ast.parse(by_keyword)) is True


def test_the_note_has_three_states_and_the_middle_one_is_still_reachable():
    """The accounting-only sentence is not deleted, it is demoted.

    It was true for a day and it is the honest answer for any future actor that
    reads the switch without acting on it — so the function must still be able
    to produce it. A two-state function would force the next person into the
    same choice that produced #4947: overstate, or say nothing.
    """
    dark = switch_wiring_note(False, False)
    accounting = switch_wiring_note(True, False)
    serving = switch_wiring_note(True, True)

    assert "INERT" in dark
    assert "ONE thing changes" in accounting and "writers RUN" not in accounting
    assert "writers RUN" in serving
    assert len({dark, accounting, serving}) == 3

    # `serves` cannot manufacture a wiring that is not there: an unwired switch
    # is dark whatever an actor would have done with it.
    assert switch_wiring_note(False, True) == dark

    # All three keep the caveat, which is the half a flipping operator is most
    # likely to get wrong.
    for note in (dark, accounting, serving):
        assert "not" in note.lower()
    for note in (accounting, serving):
        assert "event_registry" in note


def test_the_note_would_go_back_to_inert_if_the_actor_were_removed():
    """The disclosure is a function of the derived fact in BOTH directions.

    The interesting case is no longer "what if someone wires one" — someone has
    — but "what if the actor is refactored away and the reporter is left". A
    note that only knew how to become WIRED would then keep claiming the switch
    was live. Asked about a tree that does not exist, which is the only way to
    test the direction today's answer is not in.
    """
    unwired = switch_is_wired({"app.routes.admin_providers"})
    assert unwired is False
    # Asked with `serves=True` as well as False (#4947): a switch nothing reads
    # is dark no matter what an actor would have done with the answer, and the
    # three-state note must not let the second flag smuggle in a claim.
    assert "INERT" in switch_wiring_note(unwired, SWITCH_ACTOR_SERVES)
    assert "INERT" in switch_wiring_note(unwired, False)
    assert "step 7" in switch_wiring_note(unwired, SWITCH_ACTOR_SERVES)

    # And the control, so the assertion above cannot pass because the function
    # returns False for everything.
    assert switch_is_wired({"app.routes.admin_providers", "app.tasks.anything"}) is True
    assert switch_is_wired(set()) is False


def test_a_reporter_is_not_wiring_but_is_still_a_reader_that_must_be_declared():
    """The two mechanisms are independent and both are needed. A module that
    only reports the value does not make the switch live — but it is still an
    undeclared reader, and the tree walk is what catches it.

    Since #3473 the declared set is strictly larger than the reporter set, and
    the difference is exactly the actors. Asserting that relationship, rather
    than equality, is what keeps this test meaningful now that both kinds exist.
    """
    assert switch_is_wired(SWITCH_REPORTERS) is False
    assert set(SWITCH_REPORTERS) < set(SWITCH_CONSUMERS)
    assert set(SWITCH_CONSUMERS) - set(SWITCH_REPORTERS) == {
        "app.utils.authority_failover"
    }


@pytest.mark.asyncio
async def test_the_row_publishes_the_wiring_beside_the_current_authority(monkeypatch):
    """Against the EXECUTED endpoint's payload, not its source.

    `AUTHORITY-038-ROUTE-PAYLOAD-GUARD`, the follow-up CERT-2028 named. The
    first cut asserted that the strings `switch_wired` and `switch_note` appear
    somewhere in the route's AST, which is a claim about a file rather than
    about a response: it would pass on a key built and then dropped, on one
    spelled into a comment, and on one placed under the wrong object. The
    endpoint is what an operator reads, so the endpoint is what gets asserted.

    Reuses the running suite's own fixtures rather than a second stub of the
    route, so a change to how the endpoint is invoked breaks one place.

    THE MONITOR IS STUBBED, AND #4531 IS WHY. This test used to read the real
    durable ledger, which in CI cannot be reached at all — so every sport came
    back `days=None`, hit the pre-#4531 `(False, ledger_why)` short-circuit, and
    the blanket `is False` below was green because of the DEFECT rather than
    because of the property. It had already disagreed with production since
    #4493, where football and the NBA report `FAILOVER-ESPN-DARK`. A verdict
    that depends on whether the test host can reach Redis is not an assertion
    about the payload, so the ledger state is now named here.

    `[]` is a real, successful, empty measurement. It is deliberately the same
    verdict the unreadable path now produces — `gate_on_unreadable_ledger` asks
    the gate with `[]` — so this test pins the answer, not the route to it.
    """
    from tests.test_authority_agreement_endpoint import FakeSession
    import app.routes.admin_providers as route
    import app.services.authority_ledger as ledger

    monkeypatch.setattr(route, "_check_admin_secret", lambda *a, **k: None)
    import app.tasks.redis_state as redis_state

    monkeypatch.setattr(redis_state, "get_task_metrics", lambda name: {})

    async def _read(sport_key):
        return [], "read ok"

    monkeypatch.setattr(ledger, "read_ledger_days", _read)

    out = await route.statpal_authority_agreement(
        request=None, secret="x", db=FakeSession()
    )

    assert out["sports"], "no rows to inspect — the guard would be vacuous"
    for entry in out["sports"]:
        authority = entry["authority"]
        # Beside `current`, in the same object. A note published one level up
        # would not travel with the value it qualifies.
        # Was `== ESPN`, which stopped being a fact about the payload on
        # 2026-09-11 (#4954 flipped football). What the payload owes is that
        # the value it publishes is the SWITCH's value — read from the map
        # here, not from `authority_for`, which is the route's own call and
        # would make this tautological.
        assert authority["current"] == AUTHORITY_BY_SPORT.get(
            entry["sport_key"], DEFAULT_AUTHORITY
        )
        assert authority["switch_wired"] is True
        assert "INERT" not in authority["switch_note"]
        # And it is the derived sentence, not a second copy that could drift.
        assert authority["switch_note"] == SWITCH_WIRING_NOTE

        # #3473 publishes the step-7 question beside the step-6 one, because
        # they are the same operator's two halves: "does flipping do anything"
        # and "does the outage cover behind it work". Both must be inside
        # `authority`, for the same reason the note is.
        #
        # Per sport, and derived from the ruled set rather than written out:
        # D104 (2026-09-09) permits a ruled sport's failover with no streak, so
        # a blanket "nothing fires" is no longer true of this payload and an
        # eighth sport must not be able to slip in under a hardcoded name.
        #
        # THREE STATES SINCE #4954, NOT TWO. A flipped sport is served by
        # StatPal STANDING, so `decide` returns `failed_over=False` for it —
        # the same `false` an ungated sport publishes, for the opposite
        # reason. Collapsing them (asserting `is ruled` and letting football
        # fall out of the loop) is what would let the best-covered sport we
        # have publish the uncovered sport's answer unnoticed.
        failover = authority["failover"]
        ruled = entry["sport_key"] in FLIP_RULED_WITHOUT_STREAK
        flipped = (
            AUTHORITY_BY_SPORT.get(entry["sport_key"], DEFAULT_AUTHORITY) == STATPAL
        )
        assert not (flipped and not ruled), (
            f"{entry['sport_key']} is flipped but not D104-ruled — that is a "
            "streak flip and this assertion table has never seen one; extend "
            "it rather than widening the branch"
        )
        expected_fire = ruled and not flipped
        assert failover["would_fire_if_espn_went_dark"] is expected_fire, (
            f"{entry['sport_key']} ruled={ruled} flipped={flipped}, so its "
            f"projection should be {expected_fire}: {failover['why']!r}"
        )
        assert failover["code"] == (
            "STANDING-STATPAL"
            if flipped
            else "FAILOVER-ESPN-DARK" if ruled else "NO-FAILOVER-NOT-GATED"
        )
        # The field that stops the two `false`s reading alike. A flipped sport
        # and a failing-over sport are BOTH covered; only an ungated one is not.
        assert failover["would_be_served_if_espn_went_dark"] is (ruled or flipped), (
            f"{entry['sport_key']} publishes coverage {failover['would_be_served_if_espn_went_dark']} "
            f"with code {failover['code']}"
        )
        if not ruled:
            assert "measured half" in failover["why"]


def test_the_flipped_sport_is_the_one_the_evidence_names():
    """Was `test_nothing_has_flipped_…`. The day it guarded arrived.

    Its old body was `set(AUTHORITY_BY_SPORT.values()) == {ESPN}` and its
    docstring said: *"the day one reads STATPAL, this file's claim is the only
    warning a reader gets, and it had better still be true."* That day is
    2026-09-11 (#4954), so the test is re-derived onto the claim itself rather
    than deleted — the switch is WIRED, the note says so and does not say
    INERT, and nothing reached STATPAL without receipts.
    """
    flipped = sorted(k for k, v in AUTHORITY_BY_SPORT.items() if v == STATPAL)
    assert flipped == sorted(FLIP_EVIDENCE), (
        f"the switch and its receipts disagree: switch={flipped} "
        f"evidence={sorted(FLIP_EVIDENCE)}"
    )
    assert SWITCH_IS_WIRED is True
    assert "INERT" not in SWITCH_WIRING_NOTE
