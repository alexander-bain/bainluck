"""#2020 — the bounded delete rail, its five properties, and the six defects that
``C-DELETE-RAIL-PRE`` found in the first version of them.

Queue 382 was authorized to delete ~61,000 rows attended, *"with a per-batch dry-run
whose census must match the plan exactly, stop-on-mismatch."* It stopped, because no
rail in production could do that. This module was that missing device — and then a
hostile audit returned **BLOCK** on it and Alex voided all 31 applies.

So the tests come in two halves, and the second half is the more important one:

* ``TestDryRunIsTheDefault`` … ``TestOnlyTrancheAIsPrunable`` — the five original
  properties. Still true, still asserted.
* ``TestTheHostileSpecimens`` — **codex's own constructions, re-run against the
  rebuilt rail.** Each one deleted something it should not have, or passed a guard it
  should have failed. They are written from the audit's specimen data rather than
  paraphrased, because a regression test whose specimen has been "tidied" is a
  regression test for a different bug.

The sentence that organises all of it: **a band bounds CARDINALITY; every finding was
about IDENTITY.** Tests that only vary counts cannot see any of these.
"""

import pytest

from app.tasks.prune_unanchored_duplicates import (
    DEFAULT_MAX_DELETE,
    MAX_DELETE_CEILING,
    PruneRefused,
    census,
    compute_plan_hash,
    prune,
)


class _Result:
    def __init__(self, rows, rowcount=0):
        self._rows = rows
        self.rowcount = rowcount

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def one(self):
        return self._rows[0]


class _Session:
    """Answers each query by SQL shape, and records every write.

    ``verify_overrides`` makes one candidate row fail re-verification — the
    concurrent-writer case, the only way a correct batch query can still hand back a
    row that must not be deleted. ``vanish`` removes a row from the lock result.
    ``batch_ids_on_apply`` is the R2 specimen: the batch query answers differently the
    second time it is asked, which is what READ COMMITTED permits.
    """

    def __init__(
        self, *, fixtures=0, total_rows=0, keepers=0, surplus=None, deletable=0,
        anchored_copies=0, withheld_due_to_anchor=None, withheld_substantive=0,
        batch_ids=None, verify_overrides=None, delete_rowcount=None,
        keeper_ids=None, vanish=(), batch_ids_on_apply=None,
    ):
        # Rail v3 (C-DELETE-RAIL-PRE-R2 finding 4): `withheld_anchored` counted anchored
        # ROWS while `surplus` counted surplus rows, so the census could not be made to
        # add up and nothing required it to. The unit is now consistent, and `census()`
        # REFUSES when the three buckets do not sum to `surplus` — which polices this
        # fake too: a fixture that injects an unaccountable census now raises instead of
        # quietly proving the rail correct against arithmetic that cannot occur.
        surplus_val = deletable if surplus is None else surplus
        if withheld_due_to_anchor is None:
            withheld_due_to_anchor = max(
                surplus_val - deletable - withheld_substantive, 0
            )
        self._census = {
            "fixtures": fixtures,
            "total_rows": total_rows,
            "keepers": keepers,
            "surplus": surplus_val,
            "anchored_copies": anchored_copies,
            "withheld_substantive": withheld_substantive,
            "withheld_due_to_anchor": withheld_due_to_anchor,
            "deletable": deletable,
        }
        self._batch = list(batch_ids) if batch_ids is not None else []
        self._batch_on_apply = batch_ids_on_apply
        self._batch_calls = 0
        self._verify_overrides = verify_overrides or {}
        self._delete_rowcount = delete_rowcount
        self._keeper_ids = list(keeper_ids) if keeper_ids is not None else []
        self._vanish = set(vanish)
        self.writes: list[tuple[str, dict]] = []
        self.locked = False
        self.lock_order: list[int] = []

    def batch_for(self, cap=DEFAULT_MAX_DELETE, *, live=False):
        """``live=False`` is what the dry run published and the operator reviewed;
        ``live=True`` is what the database would hand back now. They differ only in
        the R2 specimen, which is the whole point of that specimen."""
        src = self._batch_on_apply if (live and self._batch_on_apply) else self._batch
        return list(src)[:cap]

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        params = params or {}

        if "DELETE FROM" in sql or sql.startswith("UPDATE "):
            self.writes.append((sql.split(" WHERE")[0], params))
            ids = params.get("ids") or []
            count = (
                self._delete_rowcount
                if self._delete_rowcount is not None and "DELETE FROM events" in sql
                else len(ids)
            )
            return _Result([], rowcount=count)

        if "AS fixtures" in sql:
            return _Result([self._census])

        if "LIMIT :cap" in sql:
            self._batch_calls += 1
            cap = int(params.get("cap", DEFAULT_MAX_DELETE))
            return _Result([(i,) for i in self.batch_for(cap, live=True)])

        if "SELECT DISTINCT k.id" in sql:
            return _Result([(i,) for i in self._keeper_ids])

        if "FOR UPDATE" in sql:
            self.locked = True
            ids = [i for i in params.get("ids", []) if i not in self._vanish]
            self.lock_order = ids
            return _Result([(i,) for i in ids])

        if "AS right_sport" in sql:
            rows = []
            for i in params.get("ids", []):
                if i in self._vanish:
                    continue
                row = {
                    "id": i, "right_sport": True, "tagged": True,
                    "unlinked": True, "anchor_free": True,
                    "empty_of_substance": True, "keeper_exists": True,
                }
                row.update(self._verify_overrides.get(i, {}))
                rows.append(row)
            return _Result(rows)

        raise AssertionError(f"unrecognised statement in the fake session: {sql[:200]}")

    async def rollback(self):
        pass


def _deleted_event_ids(session):
    for sql, params in session.writes:
        if sql.strip() == "DELETE FROM events":
            return params["ids"]
    return None


