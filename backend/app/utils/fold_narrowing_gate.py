"""CAL-P098 — the executable ruler for the fold-narrowing rewrite (`C-FOLD-REWRITE-1`).

WHY THIS FILE EXISTS. `C-FOLD-REWRITE-1` returned **BLOCK** on CAL-P096's head with
four P1 findings, and three of them are the same finding wearing different hats:
*the frozen gate could not be executed as written, because no instrument existed
that could execute it.* The row-identity evidence was two separate HTTP POSTs
against the admin rail — two sessions, two snapshots, one MD5 — where the frozen
G1 demands OLD and NEW inside **one** ``REPEATABLE READ, READ ONLY`` transaction
compared by **bilateral ``EXCEPT ALL``**. The named-node gate (G3) was unmeasured
entirely, because the rail composes ``EXPLAIN`` without ``ANALYZE`` and its
row-returning path is pinned at a 10 s statement timeout. And four of G4's five
mutation controls did not exist, so the comparator's power was never
demonstrated: a comparator nobody has fooled on purpose is a comparator nobody
has tested.

So this module is the ruler, in one place, consumed by three callers that must
not drift apart:

* ``backend/scripts/verify_fold_narrowing_row_identity.py`` — the DB-direct
  runner (one-off dyno / worker; the agent sandbox has no route to 5432).
* ``backend/tests/integration/test_calibration_fold_narrowing_row_identity_pg.py``
  — the CI gate, which runs these **exact statements** against a seeded real
  Postgres, so the harness is proved executable before production ever sees it.
* the mutation controls, which drive the same statements through five deliberate
  defects and require each one to be caught.

WHAT IS DELIBERATELY NOT HERE. No population SQL. The kill criteria make "a
comparator that reads a reimplementation rather than each tree's shipping
builder" an automatic BLOCK, so both chains are arguments to every function
below: NEW comes from ``_calibration_population_ctes()`` on the tree under test,
OLD from the frozen pre-split emission. This module never authors either, and it
has no opinion about which is which — it only compares.

ONE MORE THING THE BLOCK TAUGHT. An empty comparison agrees with itself. Every
verdict below treats ``n_old = 0`` as **NOT MEASURED**, never as agreement
(gotcha #53), because a sampled residue that happens to select no resolved
market returns exactly the same zeros as a perfect match.
"""

from __future__ import annotations

import statistics
from typing import Any, Iterable, Sequence

from app.utils.sql_comment_strip import strip_sql_comments

# ---------------------------------------------------------------------------
# The frozen sample plan
# ---------------------------------------------------------------------------

#: G1's frozen minimum: "at least eight non-adjacent residues spanning
#: ``MOD(fm.id, 64)`` and ``MOD(fm.id, 257)``, including residue 0 and both edge
#: residues."
#:
#: Read that as three separate requirements, because CAL-P096's MOD 997/9973
#: sampling satisfied none of them and still looked thorough:
#:
#: * **two moduli**, so a defect keyed on a stride cannot hide in one of them —
#:   64 is a power of two (``fm.id`` is a bigserial, so residues mod 64 track
#:   insertion order in blocks) and 257 is prime (residues scatter);
#: * **non-adjacent** residues, so consecutive-id neighbourhoods are not the
#:   whole sample;
#: * **residue 0 and both edges**, because 0 and ``k-1`` are the two residues an
#:   off-by-one in a sample predicate lands on.
#:
#: Eight is the floor, not the target. ``--residue`` widens it.
RESIDUE_PLAN: tuple[tuple[int, int], ...] = (
    (64, 0),
    (64, 31),
    (64, 63),
    (257, 0),
    (257, 61),
    (257, 127),
    (257, 191),
    (257, 256),
)

