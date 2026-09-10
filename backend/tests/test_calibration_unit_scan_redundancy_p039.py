"""CAL-P039: the roster predicate that fixes the per-unit seq scan is redundant.

WHAT THIS GUARDS, AND WHY IT EXISTS BEFORE THE FIX DOES
-------------------------------------------------------
``vm_stats`` joins ``futures_outcomes`` to ``virtual_market`` with **no
predicate on the outcomes table at all**::

    FROM virtual_market vm
    JOIN futures_outcomes fo ON fo.market_id = vm.market_id

``virtual_market`` is referenced 7 times in the chunk SQL, so PG12+
auto-materializes it; a CTE Scan carries no index and no ordering, so the
planner's only options are hash+seqscan or N blind index lookups, and it costs
the seq scan lower. Measured against production at the real unit size (5,302
markets, ``backend/scripts/probe_chunk_unit_plan.py``, 2026-08-11):

    production shape    Seq Scan    act=3,302,680    8,378.8 ms   total 9,104.5 ms
    + roster predicate  Index Scan  act=   40,696      289.2 ms   total   477.1 ms

The fix is one redundant conjunct on that join::

    AND fo.market_id = ANY(CAST(:vm_roster_market_ids AS bigint[]))

**It is not applied yet.** ``_calibration_population_ctes`` is frozen by ruling
009 and is one of ``_main_input_fingerprint``'s four ``inspect.getsource()``
roots, so applying it invalidates the staged cursor. That is an Alex/Fable call,
not a lane call, and CAL-P038's scoped exception explicitly kept the
fingerprint frozen.

So what this file guards is the **PREMISE**, not the patch. The predicate is
sound only because, under ``frozen_vm_roster=True``:

  1. ``frozen_vm_roster`` is ``unnest`` of exactly ``:vm_roster_market_ids``
     into a ``market_id`` column, and
  2. ``virtual_market`` is an **INNER** JOIN of ``market_info`` against that
     roster on ``market_id``, so every ``vm.market_id`` is literally an element
     of the array, and therefore
  3. ``fo.market_id = vm.market_id`` **already implies**
     ``fo.market_id = ANY(:vm_roster_market_ids)``.

Change any of those three and the conjunct stops being a no-op and starts being
a population filter — the exact class of silent re-shaping that Queue 300D
Item 2's coverage-census refusal exists to prevent, and that a green test suite
would not otherwise notice, because every row count downstream would still look
self-consistent.

This guard is deliberately written to fail LOUDLY with the reason, so whoever
changes the roster wiring is told what they have invalidated rather than
discovering it as a wrong curve. A test that only asserts today's SQL string
would fail on any reformat and teach people to re-baseline it; these assertions
are about STRUCTURE, and each one names the inference it protects.
"""

from __future__ import annotations

import re

import pytest

from app.tasks.precompute_calibration import (
    VM_ROSTER_IS_GROUPED_PARAM,
    VM_ROSTER_MARKET_IDS_PARAM,
    VM_ROSTER_MARKET_INFO_EXTRA,
    VM_ROSTER_VM_IDS_PARAM,
    _calibration_population_ctes,
)

#: The measured facts this guard is attached to. Kept as data so the numbers
#: live next to the assertions that depend on them rather than in a report
#: nobody re-reads. Re-measure with ``backend/scripts/probe_chunk_unit_plan.py``.
MEASUREMENT = {
    "measured_at": "2026-08-11",
    "markets_per_unit": 5302,
    "seq_scan_act_rows": 3_302_680,
    "seq_scan_ms": 8_378.8,
    "index_scan_ms": 289.2,
    "speedup": 19.1,
}


def _squash(sql: str) -> str:
    """Collapse whitespace so structural assertions survive reformatting."""
    # Strip ``--`` comments first: several of them quote SQL fragments, and a
    # structural assertion that matches inside a comment proves nothing.
    stripped = re.sub(r"--[^\n]*", " ", sql)
    return re.sub(r"\s+", " ", stripped).strip()


