"""#1801 R6 — the id-anchor invariant lives in the primitive, and EVERY caller uses it.

Codex ``C-CERT-1801-R5`` returned BLOCK. R5 put ruling 048 at the registry
boundary, where it held; the certification then found the same absorption alive
one layer down, in the rails that DELETE. Two P1s and a P2:

1. ``_merge_duplicate_events_impl``'s second arm — *one side is id-less AND no
   THIRD row shares the window* — is defeated by the two-row doubleheader.
   Row A is the anchored BOS@TOR game 1 at 13:05; row B is the id-less game 2 at
   18:35. That IS the complete doubleheader, so there is no third row, the pair
   reads "unambiguous", and the drain deletes the game the registry had just
   correctly created.
2. ``POST /api/admin/events/merge-duplicates-sql`` never required an id at all.
3. the duplicate meter cannot make the nightly verdict fail.

The fix Alex routed: **the invariant moves into the merge primitive itself, with
an AST census of all merge/delete callers as acceptance.** Not five careful
predicates in five places — that is what R1 through R5 were, and each one looked
correct in review.

The census is the load-bearing test in this file, and it earned its place twice
on its first run:

* it found a FOURTH rail nobody had named — ``merge_degenerate_combat_events``
  deletes an event on a fighter-name match inside a 28-hour window, guarded by
  the same uniqueness-as-identity surrogate codex had just rejected in the
  drain. It is ALLOWLISTED rather than routed through the primitive, because
  ruling 048 asks "are these the same event?" and refuses every pair here,
  making the rail a permanent no-op.

R7 (2026-08-15) — ``C-CERT-1801-R6`` returned BLOCK on this file and on that
fourth rail. Both findings are fixed here, and both are the same mistake in
different clothes: **a claim believed because of its shape, next to the
evidence that would have falsified it.**

1. The allowlist reason above used to end "...the row it deletes has
   ``home_team_name == away_team_name``, which is not a game and therefore
   cannot be a doubleheader's other half." The premise is true; the inference
   is not. ``Event`` has two separate nullable team FKs, and nothing ties them
   to the display labels. Codex executed event 9001 — three provider anchors,
   ``home_team_id=101``, ``away_team_id=202``, equal label "United" — and the
   rail deleted it. The rail now proves the artifact (no anchor AND no distinct
   participants) instead of inferring it from a label, and it had been
   SELECTING those three provider IDs and ignoring them the whole time.
2. This census promised ORM coverage in its docstring and delivered none: every
   line without ``DELETE FROM events`` took an unconditional ``continue``, so
   ``await session.delete(event)`` was invisible BY CONSTRUCTION. The six-site
   inventory was complete only by the accident that every current delete used
   the one spelling the scanner recognised. It is now AST-based over call
   nodes, and the hostile fixtures of BOTH shapes run through the real census
   rather than around it — the old negative control never invoked the census at
   all, which is why it could not detect the census's own defect.
* it caught an allowlist entry naming a function that does not exist
  (``delete_events_bulk``; the real one is ``delete_duplicate_events``), which
  is how an allowlist quietly grows a hole.

The general lesson, worth more than any of the four: **uniqueness is not
identity.** "I can find no evidence of a second game" and "these two rows are
the same game" are different claims, and only the second licenses a delete.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import NamedTuple

import pytest

from app.utils.event_merge_invariant import (
    CONFIRMING_RAIL_AVAILABLE,
    PROVIDER_ID_COLUMNS,
    UnanchoredMergeRefused,
    assert_mergeable,
    may_merge,
    partition_mergeable,
    refusal_reason,
    shared_provider_id_sql,
    shared_provider_ids,
)

APP = Path(__file__).resolve().parents[1] / "app"
INVARIANT_MODULE = "event_merge_invariant"


# ---------------------------------------------------------------------------
# THE SPECIMEN — codex's two-row doubleheader
# ---------------------------------------------------------------------------

class TestTheTwoRowDoubleheader:
    """The exact pair from the BLOCK, at the predicate that now decides."""

    GAME_1 = {"id": 1, "external_id": "odds_bos_tor_g1",
              "espn_id": None, "statpal_fixture_id": None}
    GAME_2 = {"id": 2, "external_id": None,
              "espn_id": None, "statpal_fixture_id": None}

    def test_the_doubleheader_is_NOT_mergeable(self):
        assert not may_merge(self.GAME_1, self.GAME_2)

    def test_the_refusal_names_the_unanchored_side(self):
        reason = refusal_reason(self.GAME_1, self.GAME_2)
        assert reason and "unanchored" in reason

    def test_assert_mergeable_RAISES_rather_than_returning_falsy(self):
        """A destructive rail that receives a falsy answer can continue by
        omission. An exception stops the delete and names the pair."""
        with pytest.raises(UnanchoredMergeRefused) as exc:
            assert_mergeable(self.GAME_1, self.GAME_2, context="test")
        assert "doubleheader" in str(exc.value)

    def test_there_is_no_third_row_to_save_us(self):
        """Why R5's surrogate failed, stated as the property it assumed.

        The old arm asked whether a THIRD same-matchup row shared the window.
        A doubleheader is two games. The surrogate was checking for a row that
        does not exist in the very case it was written to catch, and read its
        absence as safety.
        """
        doubleheader = [self.GAME_1, self.GAME_2]
        assert len(doubleheader) == 2
        mergeable, refused = partition_mergeable([(self.GAME_1, self.GAME_2)])
        assert not mergeable and len(refused) == 1

    def test_the_same_two_rows_WOULD_merge_once_an_id_arrives(self):
        """The ruling's own remedy: id-keyed reconciliation drains duplicates
        when ids later arrive. So this must not be a permanent refusal — it is
        a refusal pending evidence."""
        later = {**self.GAME_2, "external_id": "odds_bos_tor_g1"}
        assert may_merge(self.GAME_1, later)


class TestTheInvariantItself:

    def test_a_genuinely_shared_id_permits_the_merge(self):
        a = {"external_id": "x", "espn_id": None, "statpal_fixture_id": None}
        b = {"external_id": "x", "espn_id": "9", "statpal_fixture_id": None}
        assert shared_provider_ids(a, b) == {"external_id"}
        assert may_merge(a, b)

    def test_NULL_does_not_equal_NULL(self):
        """Two rows that both lack an id do not agree on it. Reading absence as
        agreement is how the admin rail's 'both NULL, keep lowest id' clause
        turned a missing fact into a delete."""
        a = {"external_id": None, "espn_id": None, "statpal_fixture_id": None}
        b = {"external_id": None, "espn_id": None, "statpal_fixture_id": None}
        assert shared_provider_ids(a, b) == set()
        assert not may_merge(a, b)

    def test_ids_that_DISAGREE_are_not_a_match(self):
        a = {"external_id": "x", "espn_id": None, "statpal_fixture_id": None}
        b = {"external_id": "y", "espn_id": None, "statpal_fixture_id": None}
        assert not may_merge(a, b)
        assert "disagree" in (refusal_reason(a, b) or "")

    @pytest.mark.parametrize("column", PROVIDER_ID_COLUMNS)
    def test_every_provider_column_can_anchor_a_merge(self, column):
        a = {c: None for c in PROVIDER_ID_COLUMNS}
        b = {c: None for c in PROVIDER_ID_COLUMNS}
        a[column] = b[column] = "shared"
        assert may_merge(a, b)

    def test_it_reads_orm_objects_as_well_as_mappings(self):
        class Row:
            id = 7
            external_id = "x"
            espn_id = None
            statpal_fixture_id = None
        assert may_merge(Row(), {"external_id": "x", "espn_id": None,
                                 "statpal_fixture_id": None})

    def test_confirming_ids_are_declared_absent_rather_than_faked(self):
        """"Shared or CONFIRMING" — and the confirming rail does not exist yet.

        This is asserted so that nobody quietly redefines "confirming" as a
        name-and-window heuristic, which is the exact thing ruling 048 forbids
        and the exact shape all five prior rounds took.
        """
        assert CONFIRMING_RAIL_AVAILABLE is False

    def test_the_sql_and_the_python_name_the_same_columns(self):
        """The two forms of the invariant cannot drift apart, because a rail
        that passes the query and fails the assertion is a rail that would have
        deleted a row the policy forbids."""
        sql = shared_provider_id_sql("a", "b")
        for column in PROVIDER_ID_COLUMNS:
            assert f"a.{column} IS NOT NULL" in sql
            assert f"a.{column} = b.{column}" in sql

    def test_the_sql_refuses_an_injection_shaped_alias(self):
        with pytest.raises(ValueError):
            shared_provider_id_sql("a; DROP TABLE events--", "b")


# ---------------------------------------------------------------------------
# THE CENSUS — Alex's named acceptance
# ---------------------------------------------------------------------------

def _python_files():
    return sorted(APP.rglob("*.py"))


def _enclosing_function(tree, lineno):
    best = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.lineno <= lineno <= (node.end_lineno or node.lineno):
                if best is None or node.lineno > best.lineno:
                    best = node
    return best


#: Receiver names an ORM delete is called on. Deliberately a closed set rather
#: than "anything that mentions Event nearby" — see the note at the call-node
#: branch of ``_census_source``, where the looser rule reported four Redis
#: ``.delete(cursor_key)`` calls on its first run. A new session variable naming
#: convention must be added here, and the ``app/`` sweep's four-rail non-vacuity
#: assertion is what fails if that is forgotten.
_SESSION_RECEIVERS = {"session", "db", "db_session", "async_session", "sess", "conn"}


#: ``Event`` as a WHOLE identifier. Substring matching would sweep in
#: ``EventConcept`` / ``EventProps`` deletes, which are different tables.
_EVENT_MODEL_RE = re.compile(r"\bEvent\b")


def _deletes_an_event(tree, source, call):
    """Does this ``session.delete(x)`` delete a row from ``events``?

    Receiver scoping alone answers "is this an ORM delete", not "an ORM delete
    of WHAT" — asked only that far, the census reported deletes of judgments,
    matching overrides, user accounts and Oscars picks. So the argument is
    resolved too, by the two signals available statically:

    1. the argument is named like an event (``event``, ``orphan_event``), or
    2. the argument is ASSIGNED, inside the same function, from an expression
       naming the ``Event`` model — ``event = await session.get(Event, id)``.

    (2) is what makes this more than a naming convention: a rail that calls its
    variable ``row`` is still caught, as long as it fetched it from ``Event``.
    A rail that defeats both — an Event fetched into an unrelated name via a
    helper — would slip through, and that is the honest limit of a static
    census. The four-rail non-vacuity assertion is the backstop: it fails if
    any known rail stops being seen, whatever the reason.
    """
    arg = call.args[0] if call.args else None
    if arg is None:
        return False
    arg_name = arg.id if isinstance(arg, ast.Name) else None
    if arg_name and "event" in arg_name.lower():
        return True
    if arg_name is None:
        return False

    enclosing = _enclosing_function(tree, call.lineno)
    if enclosing is None:
        return False
    for node in ast.walk(enclosing):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        else:
            continue
        if not any(
            isinstance(t, ast.Name) and t.id == arg_name for t in targets
        ):
            continue
        rhs = ast.get_source_segment(source, node.value) if node.value else None
        if rhs and _EVENT_MODEL_RE.search(rhs):
            return True
    return False


class DeleteSite(NamedTuple):
    """One place that can delete a row from ``events``.

    ``kind`` is load-bearing, not decoration: the R6 certification found the
    census claimed ORM coverage in its docstring and delivered none, so the
    shape a site was FOUND BY is now recorded and asserted.
    """

    path: object
    lineno: int
    name: str
    fn_source: str
    kind: str  # "sql" | "orm"


def _census_source(source, path=None):
    """The census proper, over one module's source. Returns ``DeleteSite``s.

    R6 → R7 (#1801): this used to scan lines for ``DELETE FROM events`` and
    `continue` on everything else — so ``await session.delete(event)`` was
    invisible BY CONSTRUCTION, while the docstring promised it was covered. A
    future rail could swap its raw SQL for the ORM spelling, drop the
    invariant, and keep the whole gate green. That is the self-concealing
    instrument this file exists to prevent, reproduced inside the instrument
    itself; the six-site inventory was complete only by the accident that every
    current delete uses the one spelling the scanner recognised.

    Taking a source string rather than only walking ``app/`` is the other half
    of the fix: the hostile fixtures below run through THIS function, so the
    negative controls exercise the real census instead of a hand-rolled echo
    of it.
    """
    sites = []
    try:
        tree = ast.parse(source)
    except SyntaxError:  # pragma: no cover
        return sites

    def _record(lineno, kind):
        fn = _enclosing_function(tree, lineno)
        if fn is None:
            return
        sites.append(DeleteSite(
            path, lineno, fn.name, ast.get_source_segment(source, fn) or "", kind
        ))

    # 1. Raw SQL — the literal, wherever it appears in the expression, including
    #    inside an f-string (a JoinedStr's constant parts are walked too).
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "DELETE FROM events" in node.value:
                _record(node.lineno, "sql")

    # 2. ORM / Core deletes, as CALL NODES.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn_node = node.func
        # `session.delete(event)` — attribute call named `delete`, scoped BY
        # RECEIVER.
        #
        # The first version of this scoped by enclosing-function text instead
        # ("does the function mention Event?") and immediately reported four
        # false positives — `_rc.delete(cursor_key)` Redis calls inside long
        # task functions that happen to mention Event elsewhere. That matters
        # beyond tidiness: a census that cries wolf gets its allowlist padded
        # to silence it, and an allowlist padded to silence a census is how the
        # census stops being read. Precision is what keeps this gate load-bearing.
        #
        # The receiver is the honest discriminator — the documented contract is
        # an ORM *session* delete, and a session is what an ORM delete is called
        # on. Scoping this way also removes the need for the Event-mention
        # heuristic entirely.
        if isinstance(fn_node, ast.Attribute) and fn_node.attr == "delete":
            recv = fn_node.value
            recv_name = (
                recv.attr if isinstance(recv, ast.Attribute)
                else recv.id if isinstance(recv, ast.Name)
                else None
            )
            if recv_name in _SESSION_RECEIVERS and _deletes_an_event(
                tree, source, node
            ):
                _record(node.lineno, "orm")
        # SQLAlchemy Core `delete(Event)` / `sa_delete(Event)` — the target is
        # named explicitly, so no enclosing-scope heuristic is needed.
        elif isinstance(fn_node, ast.Name) and fn_node.id in ("delete", "sa_delete"):
            first = node.args[0] if node.args else None
            if isinstance(first, ast.Name) and first.id == "Event":
                _record(node.lineno, "orm")

    # A single line can match twice (a Core delete of a raw SQL string); dedupe
    # on (lineno, kind) so counts mean what they say.
    seen, unique = set(), []
    for s in sites:
        key = (s.lineno, s.kind, s.name)
        if key not in seen:
            seen.add(key)
            unique.append(s)
    return unique


def event_delete_sites():
    """Every place in ``app/`` that can delete a row from ``events``.

    Both shapes are covered — raw SQL ``DELETE FROM events`` and an ORM
    ``session.delete(...)`` inside a function that also mentions Event — and
    ``TestTheCensusSeesBothSpellings`` proves it by driving hostile fixtures of
    each shape through the same code path.
    """
    sites = []
    for path in _python_files():
        source = path.read_text()
        if "DELETE FROM events" not in source and ".delete(" not in source:
            continue
        sites.extend(_census_source(source, path))
    return sites


#: Functions that delete an event but establish NO pairing, so the invariant
#: does not apply. Each needs a reason, and the reason is what a reviewer
#: checks — an allowlist without one is just a way to make a test pass.
DELETE_WITHOUT_MERGE_ALLOWLIST = {
    # An operator supplies explicit comma-separated event ids. Nothing is
    # inferred, nothing is absorbed into anything, and the destructive-token
    # gate already applies. (The census caught this entry's NAME being wrong on
    # its first run — which is the allowlist-staleness test earning its place.)
    "delete_duplicate_events": "operator supplies explicit ids; no pairing is inferred",
    # Purges pm_ events that matched NOTHING. There is no keeper and no
    # absorption — the opposite case from the merge rails.
    "purge_orphan_pm_events": "no keeper; deletes unmatched rows, absorbs nothing",
    # Found BY this census, and allowlisted after measuring the alternative:
    # ruling 048's shared-provider-ID invariant refuses every pair here (a
    # degenerate row shares no provider ID with the real event), making the rail
    # a permanent no-op and trading a corruption cleanup for nothing.
    #
    # This entry's REASON was wrong until R7 and is worth keeping visible. It
    # read: "deletes a corrupt home==away row, which is not a candidate game."
    # The second clause is an inference from a display label, and C-CERT-1801-R6
    # falsified it by executing the rail against event 9001 — three provider
    # anchors, `home_team_id=101`, `away_team_id=202`, equal label "United" —
    # which it deleted. Equal labels do not mean one participant; `Event` has
    # two separate nullable team FKs and no constraint tying them to the names.
    #
    # The rail now proves the artifact instead of inferring it: no provider
    # anchor AND no distinct participant IDs, or it refuses and counts
    # (`refused_anchored`). That is a DIFFERENT question from 048's — "is this
    # row real?" rather than "are these the same event?" — which is why it stays
    # allowlisted here rather than routed through the primitive.
    "_merge_degenerate_combat_events_impl":
        "establishes no cross-event pairing to guard: it proves the row is an "
        "unanchored single-participant artifact (no external_id/espn_id/"
        "statpal_fixture_id, no distinct team IDs) before deleting, refuses and "
        "counts otherwise, and keeps its >1-candidate ambiguity refusal",
    # #2020's bounded prune rail. Found BY this census, and allowlisted only after
    # stating the distinction precisely, because the easy reading is wrong: this
    # rail DOES establish a cross-event pairing (a surplus copy and the keeper,
    # matched on name and exact time), which is the very correspondence ruling 048
    # refuses to merge on.
    #
    # What makes it a different question is that NOTHING IS ABSORBED. Ruling 048's
    # harm requires a TRANSFER — every merging rail repoints `SET event_id = :keep`
    # before deleting, and that is how 5,142 / 540 / 2,097 rows of one game's data
    # ended up blended onto another's (#1779/#1798). This rail repoints nothing: it
    # DELETEs the surplus row's FK rows outright and leaves the keeper untouched, so
    # the corruption the invariant bounds cannot occur through it. That claim is not
    # left as prose — `TestTheRailNeverAbsorbs` in
    # tests/test_prune_unanchored_duplicates_2020.py asserts the rail's source
    # contains no FK-repointing statement, so the reason here stays true or the
    # suite goes red.
    #
    # And routing it through the primitive was measured, not assumed: every row in
    # this population carries external_id, espn_id and statpal_fixture_id ALL NULL
    # (0/0/0 across 72,479 rows, 2026-08-20), so `assert_mergeable` refuses every
    # pair and the rail becomes a permanent no-op — the same trade the combat entry
    # above rejected. The safety here is the destructive-token gate, the caller-
    # supplied census band, and the in-transaction re-verification that a
    # futures-linked keeper still exists for every row before it is destroyed.
    "prune":
        "no absorption: deletes surplus copies and their FK rows outright, never "
        "repoints event_id onto the keeper, so ruling 048's blending harm has no "
        "path through it; enforced by TestTheRailNeverAbsorbs",
}


class TestEveryDestructiveRailUsesThePrimitive:
    """The acceptance Alex named. This is what makes the fix structural.

    A per-caller patch is only as good as the census that found the callers,
    and the R5 certification's census — by a careful adversarial reader — missed
    one. So the census is executable and runs on every commit.
    """

    def test_the_census_finds_the_known_rails(self):
        """Non-vacuity, over ALL FOUR merging rails.

        R6 pinned two of the four. A census that quietly stopped seeing the
        other two would still have passed — and the two it did not pin include
        ``_merge_degenerate_combat_events_impl``, the rail that turned out to
        carry the P1 defect. Pinning a subset of what you claim to enumerate is
        the same false-green shape the census exists to catch.
        """
        names = {s.name for s in event_delete_sites()}
        for rail in (
            "merge_duplicate_events",
            "merge_duplicate_events_sql",
            "_merge_duplicate_events_impl",
            "_merge_degenerate_combat_events_impl",
        ):
            assert rail in names, (
                f"the census no longer sees {rail}() — it is either gone or the "
                "scanner has stopped recognising its delete spelling"
            )
        assert names, "the census found no event deletes at all — it has broken"

    def test_every_merging_delete_site_references_the_invariant(self):
        offenders = []
        for site in event_delete_sites():
            path, lineno, name, fn_source = (
                site.path, site.lineno, site.name, site.fn_source
            )
            if name in DELETE_WITHOUT_MERGE_ALLOWLIST:
                continue
            if INVARIANT_MODULE in fn_source or "assert_mergeable" in fn_source \
                    or "refusal_reason" in fn_source or "shared_provider_id_sql" in fn_source:
                continue
            offenders.append(f"{path.relative_to(APP)}:{lineno} in {name}()")
        assert not offenders, (
            "these rails delete an event without consulting the ruling-048 "
            "invariant:\n  " + "\n  ".join(offenders) +
            "\n\nEither route them through app/utils/event_merge_invariant.py, or "
            "add them to DELETE_WITHOUT_MERGE_ALLOWLIST WITH A REASON if they "
            "establish no pairing."
        )

    def test_the_allowlist_entries_all_still_exist(self):
        """An allowlist that names dead functions is a way of hiding new ones."""
        names = {s.name for s in event_delete_sites()}
        stale = set(DELETE_WITHOUT_MERGE_ALLOWLIST) - names
        assert not stale, f"allowlisted functions no longer delete events: {stale}"

    def test_the_allowlist_cannot_be_extended_without_a_reason(self):
        assert all(len(r) > 20 for r in DELETE_WITHOUT_MERGE_ALLOWLIST.values())

    def test_the_census_would_CATCH_a_new_unguarded_rail(self):
        """The negative control on the census itself, THROUGH the census.

        R6 blocked on the previous version of this test: it called
        ``_enclosing_function`` directly and asserted only that a function could
        be located around a raw SQL string. It never invoked the census, so it
        could not have detected the census's actual defect — and did not.
        """
        fake = (
            "async def rogue():\n"
            "    await db.execute(text('DELETE FROM events WHERE id = 1'))\n"
        )
        sites = _census_source(fake)
        assert [s.name for s in sites] == ["rogue"]
        assert sites[0].kind == "sql"
        assert INVARIANT_MODULE not in sites[0].fn_source


class TestTheCensusSeesBothSpellings:
    """The R6 harness gap: ORM deletes were invisible BY CONSTRUCTION.

    The old scanner `continue`d on every line without ``DELETE FROM events``,
    so ``await session.delete(event)`` could never be reported — while the
    docstring said both shapes were covered. A rail could swap spellings, drop
    the invariant, and leave this entire gate green.

    Each fixture below is hostile: an unguarded rail that a correct census must
    report. They run through ``_census_source`` — the same function the
    ``app/`` sweep uses — because a negative control that re-implements the
    thing it validates proves only that the re-implementation works.
    """

    def test_an_orm_session_delete_is_reported(self):
        fake = (
            "async def rogue_orm(session):\n"
            "    event = await session.get(Event, 1)\n"
            "    await session.delete(event)\n"
        )
        sites = _census_source(fake)
        assert [(s.name, s.kind) for s in sites] == [("rogue_orm", "orm")], (
            "an ORM event delete was invisible to the census — this is the "
            "exact R6 finding, reintroduced"
        )

    def test_a_core_delete_of_the_event_model_is_reported(self):
        fake = (
            "async def rogue_core(session):\n"
            "    await session.execute(sa_delete(Event).where(Event.id == 1))\n"
        )
        sites = _census_source(fake)
        assert [(s.name, s.kind) for s in sites] == [("rogue_core", "orm")]

    def test_both_spellings_in_one_module_are_both_reported(self):
        fake = (
            "async def rogue_sql(session):\n"
            "    await session.execute(text('DELETE FROM events WHERE id = 1'))\n"
            "\n"
            "async def rogue_orm(session):\n"
            "    event = await session.get(Event, 1)\n"
            "    await session.delete(event)\n"
        )
        found = {(s.name, s.kind) for s in _census_source(fake)}
        assert found == {("rogue_sql", "sql"), ("rogue_orm", "orm")}

    def test_an_unrelated_delete_call_is_not_reported(self):
        """The census must stay useful, not merely loud.

        A ``.delete()`` on a cache or a dict is not an event delete. Without
        this the gate would flood with noise and the allowlist would grow into
        a rubber stamp — which is how a census stops being read.
        """
        fake = (
            "async def unrelated(redis):\n"
            "    await redis.delete('some:key')\n"
        )
        assert _census_source(fake) == []

    def test_a_redis_delete_inside_an_event_touching_function_is_not_reported(self):
        """The exact false positive the first R7 census produced, pinned.

        Scoping ORM detection by "the enclosing function mentions Event"
        reported four real sites of this shape — Redis cursor resets in
        ``backfill_winners`` and ``taxonomy`` — none of which delete an event.
        The fixture keeps the Event mention, because that is what made those
        functions match.
        """
        fake = (
            "async def drain(session, _rc):\n"
            "    rows = await session.execute(select(Event).limit(10))\n"
            "    if not rows:\n"
            "        _rc.delete(_cursor_key)\n"
        )
        assert _census_source(fake) == []

    def test_the_orm_shape_is_actually_reachable_in_the_real_sweep(self):
        """Guards the scoping heuristic against being vacuously safe.

        ``_census_source`` only reports ``.delete(...)`` inside a function whose
        source mentions Event. If that condition were mis-written so it never
        matched, every ORM assertion above would still pass on fixtures that
        mention Event explicitly, while the real ``app/`` sweep stayed blind.
        This pins that the kind is produced by the same code path the sweep runs.
        """
        fake = (
            "async def rogue_orm(session):\n"
            "    event = await session.get(Event, 1)\n"
            "    await session.delete(event)\n"
        )
        assert any(s.kind == "orm" for s in _census_source(fake, Path("fake.py")))


class TestTheDrainsSqlNoLongerCarriesTheDefeatedArm:
    """R5's clause is gone, not merely bypassed."""

    @pytest.fixture(scope="class")
    def drain(self):
        source = (APP / "tasks" / "sports.py").read_text()
        tree = ast.parse(source)
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and n.name == "_merge_duplicate_events_impl")
        return ast.get_source_segment(source, fn) or ""

    def test_the_no_third_row_surrogate_is_deleted(self, drain):
        assert "c.id <> a.id" not in drain, (
            "the third-row uniqueness surrogate is back; it cannot see a "
            "two-row doubleheader"
        )

    def test_the_predicate_comes_from_the_primitive(self, drain):
        assert "shared_provider_id_sql" in drain

    def test_the_row_is_re_checked_before_the_delete(self, drain):
        assert "assert_mergeable" in drain

    def test_a_refusal_skips_the_pair_and_drains_the_rest(self, drain):
        """Gotcha #42: one bad item must never wipe the pass."""
        assert "continue" in drain and "refused" in drain