#: Every column G1 names as semantically consumed. ``deduped`` is compared with
#: ``SELECT *`` — which is strictly stronger, since it also covers columns the
#: frozen list did not think to name — but the list is asserted present so a
#: future projection change cannot quietly drop one of them out of the oracle.
G1_REQUIRED_COLUMNS: tuple[str, ...] = (
    "market_id",
    "outcome_id",
    "outcome_name",
    "vm_id",
    "source",
    "category",
    "market_type",
    "llm_league",
    "is_winner",
    "price_moved",
    "raw_cp",
    "adj_opening_probability",
    "rn",
    "rn_distance_rank",
    "eligible",
    "is_grouped",
    "is_multi",
    "candidate_market_id",
    "mnm_cp_sum",
    "is_mex_normalized",
    "is_field_incomplete",
    "is_liquid",
    "is_poly_placeholder",
    "is_poly_never_traded",
    "is_malformed_binary",
    "malformed_win_count",
    "is_esports_bundle",
    "is_no_winner_market",
    "is_draw_authority_missing",
    "is_orphan_partition",
    "is_nonexclusive_bundle",
    "is_golf_placeholder",
    "is_kalshi_prop_threshold",
    "is_weather_wide_spread",
)

#: The CTE that carries the two window functions, per tree. OLD computes them
#: inside ``ranked_outcomes`` (over the nine-way LEFT JOIN); NEW computes them
#: inside ``ranked_outcomes_core`` (over ``fo ⋈ virtual_market ⋈ clean_vms``) and
#: joins the nine afterwards. G3's "named node" is version-specific for exactly
#: this reason, and the frozen text says so: *"the Sort directly feeding the
#: ``ranked_outcomes`` WindowAgg (or the renamed core equivalent)"*.
OLD_WINDOW_CTE = "ranked_outcomes"
NEW_WINDOW_CTE = "ranked_outcomes_core"

#: The node types that ARE the window's sort. Both, and the second one is not a
#: nicety — it is what the gate's first CI execution actually found.
#:
#: G3 is about the row the window sorts, and PostgreSQL has two nodes that sort
#: a window's input. Requiring the literal string ``Sort`` made the gate
#: unmeasurable wherever the planner picked the other one, and it reported that
#: as "the named node moved" — i.e. as a fault in the rewrite — rather than as a
#: fault in the ruler. On CI's seed the plan is:
#:
#:     WindowAgg [CTE ranked_outcomes] width=1032
#:       WindowAgg width=1194
#:         Incremental Sort width=1186
#:
#: An Incremental Sort IS the sort under the window; it carries ``Plan Width``,
#: which is the whole of the clause CI can grade. What it does NOT carry is a
#: single ``Sort Method`` / ``Sort Space Used`` — it reports per-group figures
#: instead — so ``sort_node_type`` is returned alongside the metrics and the
#: spill fields come back ``None`` rather than zero. A reader must be able to
#: tell "no spill" from "this shape does not report spill that way".
SORT_NODE_TYPES = frozenset({"Sort", "Incremental Sort"})


def sample_predicate(mod: int | None, residue: int) -> str:
    """The G1 sample, injected **only** into ``market_info``, identically on both.

    G1 is explicit that the predicate goes in one place: *"inject the sample
    predicate only in ``market_info``, identically on both statements."* A
    predicate anywhere else is a population change, and a population change is
    a kill criterion rather than a sampling choice.
    """
    if mod is None:
        return ""
    if mod <= 0:
        raise ValueError(f"modulus must be positive, got {mod}")
    if not 0 <= residue < mod:
        raise ValueError(f"residue {residue} out of range for modulus {mod}")
    return f"AND MOD(fm.id, {mod}) = {residue}"


def residues_are_non_adjacent(plan: Sequence[tuple[int, int]]) -> bool:
    """True when no two sampled residues of the same modulus are neighbours."""
    by_mod: dict[int, list[int]] = {}
    for mod, residue in plan:
        by_mod.setdefault(mod, []).append(residue)
    for mod, residues in by_mod.items():
        ordered = sorted(residues)
        for lo, hi in zip(ordered, ordered[1:]):
            if hi - lo < 2:
                return False
    return True