def _plan(session, *, sport_id=37871, linked_copies=1, cap=DEFAULT_MAX_DELETE):
    """The plan hash an operator would have read off the dry run."""
    return compute_plan_hash(
        sport_id=sport_id,
        linked_copies=linked_copies,
        ids=session.batch_for(cap),
    )


async def _apply(session, *, sport_id=37871, cap=DEFAULT_MAX_DELETE, **kwargs):
    """Apply with a correct plan hash, so tests about OTHER properties are not all
    also tests about the plan hash."""
    kwargs.setdefault("plan_hash", _plan(session, sport_id=sport_id, cap=cap))
    return await prune(session, sport_id=sport_id, apply=True, max_delete=cap, **kwargs)


# ── property 1: dry-run is the default ─────────────────────────────────────


class TestDryRunIsTheDefault:
    @pytest.mark.asyncio
    async def test_apply_defaults_to_false_and_writes_nothing(self):
        """Not "the caller usually passes false" — the signature's default."""
        session = _Session(fixtures=3, total_rows=40, keepers=3, deletable=37,
                           batch_ids=[1, 2, 3])

        out = await prune(session, sport_id=37871)

        assert out["apply"] is False
        assert out["terminal"] == "dry_run"
        assert out["deleted"] == 0
        assert session.writes == []

    @pytest.mark.asyncio
    async def test_the_dry_run_exercises_the_apply_paths_guard_query(self):
        """A rehearsal that skips a statement is not a rehearsal."""
        session = _Session(deletable=7, batch_ids=[101, 102])

        out = await prune(session, sport_id=37871)

        assert session.locked is True, "the dry run must exercise the lock query"
        assert out["verified"] is True
        assert out["deleted"] == 0
        assert session.writes == []

    @pytest.mark.asyncio
    async def test_the_dry_run_publishes_a_plan_hash(self):
        """R2 — the dry run's output is what makes an apply bindable at all."""
        session = _Session(deletable=7, batch_ids=[101, 102])
        out = await prune(session, sport_id=37871)
        assert out["plan_hash"] == compute_plan_hash(
            sport_id=37871, linked_copies=1, ids=[101, 102]
        )
        assert out["plan_hash"] in out["reason"]

    @pytest.mark.asyncio
    async def test_a_dry_run_whose_guard_would_refuse_says_so_instead_of_dry_run(self):
        """The operator finds out at rehearsal, not mid-run."""
        session = _Session(deletable=7, batch_ids=[101],
                           verify_overrides={101: {"keeper_exists": False}})

        out = await prune(session, sport_id=37871)

        assert out["terminal"] == "refused"
        assert out["verified"] is False
        assert "keeper_exists" in out["reason"]
        assert session.writes == []

    @pytest.mark.asyncio
    async def test_the_dry_run_names_what_would_remain_after_the_batch(self):
        """An operator batching 31 calls needs the remainder, not just the batch."""
        session = _Session(fixtures=2565, total_rows=63454, keepers=2565,
                           deletable=60889, batch_ids=list(range(2000)))

        out = await prune(session, sport_id=37871, max_delete=2000)

        assert out["batch_size"] == 2000
        assert "58889 would remain" in out["reason"]


# ── property 2: the census travels with the answer ─────────────────────────


class TestTheCensusIsInTheResponse:
    @pytest.mark.asyncio
    async def test_every_path_returns_the_census(self):
        for apply_flag in (False, True):
            session = _Session(fixtures=1, total_rows=5, keepers=1, deletable=4,
                               batch_ids=[7, 8, 9, 10])
            if apply_flag:
                out = await _apply(session, expected_min=0, expected_max=10**9)
            else:
                out = await prune(session, sport_id=37871)
            assert out["census"]["fixtures"] == 1
            assert out["census"]["deletable"] == 4
            assert out["census"]["total_rows"] == 5

    @pytest.mark.asyncio
    async def test_census_is_callable_on_its_own(self):
        session = _Session(fixtures=35, total_rows=7596, keepers=0, deletable=7596)
        assert (await census(session, sport_id=37871, linked_copies=0))["fixtures"] == 35

    @pytest.mark.asyncio
    async def test_the_census_separates_deletable_from_merely_surplus(self):
        """#2057's recut, made readable.

        ``surplus`` is how many extra copies exist; ``deletable`` is how many of them
        carry nothing. The gap is the population that needs a ruling, and a response
        that reported only one number would hide it — which is what the first version
        did, and why 1,230 rows of real history sat inside an "authorized" 60,889.
        """
        session = _Session(fixtures=2565, total_rows=63454, keepers=2565,
                           surplus=60889, deletable=59659,
                           withheld_substantive=1230, batch_ids=[1])

        out = await prune(session, sport_id=37871)

        assert out["census"]["surplus"] == 60889
        assert out["census"]["deletable"] == 59659
        assert out["census"]["withheld_substantive"] == 1230


# ── property 3: the per-call cap ───────────────────────────────────────────


class TestThePerCallCap:
    @pytest.mark.asyncio
    async def test_a_cap_above_the_ceiling_is_refused(self):
        session = _Session(deletable=60889, batch_ids=[1])
        with pytest.raises(PruneRefused, match="max_delete"):
            await prune(session, sport_id=37871, max_delete=MAX_DELETE_CEILING + 1)
        assert session.writes == []

    @pytest.mark.asyncio
    async def test_a_zero_cap_is_refused_rather_than_treated_as_unlimited(self):
        """The dangerous reading of 0. Named, because it is the one that kills."""
        session = _Session(deletable=60889, batch_ids=[1])
        with pytest.raises(PruneRefused):
            await prune(session, sport_id=37871, max_delete=0)

    @pytest.mark.asyncio
    async def test_the_cap_is_passed_to_the_batch_query_not_applied_after(self):
        """A cap applied in Python after fetching 61,000 ids is not a cap."""
        seen = {}
        session = _Session(deletable=60889, batch_ids=[1, 2])
        original = session.execute

        async def spy(stmt, params=None):
            if params and "cap" in params:
                seen["cap"] = params["cap"]
            return await original(stmt, params)

        session.execute = spy
        await prune(session, sport_id=37871, max_delete=137)
        assert seen.get("cap") == 137

    def test_the_default_cap_is_bounded(self):
        assert 1 <= DEFAULT_MAX_DELETE <= MAX_DELETE_CEILING