# ---------------------------------------------------------------------------
# P2 — the meter can now fail the verdict
# ---------------------------------------------------------------------------

class TestTheMeterCanFailTheNightlyVerdict:
    """Codex C-CERT-1801-R5 P2.

    ``_run_duplicate_events`` set ``passed`` from ``len(dups) == 0`` alone, so
    the provenance meter's two named failures — an unknown count, and a backlog
    nothing drains — were evidence that could never turn the night red. A meter
    that cannot fail a verdict is not a gate, and #1501 is this codebase's
    standing lesson about an absence rendering as health.
    """

    @pytest.fixture(scope="class")
    def source(self):
        return (APP / "tasks" / "flow_sentinel.py").read_text()

    def test_passed_is_no_longer_the_duplicate_count_alone(self, source):
        assert "len(dups) == 0 and not meter_failures" in source

    def test_an_unmeasured_meter_is_a_failure(self, source):
        assert 'if not meter.get("measured")' in source
        assert "UNMEASURED" in source

    def test_zero_reconciled_against_nonzero_created_is_a_failure(self, source):
        assert "created > 0 and reconciled == 0" in source

    def test_the_trend_check_is_NOT_faked_from_an_absent_key(self, source):
        """The meter emits no prior value. A `> previous` comparison here would
        never fire — dead code shaped like a gate, which is the very defect
        being repaired. Assert it stays out until a prior is actually persisted.
        """
        assert "unreconciled_previous" not in source

    def test_a_nonzero_duplicate_count_is_still_NOT_a_failure_by_itself(self, source):
        """Ruling 048 is unchanged: duplicates are the accepted price of never
        eating a real game. Only unmeasurability and non-draining fail."""
        assert "not a failure" in source or "accepted price" in source