# ---------------------------------------------------------------------------
# G1 — bilateral row identity
# ---------------------------------------------------------------------------

#: The bucket tuple the Queue 299 / #259 precedent names as the AGGREGATE
#: comparator — the thing that must stay green while row identity goes red on a
#: swapped row. It is the secondary check, never the oracle.
_BUCKET_SELECT = """
        SELECT source, category, price_moved,
               width_bucket(adj_opening_probability, 0, 1, 10) AS bucket_idx,
               COUNT(*) AS n,
               COUNT(*) FILTER (WHERE is_winner) AS winners,
               SUM(adj_opening_probability) AS sum_prob
        FROM {relation}
        GROUP BY 1, 2, 3, 4
"""


def g1_statement(
    *,
    old_chain: str,
    new_chain: str,
    new_rows_expr: str = "SELECT * FROM new_base",
    strip_comments: bool = True,
) -> str:
    """One statement, one snapshot, both directions of ``EXCEPT ALL``.

    Each chain is nested inside its own scalar subquery so the two identical CTE
    name sets cannot collide — PostgreSQL scopes a ``WITH`` to the sub-SELECT
    that carries it, which is what makes a single-statement comparison possible
    at all. That matters more than it sounds: the alternative CAL-P096 reached
    for was two HTTP requests, and two requests are two snapshots on a
    population that ingests continuously.

    ``new_rows_expr`` is the mutation seam. It defaults to the identity, and the
    G4 controls replace it with a relation that differs from ``new_base`` in one
    deliberate way — a swapped row, most importantly, which is the only mutant
    that keeps every bucket aggregate identical.
    """
    sql = f"""
WITH
old_rows AS MATERIALIZED (
    SELECT * FROM (
        WITH {old_chain}
        SELECT * FROM deduped
    ) AS _old_chain
),
new_base AS MATERIALIZED (
    SELECT * FROM (
        WITH {new_chain}
        SELECT * FROM deduped
    ) AS _new_chain
),
new_rows AS MATERIALIZED (
    {new_rows_expr}
),
old_only AS (SELECT * FROM old_rows EXCEPT ALL SELECT * FROM new_rows),
new_only AS (SELECT * FROM new_rows EXCEPT ALL SELECT * FROM old_rows),
dup_old AS (SELECT outcome_id, COUNT(*) AS c FROM old_rows GROUP BY outcome_id),
dup_new AS (SELECT outcome_id, COUNT(*) AS c FROM new_rows GROUP BY outcome_id),
buckets_old AS ({_BUCKET_SELECT.format(relation="old_rows")}),
buckets_new AS ({_BUCKET_SELECT.format(relation="new_rows")})
SELECT
    (SELECT COUNT(*) FROM old_rows)                       AS n_old,
    (SELECT COUNT(*) FROM new_rows)                       AS n_new,
    (SELECT COUNT(DISTINCT market_id) FROM old_rows)      AS markets_old,
    (SELECT COUNT(DISTINCT market_id) FROM new_rows)      AS markets_new,
    (SELECT COUNT(*) FROM old_only)                       AS old_only_rows,
    (SELECT COUNT(*) FROM new_only)                       AS new_only_rows,
    (SELECT COUNT(*) FROM (SELECT * FROM dup_old EXCEPT ALL SELECT * FROM dup_new) x)
                                                          AS dup_old_only,
    (SELECT COUNT(*) FROM (SELECT * FROM dup_new EXCEPT ALL SELECT * FROM dup_old) x)
                                                          AS dup_new_only,
    (SELECT COALESCE(MAX(c), 0) FROM dup_old)             AS max_dup_old,
    (SELECT COALESCE(MAX(c), 0) FROM dup_new)             AS max_dup_new,
    (SELECT COUNT(*) FROM (SELECT * FROM buckets_old EXCEPT ALL SELECT * FROM buckets_new) x)
                                                          AS bucket_old_only,
    (SELECT COUNT(*) FROM (SELECT * FROM buckets_new EXCEPT ALL SELECT * FROM buckets_old) x)
                                                          AS bucket_new_only,
    (SELECT COUNT(*) FROM buckets_old)                    AS n_buckets_old,
    (SELECT COUNT(*) FROM buckets_new)                    AS n_buckets_new
""".strip()
    return strip_sql_comments(sql) if strip_comments else sql