@pytest.fixture(scope="module")
def frozen_sql() -> str:
    return _squash(
        _calibration_population_ctes(
            frozen_vm_roster=True,
            market_info_extra=VM_ROSTER_MARKET_INFO_EXTRA,
        )
    )


@pytest.fixture(scope="module")
def global_sql() -> str:
    return _squash(_calibration_population_ctes(frozen_vm_roster=False))


class TestRosterPredicateIsRedundant:
    """The three-step inference that makes the pushdown a no-op."""

    def test_frozen_roster_unnests_the_market_ids_param(self, frozen_sql: str) -> None:
        """Step 1: the roster's market_id column IS the bind array."""
        assert "frozen_vm_roster AS (" in frozen_sql, (
            "the frozen branch no longer declares frozen_vm_roster — the "
            "pushdown premise (step 1) cannot be checked, re-prove it"
        )
        m = re.search(r"frozen_vm_roster AS \((.*?)\), virtual_market AS \(", frozen_sql)
        assert m, "could not isolate the frozen_vm_roster CTE body"
        body = m.group(1)
        assert "unnest(" in body
        assert f":{VM_ROSTER_MARKET_IDS_PARAM}" in body, (
            f"frozen_vm_roster no longer unnests :{VM_ROSTER_MARKET_IDS_PARAM}. "
            "The redundant predicate 'fo.market_id = ANY(that array)' is only "
            "sound because the roster IS that array — re-prove before applying it."
        )
        # The three parallel arrays must stay positionally aligned with the
        # column list, or vm_id/is_grouped silently swap onto the wrong market.
        assert re.search(
            r"AS t\(\s*market_id\s*,\s*vm_id\s*,\s*is_grouped\s*\)", body
        ), "the roster column list changed shape; the array order is load-bearing"
        assert body.index(f":{VM_ROSTER_MARKET_IDS_PARAM}") < body.index(
            f":{VM_ROSTER_VM_IDS_PARAM}"
        ) < body.index(f":{VM_ROSTER_IS_GROUPED_PARAM}"), (
            "the unnest argument order no longer matches (market_id, vm_id, "
            "is_grouped) — the roster would be transposed"
        )

    def test_virtual_market_inner_joins_the_roster(self, frozen_sql: str) -> None:
        """Step 2: an INNER join, so vm.market_id cannot escape the array."""
        m = re.search(r"virtual_market AS \((.*?)\)$", frozen_sql) or re.search(
            r"virtual_market AS \((.*)", frozen_sql
        )
        assert m, "could not isolate the frozen virtual_market CTE body"
        body = m.group(1)
        assert "FROM market_info mi" in body
        join = re.search(
            r"(LEFT\s+|RIGHT\s+|FULL\s+)?(OUTER\s+)?JOIN frozen_vm_roster vr ON "
            r"vr\.market_id = mi\.market_id",
            body,
        )
        assert join, (
            "virtual_market no longer joins frozen_vm_roster on market_id — "
            "step 2 of the pushdown premise is gone"
        )
        assert join.group(1) is None and join.group(2) is None, (
            "virtual_market's roster join became an OUTER join. An outer join "
            "admits vm rows whose market_id is NOT in :vm_roster_market_ids, so "
            "'AND fo.market_id = ANY(array)' would become a real filter and "
            "silently drop population. This is the one change that makes the "
            "redundant predicate unsound while leaving every row count "
            "self-consistent."
        )

    def test_vm_stats_join_is_the_unpredicated_one(self, frozen_sql: str) -> None:
        """Step 3: the join the predicate attaches to, with nothing on `fo`."""
        m = re.search(r"vm_stats AS \((.*?)\), clean_vms AS \(", frozen_sql)
        assert m, "could not isolate the vm_stats CTE body"
        body = m.group(1)
        assert "FROM virtual_market vm JOIN futures_outcomes fo ON fo.market_id = vm.market_id" in body, (
            "vm_stats' join shape changed. It is the single Seq Scan in the "
            f"chunk plan ({MEASUREMENT['seq_scan_act_rows']:,} rows, "
            f"{MEASUREMENT['seq_scan_ms']} ms, measured "
            f"{MEASUREMENT['measured_at']}) and the target of the roster "
            "predicate — re-measure with backend/scripts/probe_chunk_unit_plan.py"
        )
        # If someone applies the fix, THIS is where it goes, and the assertion
        # above still holds because the conjunct follows the ON clause.
        assert "GROUP BY vm.vm_id" in body


