#!/usr/bin/env python3
"""CAL-P151 — the six cricket families, run through the PRODUCER'S OWN CHAIN.

WHY THIS EXISTS. CAL-P150 measured the six Polymarket cricket name-families on
the RAW tables and found two of them missing a graded winner on ~two thirds of
their markets ("who wins the toss?": 424 of 647; "completed match?": 392 of 630).
It then refused to draw a conclusion, for a reason that is the whole point of
this file: **the raw fold's gaps are all POSITIVE (over-prediction) while the
published cell's gap is -4.51 (under-prediction)**, so the sign flips between the
two populations and the published miss is carried by a subset the raw cut cannot
see. Lesson 19: a cell census is not a published-population census.

The directive names exactly one next step, and this is it:

    run those six name families through `_calibration_population_ctes` and
    answer WHICH REACH `deduped`.

If the no-winner families are already excluded by the chain's own result-
authority rungs, the published miss is elsewhere and STALENESS is next. If they
reach `deduped`, the cell's published number is measuring OUR GRADING.

THE CHAIN IS USED VERBATIM
---------------------------
This imports `_calibration_population_ctes` and uses its output as-is — the same
reader-only path `calibration_published_twin.py` and `routes/calibration.py`
take. Ruling 009 freezes COMMITS to that module, not reads of it, so
`_main_input_fingerprint()` does not move and no banked unit is invalidated.
Nothing here re-implements the predicate; a hand-mirror would be answering a
different question badly (CAL-P078's argument, unchanged).

FOUR OBSTACLES, EACH MEASURED RATHER THAN ASSUMED
--------------------------------------------------
Getting the frozen chain to run on the admin read rail took four fixes, and each
one is a fact about the rail or the schema that the next reader will hit too.

**1. The rail counts semicolons LEXICALLY (gotcha #149).** The chain carries 20
semicolons, every one inside a `--` comment, so it is refused as
`Multi-statement queries not allowed` before it is ever planned. The repo
already owns the tool for this — `app.utils.sql_comment_strip`, built for #2076
— so it is reused rather than re-solved with a regex, which would be wrong in
three ways this SQL exhibits. The stripped copy is READ-ONLY; the frozen builder
is untouched. (Its docstring says 15 semicolons; the chain carries 20 today, D5
having added comments on 2026-08-30. The count is prose — the assert is what
holds.)

**2. The category predicate has NO INDEX.** `futures_markets` carries 23 indexes
and **every one mentioning `llm_sport_category` is PARTIAL on `status='open'`**
(`ix_fm_open_category`, `ix_fm_feed_open_sports`). The calibration population is
`status='resolved'`. So a category-scoped read of it is a sequential scan of a
wide JSONB-bearing table, and it does not fit the 10 s row budget: the COALESCE
form, the sargable `fm.llm_sport_category='cricket'` form, and a bare `COUNT(*)`
over the same predicate ALL return `statement_timeout` (correlations
c25714c8df77, 0e518296f306, 5ead2f0cafd9), as does `SELECT COUNT(*) FROM
market_info` on the scoped chain (c4a1226e2e9e). This is a schema fact, not a
query defect, and it is why CAL-P150's raw fold chunked too.

So the scope is applied as an EXPLICIT PRIMARY-KEY LIST, collected first by
id-range chunks (each of which fits) and then replayed through the chain, where
it drives the pkey index instead of a scan.

**3. `market_info` is not MATERIALIZED, so every reference re-runs it.** Even as
a 7,992-id pkey list it costs ~1.8 s per inline, and the chain references it a
dozen times — the whole-population fold still timed out (cc6ca2b9047a7678). The
chain therefore runs in CHUNKS.

**4. 🔴 CHUNKING THIS CHAIN IS A DOCUMENTED HAZARD, AND THE CHUNKS ARE BUILT SO
IT CANNOT BITE.** `_virtual_market_ctes`' own docstring says it: `group_sizes`
and `event_sizes` are counted over `market_info`, so re-deriving them from a
FILTERED `market_info` silently changes virtual-question identity — an event
that falls below the >=3 gate re-assigns every one of its markets from `e:` to
`m:`, a different question, a different representative, a different bucket. The
designed answer is `frozen_vm_roster=True`, which replays a roster computed once
over the whole population; it takes bind-parameter arrays, which the read rail
cannot carry, so it is not available here.

What IS available is chunking on a boundary the aggregates cannot see across.
Markets are unioned into COMPONENTS by shared `(group_id, source)` and shared
`(event_id, source)`, and a component is never split. Every group and every
event is therefore whole within exactly one chunk, so `group_sizes` and
`event_sizes` computed inside a chunk equal their global values, and the chunk
is a REPLAY rather than a re-derivation. MEASURED: 7,992 markets form 5,626
components whose LARGEST is 21 markets, so the packing is never forced to split
one.

The only other global aggregate would be a window function, and there are
exactly two — `ROW_NUMBER()` and `RANK()` — both `PARTITION BY vm_id`, which is
component-local by construction. Everything else in the chain is per-market or
per-vm.

The scope proof is belt-and-braces on top of that: it re-measures whether any
cricket group/event key even CONTAINS a foreign market, and exits 4 if one is
found whose >=3 gate could flip. Measured 2026-08-30: 0 mixed groups of 5,914;
7 mixed events of 240, all `kalshi` with `total=2` — below the gate either way.

WHAT THIS MEASURES
-------------------
Per family, on the chain, summed over chunks (every reported quantity is a
count or a sum, so chunk-additivity is exact):

  * `n_norm`   — outcomes that reached `normalized`, i.e. entered the chain
  * `n_pub`    — outcomes that reached `deduped`, i.e. the PUBLISHED rows
  * the per-rung exclusion flags, so a family that does not arrive is not merely
    absent, it is absent FOR A NAMED REASON
  * the published price sum and realized winners, so the surviving rows' own gap
    is readable in the same units as the cell

`deduped` and `adj_opening_probability` are the two names `routes/calibration.py`'s
debug sampler reads, so this counts the rows the published curve actually
buckets rather than a lookalike set.

EXIT CODES (gotcha #124):
  0  the fold completed and every family is reported
  4  the scope proof FAILED — a key exists whose >=3 gate could flip under the
     filter, so the chunked chain is a re-derivation and must not be read
  5  a query failed, a chunk was lost, or the environment is missing
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "backend"))

API = os.environ.get("BAINLUCK_API", "").rstrip("/")
TOKEN = os.environ.get("ADMIN_TOKEN", "")

#: The sargable form of the category test. `COALESCE(c,'uncategorized')='cricket'`
#: — what `market_info` itself computes — selects the same rows for THIS value
#: and only for this value: a NULL category becomes 'uncategorized', which is not
#: 'cricket'. Stated because the substitution would be WRONG for the literal
#: 'uncategorized', and a reader copying this line for another cell must see that.
CRICKET_CATEGORY_SQL = "fm.llm_sport_category = 'cricket'"
CATEGORY_EQUIVALENCE_NOTE = (
    "COALESCE(c,'uncategorized')='cricket' <=> c='cricket' "
    "(NULL -> 'uncategorized' != 'cricket'); NOT valid for 'uncategorized'"
)

#: Id-range width for the collection scan. MEASURED: 2M ~0.5 s, 5M ~2.1 s, 20M
#: ~8.9 s against a 10 s budget — 20M is not a margin, it is a coin flip. A chunk
#: that comes back at the row cap or times out is HALVED, never retried: a retry
#: re-runs the same too-big scan and fails the same way.
ID_CHUNK = 2_000_000
ID_MAX = 59_852_510
ROW_LIMIT = 1000

#: Markets per fold chunk. MEASURED: the whole chain over ~1,000 markets returned
#: `deduped` in ~3.0 s at 18:40 UTC and TIMED OUT on the fuller tail query at
#: 18:50, while the collection scan needed five halvings in the same run and one
#: ten minutes earlier — production load moved underneath the measurement. The
#: cap is therefore set well under the observed ceiling and the fold halves
#: adaptively on top of that. Components are packed up to this size and NEVER
#: split (see obstacle 4).
FOLD_CHUNK_MARKETS = 400

#: The family classifier, the same cut CAL-P150's raw fold used, so the two
#: readings are comparable family-for-family rather than two different cuts that
#: happen to share names.
FAMILY_SQL = (
    "CASE WHEN position(' - ' in fm.name) = 0 THEN 'match_winner' "
    "ELSE lower(btrim(substring(fm.name from position(' - ' in fm.name) + 3))) END"
)

#: The scope proof, driven by an EXPLICIT key list rather than a subquery.
#:
#: Two forms were tried and both are unreliable, for the same reason:
#:
#:  * grouping the WHOLE resolved population and keeping rows where a cricket
#:    market appears (correlation 36045f615b56), and
#:  * narrowing with `SELECT DISTINCT fm.group_id ... WHERE llm_sport_category
#:    ='cricket'` (correlation 6da83f5cf27a)
#:
#: — because the second still contains the FIRST one's problem: finding cricket's
#: keys at all needs the unindexed `status='resolved' AND llm_sport_category`
#: scan. Both returned by hand and then, minutes later, did not. A proof that
#: answers only when the database is in a good mood is not a proof.
#:
#: So collection runs FIRST, and the key set comes out of it in Python. The proof
#: then only ever asks index-driven questions about named keys. Its answer was
#: checked against the wide form's output while that still ran: 0 mixed groups of
#: 5,914, 7 mixed events of 240.
#:
#: Keys are batched because the lists are thousands long; `HAVING` keeps only the
#: mixed ones, so the result stays small however many batches it takes.
SCOPE_PROOF_SQL = """
SELECT '{kind}' AS kind, fm.{col}::text AS key, fm.source AS source,
       COUNT(*) AS total,
       COUNT(*) FILTER (WHERE fm.llm_sport_category='cricket') AS cric,
       (COUNT(*) >= 3) AS gate_unfiltered,
       (COUNT(*) FILTER (WHERE fm.llm_sport_category='cricket') >= 3) AS gate_filtered