# ── property 4: explicit bounded binding ───────────────────────────────────


class TestTheDeleteIsBoundToAnIdList:
    @pytest.mark.asyncio
    async def test_the_destructive_statement_carries_the_exact_batch(self):
        session = _Session(fixtures=2, total_rows=9, keepers=2, deletable=7,
                           batch_ids=[101, 102, 103])

        out = await _apply(session, expected_min=7, expected_max=7)

        assert out["terminal"] == "complete"
        assert _deleted_event_ids(session) == [101, 102, 103]
        assert out["deleted"] == 3

    @pytest.mark.asyncio
    async def test_rows_are_locked_and_re_verified_before_the_delete(self):
        session = _Session(deletable=7, batch_ids=[101])
        await _apply(session, expected_min=7, expected_max=7)
        assert session.locked is True

    @pytest.mark.asyncio
    async def test_a_row_that_gained_a_futures_link_refuses_the_whole_batch(self):
        """The concurrent-writer case: the batch was right when it was chosen."""
        session = _Session(deletable=7, batch_ids=[101, 102],
                           verify_overrides={102: {"unlinked": False}})

        with pytest.raises(PruneRefused, match="unlinked"):
            await _apply(session, expected_min=7, expected_max=7)

        assert _deleted_event_ids(session) is None

    @pytest.mark.asyncio
    async def test_a_row_whose_keeper_disappeared_refuses_the_whole_batch(self):
        """Deleting the last copy of a fixture is the unrecoverable mistake."""
        session = _Session(deletable=7, batch_ids=[101],
                           verify_overrides={101: {"keeper_exists": False}})

        with pytest.raises(PruneRefused, match="keeper_exists"):
            await _apply(session, expected_min=7, expected_max=7)
        assert _deleted_event_ids(session) is None

    @pytest.mark.asyncio
    async def test_a_row_from_another_sport_refuses_the_whole_batch(self):
        session = _Session(deletable=7, batch_ids=[101],
                           verify_overrides={101: {"right_sport": False}})
        with pytest.raises(PruneRefused, match="right_sport"):
            await _apply(session, expected_min=7, expected_max=7)

    @pytest.mark.asyncio
    async def test_an_untagged_row_refuses_the_whole_batch(self):
        session = _Session(deletable=7, batch_ids=[101],
                           verify_overrides={101: {"tagged": False}})
        with pytest.raises(PruneRefused, match="'tagged'"):
            await _apply(session, expected_min=7, expected_max=7)

    @pytest.mark.asyncio
    async def test_a_rowcount_that_disagrees_with_the_batch_refuses(self):
        session = _Session(deletable=7, batch_ids=[101, 102], delete_rowcount=1)
        with pytest.raises(PruneRefused, match="batch held"):
            await _apply(session, expected_min=7, expected_max=7)


# ── property 5: stop-on-mismatch, mechanically ─────────────────────────────


class TestStopOnMismatch:
    @pytest.mark.asyncio
    async def test_apply_without_a_band_refuses(self):
        """A missing band must not read as an unbounded one."""
        session = _Session(deletable=60889, batch_ids=[1, 2])
        out = await prune(session, sport_id=37871, apply=True)
        assert out["terminal"] == "refused"
        assert "expected_min" in out["reason"]
        assert session.writes == []

    @pytest.mark.asyncio
    async def test_only_one_bound_supplied_still_refuses(self):
        session = _Session(deletable=60889, batch_ids=[1])
        out = await prune(session, sport_id=37871, apply=True, expected_min=60500)
        assert out["terminal"] == "refused"
        assert session.writes == []

    @pytest.mark.asyncio
    async def test_a_count_above_the_band_refuses_and_says_both_numbers(self):
        session = _Session(deletable=61501, batch_ids=[1, 2])

        out = await _apply(session, expected_min=60500, expected_max=61500)

        assert out["terminal"] == "refused"
        assert "CENSUS MISMATCH" in out["reason"]
        assert "61501" in out["reason"] and "61500" in out["reason"]
        assert session.writes == []

    @pytest.mark.asyncio
    async def test_a_count_below_the_band_refuses_too(self):
        """Both directions. A population that SHRANK unexpectedly is also drift —
        and it is the direction a reader forgives, which is why it is asserted."""
        session = _Session(deletable=60499, batch_ids=[1])
        out = await _apply(session, expected_min=60500, expected_max=61500)
        assert out["terminal"] == "refused"
        assert session.writes == []

    @pytest.mark.asyncio
    async def test_the_authorized_band_admits_todays_live_number(self):
        """Alex's band, and the census measured 2026-08-20T18:38:20Z."""
        session = _Session(fixtures=2565, total_rows=63454, keepers=2565,
                           deletable=60889, batch_ids=[1, 2, 3])

        out = await _apply(session, expected_min=60500, expected_max=61500, cap=3)

        assert out["terminal"] == "complete"
        assert out["deleted"] == 3
        assert out["remaining_deletable"] == 60886


# ── the partition: B and C cannot be pruned by this rail ───────────────────


