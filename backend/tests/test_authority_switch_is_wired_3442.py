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
    assert "INERT" in switch_wiring_note(unwired)
    assert "step 7" in switch_wiring_note(unwired)

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
    """
    from tests.test_authority_agreement_endpoint import FakeSession
    import app.routes.admin_providers as route

    monkeypatch.setattr(route, "_check_admin_secret", lambda *a, **k: None)
    import app.tasks.redis_state as redis_state

    monkeypatch.setattr(redis_state, "get_task_metrics", lambda name: {})

    out = await route.statpal_authority_agreement(
        request=None, secret="x", db=FakeSession()
    )

    assert out["sports"], "no rows to inspect — the guard would be vacuous"
    for entry in out["sports"]:
        authority = entry["authority"]
        # Beside `current`, in the same object. A note published one level up
        # would not travel with the value it qualifies.
        assert authority["current"] == ESPN
        assert authority["switch_wired"] is True
        assert "INERT" not in authority["switch_note"]
        # And it is the derived sentence, not a second copy that could drift.
        assert authority["switch_note"] == SWITCH_WIRING_NOTE

        # #3473 publishes the step-7 question beside the step-6 one, because
        # they are the same operator's two halves: "does flipping do anything"
        # and "does the outage cover behind it work". Both must be inside
        # `authority`, for the same reason the note is.
        failover = authority["failover"]
        assert failover["would_fire_if_espn_went_dark"] is False
        assert failover["code"] == "NO-FAILOVER-NOT-GATED"
        assert "measured half" in failover["why"]


def test_nothing_has_flipped_so_the_note_is_the_only_thing_standing_between():
    """Context, and a tripwire. While every value is ESPN the inert switch is
    harmless; the day one reads STATPAL, this file's claim is the only warning a
    reader gets, and it had better still be true."""
    assert set(AUTHORITY_BY_SPORT.values()) == {ESPN}
