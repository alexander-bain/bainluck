"""CAL-P138 — the leg-swap partition, computed OFFLINE from CAL-P137's cache.

CAL-P137 measured that 1,511 of `polymarket/baseball`'s 2,175 condemned O/U
families are fixed by reading exactly ONE rung from the other leg, and that
81.2% of those families' over/under pairs sum to 1.00 — so "flip this rung" and
"read this market's stored Under column" are the same operation. It then refused
to propose anything, for two stated reasons (its README §7):

  * every number in it is a RAW-CELL count (lesson 19) and nobody had asked how
    many of those markets reach the PUBLISHED curve — CAL-P137-1;
  * 571 baseball and 3,843 soccer condemned families admit NO flip assignment at
    all, and nobody knows what they are, so the class is not clean — CAL-P137-3.

This module answers the part of both questions that is a PARTITION: it turns
CAL-P137's family-grain histogram into a MARKET-grain partition that
``calibration_cell_exact``'s per-chunk dimension machinery can carry into the
producer's own CTE chain. It computes no law of its own — the grammar, the
family key, the price selection and the monotonicity verdict are all imported
from ``app.utils.ladder_monotonicity``, and the rows are ``pull_eras.as_dicts``
unchanged, so the population is byte-identical to the one CAL-P137 measured.

WHAT IT ADDS TO CAL-P137, AND WHY IT IS NOT IN THE SHIPPED MODULE
------------------------------------------------------------------
``era-fold._min_flips`` returns the COST of the cheapest legal assignment. To
name the market that is on the wrong leg you need the ASSIGNMENT, and to trust
that name you need to know the assignment is UNIQUE — a family with two distinct
one-flip repairs does not accuse a specific row of anything.
:func:`min_flip_assignment` returns cost, uniqueness and the flipped rung values
together, by the same two-state DP with backpointers and an optimal-path count.

🔴 IT IS CHECKED AGAINST ``_min_flips``, NOT TRUSTED. :func:`self_check` runs
both over every condemned family of every cell and asserts the costs agree
exactly. That is a claim about agreement and not about truth (lesson 9), but
agreement with the function whose numbers CAL-P137 published is precisely the
claim this session needs before it re-uses them.

It stays out of ``app/utils/ladder_monotonicity`` for CAL-P137's reason,
unchanged: that module is the one the frozen curve reads, the leakage line runs
through the middle of it, and a detector earns its way in behind a named ship
(the RIDER RULE). CAL-P137-2 is still parked.

THE ARMS, AND WHICH COMPARISON IS LOAD-BEARING
------------------------------------------------
``a_flip1_suspect``   the single market a UNIQUE one-flip repair accuses
``b_flip1_sibling``   the other rungs of those same families — the control that
                      says whether the family or only the accused row is broken
``c_flip1_ambiguous`` one-flip families whose repair is NOT unique; the accusation
                      cannot be pinned to a row, so it is counted apart rather
                      than folded into ``a``
``d_flip2plus``       condemned families needing two or more flips
``e_no_assignment``   condemned families no leg swap can fix — CAL-P137-3's
                      population, sized here against the published curve
``f_mono_ambiguous``  families the law KEEPS because their key is unsafe
``g_mono_coherent``   families that obey the law — the cell as it would look if a
                      rule dropped everything above
``z_not_in_a_ladder`` the rest of the cell, which no mechanism here can touch and
                      which doctrine 18 grades a row-dropping fix against

Eight arms is at lesson 11's limit and the roll-up that carries the reading is
``a`` against ``g``: if the leg-swap story is true, the accused rows are grossly
miscalibrated and their coherent siblings are not.

⚠️ A MARKET CAN BE A RUNG OF TWO FAMILIES. ``ladder_report`` resolves that by
condemning the market if EITHER family condemns it; this partition resolves it
the same way, by arm precedence in the order above, so no market is counted
twice and the worse verdict wins. :func:`classify` publishes
``markets_in_two_arms_before_precedence`` so the size of that overlap is a
measured number rather than an assumption.
"""
import collections
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cal-p137"))

from app.utils.ladder_monotonicity import (  # noqa: E402
    ambiguous_families,
    condemned_families,
    name_rungs,
    proposition_price,
    read_name_ladders,
    scoped_key,
)

from era_fold_import import min_flips as _era_min_flips  # noqa: E402
from pull_eras import as_dicts  # noqa: E402