class TestOnlyTrancheAIsPrunable:
    @pytest.mark.asyncio
    async def test_tranche_b_zero_linked_copies_is_refused_by_construction(self):
        session = _Session(fixtures=35, total_rows=7596, keepers=0, deletable=7596,
                           batch_ids=list(range(100)))

        out = await prune(session, sport_id=37871, linked_copies=0, apply=True,
                          expected_min=0, expected_max=10**9)

        assert out["terminal"] == "refused"
        assert out["batch"] == []
        assert session.writes == []

    @pytest.mark.asyncio
    async def test_tranche_c_two_or_more_linked_copies_is_refused(self):
        """Deleting here would orphan real futures links — 161 of them, measured."""
        session = _Session(fixtures=103, total_rows=1429, keepers=206, deletable=1223,
                           batch_ids=list(range(100)))

        out = await prune(session, sport_id=37871, linked_copies=2, apply=True,
                          expected_min=0, expected_max=10**9)

        assert out["terminal"] == "refused"
        assert session.writes == []

    @pytest.mark.asyncio
    async def test_the_keeper_rule_is_stated_in_the_response(self):
        session = _Session(deletable=4, batch_ids=[1])
        out = await prune(session, sport_id=37871)
        assert "futures-linked copy" in out["keeper_rule"]
        assert "zero child rows" in out["keeper_rule"], (
            "#2057's recut must be visible to the operator reading the response, not "
            "only to someone reading the SQL"
        )


class TestTheEmptyCase:
    @pytest.mark.asyncio
    async def test_an_empty_partition_is_no_work_not_a_silent_success(self):
        """gotcha #53 — an exhausted run and a mis-targeted one must not render alike."""
        session = _Session(fixtures=0, total_rows=0, keepers=0, deletable=0,
                           batch_ids=[])
        out = await prune(session, sport_id=37871, apply=True,
                          expected_min=0, expected_max=0, plan_hash="unused")
        assert out["terminal"] == "no_work"

    @pytest.mark.asyncio
    async def test_no_work_distinguishes_exhausted_from_all_withheld(self):
        """The two zero-batch cases are different facts and must not read alike.

        gotcha #53 again, one level in: "nothing left to delete" and "everything left
        is too valuable to delete" both produce an empty batch. Only the second one
        means somebody owes a ruling.
        """
        session = _Session(fixtures=40, total_rows=90, keepers=40,
                           surplus=50, deletable=0, withheld_substantive=50,
                           batch_ids=[])
        out = await prune(session, sport_id=37871)
        assert out["terminal"] == "no_work"
        assert "50 surplus" in out["reason"]
        # Rail v3: this asserted "hold child data", and that phrase was the finding-1
        # error stated in the operator's own words — child rows were only ever one of
        # the three ways a row holds something. The reason now names all three.
        assert "hold an observation" in out["reason"]
        assert "the row itself" in out["reason"]


# ═══════════════════════════════════════════════════════════════════════════
# C-DELETE-RAIL-PRE — codex's own specimens, re-run against the rebuilt rail
# ═══════════════════════════════════════════════════════════════════════════