#: The keys ``g1_statement`` returns, in order. asyncpg hands back a Record and
#: SQLAlchemy a Row; both are zipped against this rather than trusting position
#: at the call site.
G1_COLUMNS: tuple[str, ...] = (
    "n_old",
    "n_new",
    "markets_old",
    "markets_new",
    "old_only_rows",
    "new_only_rows",
    "dup_old_only",
    "dup_new_only",
    "max_dup_old",
    "max_dup_new",
    "bucket_old_only",
    "bucket_new_only",
    "n_buckets_old",
    "n_buckets_new",
)


def row_swap_expr(*, columns: Sequence[str], victim_outcome_id: int, offset: int) -> str:
    """G4 control 3: delete one final row, insert one with the same aggregate.

    The replacement carries every column of the victim except ``outcome_id``,
    which is displaced by ``offset``. ``outcome_id`` is in **no** bucket key and
    in no aggregate, so:

    * the bucket comparator must stay GREEN — same source, category,
      ``price_moved``, bucket, count, winners and probability sum;
    * the row-identity comparator must go RED — one old-only row and one
      new-only row.

    That disagreement is the whole point of Queue 299's precedent, and the
    frozen G1 says so in as many words: *"if the suite cannot demonstrate this
    disagreement, G1 is vacuous and the cert is BLOCK."* The column list is read
    from the live relation rather than hard-coded, so adding a column to
    ``deduped`` cannot silently reduce what the swap perturbs.
    """
    if "outcome_id" not in columns:
        raise ValueError("deduped has no outcome_id column — the swap has no key")
    projected = ", ".join(
        f"outcome_id + {int(offset)} AS outcome_id" if c == "outcome_id" else c
        for c in columns
    )
    return (
        f"SELECT * FROM new_base WHERE outcome_id <> {int(victim_outcome_id)}\n"
        f"    UNION ALL\n"
        f"    SELECT {projected} FROM new_base WHERE outcome_id = {int(victim_outcome_id)}"
    )


def g1_verdict(row: dict[str, Any]) -> tuple[str, list[str]]:
    """PASS / FAIL / NOT_MEASURED for one sampled residue.

    ``NOT_MEASURED`` is a first-class outcome and is never folded into PASS. A
    residue that selected nothing produces all-zero counters, which is
    byte-identical to a perfect comparison — the difference between "they agree"
    and "there was nothing to disagree about" is ``n_old``, and nothing else.
    """
    reasons: list[str] = []
    if int(row["n_old"]) == 0 and int(row["n_new"]) == 0:
        return "NOT_MEASURED", ["the sample published zero rows on both sides"]

    if int(row["old_only_rows"]):
        reasons.append(f"{row['old_only_rows']} old-only row(s) under EXCEPT ALL")
    if int(row["new_only_rows"]):
        reasons.append(f"{row['new_only_rows']} new-only row(s) under EXCEPT ALL")
    if int(row["n_old"]) != int(row["n_new"]):
        reasons.append(f"row count {row['n_old']} -> {row['n_new']}")
    if int(row["dup_old_only"]) or int(row["dup_new_only"]):
        reasons.append(
            "duplicate cardinality by outcome_id differs "
            f"({row['dup_old_only']} / {row['dup_new_only']})"
        )
    if int(row["bucket_old_only"]) or int(row["bucket_new_only"]):
        reasons.append(
            "grouped buckets differ "
            f"({row['bucket_old_only']} / {row['bucket_new_only']}) — "
            "secondary check, reported after the row oracle"
        )
    return ("PASS" if not reasons else "FAIL"), reasons