class TestScopingHoldsBothWays:
    """The predicate must never leak into the unfrozen (global) build."""

    def test_global_build_has_no_roster_param(self, global_sql: str) -> None:
        for param in (
            VM_ROSTER_MARKET_IDS_PARAM,
            VM_ROSTER_VM_IDS_PARAM,
            VM_ROSTER_IS_GROUPED_PARAM,
        ):
            assert f":{param}" not in global_sql, (
                f"the global (unfrozen) population references :{param}. The "
                "global build derives vm identity from group/event cardinality "
                "over the WHOLE population and has no roster to be scoped by; a "
                "roster predicate there would filter the population to a chunk."
            )

    def test_global_build_still_derives_identity_itself(self, global_sql: str) -> None:
        assert "group_sizes AS (" in global_sql
        assert "event_sizes AS (" in global_sql
        assert "frozen_vm_roster" not in global_sql

    def test_market_info_extra_scopes_only_when_asked(self) -> None:
        unscoped = _squash(_calibration_population_ctes(frozen_vm_roster=True))
        scoped = _squash(
            _calibration_population_ctes(
                frozen_vm_roster=True, market_info_extra=VM_ROSTER_MARKET_INFO_EXTRA
            )
        )
        assert VM_ROSTER_MARKET_IDS_PARAM in _squash(VM_ROSTER_MARKET_INFO_EXTRA)
        assert _squash(VM_ROSTER_MARKET_INFO_EXTRA) in scoped
        assert _squash(VM_ROSTER_MARKET_INFO_EXTRA) not in unscoped, (
            "market_info is scoped even without market_info_extra — the caller "
            "no longer controls chunk scoping"
        )
        # Worth stating: the pushdown's soundness does NOT depend on this
        # scoping. It rests on the INNER join in step 2, which holds in both
        # variants. Asserted so a future reader does not remove the join
        # thinking market_info_extra is carrying the argument.
        for variant in (unscoped, scoped):
            assert (
                "JOIN frozen_vm_roster vr ON vr.market_id = mi.market_id" in variant
            )


class TestSeqScanIsStillWorthFixing:
    """A ratchet on the measurement, not on the SQL."""

    def test_measurement_block_is_internally_consistent(self) -> None:
        # Cheap, but it has caught a real class of rot in this lane: a headline
        # figure edited in prose while the ratio it implies was left alone
        # (CAL-P037 found CAL-P036's 439.7 MB was 257.0 MB at the real shape).
        ratio = (
            MEASUREMENT["seq_scan_ms"] + 726.0
        ) / (MEASUREMENT["index_scan_ms"] + 188.0)
        assert abs(ratio - MEASUREMENT["speedup"]) < 1.0, (
            "the recorded speed-up no longer follows from the recorded node "
            "times — re-run backend/scripts/probe_chunk_unit_plan.py and update "
            "MEASUREMENT as one edit"
        )

    def test_probe_script_exists_and_names_this_guard(self) -> None:
        from pathlib import Path

        probe = (
            Path(__file__).resolve().parents[1] / "scripts" / "probe_chunk_unit_plan.py"
        )
        assert probe.exists(), (
            "the probe that produced MEASUREMENT is gone; this guard's numbers "
            "become unfalsifiable prose the moment it is unreachable"
        )
        text = probe.read_text()
        assert "vm_stats" in text and "row_identity" in text