FROM futures_markets fm
WHERE fm.status='resolved' AND fm.{col} IN ({keys})
GROUP BY 1,2,3
HAVING COUNT(*) <> COUNT(*) FILTER (WHERE fm.llm_sport_category='cricket')
"""

#: Keys per scope-proof batch. The IN list drives an index scan either way; this
#: only bounds the SQL text and the per-statement row count.
SCOPE_KEY_BATCH = 800

#: 🔴 THE PUBLISHED SIDE IS COUNTED ON `deduped` DIRECTLY, NOT BY JOINING TO IT.
#:
#: The first cut of this tail selected from `normalized` and LEFT JOINed
#: `deduped` on `outcome_id` to mark which rows survived. That is wrong, and it
#: was wrong in the flattering direction — it read **4,096** published rows for
#: a cell the payload publishes **3,258** of.
#:
#: `deduped` is NOT unique on `outcome_id`. MEASURED on the deployed chain:
#: 3,260 rows carry 2,842 distinct outcome ids, so **418 rows are duplicates** —
#: that is D5's phantom fan-out, sitting in the live cricket cell. A LEFT JOIN
#: from one row to several multiplies the left side, so the join reported the
#: duplication twice over.
#:
#: Counting `deduped`'s own rows instead gives 3,260 against the payload's 3,258
#: — a two-row difference on a live database, i.e. the instrument reproduces the
#: published cell. That agreement is the reason to trust anything else here, and
#: it only appeared once the join was removed.
#:
#: Both quantities are reported: `rows` is what the payload counts, `distinct`
#: is what the population actually contains, and the gap between them IS the
#: defect.
FOLD_TAIL = f"""
, pub AS (
    SELECT {FAMILY_SQL} AS family, d.outcome_id, d.market_id,
           d.adj_opening_probability AS p, d.is_winner
    FROM deduped d
    JOIN futures_markets fm ON fm.id = d.market_id
    WHERE d.source = 'polymarket' AND d.category = 'cricket'
),
norm AS (
    SELECT {FAMILY_SQL} AS family, ro.outcome_id, ro.market_id,
           ro.adj_opening_probability AS p, ro.is_winner,
           ro.is_liquid, ro.is_poly_placeholder, ro.is_malformed_binary,
           ro.is_no_winner_market, ro.is_draw_authority_missing,
           ro.is_orphan_partition, ro.is_field_incomplete
    FROM normalized ro
    JOIN futures_markets fm ON fm.id = ro.market_id
    WHERE ro.source = 'polymarket' AND ro.category = 'cricket'
)
SELECT 'pub' AS side, family,
       COUNT(*)                                        AS rows_,
       COUNT(DISTINCT outcome_id)                      AS distinct_outcomes,
       COUNT(DISTINCT market_id)                       AS mkts,
       COALESCE(SUM(p), 0)                             AS sum_p,
       COUNT(*) FILTER (WHERE is_winner)               AS winners,
       0 AS x_no_winner_market, 0 AS x_field_incomplete,
       0 AS x_orphan_partition, 0 AS x_draw_authority,
       0 AS x_malformed_binary, 0 AS x_illiquid, 0 AS x_poly_placeholder