# ---------------------------------------------------------------------------
# G3 — the named node
# ---------------------------------------------------------------------------

#: G3's width bar: the new Sort's ``Plan Width`` at most 25% of the old one.
G3_MAX_WIDTH_RATIO = 0.25
#: G3's time bar on the median of Sort + WindowAgg actual time.
G3_MAX_MEDIAN_TIME_RATIO = 0.70
#: G3's per-sample regression bar. No single sample may be more than 10% slower.
G3_MAX_SAMPLE_REGRESSION = 1.10


def g3_statement(chain: str, *, strip_comments: bool = True) -> str:
    """``EXPLAIN (ANALYZE, BUFFERS, VERBOSE, FORMAT JSON)`` over the real chain.

    ``ANALYZE`` executes. That is the point and it is also why the runner sets a
    statement timeout per statement and reports a cancellation as
    ``NOT_MEASURED``: planner cost is not a performance verdict, and CAL-P096's
    artifact recording only ``5,145,793 -> 3,034,646`` is precisely the claim
    the frozen gate refuses to accept.
    """
    sql = f"EXPLAIN (ANALYZE, BUFFERS, VERBOSE, FORMAT JSON)\nWITH {chain}\nSELECT * FROM deduped"
    return strip_sql_comments(sql) if strip_comments else sql


def _walk(node: dict) -> Iterable[dict]:
    yield node
    for child in node.get("Plans", []) or []:
        yield from _walk(child)


def find_window_cte(plan_root: dict, cte_name: str) -> dict | None:
    """The plan node that IS the named CTE, located by ``Subplan Name``.

    PostgreSQL labels a materialized CTE's own plan ``CTE <name>``. Matching on
    that is stable across plan shapes in a way that "the deepest Sort" is not —
    this population sorts in several places and picking the wrong one is how a
    performance gate reports a number about an unrelated node.
    """
    wanted = f"CTE {cte_name}"
    for node in _walk(plan_root):
        if node.get("Subplan Name") == wanted:
            return node
    return None


def named_node_metrics(plan_root: dict, cte_name: str) -> dict[str, Any]:
    """Sort + WindowAgg actuals for the window CTE, or a stated reason why not.

    The two windows (``rn`` and ``rn_distance_rank``) share an ORDER BY prefix,
    so PostgreSQL satisfies both from one Sort — but it still emits **two**
    WindowAgg nodes, stacked. The measured pair is the INNER WindowAgg (the one
    whose child is the Sort) plus that Sort; the OUTER WindowAgg's total cost is
    reported separately as the subtree cost, because that is the number
    ``C-FOLD-EXPLAIN-1`` called 84.2% of the plan.
    """
    cte = find_window_cte(plan_root, cte_name)
    if cte is None:
        return {"measured": False, "reason": f"no plan node named 'CTE {cte_name}'"}

    windows = [n for n in _walk(cte) if n.get("Node Type") == "WindowAgg"]
    if not windows:
        return {"measured": False, "reason": f"CTE {cte_name} contains no WindowAgg"}

    inner = None
    for node in windows:
        children = node.get("Plans", []) or []
        if len(children) == 1 and children[0].get("Node Type") in SORT_NODE_TYPES:
            inner = node
            break
    if inner is None:
        seen = sorted(
            {
                (n.get("Plans") or [{}])[0].get("Node Type", "?")
                for n in windows
                if n.get("Plans")
            }
        )
        return {
            "measured": False,
            "reason": (
                f"no WindowAgg in CTE {cte_name} is fed directly by one of "
                f"{sorted(SORT_NODE_TYPES)} — the planner chose a different "
                f"input shape and the frozen node does not exist here. "
                f"WindowAgg children seen: {seen}"
            ),
        }
    sort = inner["Plans"][0]
    outer = windows[0]

    def _actual(node: dict, key: str) -> Any:
        return node.get(key)

    rows = _actual(sort, "Actual Rows")
    loops = _actual(sort, "Actual Loops")
    return {
        "measured": rows is not None,
        "reason": None if rows is not None else "EXPLAIN carried no actuals (ANALYZE off?)",
        "sort_actual_rows": rows,
        "sort_actual_loops": loops,
        "sort_input_rows": (rows * loops) if rows is not None and loops else rows,
        "sort_plan_width": sort.get("Plan Width"),
        # Which of SORT_NODE_TYPES was measured. An Incremental Sort reports
        # per-group statistics instead of one Sort Method / Sort Space Used, so
        # those come back None here and the reader needs to know that is a
        # property of the node shape and not a measured absence of spill.
        "sort_node_type": sort.get("Node Type"),
        "sort_method": sort.get("Sort Method"),
        "sort_space_used_kb": sort.get("Sort Space Used"),
        "sort_space_type": sort.get("Sort Space Type"),
        "sort_actual_total_ms": sort.get("Actual Total Time"),
        "temp_read_blocks": sort.get("Temp Read Blocks"),
        "temp_written_blocks": sort.get("Temp Written Blocks"),
        "windowagg_actual_rows": inner.get("Actual Rows"),
        "windowagg_actual_total_ms": inner.get("Actual Total Time"),
        "windowagg_subtree_total_cost": outer.get("Total Cost"),
        "windowagg_nodes": len(windows),
    }


