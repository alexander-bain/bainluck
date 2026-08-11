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