class TestTheHostileSpecimens:
    """Every one of these deleted something, or passed a guard, on the voided rail.

    They are kept together rather than filed under the property each one violates,
    because what they have in common is the point: **not one of them changes a
    count.** The band was the whole authorization and the band sees none of this.
    """

    # ── R1: two real games, same key, and the linked one wins ──────────────

    @pytest.mark.asyncio
    async def test_r1_a_surplus_row_carrying_a_provider_anchor_is_never_deleted(self):
        """Codex built keeper 9001 / surplus 9002 with the required one-linked shape
        and distinct ``espn_id`` values, and the real ``prune()`` returned
        ``terminal=complete`` and deleted 9002 — two halves of a doubleheader, and
        ``ARTIFACT-Q378-2018-MC.md`` says BOTH must survive.

        ``provenance:unanchored`` is a creation-history tag: ``_attach_claim`` can
        stamp a provider id later without removing it. So the tag is not the invariant
        — the columns are, and they are re-derived from the locked row.
        """
        session = _Session(deletable=1, batch_ids=[9002],
                           verify_overrides={9002: {"anchor_free": False}})

        with pytest.raises(PruneRefused, match="anchor_free"):
            await _apply(session, expected_min=1, expected_max=1)

        assert _deleted_event_ids(session) is None

    @pytest.mark.asyncio
    async def test_r1_the_batch_query_refuses_anchored_rows_at_selection_too(self):
        """Belt and braces, and they fail differently: the predicate keeps anchored
        rows out of the batch, the re-verification catches one that acquired an anchor
        after selection. Only the second is a race; the first is the population."""
        from app.tasks.prune_unanchored_duplicates import _batch_sql

        sql = " ".join(str(_batch_sql()).split())
        assert "t.anchor_free = true" in sql
        assert "p.anchored_copies = 0" in sql, (
            "a fixture with ANY anchored copy is an identity question, not a "
            "duplicate — the whole fixture is withheld, not just that row"
        )

    # ── #2057 / R3: the linked copy can be the wrong keeper ────────────────

    @pytest.mark.asyncio
    async def test_2057_a_surplus_row_holding_child_data_is_never_deleted(self):
        """#2018's surplus row carried **101** ``win_prob_snapshots``. #2057 found
        17/17 duplicate games carrying markets on ONE copy only, so the linked copy is
        not automatically the substantive one.

        The rebuilt rail does not transfer those 101 rows to the keeper — transfer is
        ruling 048's harm. It declines to delete the row.
        """
        session = _Session(deletable=1, batch_ids=[15198473],
                           verify_overrides={15198473: {"empty_of_substance": False}})

        with pytest.raises(PruneRefused, match="empty_of_substance"):
            await _apply(session, expected_min=1, expected_max=1)

        assert _deleted_event_ids(session) is None

    @pytest.mark.asyncio
    async def test_r3_the_apply_path_issues_no_child_table_deletes_at_all(self):
        """The strongest form of "unique history is not destroyed": there is no
        statement that could destroy it.

        The old rail looped ``DELETE FROM <table> WHERE event_id = ANY(:ids)`` over
        eight tables. That loop is gone — every row reaching the delete has been
        proved childless twice, so the loop was ten statements that would silently
        start doing something the moment that proof weakened.
        """
        session = _Session(deletable=3, batch_ids=[101, 102, 103])

        await _apply(session, expected_min=3, expected_max=3)

        deletes = [sql for sql, _ in session.writes if sql.startswith("DELETE FROM")]
        assert deletes == ["DELETE FROM events"], (
            f"the rail issued child deletes it no longer needs: {deletes}"
        )

    # ── R2: same count, different set ──────────────────────────────────────

    @pytest.mark.asyncio
    async def test_r2_same_count_different_set_is_refused(self):
        """Codex's two-session specimen, verbatim: ``dry_batch=[101,102]`` then
        ``apply_batch=[99,102]`` — *same exact band count, different set*.

        Under READ COMMITTED the census and the batch share no MVCC snapshot, so
        ``ORDER BY commence_time, id`` — total for ONE database state — cannot bind
        two transactions. Only a content address can.
        """
        session = _Session(deletable=2, batch_ids=[101, 102],
                           batch_ids_on_apply=[99, 102])

        reviewed = compute_plan_hash(sport_id=37871, linked_copies=1, ids=[101, 102])
        out = await prune(session, sport_id=37871, apply=True,
                          expected_min=2, expected_max=2, plan_hash=reviewed)

        assert out["terminal"] == "refused"
        assert "PLAN MISMATCH" in out["reason"]
        assert _deleted_event_ids(session) is None
        assert session.writes == []

    @pytest.mark.asyncio
    async def test_r2_apply_without_a_plan_hash_refuses_even_with_a_perfect_band(self):
        """The band can be exactly right and the authorization still absent."""
        session = _Session(deletable=60889, batch_ids=[1, 2])
        out = await prune(session, sport_id=37871, apply=True,
                          expected_min=60889, expected_max=60889)
        assert out["terminal"] == "refused"
        assert "plan_hash" in out["reason"]
        assert session.writes == []

    def test_r2_the_hash_is_order_sensitive_and_partition_scoped(self):
        """Reordering means the LIMIT cut somewhere else; a different partition that
        happens to yield the same ids is a different plan."""
        a = compute_plan_hash(sport_id=1, linked_copies=1, ids=[1, 2, 3])
        assert a != compute_plan_hash(sport_id=1, linked_copies=1, ids=[3, 2, 1])
        assert a != compute_plan_hash(sport_id=2, linked_copies=1, ids=[1, 2, 3])
        assert a != compute_plan_hash(sport_id=1, linked_copies=2, ids=[1, 2, 3])
        assert a == compute_plan_hash(sport_id=1, linked_copies=1, ids=[1, 2, 3])

    # ── R4: the FK inventory ───────────────────────────────────────────────

    def test_r4_the_inventory_is_derived_from_metadata_not_restated(self):
        from app.utils.event_fk_inventory import (
            EVENT_CHILD_DISPOSITIONS,
            derive_event_child_tables,
            unclassified_event_children,
        )

        derived = derive_event_child_tables()

        # Both enumerations run 2026-08-20 — codex's C-EVENT-CHILD-CENSUS from
        # information_schema, and lane1's independent one (fingerprint
        # 31ae6a56ff829aa5). They agreed on the SET. This pins it.
        # UPDATED 2026-08-26 (#2213, queue 413): 10 -> 11. `event_provider_anchors`
        # was created in Postgres on 2026-08-24 by the `anchors_and_captures`
        # migration and had no ORM model until queue 413, so this DERIVATION could
        # not see it and the two 08-20 enumerations could not have listed it. The
        # pin moved because the schema did, which is the case this test is for —
        # it turned CI red on the new model exactly as designed, and the number is
        # updated here together with the disposition rather than instead of it.
        assert set(derived) == {
            "espn_snapshots", "event_provider_anchors", "futures_markets",
            "game_moments", "line_movement_analyses", "odds_aggregated",
            "odds_snapshots", "ranking_judgments", "score_snapshots",
            "scoring_plays", "win_prob_snapshots",
        }
        assert len(derived) == 11
        assert unclassified_event_children() == ()
        assert set(EVENT_CHILD_DISPOSITIONS) == set(derived)

    # ``test_r4_the_merge_rails_fk_list_is_still_short_and_that_is_a_LIVE_defect``
    # stood here. It was a CHARACTERIZATION test pinning the merge rails' eight-table
    # hand-list against metadata's ten, and its docstring ended: "If you are here
    # because this test failed: good. Delete it and say so."
    #
    # Saying so (queue 387 item 3): the defect it pinned is FIXED. All three
    # transfer-then-DELETE rails — ``_merge_duplicate_events_impl``,
    # ``_merge_degenerate_combat_events_impl`` and
    # ``reconcile_unanchored_events._absorb`` — now repoint through
    # ``app.utils.event_child_repoint.repoint_event_children``, whose table list is
    # DERIVED from ``Base.metadata`` on every call. ``_EVENT_FK_TABLES`` no longer
    # exists, which is why this test could not merely be inverted in place.
    #
    # Its replacement is POSITIVE and lives in ``tests/test_merge_rail_fk_repoint_r4.py``
    # — positive because a pinned "still broken" number can only ever catch the fix,
    # never the regression. It asserts that the repoint ISSUES A STATEMENT for each of
    # the ten derived tables, that no call site holds a literal table list any more,
    # and that the two children carrying an event-scoped UNIQUE constraint are
    # pre-deduped rather than left to raise ``IntegrityError`` mid-merge.

    def test_r4_the_two_tables_the_old_list_missed_are_present(self):
        """Named individually, because they failed in opposite directions and a
        set-equality assertion above would still pass if someone re-broke one."""
        from app.utils.event_fk_inventory import (
            CASCADING_CHILD_TABLES,
            derive_event_child_tables,
        )

        derived = derive_event_child_tables()
        # vanished silently under the old rail (ON DELETE CASCADE, unnamed)
        assert "game_moments" in derived
        assert "game_moments" in CASCADING_CHILD_TABLES
        # made the parent DELETE fail with an FK violation (no ON DELETE action)
        assert "ranking_judgments" in derived
        assert "ranking_judgments" not in CASCADING_CHILD_TABLES

    @pytest.mark.asyncio
    async def test_r4_an_unclassified_child_table_stops_the_rail_on_every_path(self):
        """Including the read-only one. A census that silently ignores a new child
        table is how the operator learns about it from a 500 on call 1 of 31."""
        import app.tasks.prune_unanchored_duplicates as rail

        session = _Session(deletable=5, batch_ids=[1])
        original = rail.unclassified_event_children
        rail.unclassified_event_children = lambda: ("newly_added_child_table",)
        try:
            with pytest.raises(PruneRefused, match="newly_added_child_table"):
                await prune(session, sport_id=37871)
        finally:
            rail.unclassified_event_children = original

    @pytest.mark.asyncio
    async def test_r4_the_response_names_the_cascading_tables(self):
        """An effect no response mentions is an effect nobody reviews."""
        session = _Session(deletable=5, batch_ids=[1])
        out = await prune(session, sport_id=37871)
        assert "game_moments" in out["cascading_tables"]
        # The anchor table CASCADEs too, and it is the one child whose silent
        # removal would also remove the proof that the deletion was correct — so
        # it must appear by name, not merely be counted (#2213).
        assert "event_provider_anchors" in out["cascading_tables"]
        assert len(out["substance_tables"]) == 11

    # ── R5: the never-absorbs guard, read semantically ─────────────────────

    @pytest.mark.asyncio
    async def test_r5_no_executed_statement_repoints_an_fk(self):
        """**This is the R5 fix, and the change is where it looks.**

        The old guard read ``inspect.getsource`` for the literal spellings
        ``SET event_id =`` / ``set event_id =``. Codex composed

            UPDATE odds_snapshots SET {"event_" + "id"} = :destination
             WHERE event_id = ANY(:ids)

        which **passed both predicates** — the source contains no such substring, and
        the parameter is not named ``keep``. Substring absence is not an invariant.

        A composed string is only invisible in the SOURCE. By the time it reaches the
        session it has rendered to ``SET event_id = :destination`` like any other. So
        the guard now reads the statements the rail actually executed, which catches
        every spelling that produces SQL — composed, concatenated, or f-string.
        """
        import re

        from app.utils.event_fk_inventory import derive_event_child_tables

        session = _Session(deletable=3, batch_ids=[101, 102, 103])
        recorded: list[str] = []
        original = session.execute

        async def recorder(stmt, params=None):
            recorded.append(" ".join(str(stmt).split()))
            return await original(stmt, params)

        session.execute = recorder
        await _apply(session, expected_min=3, expected_max=3)

        assert recorded, "expected the apply path to execute statements"
        children = set(derive_event_child_tables())
        repoint = re.compile(
            r"update\s+(\w+)\s+set\s+event_id\s*=", re.IGNORECASE
        )
        for sql in recorded:
            match = repoint.search(sql)
            assert match is None or match.group(1) not in children, (
                f"this rail repoints an FK onto another event: {sql!r}. That is "
                "absorption, and its ruling-048 allowlist entry is no longer true."
            )

    def test_r5_the_guard_itself_goes_red_on_the_hostile_composed_form(self):
        """A mutation test on the guard, not on the rail.

        The point of R5 was that the guard stayed green while its reason became
        false. So the guard is fed codex's exact hostile statement and must reject it
        — otherwise the test above proves only that the rail happens to be clean
        today, which is what the old one proved.
        """
        import re

        from app.utils.event_fk_inventory import derive_event_child_tables

        hostile = (
            'UPDATE odds_snapshots SET {} = :destination '
            'WHERE event_id = ANY(:ids)'
        ).format("event_" + "id")

        children = set(derive_event_child_tables())
        repoint = re.compile(r"update\s+(\w+)\s+set\s+event_id\s*=", re.IGNORECASE)
        match = repoint.search(" ".join(hostile.split()))
        assert match is not None and match.group(1) in children, (
            "the guard must reject the composed form that defeated the substring "
            "check — if this assertion fails the guard is decorative again"
        )

    def test_r5_no_orm_attribute_assignment_to_event_id(self):
        """The one form that produces no SQL text, so the runtime guard cannot see it.

        ORM assignment (``row.event_id = keeper``) is invisible to a statement
        recorder for the same reason a composed string is invisible to a source
        grep — each check has a blind spot and they are different blind spots. AST,
        not grep: a comment or a string containing ``.event_id =`` is not an
        assignment, and this must not be satisfiable by re-wording a docstring.
        """
        import ast
        import inspect

        from app.tasks import prune_unanchored_duplicates as rail

        tree = ast.parse(inspect.getsource(rail))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AugAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                assert not (
                    isinstance(target, ast.Attribute) and target.attr == "event_id"
                ), (
                    "this rail assigns to .event_id via the ORM — that is a transfer "
                    f"the statement recorder cannot see (line {node.lineno})"
                )

    @pytest.mark.asyncio
    async def test_r5_no_write_it_issues_mentions_a_keeper_id(self):
        """The original behavioural half, kept: every write is bound to the batch."""
        session = _Session(deletable=7, batch_ids=[101, 102])
        await _apply(session, expected_min=7, expected_max=7)

        assert session.writes, "expected the apply path to write"
        for sql, params in session.writes:
            assert "keep" not in (params or {}), (sql, params)
            assert set(params.get("ids", [])) <= {101, 102}, (sql, params)

    # ── R6: the keeper is locked, in a deterministic order ─────────────────

    @pytest.mark.asyncio
    async def test_r6_the_keeper_is_locked_not_merely_read(self):
        """A concurrent delete/merge could remove the keeper after the ``EXISTS``
        check while this transaction still owned the surplus — **both copies gone**,
        which is unrecoverable fixture loss."""
        session = _Session(deletable=2, batch_ids=[101, 102], keeper_ids=[500])

        await _apply(session, expected_min=2, expected_max=2)

        assert 500 in session.lock_order, (
            "the keeper was read through a correlated EXISTS and never locked"
        )

    @pytest.mark.asyncio
    async def test_r6_candidates_and_keepers_are_locked_in_one_ascending_pass(self):
        """gotcha #13 — with no ``ORDER BY`` on 2,000 candidate locks, two overlapping
        callers acquire in planner order and deadlock. One statement, ascending id."""
        session = _Session(deletable=4, batch_ids=[900, 102, 400],
                           keeper_ids=[700, 101])

        await _apply(session, expected_min=4, expected_max=4)

        assert session.lock_order == sorted(session.lock_order)
        assert set(session.lock_order) == {101, 102, 400, 700, 900}

    @pytest.mark.asyncio
    async def test_r6_a_keeper_that_vanished_before_the_lock_refuses(self):
        """The failure the lock exists to prevent, asserted rather than argued."""
        session = _Session(deletable=2, batch_ids=[101], keeper_ids=[500],
                           vanish={500})

        with pytest.raises(PruneRefused, match="KEEPER"):
            await _apply(session, expected_min=2, expected_max=2)

        assert _deleted_event_ids(session) is None