def final_rows(plan_root: dict) -> Any:
    return plan_root.get("Actual Rows")


def node_time_ms(metrics: dict[str, Any]) -> float | None:
    """Combined Sort + WindowAgg actual time.

    ``Actual Total Time`` on a node is inclusive of its children, so the
    WindowAgg's own figure already contains the Sort's. Taking the WindowAgg's
    inclusive time IS "Sort + WindowAgg"; adding them would double-count the
    Sort and flatter whichever side sorts more.
    """
    value = metrics.get("windowagg_actual_total_ms")
    if value is None:
        value = metrics.get("sort_actual_total_ms")
    return float(value) if value is not None else None


def g3_verdict(samples: Sequence[dict[str, Any]]) -> tuple[str, list[str], dict[str, Any]]:
    """Grade G3's five clauses over the measured samples.

    ``samples`` are dicts with ``old`` and ``new`` metric blocks plus the final
    row counts, one per residue. Anything unmeasured makes the whole gate
    ``NOT_MEASURED`` — the kill criteria forbid rendering could-not-check as
    agreement, and a median over the samples that happened to finish is exactly
    that.
    """
    usable = [s for s in samples if s.get("old", {}).get("measured") and s.get("new", {}).get("measured")]
    summary: dict[str, Any] = {"samples": len(samples), "usable": len(usable)}
    if not usable:
        return "NOT_MEASURED", ["no sample produced actuals on both sides"], summary
    if len(usable) < len(samples):
        return (
            "NOT_MEASURED",
            [
                f"{len(samples) - len(usable)} of {len(samples)} samples did not "
                "measure; a median over the survivors is not the gate"
            ],
            summary,
        )

    reasons: list[str] = []

    # 1. identical executed population into the window, every sample.
    row_deltas = []
    for s in usable:
        old_rows = s["old"].get("sort_input_rows")
        new_rows = s["new"].get("sort_input_rows")
        row_deltas.append((s.get("label"), old_rows, new_rows))
        if old_rows != new_rows:
            reasons.append(
                f"{s.get('label')}: WindowAgg input rows {old_rows} -> {new_rows} "
                "(the executed population may not change)"
            )
    summary["window_input_rows"] = row_deltas

    # 2. width ratio.
    widths = []
    for s in usable:
        old_w = s["old"].get("sort_plan_width")
        new_w = s["new"].get("sort_plan_width")
        widths.append((s.get("label"), old_w, new_w))
        if not old_w or new_w is None:
            reasons.append(
                f"{s.get('label')}: Sort reported no Plan Width "
                f"(old={old_w!r}, new={new_w!r})"
            )
            continue
        if new_w > old_w * G3_MAX_WIDTH_RATIO:
            reasons.append(
                f"{s.get('label')}: Sort width {new_w} B is "
                f"{new_w / old_w:.1%} of OLD ({old_w} B), bar is "
                f"{G3_MAX_WIDTH_RATIO:.0%}"
            )
    summary["sort_plan_width"] = widths

    # 3. median combined node time, and no sample more than 10% slower.
    old_times, new_times = [], []
    for s in usable:
        o, n = node_time_ms(s["old"]), node_time_ms(s["new"])
        if o is None or n is None:
            reasons.append(f"{s.get('label')}: node time missing on one side")
            continue
        old_times.append(o)
        new_times.append(n)
        if o > 0 and n > o * G3_MAX_SAMPLE_REGRESSION:
            reasons.append(
                f"{s.get('label')}: node time regressed {n / o:.2f}x "
                f"({o:.1f} ms -> {n:.1f} ms)"
            )
    if old_times and new_times:
        med_old = statistics.median(old_times)
        med_new = statistics.median(new_times)
        summary["median_node_ms"] = {"old": med_old, "new": med_new}
        if med_old > 0 and med_new > med_old * G3_MAX_MEDIAN_TIME_RATIO:
            reasons.append(
                f"median Sort+WindowAgg time {med_new:.1f} ms is "
                f"{med_new / med_old:.1%} of OLD ({med_old:.1f} ms), bar is "
                f"{G3_MAX_MEDIAN_TIME_RATIO:.0%}"
            )

    # 4. spill must not increase. An unchanged spill is reported, never passed
    #    off as a win.
    spills = []
    for s in usable:
        o_disk = (s["old"].get("sort_space_type") or "").lower() == "disk"
        n_disk = (s["new"].get("sort_space_type") or "").lower() == "disk"
        o_temp = (s["old"].get("temp_written_blocks") or 0)
        n_temp = (s["new"].get("temp_written_blocks") or 0)
        spills.append(
            {
                "label": s.get("label"),
                "old_space_type": s["old"].get("sort_space_type"),
                "new_space_type": s["new"].get("sort_space_type"),
                "old_space_kb": s["old"].get("sort_space_used_kb"),
                "new_space_kb": s["new"].get("sort_space_used_kb"),
                "old_temp_written": o_temp,
                "new_temp_written": n_temp,
                "both_spilled": o_disk and n_disk,
            }
        )
        if n_temp > o_temp:
            reasons.append(
                f"{s.get('label')}: temp blocks written rose {o_temp} -> {n_temp}"
            )
        if n_disk and not o_disk:
            reasons.append(f"{s.get('label')}: NEW spills to disk where OLD did not")
    summary["spill"] = spills

    # 5. final rows identical — a cheaper node cannot compensate for a
    #    different answer. G1 is the oracle; this is the plan-level echo of it.
    for s in usable:
        if s.get("final_rows_old") != s.get("final_rows_new"):
            reasons.append(
                f"{s.get('label')}: final rows "
                f"{s.get('final_rows_old')} -> {s.get('final_rows_new')}"
            )

    return ("PASS" if not reasons else "FAIL"), reasons, summary