# ---------------------------------------------------------------------------
# D119 / CAL-P1090 — the pushdown, extended from one site to every site.
#
# CAL-P039 above measured ONE CTE and left the rest paying the same full scan.
# D119 (Alex, 2026-09-10) unlocks the frozen file for exactly one change: "each
# piece scans its own slot". The guard below is deliberately an ENUMERATION over
# the rendered SQL rather than a list of known CTEs, because the failure this
# lane keeps re-living is not a wrong predicate — it is a NEW scan site arriving
# unscoped and nobody noticing until a generation takes three days again.
#
# TWO FAMILIES, TWO SOUNDNESS ARGUMENTS. This is the part a reader must not
# collapse into one rule:
#
#   * a CTE that joins ``virtual_market`` is covered by that CTE's INNER join
#     onto ``frozen_vm_roster``, which holds in BOTH frozen variants; and
#   * a CTE that joins ``market_info`` DIRECTLY is covered only while
#     ``market_info``'s own WHERE carries the roster restriction — which is the
#     CALLER's argument, not a property of ``frozen_vm_roster``.
#
# Render the second family's conjunct without the first family's precondition
# and the "redundant" predicate silently becomes a population FILTER, with every
# downstream row count still self-consistent. That is the whole reason the two
# gates are separate, and it is what ``test_market_info_joined_scans_*`` pins.
# ---------------------------------------------------------------------------

#: The conjunct, squashed, exactly as the enumeration expects to find it.
ROSTER_CONJUNCT = f"AND fo.market_id = ANY(CAST(:{VM_ROSTER_MARKET_IDS_PARAM} AS bigint[]))"

#: Scan sites whose soundness comes from ``virtual_market``'s INNER join onto the
#: roster, so they carry the conjunct in BOTH frozen variants.
VM_JOINED_SCANS = {"vm_stats", "ranked_outcomes"}

#: Scan sites that join ``market_info`` directly, so they carry the conjunct ONLY
#: when ``market_info`` is itself roster-scoped.
MI_JOINED_SCANS = {
    "market_result_shape",
    "bundle_price_sum",
    "golf_placeholder_markets",
    "mex_field_candidates",
    "mex_field_divisor",
}


def _strip_comments(sql: str) -> str:
    # Parens inside ``--`` comments would desynchronise the depth counter below,
    # and several comments in this chain quote SQL fragments verbatim.
    return re.sub(r"--[^\n]*", " ", sql)


def _iter_ctes(sql: str):
    """Yield ``(name, body)`` for every CTE, by paren matching, not by regex.

    Written as a parser rather than a split on ``), name AS (`` so that a nested
    subquery, a window function or a reformat cannot silently drop a CTE from the
    enumeration — a dropped CTE would make this guard pass by not looking.
    """
    text = _strip_comments(sql)
    for m in re.finditer(r"(\w+) AS (?:MATERIALIZED )?\(", text):
        depth = 0
        i = m.end() - 1
        while i < len(text):
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        yield m.group(1), re.sub(r"\s+", " ", text[m.end() : i])


def _outcomes_scans(sql: str) -> dict[str, bool]:
    """CTE name -> does it carry the roster conjunct, for every CTE scanning ``fo``.

    Matches the DECLARATION ``futures_outcomes fo`` with a word boundary, which
    is what excludes the two correlated subqueries in the player-props pair
    columns (aliases ``fo8`` / ``fo9``). Those are keyed to the outer row
    (``fo8.market_id = fo.market_id``), so they are already index-driven and a
    roster conjunct on them would restrict nothing the correlation has not
    already pinned.
    """
    return {
        name: ROSTER_CONJUNCT in body
        for name, body in _iter_ctes(sql)
        if re.search(r"futures_outcomes\s+fo\b", body)
    }