# ═══════════════════════════════════════════════════════════════════════════
# C-DELETE-RAIL-PRE-R2 — the second BLOCK, and rail v3's answer to it
# ═══════════════════════════════════════════════════════════════════════════
#
# R2's verdict: "CHILDLESS IS NOT CARRIES NOTHING: THE RAIL STILL DELETES DISTINCT GAME
# STATE STORED ON THE EVENT ROW, AND ITS USER-PIN WRITE IS IMPOSSIBLE UNDER THE DECLARED
# SCHEMA."
#
# The v2 rail turned "no child rows" into "holds no observation". Those are different
# claims, and the gap between them is a whole event row — the system's own record of
# game-existence, result and line. Ruling 048 from the destructive side: the name/time
# fixture key cannot prove two rows are one game, so emptiness cannot be read as
# duplicate identity.


class TestR2Finding1ParentLocalSubstance:
    """A childless, anchorless row can still be the only record of a distinct game."""

    def test_the_predicate_reads_the_rows_own_columns_not_only_children(self):
        """Codex's specimen was a completed 5–3 game with opening 0.57 / closing 0.64
        and zero child rows. Every column it used must be in the predicate."""
        from app.tasks.prune_unanchored_duplicates import _substance_predicate

        sql = _substance_predicate("e")
        for col in ("home_score", "away_score", "completed_at",
                    "opening_home_probability", "closing_home_probability"):
            assert f"e.{col} IS NULL" in sql, (
                f"{col} is parent-local game state and the predicate ignores it — "
                f"this is exactly the row codex deleted"
            )

    def test_status_is_weighed_even_though_it_is_never_null(self):
        """`events.status` is NOT NULL with a 'scheduled' default, so an IS NULL test
        would silently never fire. A column that cannot be absent needs a value test."""
        from app.tasks.prune_unanchored_duplicates import _substance_predicate

        assert "e.status IN ('scheduled')" in _substance_predicate("e")

    def test_empty_jsonb_is_not_mistaken_for_substance(self):
        """The other direction (gotcha #43). `{}` is what an initialized-but-never-
        written blob looks like; reading it as substance would withhold the whole
        population and the rail would do nothing while looking careful."""
        from app.tasks.prune_unanchored_duplicates import _substance_predicate

        sql = _substance_predicate("e")
        assert "e.box_score_data IS NULL OR e.box_score_data::text IN ('{}', '[]')" in sql
        assert ("e.win_probability_sources IS NULL OR "
                "e.win_probability_sources::text IN ('{}', '[]')") in sql

    def test_every_declared_parent_substance_column_reaches_the_sql(self):
        """The list and the predicate must not drift — the same failure mode R4 fixed
        for the hand-maintained FK tuple."""
        from app.tasks.prune_unanchored_duplicates import _substance_predicate
        from app.utils.event_fk_inventory import PARENT_SUBSTANCE_COLUMNS

        sql = _substance_predicate("e")
        missing = [c for c in PARENT_SUBSTANCE_COLUMNS if f"e.{c} IS NULL" not in sql]
        assert missing == [], f"declared but not enforced: {missing}"