# ---------------------------------------------------------------------------
# G4 — the mutation controls
# ---------------------------------------------------------------------------


def cte_span(sql: str, name: str) -> tuple[int, int]:
    """``(start, end)`` character offsets of CTE ``name``'s parenthesised body."""
    import re

    marker = re.search(rf"\b{re.escape(name)}\s+AS\s+(MATERIALIZED\s+)?\(", sql)
    if marker is None:
        raise ValueError(f"CTE {name!r} not found")
    start = sql.index("(", marker.start())
    depth = 0
    for i in range(start, len(sql)):
        if sql[i] == "(":
            depth += 1
        elif sql[i] == ")":
            depth -= 1
            if depth == 0:
                return start + 1, i
    raise ValueError(f"unbalanced parens in CTE {name!r}")


def mutate_in_cte(sql: str, cte: str, old: str, new: str) -> str:
    """Replace ``old`` with ``new`` inside one CTE, and prove the edit landed.

    A mutation that silently fails to apply is worse than no mutation: the
    control runs, the gate stays green, and the green is recorded as evidence
    that the comparator has teeth. So this raises rather than returning the
    input unchanged.
    """
    start, end = cte_span(sql, cte)
    body = sql[start:end]
    if old not in body:
        raise ValueError(f"mutation anchor not present in CTE {cte!r}: {old!r}")
    mutated = body.replace(old, new, 1)
    if mutated == body:
        raise ValueError(f"mutation was a no-op in CTE {cte!r}")
    return sql[:start] + mutated + sql[end:]