FROM pub GROUP BY 1, 2
UNION ALL
SELECT 'norm' AS side, family,
       COUNT(*)                                        AS rows_,
       COUNT(DISTINCT outcome_id)                      AS distinct_outcomes,
       COUNT(DISTINCT market_id)                       AS mkts,
       COALESCE(SUM(p), 0)                             AS sum_p,
       COUNT(*) FILTER (WHERE is_winner)               AS winners,
       COUNT(*) FILTER (WHERE is_no_winner_market)     AS x_no_winner_market,
       COUNT(*) FILTER (WHERE is_field_incomplete)     AS x_field_incomplete,
       COUNT(*) FILTER (WHERE is_orphan_partition)     AS x_orphan_partition,
       COUNT(*) FILTER (WHERE is_draw_authority_missing) AS x_draw_authority,
       COUNT(*) FILTER (WHERE is_malformed_binary)     AS x_malformed_binary,
       COUNT(*) FILTER (WHERE NOT is_liquid)           AS x_illiquid,
       COUNT(*) FILTER (WHERE is_poly_placeholder)     AS x_poly_placeholder
FROM norm GROUP BY 1, 2
ORDER BY 2, 1
"""

#: Every column the fold sums. Named so the accumulator cannot silently drop one
#: when the SELECT list grows — a missing key here would read as a zero, which is
#: the flattering direction.
SUM_COLUMNS = [
    "rows_", "distinct_outcomes", "mkts", "winners",
    "x_no_winner_market", "x_field_incomplete", "x_orphan_partition",
    "x_draw_authority", "x_malformed_binary", "x_illiquid", "x_poly_placeholder",
]

EXCLUSION_FLAGS = [
    ("x_no_winner_market", "no-winner"),
    ("x_field_incomplete", "field-incompl"),
    ("x_orphan_partition", "orphan-part"),
    ("x_draw_authority", "draw-auth"),
    ("x_malformed_binary", "malformed"),
    ("x_illiquid", "illiquid"),
    ("x_poly_placeholder", "poly-placeh"),
]


def query(sql: str, limit: int = 500) -> dict:
    body = json.dumps({"sql": sql, "limit": limit}).encode()
    req = urllib.request.Request(
        f"{API}/api/admin/db-query",
        data=body,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as fh:
        return json.load(fh)


def rows_as_dicts(res: dict) -> list[dict]:
    """db-query rows are ARRAYS — zip them against the declared column order."""
    cols = res.get("columns") or []
    return [dict(zip(cols, row)) for row in (res.get("rows") or [])]


#: The branch's base — the commit the DEPLOYED producer is running. The lift's
#: five commits sit on top of it and are NOT deployed.
BASE_SHA = "682c0b37"


def load_population_builder(chain: str):
    """Return `_calibration_population_ctes` from either the branch or its base.

    🔴 THIS DISTINCTION IS THE WHOLE REASON THE FLAG EXISTS. The worktree is
    `program/calibration-119`, which carries D5, D13, D12, D21 and D22 — none of
    them deployed. Importing the builder from the worktree therefore folds the
    REPAIRED chain over the LIVE database, which is a preview of the lift, not a
    reading of the published cell. Both are worth having and they answer
    different questions:

      `--chain=base`  the DEPLOYED predicate. This is the one that can be
                      checked against `/api/calibration`, because it is the code
                      that produced it.
      (default) head  the BRANCH predicate. A preview of what the same cell
                      looks like after the lift lands.

    Quoting one as the other is the defect wearing the repair's name. MEASURED:
    the two builders differ (53,452 vs 59,376 chars); `_virtual_market_ctes` is
    identical between them, so the component-chunking argument holds for both.

    The base copy is read with `git show` into a temp file and loaded by path.
    Its `app.*` imports resolve against the worktree, which is fine — the only
    thing taken from it is the SQL string, and the builder is a pure function of
    its arguments and its own module constants.
    """
    if chain == "head":
        from app.tasks.precompute_calibration import _calibration_population_ctes

        return _calibration_population_ctes

    import importlib.util
    import subprocess
    import tempfile

    src = subprocess.run(
        ["git", "show", f"{BASE_SHA}:backend/app/tasks/precompute_calibration.py"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    tmp = tempfile.NamedTemporaryFile(
        "w", suffix="_base_precompute.py", delete=False
    )
    tmp.write(src)
    tmp.close()
    spec = importlib.util.spec_from_file_location("cal_p151_base_precompute", tmp.name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._calibration_population_ctes


def _sql_literal(value) -> str:
    """A single SQL literal. Quotes are doubled — group ids are provider strings."""
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def prove_scope(markets: list[dict]) -> tuple[bool, list[dict]]:
    """Re-measure the chunk-safety condition rather than trusting the docstring.

    A mixed key is only DANGEROUS when the >=3 gate answers differently with the
    foreign markets present and absent. A mixed key where both answers agree
    changes no vm_id, so it is reported and allowed; one where they differ makes
    every chunk a re-derivation and the run must stop.
    """
    mixed: list[dict] = []
    for kind, col in (("group", "group_id"), ("event", "event_id")):
        keys = sorted({m[col] for m in markets if m[col] is not None})
        for i in range(0, len(keys), SCOPE_KEY_BATCH):
            batch = keys[i : i + SCOPE_KEY_BATCH]
            sql = SCOPE_PROOF_SQL.format(
                kind=kind, col=col, keys=",".join(_sql_literal(k) for k in batch)
            )
            mixed.extend(rows_as_dicts(query(sql)))
    dangerous = [
        m for m in mixed if bool(m["gate_unfiltered"]) != bool(m["gate_filtered"])
    ]
    return (not dangerous), mixed


def collect_cricket_markets() -> list[dict]:
    """Every `status='resolved'` cricket market, by id-range chunks.

    ALL sources, not just polymarket. The chain's group/event cardinality is
    counted over `market_info`, so a Kalshi cricket market sharing an event with
    a Polymarket one has to be present or the >=3 gate is answered on a smaller
    population than the producer answers it on. Collecting only the cell's own
    source would be the exact re-derivation the scope proof exists to rule out.
    """
    out: list[dict] = []
    lo = 0
    step = ID_CHUNK
    while lo < ID_MAX:
        hi = min(lo + step, ID_MAX)
        sql = (
            "SELECT fm.id, fm.source, fm.group_id, fm.event_id "
            "FROM futures_markets fm "
            f"WHERE fm.status='resolved' AND {CRICKET_CATEGORY_SQL} "
            f"AND fm.id >= {lo} AND fm.id < {hi} ORDER BY fm.id"
        )
        try:
            res = query(sql, limit=ROW_LIMIT)
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:200]
            if step <= 15_625:
                raise RuntimeError(f"chunk {lo}-{hi} fails even at {step:,}: {detail!r}")
            step //= 2
            print(f"    chunk {lo:,}-{hi:,} failed; halving to {step:,}")
            continue
        if res.get("truncated") or res.get("row_count", 0) >= ROW_LIMIT:
            step //= 2
            print(f"    chunk {lo:,}-{hi:,} hit the row cap; halving to {step:,}")
            continue
        out.extend(rows_as_dicts(res))
        lo = hi
    return out


def components(markets: list[dict]) -> list[list[int]]:
    """Union markets by shared (group_id, source) and shared (event_id, source).

    A component is the smallest set the chain's two global aggregates cannot see
    across, so a chunk made of whole components computes `group_sizes` and
    `event_sizes` exactly as the unchunked chain would.
    """
    parent: dict = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for m in markets:
        key = ("m", m["id"])
        find(key)
        if m["group_id"]:
            union(key, ("g", m["source"], m["group_id"]))
        if m["event_id"]:
            union(key, ("e", m["source"], m["event_id"]))

    groups: dict = {}
    for m in markets:
        groups.setdefault(find(("m", m["id"])), []).append(int(m["id"]))
    return list(groups.values())


def pack(comps: list[list[int]], cap: int) -> list[list[list[int]]]:
    """Pack whole components into chunks, largest first. A component is NEVER split.

    Returns chunks as LISTS OF COMPONENTS, not flat id lists, so that a chunk
    which times out can be halved along the same boundary it was built on. A
    flat list would invite a split through the middle of a component, which is
    precisely the re-derivation this whole design exists to avoid — and it would
    be silent, because a smaller chunk still returns rows.

    If a single component exceeded the cap it is emitted alone and oversized
    rather than cut: correctness before budget. Measured max is 21.
    """
    chunks: list[list[list[int]]] = []
    cur: list[list[int]] = []
    size = 0
    for comp in sorted(comps, key=len, reverse=True):
        if cur and size + len(comp) > cap:
            chunks.append(cur)
            cur, size = [], 0
        cur.append(comp)
        size += len(comp)
    if cur:
        chunks.append(cur)
    return chunks


def main() -> int:
    if not API or not TOKEN:
        print("🔴 source ~/.claude/.env first (BAINLUCK_API / ADMIN_TOKEN)")
        return 5

    print("=" * 96)
    print("CAL-P151 — the six cricket families on the PRODUCER'S OWN CHAIN")
    print("=" * 96)

    print("\n[1/4] COLLECT the cricket population by primary key")
    print(f"  {CATEGORY_EQUIVALENCE_NOTE}")
    try:
        markets = collect_cricket_markets()
    except (urllib.error.HTTPError, RuntimeError) as exc:
        print(f"🔴 collection failed: {exc}")
        return 5
    if not markets:
        print("🔴 no cricket markets collected — an empty 200 is not an absence (#53).")
        return 5
    by_source: dict[str, int] = {}
    for m in markets:
        by_source[str(m["source"])] = by_source.get(str(m["source"]), 0) + 1
    print(f"  {len(markets):,} resolved cricket markets — by source: {by_source}")

    print("\n[2/4] SCOPE PROOF — could chunking change virtual-question identity?")
    try:
        safe, mixed = prove_scope(markets)
    except urllib.error.HTTPError as exc:
        print(f"🔴 scope proof failed: {exc} {exc.read()[:300]!r}")
        return 5
    dangerous = [
        m for m in mixed if bool(m["gate_unfiltered"]) != bool(m["gate_filtered"])
    ]
    print(
        "  keys where a cricket market shares a group/event with a foreign one: "
        f"{len(mixed)}"
    )
    for m in mixed:
        print(
            f"    {m['kind']:5s} {str(m['key']):>10s} {m['source']:<11s} "
            f"total={m['total']:<3} cricket={m['cric']:<3} "
            f"gate unfiltered={m['gate_unfiltered']} filtered={m['gate_filtered']}"
        )
    print(f"  keys whose >=3 gate would FLIP: {len(dangerous)}")
    if not safe:
        print(
            "🔴 THE CHUNKED CHAIN WOULD BE A RE-DERIVATION, NOT A REPLAY. vm identity "
            "changes for the keys above and every number below would be measured on a "
            "different population than the producer's. Refusing to fold. "
            "(_virtual_market_ctes' own docstring is the cite.)"
        )
        return 4
    print("  ✅ every mixed key answers the gate identically either way.")

    print("\n[3/4] CHUNK on component boundaries")
    comps = components(markets)
    chunks = pack(comps, FOLD_CHUNK_MARKETS)
    biggest = max(len(c) for c in comps)
    chunk_sizes = [sum(len(c) for c in chunk) for chunk in chunks]
    print(
        f"  {len(comps):,} components (largest {biggest} markets) packed into "
        f"{len(chunks)} chunks of {chunk_sizes} markets"
    )
    if biggest > FOLD_CHUNK_MARKETS:
        print(
            f"  ⚠️ a component ({biggest}) exceeds the chunk cap and is emitted whole "
            f"— correctness before budget; that chunk may time out."
        )
    packed = sum(chunk_sizes)
    if packed != len(markets):
        print(f"🔴 packing lost markets: {packed} != {len(markets)}")
        return 5

    chain = "base" if "--chain=base" in sys.argv else "head"
    print(f"\n[4/4] THE FOLD — which families reach `deduped`?   [chain: {chain}]")
    _calibration_population_ctes = load_population_builder(chain)
    from app.utils.sql_comment_strip import (
        count_statement_separators,
        strip_sql_comments,
    )

    acc: dict[str, dict] = {}
    # A worklist rather than a for-loop: a chunk that times out is HALVED along
    # its component boundary and both halves go back on the list. Halving, not
    # retrying — a retry re-runs the same too-expensive plan and fails the same
    # way, and the load that caused it is not ours to wait out.
    work: list[list[list[int]]] = list(chunks)
    done = 0
    markets_folded = 0
    while work:
        chunk = work.pop(0)
        flat = [i for comp in chunk for i in comp]
        scope = "AND fm.id IN (" + ",".join(str(i) for i in flat) + ")"
        raw = (
            "WITH "
            + _calibration_population_ctes(market_info_extra=scope)
            + FOLD_TAIL
        )
        sql = strip_sql_comments(raw)
        seps = count_statement_separators(sql)
        if seps:
            print(f"🔴 stripped copy still carries {seps} semicolon(s).")
            return 5
        try:
            res = query(sql)
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:200]
            if len(chunk) < 2:
                print(
                    f"🔴 a single component of {len(flat)} markets cannot be folded "
                    f"and must not be split: {detail!r}"
                )
                print("   the fold is INCOMPLETE and its partial numbers must not be read.")
                return 5
            mid = len(chunk) // 2
            work.insert(0, chunk[mid:])
            work.insert(0, chunk[:mid])
            print(
                f"    chunk of {len(flat):,} markets timed out; halving on the "
                f"component boundary ({mid} + {len(chunk) - mid} components)"
            )
            continue
        rows = rows_as_dicts(res)
        for r in rows:
            side = str(r["side"])
            a = acc.setdefault(str(r["family"]), {}).setdefault(
                side, {k: 0 for k in SUM_COLUMNS} | {"sum_p": 0.0}
            )
            for k in SUM_COLUMNS:
                a[k] += int(r[k])
            a["sum_p"] += float(r["sum_p"] or 0.0)
        done += 1
        markets_folded += len(flat)
        print(
            f"  chunk {done} ({len(flat):,} markets, {res.get('duration_ms', 0):.0f} ms) "
            f"-> {len(rows)} families   [{markets_folded:,}/{len(markets):,} folded]"
        )

    # Every market must have passed through exactly one chunk. A silent shortfall
    # here would read as a smaller population rather than as a lost chunk.
    if markets_folded != len(markets):
        print(f"🔴 folded {markets_folded:,} markets but collected {len(markets):,}.")
        return 5

    if not acc:
        print("🔴 the fold returned NO ROWS across every chunk. That is not 'no")
        print("   cricket' — it is an empty 200 (gotcha #53) and must be")
        print("   disambiguated before any conclusion is drawn from it.")
        return 5

    print(f"\nRESULT — polymarket/cricket   [chain: {chain}]")

    def side(name, s_):
        return acc.get(name, {}).get(s_, {k: 0 for k in SUM_COLUMNS} | {"sum_p": 0.0})

    fams = sorted(acc.keys(), key=lambda n: -side(n, "norm")["rows_"])
    hdr = (
        f"{'family':<24} {'norm':>7} {'pub':>7} {'pub_dist':>9} {'phantom':>8} "
        f"{'reach':>7}  {'mean_p':>7} {'realized':>8} {'gap_pp':>7}"
    )
    print("\n" + hdr)
    print("-" * len(hdr))
    t_rows = t_dist = t_win = 0
    t_p = 0.0
    for name in fams:
        n = side(name, "norm")
        p_ = side(name, "pub")
        rows_ = p_["rows_"]
        dist = p_["distinct_outcomes"]
        phantom = rows_ - dist
        reach = 100.0 * rows_ / n["rows_"] if n["rows_"] else 0.0
        mean_p = p_["sum_p"] / rows_ if rows_ else 0.0
        realized = p_["winners"] / rows_ if rows_ else 0.0
        gap = (realized - mean_p) * 100.0 if rows_ else 0.0
        t_rows += rows_
        t_dist += dist
        t_win += p_["winners"]
        t_p += p_["sum_p"]
        print(
            f"{name[:24]:<24} {n['rows_']:>7,} {rows_:>7,} {dist:>9,} {phantom:>8,} "
            f"{reach:>6.1f}%  {mean_p:>7.4f} {realized:>8.4f} {gap:>+7.2f}"
        )
    print("-" * len(hdr))
    pm = t_p / t_rows if t_rows else 0.0
    pr = t_win / t_rows if t_rows else 0.0
    print(
        f"{'POOLED':<24} {'':>7} {t_rows:>7,} {t_dist:>9,} {t_rows - t_dist:>8,} "
        f"{'':>7}  {pm:>7.4f} {pr:>8.4f} {(pr - pm) * 100.0:>+7.2f}"
    )
    print(
        f"\n  `pub` is what the payload COUNTS; `pub_dist` is how many distinct\n"
        f"  outcomes those rows represent. `phantom` = pub - pub_dist is D5's\n"
        f"  fan-out, measured inside this cell: {t_rows - t_dist:,} of {t_rows:,} rows "
        f"({100.0 * (t_rows - t_dist) / t_rows if t_rows else 0:.1f}%)."
    )

    print("\nWHY A FAMILY DOES NOT ARRIVE — per-rung exclusions over `normalized`:")
    fh_ = f"{'family':<24} " + " ".join(f"{lbl:>13}" for _, lbl in EXCLUSION_FLAGS)
    print(fh_)
    print("-" * len(fh_))
    for name in fams:
        n = side(name, "norm")
        print(
            f"{name[:24]:<24} " + " ".join(f"{n[k]:>13,}" for k, _ in EXCLUSION_FLAGS)
        )

    out = os.path.join(HERE, f"cricket-population-fold-{chain}.json")
    with open(out, "w") as fh:
        json.dump(
            {
                "chain": chain,
                "base_sha": BASE_SHA,
                "scope_proof": {"mixed_keys": mixed, "dangerous_keys": dangerous},
                "population": {
                    "markets": len(markets),
                    "by_source": by_source,
                    "components": len(comps),
                    "largest_component": biggest,
                    "chunks": chunk_sizes,
                },
                "families": acc,
                "pooled": {
                    "rows": t_rows,
                    "distinct_outcomes": t_dist,
                    "phantom_rows": t_rows - t_dist,
                    "mean_p": pm,
                    "realized": pr,
                    "gap_pp": (pr - pm) * 100.0,
                },
            },
            fh,
            indent=1,
            default=str,
        )
    print(f"\nbanked -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