class TestR2Finding2ThePinRefusesAtSelectionNotAtAnImpossibleWrite:
    """The pinned candidate must fail at the REAL refusal point.

    v2 emitted `UPDATE user_pins SET target_id = NULL`, which cannot succeed —
    `target_id` is `nullable=False` in both the model and the migration. On a real
    database that raises IntegrityError and the event DELETE is never reached; all 48
    committed tests were green only because the fake session accepts every UPDATE.

    So there were two defects and the NULL was the smaller one: **a pin is substance.**
    A row somebody pinned does not "carry nothing". Rail v3 withholds it at the
    predicate, where a dry run can show it, instead of discovering it at the final
    write, where nothing can.
    """

    def test_a_pin_is_classified_as_substance_not_as_a_nullable_pointer(self):
        from app.utils import event_fk_inventory as inv

        assert "user_pins" in inv.EVENT_PSEUDO_FK_SUBSTANCE
        assert not hasattr(inv, "EVENT_POINTER_TABLES"), (
            "the POINTER classification is the defect — deleting the name is what "
            "stops it being reintroduced by a well-meaning patch"
        )

    def test_a_pinned_row_is_excluded_by_the_predicate(self):
        from app.tasks.prune_unanchored_duplicates import _substance_predicate

        sql = _substance_predicate("e")
        assert "FROM user_pins" in sql
        assert "pin_type = 'event'" in sql, (
            "user_pins is polymorphic — an unscoped test would withhold rows pinned "
            "for some other entity type entirely"
        )

    @pytest.mark.asyncio
    async def test_the_apply_path_issues_no_pointer_update_at_all(self):
        """The executable half. Not 'the UPDATE is correct now' — there is no UPDATE."""
        session = _Session(fixtures=4, total_rows=9, keepers=4, surplus=5,
                           deletable=5, batch_ids=[11, 12], keeper_ids=[90])
        out = await prune(
            session, sport_id=37871, apply=True,
            expected_min=1, expected_max=99,
            plan_hash=_plan(session, cap=DEFAULT_MAX_DELETE),
        )
        assert out["terminal"] == "complete"
        updates = [sql for sql, _ in session.writes if sql.strip().startswith("UPDATE")]
        assert updates == [], (
            f"the rail still issues a pointer write: {updates}. On a real "
            f"constraint-bearing database this is an IntegrityError, not a null-out"
        )

    def test_the_response_no_longer_advertises_nullable_pointer_tables(self):
        """The operator-facing half: the response called these 'pointer_tables', i.e.
        'things I will null'. It must not describe an operation the rail cannot do."""
        from app.tasks.prune_unanchored_duplicates import prune as _p
        import inspect

        src = inspect.getsource(_p)
        assert '"pointer_tables"' not in src
        assert '"pseudo_fk_substance_tables"' in src