class TestEveryUnitScansItsOwnSlot:
    """D119: the pushdown reaches every scan site, in the right scope."""

    def test_the_enumeration_finds_every_known_scan_site(self) -> None:
        found = set(
            _outcomes_scans(
                _calibration_population_ctes(
                    frozen_vm_roster=True,
                    market_info_extra=VM_ROSTER_MARKET_INFO_EXTRA,
                )
            )
        )
        expected = VM_JOINED_SCANS | MI_JOINED_SCANS
        assert found == expected, (
            "the set of CTEs scanning futures_outcomes changed.\n"
            f"  new/unscoped: {sorted(found - expected)}\n"
            f"  gone:         {sorted(expected - found)}\n"
            "A NEW scan site is the thing this guard exists to catch: it will "
            "pay a full 3.3M-row scan per unit (~626 s of a ~630 s unit read, "
            "measured CAL-P1090) unless it carries the roster conjunct. Add it "
            "to VM_JOINED_SCANS if it joins virtual_market, or to "
            "MI_JOINED_SCANS if it joins market_info directly — and read the "
            "two-families comment above before choosing, because the gates are "
            "NOT interchangeable."
        )

    def test_all_scans_are_scoped_when_frozen_and_market_info_is_scoped(self) -> None:
        """The production frozen shape: every site scans its own slot."""
        scans = _outcomes_scans(
            _calibration_population_ctes(
                frozen_vm_roster=True, market_info_extra=VM_ROSTER_MARKET_INFO_EXTRA
            )
        )
        unscoped = sorted(name for name, has in scans.items() if not has)
        assert not unscoped, (
            f"these CTEs still scan the whole of futures_outcomes: {unscoped}. "
            "Each one costs a full 3.3M-row seq scan per unit, paid B times per "
            "generation — which is what D119 was granted to remove."
        )

    def test_virtual_market_joined_scans_are_scoped_in_both_frozen_variants(
        self,
    ) -> None:
        """Family 1: sound on ``frozen_vm_roster`` alone."""
        scans = _outcomes_scans(_calibration_population_ctes(frozen_vm_roster=True))
        for name in VM_JOINED_SCANS:
            assert scans.get(name) is True, (
                f"{name} joins virtual_market, whose INNER join onto "
                "frozen_vm_roster holds whether or not market_info is scoped, so "
                "it should carry the conjunct in BOTH frozen variants. Losing it "
                "here means the pushdown was re-gated on the wrong precondition."
            )

    def test_market_info_joined_scans_are_not_scoped_when_market_info_is_not(
        self,
    ) -> None:
        """Family 2, and the reason the two gates are separate.

        ``frozen_vm_roster=True`` with no ``market_info_extra`` leaves
        ``market_info`` holding the WHOLE resolved population. A conjunct on
        these sites would then not be redundant — it would silently cut the
        population to the roster while every downstream count still reconciled.
        """
        scans = _outcomes_scans(_calibration_population_ctes(frozen_vm_roster=True))
        leaked = sorted(name for name in MI_JOINED_SCANS if scans.get(name))
        assert not leaked, (
            f"{leaked} carry the roster conjunct while market_info is NOT "
            "roster-scoped. The conjunct stops being a planner hint and becomes "
            "a population filter: these CTEs would silently drop every outcome "
            "outside the roster, and no row count downstream would look wrong. "
            "Re-gate on the market_info restriction being PRESENT, not on the "
            "frozen_vm_roster flag."
        )

    def test_no_scan_is_roster_scoped_on_the_global_path(self) -> None:
        scans = _outcomes_scans(_calibration_population_ctes())
        leaked = sorted(name for name, has in scans.items() if has)
        assert not leaked, (
            f"{leaked} reference the roster array on the GLOBAL path, where no "
            "roster is bound. The statement would fail to execute at best, and "
            "filter the whole population to a chunk at worst."
        )

    def test_the_enumeration_is_sensitive_to_a_dropped_conjunct(self) -> None:
        """The guard's own red test: remove one conjunct, the check must notice.

        An enumeration that silently matched nothing would pass every assertion
        above while proving nothing — the failure mode a green suite hides best.
        """
        sql = _calibration_population_ctes(
            frozen_vm_roster=True, market_info_extra=VM_ROSTER_MARKET_INFO_EXTRA
        )
        raw_conjunct = (
            f"\n                  AND fo.market_id "
            f"= ANY(CAST(:{VM_ROSTER_MARKET_IDS_PARAM} AS bigint[]))"
        )
        total = sql.count(raw_conjunct)
        assert total == len(VM_JOINED_SCANS | MI_JOINED_SCANS), (
            f"expected one conjunct per scan site, found {total}"
        )
        for nth in range(total):
            head, sep, tail = _nth_split(sql, raw_conjunct, nth)
            mutated = head + sep.replace(raw_conjunct, "") + tail
            scans = _outcomes_scans(mutated)
            assert sorted(n for n, has in scans.items() if not has), (
                f"dropping conjunct #{nth} left every CTE looking scoped — the "
                "enumeration is not actually reading the SQL it claims to read"
            )


