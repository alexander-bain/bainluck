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
  drain. It is ALLOWLISTED rather than guarded, and the reason is recorded at
  both ends: the row it deletes has ``home_team_name == away_team_name``, which
  is not a game and therefore cannot be a doubleheader's other half. Guarding it
  was tried and measured — the invariant refuses every pair and the repair
  simply stops happening.
* it caught an allowlist entry naming a function that does not exist
  (``delete_events_bulk``; the real one is ``delete_duplicate_events``), which
  is how an allowlist quietly grows a hole.

The general lesson, worth more than any of the four: **uniqueness is not
identity.** "I can find no evidence of a second game" and "these two rows are
the same game" are different claims, and only the second licenses a delete.
"""

from __future__ import annotations

import ast
from pathlib import Path

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


def event_delete_sites():
    """Every place in ``app/`` that can delete a row from ``events``.

    Both shapes are covered: raw SQL ``DELETE FROM events`` and an ORM
    ``session.delete(...)`` inside a function that also mentions Event. Yields
    ``(path, lineno, function_name, function_source)``.
    """
    sites = []
    for path in _python_files():
        source = path.read_text()
        if "DELETE FROM events" not in source and ".delete(" not in source:
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:  # pragma: no cover
            continue
        for i, line in enumerate(source.splitlines(), start=1):
            stripped = line.strip()
            is_sql_delete = "DELETE FROM events" in stripped
            if not is_sql_delete:
                continue
            fn = _enclosing_function(tree, i)
            if fn is None:
                continue
            fn_source = ast.get_source_segment(source, fn) or ""
            sites.append((path, i, fn.name, fn_source))
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
    # Found BY this census, and allowlisted after measuring the alternative.
    # The deleted row has home_team_name == away_team_name: not a game, so it
    # cannot be a doubleheader's other half, which is the hazard 048 addresses.
    # Guarding it was tried — the invariant refuses every pair, the rail becomes
    # a permanent no-op, and the repair it exists to perform stops happening.
    "_merge_degenerate_combat_events_impl":
        "deletes a corrupt home==away row, which is not a candidate game; "
        "keeps its own >1-candidate ambiguity refusal",
}


class TestEveryDestructiveRailUsesThePrimitive:
    """The acceptance Alex named. This is what makes the fix structural.

    A per-caller patch is only as good as the census that found the callers,
    and the R5 certification's census — by a careful adversarial reader — missed
    one. So the census is executable and runs on every commit.
    """

    def test_the_census_finds_the_known_rails(self):
        names = {name for _, _, name, _ in event_delete_sites()}
        assert "_merge_duplicate_events_impl" in names
        assert "merge_duplicate_events_sql" in names
        assert names, "the census found no event deletes at all — it has broken"

    def test_every_merging_delete_site_references_the_invariant(self):
        offenders = []
        for path, lineno, name, fn_source in event_delete_sites():
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
        names = {name for _, _, name, _ in event_delete_sites()}
        stale = set(DELETE_WITHOUT_MERGE_ALLOWLIST) - names
        assert not stale, f"allowlisted functions no longer delete events: {stale}"

    def test_the_allowlist_cannot_be_extended_without_a_reason(self):
        assert all(len(r) > 20 for r in DELETE_WITHOUT_MERGE_ALLOWLIST.values())

    def test_the_census_would_CATCH_a_new_unguarded_rail(self):
        """The negative control on the census itself.

        Without this, a census that silently stopped matching would report a
        clean board forever — which is the same false-green shape as everything
        else in this issue.
        """
        fake = "async def rogue():\n    await db.execute(text('DELETE FROM events WHERE id = 1'))\n"
        tree = ast.parse(fake)
        fn = _enclosing_function(tree, 2)
        assert fn is not None and fn.name == "rogue"
        assert INVARIANT_MODULE not in (ast.get_source_segment(fake, fn) or "")


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