class TestR2Finding3TheCensusMustAccount:
    """The operating census must state its exact withheld/deletable populations.

    v2 reported `withheld_anchored` as a count of anchored ROWS while `surplus` counted
    surplus rows — different units in the same table. One anchored keeper with ten empty
    siblings reported `withheld_anchored: 1` against ten undeletable rows, leaving nine
    unexplained. Nothing caught it because nothing was ever required to add up.
    """

    @pytest.mark.asyncio
    async def test_the_three_buckets_sum_to_surplus(self):
        session = _Session(fixtures=10, total_rows=30, keepers=10, surplus=20,
                           deletable=12, withheld_substantive=5,
                           withheld_due_to_anchor=3)
        counts = await census(session, sport_id=37871, linked_copies=1)

        assert counts["surplus"] == 20
        assert counts["surplus_accounted"] == 20
        assert (counts["withheld_substantive"]
                + counts["withheld_due_to_anchor"]
                + counts["deletable"]) == counts["surplus"]

    @pytest.mark.asyncio
    async def test_a_census_that_does_not_account_REFUSES(self):
        """Codex's ten-sibling specimen: surplus 10, deletable 0, and only '1' named.
        Nine rows unexplained must be a refusal, not a footnote — an operator
        reconciling why the live population shrank has no other signal."""
        from app.tasks.prune_unanchored_duplicates import CensusDoesNotAccount

        session = _Session(fixtures=1, total_rows=11, keepers=1, surplus=10,
                           deletable=0, withheld_substantive=0,
                           withheld_due_to_anchor=1)   # <- the 9-row hole
        with pytest.raises(CensusDoesNotAccount) as exc:
            await census(session, sport_id=37871, linked_copies=1)
        assert "surplus=10" in str(exc.value)

    @pytest.mark.asyncio
    async def test_the_withheld_population_is_counted_in_ROWS_not_fixtures(self):
        """The unit bug itself. Ten surplus rows withheld by one anchored copy must
        report ten, not one."""
        session = _Session(fixtures=1, total_rows=11, keepers=1, surplus=10,
                           deletable=0, withheld_substantive=0,
                           withheld_due_to_anchor=10, anchored_copies=1)
        counts = await census(session, sport_id=37871, linked_copies=1)

        assert counts["withheld_due_to_anchor"] == 10, "rows, not fixtures"
        assert counts["anchored_copies"] == 1, "the fixture-unit figure is kept, named"

    @pytest.mark.asyncio
    async def test_the_no_work_reason_names_all_three_ways_a_row_is_held(self):
        session = _Session(fixtures=40, total_rows=90, keepers=40, surplus=50,
                           deletable=0, withheld_substantive=50, batch_ids=[])
        out = await prune(session, sport_id=37871)

        assert out["terminal"] == "no_work"
        assert "child row, pin, or a non-empty column on the row itself" in out["reason"]

    @pytest.mark.asyncio
    async def test_the_response_states_the_parent_columns_it_weighed(self):
        """R2 finding 3 is 'state the populations', and a population defined by a
        predicate is not stated until the predicate's terms are visible."""
        from app.utils.event_fk_inventory import PARENT_SUBSTANCE_COLUMNS

        session = _Session(fixtures=0, total_rows=0, keepers=0, surplus=0,
                           deletable=0, batch_ids=[])
        out = await prune(session, sport_id=37871)

        assert out["parent_substance_columns"] == list(PARENT_SUBSTANCE_COLUMNS)
        assert "home_score" in out["parent_substance_columns"]