#: The Polymarket ladder identity. Same table entry ``calibration_cell_exact``
#: uses (``MONO_CONTEXT_COLUMN['polymarket']``) and same value CAL-P136's arm D
#: and CAL-P137's whole census used. Kalshi's ``group_id`` is one-per-market and
#: would annihilate the partition, which is why this module is Polymarket-only.
CONTEXT = "group_id"

#: The arm names, in PRECEDENCE order. A market reachable from two families
#: takes the earliest arm it qualifies for, so the worse verdict wins — the same
#: tie-break ``ladder_report`` applies when it condemns a market for either of
#: its two families.
ARMS = (
    "a_flip1_suspect",
    "b_flip1_sibling",
    "c_flip1_ambiguous",
    "d_flip2plus",
    "e_no_assignment",
    "f_mono_ambiguous",
    "g_mono_coherent",
)

#: Stop counting optimal paths here. Uniqueness is the only question asked of
#: the count, so anything above one is the same answer, and an unbounded count
#: on a long ladder is a big-integer for no reason.
PATH_COUNT_CAP = 4


def min_flip_assignment(values, direction):
    """Cheapest legal leg-swap repair: ``(cost, unique, flipped_indices)``.

    ``values`` are the family's prices in ascending RUNG order — the same order
    ``era-fold._min_flips`` walks. Each rung has two candidate prices, the one
    stored and the one the opposite leg would give (``1 - p``), and the law
    fixes which pairs are legal, so the cheapest assignment is a two-state DP.
    This one carries backpointers and a bounded count of optimal paths so it can
    say WHICH rung it accuses and whether that accusation is the only one.

    Returns ``(None, False, ())`` when no assignment satisfies the law — a real
    answer and not a zero, exactly as ``_min_flips`` returns ``None``: the family
    is broken in a way a leg swap cannot explain, and that population is
    CAL-P137-3.
    """
    ok = ((lambda prev, cur: cur <= prev) if direction == "dec"
          else (lambda prev, cur: cur >= prev))

    # state s in (0, 1): rung i read as stored / read from the other leg.
    def val(i, s):
        return values[i] if s == 0 else 1.0 - values[i]

    cost = [{0: 0, 1: 1}]
    paths = [{0: 1, 1: 1}]
    back = [{0: (), 1: ()}]
    for i in range(1, len(values)):
        c, p, b = {}, {}, {}
        for s in (0, 1):
            best, npaths, froms = None, 0, []
            for s_prev, prev_cost in cost[i - 1].items():
                if not ok(val(i - 1, s_prev), val(i, s)):
                    continue
                if best is None or prev_cost < best:
                    best, npaths, froms = prev_cost, paths[i - 1][s_prev], [s_prev]
                elif prev_cost == best:
                    npaths = min(PATH_COUNT_CAP, npaths + paths[i - 1][s_prev])
                    froms.append(s_prev)
            if best is None:
                continue
            c[s] = best + s
            p[s] = min(PATH_COUNT_CAP, npaths)
            b[s] = tuple(froms)
        if not c:
            return None, False, ()
        cost.append(c)
        paths.append(p)
        back.append(b)

    last = len(values) - 1
    best = min(cost[last].values())
    finals = [s for s, v in cost[last].items() if v == best]
    total_paths = min(PATH_COUNT_CAP, sum(paths[last][s] for s in finals))

    # Walk back along ONE optimal path. It names the accused rungs only when
    # ``total_paths == 1``, and the caller is required to check that before
    # reading them — which is why uniqueness is returned next to the indices
    # rather than left for the caller to re-derive.
    s = finals[0]
    flipped = []
    for i in range(last, -1, -1):
        if s == 1:
            flipped.append(i)
        if i:
            s = back[i][s][0]
    return best, total_paths == 1, tuple(sorted(flipped))


def _families(rows):
    """The priced rows, the family table and the two verdict sets.

    Every step here is the shipped module's — ``proposition_price`` picks the leg
    that prices the proposition, ``read_name_ladders`` builds the families under
    the scoped key, and the two verdict sets are ``ambiguous_families`` and
    ``condemned_families``. Nothing is re-derived.
    """
    priced = []
    for r in rows:
        price, reason = proposition_price(r)
        if price is not None:
            priced.append({**r, "_p": price, "_leg": reason})
    lad = read_name_ladders(priced, price_key="_p", context_key=CONTEXT)
    amb = ambiguous_families(lad)
    return priced, lad, amb, condemned_families(lad) - amb