def _nth_split(sql: str, needle: str, nth: int) -> tuple[str, str, str]:
    idx = -1
    for _ in range(nth + 1):
        idx = sql.index(needle, idx + 1)
    return sql[:idx], needle, sql[idx + len(needle) :]


class TestRosterGateIsHashedIntoTheCursorFingerprint:
    """A SQL-shaping helper that is not hashed is a resumable half-old payload."""

    def test_the_gate_helper_is_a_root_of_both_fingerprints(self) -> None:
        import inspect

        from app.tasks import precompute_calibration as pc

        for fn in (pc.population_predicate_fingerprint, pc._main_input_fingerprint):
            source = inspect.getsource(fn)
            assert "_roster_pushdown_predicates" in source, (
                f"{fn.__name__} does not hash _roster_pushdown_predicates. "
                "inspect.getsource covers a function and never its callees, so "
                "widening the pushdown gate would change which rows a chunk "
                "reads while leaving a carried cursor resumable — units built "
                "from two different populations merged into one payload."
            )

    def test_changing_the_gate_moves_the_digest(self, monkeypatch) -> None:
        from app.tasks import precompute_calibration as pc

        before = pc._main_input_fingerprint()

        def _widened(*, frozen_vm_roster: bool, market_info_extra: str):
            return ("", "")

        monkeypatch.setattr(pc, "_roster_pushdown_predicates", _widened)
        assert pc._main_input_fingerprint() != before, (
            "the digest did not move when the pushdown gate changed — the "
            "fingerprint is not actually reading this helper's source"
        )


class TestCoverageUniverseSharesTheSameGate:
    """The census' universe joins market_info too, so it takes the same rule."""

    def test_chunk_scoped_universe_carries_a_supplied_predicate(self) -> None:
        from app.tasks.precompute_calibration import _coverage_universe_cte

        scoped = _squash(
            _coverage_universe_cte(chunk_scoped=True, roster_predicate="\n  AND x")
        )
        assert "JOIN market_info mi ON mi.market_id = fo.market_id AND x" in scoped

    def test_global_universe_never_takes_one(self) -> None:
        from app.tasks.precompute_calibration import _coverage_universe_cte

        glob = _squash(
            _coverage_universe_cte(chunk_scoped=False, roster_predicate="\n  AND x")
        )
        assert "AND x" not in glob, (
            "the global coverage universe joins futures_markets over the WHOLE "
            "resolved population; a roster predicate there is a real filter"
        )

    def test_the_chunk_scope_guard_still_sees_its_market_info_join(self) -> None:
        """``_main_futures_sql`` refuses the census unless it finds this string."""
        from app.tasks.precompute_calibration import _coverage_universe_cte

        universe = _coverage_universe_cte(
            chunk_scoped=True, roster_predicate="\n                  AND whatever"
        )
        assert "JOIN market_info" in universe, (
            "the pushdown broke the substring _main_futures_sql greps for before "
            "enabling the census; it would refuse to build with the census on"
        )