def append_to_cte(sql: str, cte: str, clause: str) -> str:
    """Append a clause to the end of one CTE's body (before its close paren)."""
    start, end = cte_span(sql, cte)
    body = sql[start:end].rstrip()
    return sql[:start] + body + "\n" + clause + "\n" + sql[end:]


def mutant_global_rn1(new_chain: str) -> str:
    """G4.2 — apply ``rn = 1`` globally, before the flags exist.

    This is `C-FOLD-EXPLAIN-1 §3`'s own proposal, and the reason it is a MUTANT
    rather than the implementation: ``field_completeness`` aggregates the flags
    over every row of a market, ``mode_prices`` over every multi row, and
    ``deduped``'s ``is_multi`` arm publishes many rows per virtual question.
    ``rn = 1`` is only the single/binary ELSE arm. Filtering there drops
    legitimate members, so the comparator must see it.

    The filter goes on the OUTER ``ranked_outcomes`` — the CTE that joins the
    nine flag relations — because that is precisely §3's shape: the window has
    already run, and the joins are being spared the rows the window discarded.
    """
    return append_to_cte(strip_sql_comments(new_chain), "ranked_outcomes", "WHERE core.rn = 1")


def mutant_flag_flip(new_chain: str) -> str:
    """G4.4 — change one exclusion flag, keeping ids and buckets fixed.

    ``is_nonexclusive_bundle`` is chosen deliberately. It is the one flag the
    population carries as **census only** — it does not appear in ``deduped``'s
    WHERE, so inverting it changes no row's membership, no probability and no
    bucket. Aggregate equality therefore stays green and only the per-row value
    moves, which is the precise failure mode an aggregate oracle cannot see.
    """
    return mutate_in_cte(
        strip_sql_comments(new_chain),
        "ranked_outcomes",
        "(nbm.market_id IS NOT NULL) AS is_nonexclusive_bundle",
        "(nbm.market_id IS NULL) AS is_nonexclusive_bundle",
    )


def mutant_narrow_population(new_chain: str) -> str:
    """G4.5 — add a population predicate solely to make the timing gate pass."""
    return append_to_cte(
        strip_sql_comments(new_chain), NEW_WINDOW_CTE, "AND MOD(fo.id, 2) = 0"
    )


#: The five frozen controls, by name, with what each is supposed to prove.
#: ``wide_shape`` and ``aggregate_collision`` are not chain rewrites — the first
#: substitutes the OLD chain wholesale (identical rows, wide Sort: G3 must fail
#: while G1 passes) and the second perturbs the comparator's NEW relation rather
#: than the SQL that builds it.
MUTANTS: dict[str, str] = {
    "wide_shape": "the pre-rewrite wide-row shape — G1 green, G3 width RED",
    "global_rn1": "flags joined after a global rn=1 — drops multi/field members",
    "row_swap": "one row replaced by an aggregate-identical row — buckets green, rows RED",
    "flag_flip": "one exclusion flag inverted — buckets green, values RED",
    "narrow_population": "an added predicate narrows the published population",
}