def _rung_owner(priced):
    """``(family key, rung value) -> market_id``, by the module's own grammar.

    ``read_name_ladders`` records ``member_ids`` as a flat list in row order, so
    it cannot say which market carried which rung. This re-walks ``name_rungs``
    and ``scoped_key`` — the same two functions the family table was built from,
    not a second reading of the name — and keeps the FIRST market at each rung,
    which is the one whose price the family table kept (the module skips a
    repeat value into ``duplicate_values`` rather than overwriting).
    """
    owner = {}
    for row in priced:
        name = row.get("name")
        if not isinstance(name, str):
            continue
        context = row.get(CONTEXT)
        for (blanked, direction), value in name_rungs(name):
            key = (scoped_key(context, blanked), direction)
            owner.setdefault((key, round(float(value), 6)), row["market_id"])
    return owner


def classify(cat):
    """The market-id partition for one cell, plus the census behind it.

    Returns ``{"arms": {arm: set(market_id)}, "census": {...}}``. The arms are
    disjoint by construction: a market qualifying for two is assigned the
    earliest in :data:`ARMS`, and the census counts how often that happened.
    """
    rows = as_dicts(cat)
    priced, lad, amb, cond = _families(rows)
    owner = _rung_owner(priced)

    claims = collections.defaultdict(set)  # market_id -> {arm}
    flips_hist = collections.Counter()
    unique_one_flip_families = 0
    for key in cond:
        rungs = lad[key]["rungs"]
        ordered = sorted(rungs)
        values = [rungs[v] for v in ordered]
        cost, unique, flipped = min_flip_assignment(values, key[1])
        members = {owner.get((key, v)) for v in ordered} - {None}
        if cost is None:
            arm_all = "e_no_assignment"
        elif cost >= 2:
            arm_all = "d_flip2plus"
        elif not unique:
            arm_all = "c_flip1_ambiguous"
        else:
            arm_all = "b_flip1_sibling"
            unique_one_flip_families += 1
            for i in flipped:
                mid = owner.get((key, ordered[i]))
                if mid is not None:
                    claims[mid].add("a_flip1_suspect")
        flips_hist[("no_assignment" if cost is None
                    else str(cost) if cost < 4 else "4+")] += 1
        for mid in members:
            claims[mid].add(arm_all)

    # The families the law does NOT condemn, so the arms below are the controls.
    for key, v in lad.items():
        if key in cond or len(v["rungs"]) < 2:
            continue
        arm = "f_mono_ambiguous" if key in amb else "g_mono_coherent"
        for mid in v["member_ids"]:
            if mid is not None:
                claims[mid].add(arm)

    order = {a: i for i, a in enumerate(ARMS)}
    arms = {a: set() for a in ARMS}
    two_arms = 0
    for mid, got in claims.items():
        # ``a_flip1_suspect`` and ``b_flip1_sibling`` on the same market is not
        # an overlap, it is how the accused row is named inside its own family;
        # the precedence below resolves it and it must not inflate the count.
        if len(got - {"a_flip1_suspect", "b_flip1_sibling"}) > 1:
            two_arms += 1
        arms[min(got, key=lambda a: order[a])].add(mid)

    return {
        "arms": arms,
        "census": {
            "cell": f"polymarket/{cat}",
            "rows_cached": len(rows),
            "rows_priced": len(priced),
            "families": len(lad),
            "families_condemned": len(cond),
            "families_ambiguous_kept": len(amb),
            "min_flips_histogram": dict(sorted(flips_hist.items(), key=lambda kv: kv[0])),
            "unique_one_flip_families": unique_one_flip_families,
            "markets_in_two_arms_before_precedence": two_arms,
            "markets_per_arm": {a: len(arms[a]) for a in ARMS},
        },
    }


def self_check(cat):
    """Does :func:`min_flip_assignment` agree with ``era-fold._min_flips``?

    Lesson 9 — this is a claim about agreement, not about truth. It is the claim
    that matters, because CAL-P137's published histogram came out of
    ``_min_flips`` and this session re-uses those families by name. A cost
    disagreement anywhere means the two sessions are not partitioning the same
    thing and nothing downstream is readable.
    """
    rows = as_dicts(cat)
    _, lad, _, cond = _families(rows)
    checked = disagreed = 0
    example = []
    for key in cond:
        rungs = lad[key]["rungs"]
        values = [rungs[v] for v in sorted(rungs)]
        theirs = _era_min_flips(values, key[1])
        mine, _, _ = min_flip_assignment(values, key[1])
        checked += 1
        if theirs != mine:
            disagreed += 1
            if len(example) < 5:
                example.append({"key": list(key), "era_fold": theirs, "here": mine,
                                "values": values})
    return {"families_checked": checked, "cost_disagreements": disagreed,
            "examples": example, "ok": disagreed == 0}
