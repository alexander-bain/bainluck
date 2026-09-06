"""What reading the authority switch actually does, kept true by a tree walk.

#3442. `AUTHORITY_BY_SPORT` is the one-line-per-sport flip described by program
step 6, and today **exactly one module under `app/` reads it: the admin route
that reports its own value.** No ingest task, registry path or serving route
asks `authority_for` anything, so changing a line changes one string on an admin
page and nothing else.

That is not a defect — a dark switch is what step 6 built, and
`test_a_genuine_seven_now_reaches_the_gate_but_flips_nothing_by_itself` already
pins that opening the gate does not move the switch. What this file adds is the
next question, which nothing asked: *and if someone DID move it?*

The timing is why it is worth a file. NFL, NBA and NHL all read gate `MEETS` at
day 2 of 7 on production (2026-09-06 05:44Z), so the earliest a genuine seven
exists is around 2026-09-11. On that day someone reads a YOUR-TURN entry, edits
one line, sees the admin row change from `espn` to `statpal`, and reasonably
concludes the site now runs on StatPal for that sport. It would not.

**The config file already knew.** Its module docstring says "the consumer that
acts on it is lane1's to build". What it did not do is say it anywhere the
person deciding would look: the row publishes `authority.current` and a gate
note reading like a two-condition procedure, and an operator is not expected to
open a config module to learn that satisfying both conditions does nothing. A
true sentence in the wrong file is how this lane's last defect worked too
(#3432), and the fix is the same one — put it on the row, and derive it so it
cannot outlive its condition.

So the claim is declared (`SWITCH_CONSUMERS`), published where the person
deciding will read it (`authority.switch_note` on the agreement row), and pinned
here by walking `app/` with the ast module — never by grepping, because a
`from app.config.authority_by_sport import (\\n    authority_for,\\n)` wrapped
across lines defeats a substring scan, and an import written that way is what
the linter produces.

Wiring a real consumer fails these tests. That is the intended cost: the note
saying "INERT" must stop being served the same day it stops being true.
"""

from __future__ import annotations

import ast
from pathlib import Path

from app.config.authority_by_sport import (
    AUTHORITY_BY_SPORT,
    ESPN,
    SWITCH_CONSUMERS,
    SWITCH_IS_WIRED,
    SWITCH_REPORTERS,
    SWITCH_WIRING_NOTE,
    switch_is_wired,
    switch_wiring_note,
)

APP = Path(__file__).resolve().parent.parent / "app"

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


def test_the_walk_finds_the_one_consumer_we_know_about():
    """The guard would pass vacuously if the walk found nothing at all — an
    import-detection bug and a genuinely unread switch look identical from the
    assertion above."""
    assert _consumers() == {"app.routes.admin_providers"}


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


def test_the_note_says_inert_while_the_only_consumer_is_the_page_reporting_it():
    """The published sentence, checked against the derived fact rather than
    written twice."""
    assert SWITCH_IS_WIRED is False
    assert "INERT" in SWITCH_WIRING_NOTE
    assert "step 7" in SWITCH_WIRING_NOTE


def test_the_note_flips_when_a_real_consumer_appears():
    """The disclosure is derived by a function, so it cannot outlive the
    condition it describes — nobody has to remember to delete the `INERT`
    sentence. Asked about a tree that does not exist yet, which is the only way
    to test a predicate whose today-answer the other tests already pin."""
    wired = switch_is_wired({"app.routes.admin_providers", "app.tasks.espn_sync"})
    assert wired is True
    assert "INERT" not in switch_wiring_note(wired)
    assert "changes what the site serves" in switch_wiring_note(wired)

    # And the control, so the assertion above cannot pass because the function
    # returns True for everything: the reporting route alone is not wiring.
    assert switch_is_wired({"app.routes.admin_providers"}) is False
    assert switch_is_wired(set()) is False


def test_a_second_reporter_would_still_not_be_wiring_but_must_be_declared():
    """The two mechanisms are independent and both are needed. A module that
    only reports the value does not make the switch live — but it is still an
    undeclared reader, and the tree walk is what catches it."""
    assert switch_is_wired(SWITCH_REPORTERS) is False
    assert set(SWITCH_CONSUMERS) == set(SWITCH_REPORTERS)


def test_the_row_publishes_the_wiring_beside_the_current_authority():
    """End to end through the route's own module, so the two ends cannot agree
    while the wiring between them is dead."""
    import app.routes.admin_providers as route

    source = ast.parse(Path(route.__file__).read_text())
    published = {
        node.value
        for node in ast.walk(source)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "switch_wired" in published
    assert "switch_note" in published


def test_nothing_has_flipped_so_the_note_is_the_only_thing_standing_between():
    """Context, and a tripwire. While every value is ESPN the inert switch is
    harmless; the day one reads STATPAL, this file's claim is the only warning a
    reader gets, and it had better still be true."""
    assert set(AUTHORITY_BY_SPORT.values()) == {ESPN}
