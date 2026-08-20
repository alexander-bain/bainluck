"""#2020 — the bounded delete rail, and the five properties that make it usable.

Queue 382 was authorized to delete ~61,000 rows attended, *"with a per-batch dry-run
whose census must match the plan exactly, stop-on-mismatch."* It stopped, because no
rail in production could do that: the only capable endpoint took a comma-separated id
list with no ``apply=false``, no census and no cap, so the authorized shape reduced to
~500 unverifiable destructive calls.

Every test here asserts a property whose absence is why that stop happened. They are
written against a fake session rather than a database because the properties under
test are about **what the rail refuses to do**, and a refusal is provable without
Postgres — the SQL correctness is a separate, weaker claim, covered by running the
census predicate against production and comparing it to the authorized plan.

The load-bearing one is ``TestStopOnMismatch``: a human promising to check the census
and a rail refusing on the census are not the same object, and only the second one
survives being run 31 times in a row at 2am.
"""

import pytest

from app.tasks.prune_unanchored_duplicates import (
    DEFAULT_MAX_DELETE,
    MAX_DELETE_CEILING,
    PruneRefused,
    census,
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
    """Answers census / batch / verify by SQL shape, and records every write.

    ``verify_overrides`` lets a test make one candidate row fail re-verification —
    the concurrent-writer case, which is the only way a correct batch query can still
    hand back a row that must not be deleted.
    """

    def __init__(
        self, *, fixtures=0, total_rows=0, keepers=0, deletable=0,
        batch_ids=None, verify_overrides=None, delete_rowcount=None,
    ):
        self._census = {
            "fixtures": fixtures, "total_rows": total_rows,
            "keepers": keepers, "deletable": deletable,
        }
        self._batch = batch_ids if batch_ids is not None else []
        self._verify_overrides = verify_overrides or {}
        self._delete_rowcount = delete_rowcount
        self.writes: list[tuple[str, dict]] = []
        self.locked = False

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

        if "FOR UPDATE" in sql:
            self.locked = True
            rows = []
            for i in params.get("ids", []):
                row = {
                    "id": i, "right_sport": True, "tagged": True,
                    "unlinked": True, "keeper_exists": True,
                }
                row.update(self._verify_overrides.get(i, {}))
                if self._verify_overrides.get(i) == "VANISH":
                    continue
                rows.append(row)
            return _Result(rows)

        if "COUNT(*) AS fixtures" in sql or "AS deletable" in sql:
            return _Result([self._census])

        # the batch query
        return _Result([(i,) for i in self._batch])

    async def rollback(self):
        pass


def _deleted_event_ids(session):
    for sql, params in session.writes:
        if sql.strip() == "DELETE FROM events":
            return params["ids"]
    return None


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
        """A rehearsal that skips a statement is not a rehearsal.

        ``_VERIFY_SQL`` is the only query the apply path runs that the census and
        batch queries do not, and it is the most intricate of the three (a
        ``FOR UPDATE`` with two correlated EXISTS). If the dry run skipped it, the
        first thing an operator would learn about a defect in it is a 500 on the
        first destructive call of a 31-call run. So the dry run runs it — the locks
        are released by the caller's rollback.
        """
        session = _Session(deletable=7, batch_ids=[101, 102])

        out = await prune(session, sport_id=37871)

        assert session.locked is True, "the dry run must exercise the FOR UPDATE query"
        assert out["verified"] is True
        assert out["deleted"] == 0
        assert session.writes == []

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
        for apply_flag, kwargs in (
            (False, {}),
            (True, {"expected_min": 0, "expected_max": 10**9}),
        ):
            session = _Session(fixtures=1, total_rows=5, keepers=1, deletable=4,
                               batch_ids=[7, 8, 9, 10])
            out = await prune(session, sport_id=37871, apply=apply_flag, **kwargs)
            assert out["census"] == {
                "fixtures": 1, "total_rows": 5, "keepers": 1, "deletable": 4,
            }, out

    @pytest.mark.asyncio
    async def test_census_is_callable_on_its_own(self):
        session = _Session(fixtures=35, total_rows=7596, keepers=0, deletable=7596)
        assert (await census(session, sport_id=37871, linked_copies=0))["fixtures"] == 35


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
        """No predicate on the DELETE that could match a row nobody counted."""
        session = _Session(fixtures=2, total_rows=9, keepers=2, deletable=7,
                           batch_ids=[101, 102, 103])

        out = await prune(session, sport_id=37871, apply=True,
                          expected_min=7, expected_max=7)

        assert out["terminal"] == "complete"
        assert _deleted_event_ids(session) == [101, 102, 103]
        assert out["deleted"] == 3

    @pytest.mark.asyncio
    async def test_rows_are_locked_and_re_verified_before_the_delete(self):
        session = _Session(deletable=7, batch_ids=[101])
        await prune(session, sport_id=37871, apply=True,
                    expected_min=7, expected_max=7)
        assert session.locked is True

    @pytest.mark.asyncio
    async def test_a_row_that_gained_a_futures_link_refuses_the_whole_batch(self):
        """The concurrent-writer case: the batch was right when it was chosen.

        Refusing the BATCH rather than skipping the row is deliberate — a partition
        that changed under the census is a partition whose census is stale, and the
        next call re-reads it.
        """
        session = _Session(deletable=7, batch_ids=[101, 102],
                           verify_overrides={102: {"unlinked": False}})

        with pytest.raises(PruneRefused, match="unlinked"):
            await prune(session, sport_id=37871, apply=True,
                        expected_min=7, expected_max=7)

        assert _deleted_event_ids(session) is None

    @pytest.mark.asyncio
    async def test_a_row_whose_keeper_disappeared_refuses_the_whole_batch(self):
        """Deleting the last copy of a fixture is the unrecoverable mistake."""
        session = _Session(deletable=7, batch_ids=[101],
                           verify_overrides={101: {"keeper_exists": False}})

        with pytest.raises(PruneRefused, match="keeper_exists"):
            await prune(session, sport_id=37871, apply=True,
                        expected_min=7, expected_max=7)
        assert _deleted_event_ids(session) is None

    @pytest.mark.asyncio
    async def test_a_row_from_another_sport_refuses_the_whole_batch(self):
        session = _Session(deletable=7, batch_ids=[101],
                           verify_overrides={101: {"right_sport": False}})
        with pytest.raises(PruneRefused, match="right_sport"):
            await prune(session, sport_id=37871, apply=True,
                        expected_min=7, expected_max=7)

    @pytest.mark.asyncio
    async def test_an_untagged_row_refuses_the_whole_batch(self):
        session = _Session(deletable=7, batch_ids=[101],
                           verify_overrides={101: {"tagged": False}})
        with pytest.raises(PruneRefused, match="'tagged'"):
            await prune(session, sport_id=37871, apply=True,
                        expected_min=7, expected_max=7)

    @pytest.mark.asyncio
    async def test_a_rowcount_that_disagrees_with_the_batch_refuses(self):
        """Bound to an id list, so a mismatch means something else deleted them."""
        session = _Session(deletable=7, batch_ids=[101, 102], delete_rowcount=1)
        with pytest.raises(PruneRefused, match="batch held"):
            await prune(session, sport_id=37871, apply=True,
                        expected_min=7, expected_max=7)


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

        out = await prune(session, sport_id=37871, apply=True,
                          expected_min=60500, expected_max=61500)

        assert out["terminal"] == "refused"
        assert "CENSUS MISMATCH" in out["reason"]
        assert "61501" in out["reason"] and "61500" in out["reason"]
        assert session.writes == []

    @pytest.mark.asyncio
    async def test_a_count_below_the_band_refuses_too(self):
        """Both directions. A population that SHRANK unexpectedly is also drift —
        and it is the direction a reader forgives, which is why it is asserted."""
        session = _Session(deletable=60499, batch_ids=[1])
        out = await prune(session, sport_id=37871, apply=True,
                          expected_min=60500, expected_max=61500)
        assert out["terminal"] == "refused"
        assert session.writes == []

    @pytest.mark.asyncio
    async def test_the_authorized_band_admits_todays_live_number(self):
        """Alex's band, and the census measured 2026-08-20T18:38:20Z.

        Pinned as a literal so that a future change to the band's meaning has to
        walk past this test rather than around it.
        """
        session = _Session(fixtures=2565, total_rows=63454, keepers=2565,
                           deletable=60889, batch_ids=[1, 2, 3])

        out = await prune(session, sport_id=37871, apply=True,
                          expected_min=60500, expected_max=61500, max_delete=3)

        assert out["terminal"] == "complete"
        assert out["deleted"] == 3
        assert out["remaining_deletable"] == 60886


# ── the partition: B and C cannot be pruned by this rail ───────────────────


class TestOnlyTrancheAIsPrunable:
    @pytest.mark.asyncio
    async def test_tranche_b_zero_linked_copies_is_refused_by_construction(self):
        """No linked copy means no keeper rule — and 35 fixtures of esports with
        every provider id NULL is precisely the population where guessing a keeper
        would be the whole mistake."""
        session = _Session(fixtures=35, total_rows=7596, keepers=0, deletable=7596,
                           batch_ids=list(range(100)))

        out = await prune(session, sport_id=37871, linked_copies=0, apply=True,
                          expected_min=0, expected_max=10**9)

        assert out["terminal"] == "refused"
        assert out["batch"] == []
        assert session.writes == []

    @pytest.mark.asyncio
    async def test_tranche_c_two_or_more_linked_copies_is_refused(self):
        """Deleting here would orphan real futures links."""
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
        assert out["keeper_rule"] == "the futures-linked copy"


class TestTheRailNeverAbsorbs:
    """The claim the ruling-048 census allowlist is standing on, made checkable.

    `DELETE_WITHOUT_MERGE_ALLOWLIST` in ``test_event_merge_invariant_r6.py`` exempts
    this rail from the invariant on ONE ground: it establishes a pairing but performs
    no absorption. Ruling 048's harm requires a **transfer** — every merging rail
    repoints ``SET event_id = :keep`` before deleting, and that is how 5,142 / 540 /
    2,097 rows of one game's data ended up on another's (#1779/#1798).

    An allowlist reason nobody executes is the thing the allowlist docstring warns
    about ("the reason is what a reviewer checks"). So the reason is executed here.
    If someone later adds a repoint to this rail — a reasonable-looking change, since
    every neighbouring rail does exactly that — this goes red before the allowlist
    entry silently becomes a lie.
    """

    def test_the_rail_never_repoints_an_fk_onto_a_keeper(self):
        import inspect

        from app.tasks import prune_unanchored_duplicates as rail

        source = inspect.getsource(rail)
        # the merging spelling, in every casing the codebase actually uses
        for forbidden in ("SET event_id =", "set event_id ="):
            assert forbidden not in source, (
                f"this rail now repoints an FK ({forbidden!r}) — that is absorption, "
                "and its ruling-048 allowlist entry is no longer true. Either remove "
                "the repoint or route the rail through event_merge_invariant."
            )

    @pytest.mark.asyncio
    async def test_no_write_it_issues_mentions_a_keeper_id(self):
        """The behavioural half: every write is bound to the batch, never the keeper."""
        session = _Session(deletable=7, batch_ids=[101, 102])
        await prune(session, sport_id=37871, apply=True,
                    expected_min=7, expected_max=7)

        assert session.writes, "expected the apply path to write"
        for sql, params in session.writes:
            assert "keep" not in (params or {}), (sql, params)
            assert set(params.get("ids", [])) <= {101, 102}, (sql, params)


class TestTheEmptyCase:
    @pytest.mark.asyncio
    async def test_an_empty_partition_is_no_work_not_a_silent_success(self):
        """gotcha #53 — an exhausted run and a mis-targeted one must not render alike."""
        session = _Session(fixtures=0, total_rows=0, keepers=0, deletable=0,
                           batch_ids=[])
        out = await prune(session, sport_id=37871, apply=True,
                          expected_min=0, expected_max=0)
        assert out["terminal"] == "no_work"
        assert out["deleted"] == 0
