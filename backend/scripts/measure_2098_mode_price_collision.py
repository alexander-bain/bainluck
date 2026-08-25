#!/usr/bin/env python3
"""CAL-P087 (#2098) — does the source-blind ``mode_prices`` join actually collide?

⚠️ **THE DEFECT THIS MEASURED IS FIXED as of CAL-P090 / ``program/calibration-88``**
(ruling 125; ``mode_prices`` now projects and GROUPs BY ``source`` and ``deduped``'s
join carries ``AND mp.source = ro.source``). This script is kept and kept RUNNING
because the cert (C-2098-SOURCE-1 §6) wants the before re-derivable next to the
after, not because the question is still open.

What that means for each instrument:

* **Instrument B (``--out``, the chunked upper bound) is unaffected.** Its SQL is a
  hand-written literal that builds BOTH the source-blind (``cur``) and
  source-scoped (``alt``) mode groups itself, so it still measures the same 35 rows
  it measured on 2026-08-22 regardless of what the module's SQL now says.
* **Instrument A (``--chain-plan``) is direction-aware** — see :func:`build_chains`.
  Against post-fix source it derives the PRE-fix chain by reverting, so the 3-way
  cost comparison below is still produced and still means what it says. It refuses
  loudly if it can find neither state, rather than comparing a chain against itself
  and reporting a flattering zero (gotcha #53).

The question, stated exactly
----------------------------
``app/tasks/calibration_published_twin_worker.py`` records a correctness caveat
against source-chunking the fold:

    ``vm_id`` is ``'g:'||group_id | 'e:'||event_id | 'm:'||market_id`` and carries
    **no source**, while ``mode_prices`` groups by bare ``vm_id`` and ``deduped``
    joins on bare ``vm_id``. Measured: **1,271 event_ids reach ``event_size >= 3``
    under more than one source** (0 group_ids do). On those, an unchunked fold can
    suppress one source's legs with a mode price computed from the other's, and a
    chunked fold cannot. **Whether any of the 1,271 actually cross-suppresses today
    is NOT measured.**

This script turns that last sentence into a number. **Measurement only** — it
proposes nothing and changes nothing.

Two instruments, and why there are two
--------------------------------------
**A. The faithful one, which does not fit.** ``--chain-plan`` builds two folds
over :func:`_calibration_population_ctes`'s VERBATIM output, differing in exactly
three string substitutions (``mode_prices`` gains ``source`` in its SELECT and
GROUP BY; ``deduped``'s join gains ``AND mp.source = ro.source``). The row
difference between them is attributable to that join's source-blindness and to
nothing else. It is the instrument you would want.

It cannot be run. Measured 2026-08-22, plan-only against production:

    unscoped fold            total_cost = 12,719,996
    scoped to shared events  total_cost = 10,235,054   (0.80x)
    same, source-scoped mode total_cost = 10,234,964   (0.80x)

Scoping the base scan to the 1,288 collidable events removes only 20% of the
planner's cost — ``ranked_outcomes`` still estimates 1,077,901 rows — so the
scoped fold inherits #2076's wall (never finished in 1,350 s) against a 25 s
ceiling on the only read rail available during the freeze. ``--chain-plan``
prints that evidence and stops. It is kept because "we could not run the right
instrument" is a finding with numbers, not an excuse.

**B. The one that fits, and what it costs in fidelity.** ``--chunked`` (the
default) measures the collision directly from ``futures_markets`` and
``futures_outcomes``, partitioned by ``event_id`` range.

The partition is exact for this question: an ``e:`` vm_id is ``'e:'||event_id``,
so every row that can collide on it lives in the one chunk containing that
event. Group sizes are resolved GLOBALLY inside each chunk (looked up by
``group_id`` across the whole table, via ``ix_futures_markets_group_id``), so a
market that is really ``g:`` is never mistaken for ``e:`` because its siblings
fell in another chunk.

It is a re-derivation of the population, which this codebase warns against (the
C14 drift lesson), so it is deliberately built to fail in ONE direction:

* ``adj_opening_probability`` is taken as ``COALESCE(calibration_probability,
  opening_probability)``. This is EXACT for every row that can participate:
  ``mode_prices`` excludes ``is_mex_normalized`` rows, and mex normalization is
  the only thing that makes ``adj_opening_probability`` differ from that
  expression. Rows suppressed by a mode price are ``is_multi AND NOT
  is_mex_normalized``, so both sides of the collision carry the raw price.
* the expensive per-outcome exclusions are OMITTED — ``is_liquid``,
  ``is_field_incomplete``, ``is_poly_placeholder``, the malformed/void/orphan
  rungs, and ``clean_vms``'s ``has_winner >= 1``. Omitting an exclusion can only
  ADD candidate rows and ADD mode-price groups.
* the published band (``0.005 < p < 0.98``) and ``eligible >= 3`` ARE applied,
  because they bound which rows a mode price can actually suppress.

So the chunked number is an **UPPER BOUND** on cross-suppressed published rows.
A bound of zero is a definitive zero. A bound above zero is a bound, and must be
reported as one — never as the count.

How to run
----------
    source ~/.claude/.env
    python3 scripts/measure_2098_mode_price_collision.py --out /tmp/artifact.json
    python3 scripts/measure_2098_mode_price_collision.py --chain-plan

Read-only throughout: plain SELECTs on the ``db-query`` row path (10 s statement
timeout, no writes) and ``explain: true`` without ``analyze`` for the chain
plans, which does not execute at all.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.sql_comment_strip import (  # noqa: E402
    count_statement_separators,
    strip_sql_comments,
)

# ==========================================================================
# Instrument A — the faithful chain, plan-only.
# ==========================================================================

#: Events reaching >= 3 resolved futures markets under more than one source.
#: Measured 2026-08-22 against production: **1,288 rows** (a superset of the
#: 1,271 the worker header records, which counts over the further-filtered
#: ``market_info``), 12.4 s cold.
SHARED_EVENTS_SQL = """(
                        SELECT p.event_id
                        FROM (
                            SELECT event_id, source, COUNT(*) AS c
                            FROM futures_markets
                            WHERE status = 'resolved' AND event_id IS NOT NULL
                            GROUP BY 1, 2
                        ) p
                        WHERE p.c >= 3
                        GROUP BY p.event_id
                        HAVING COUNT(DISTINCT p.source) > 1
                    )"""

#: Injected into ``market_info``'s WHERE. The second arm completes any group a
#: scoped market belongs to, so ``group_sizes`` cannot be truncated by the scope
#: and flip a ``g:`` market to ``e:`` (the warning in ``_virtual_market_ctes``).
MARKET_INFO_SCOPE = f"""
                  AND (
                    fm.event_id IN {SHARED_EVENTS_SQL}
                    OR fm.group_id IN (
                        SELECT g.group_id
                        FROM futures_markets g
                        WHERE g.status = 'resolved'
                          AND g.group_id IS NOT NULL
                          AND g.event_id IN {SHARED_EVENTS_SQL}
                    )
                  )
"""

# The three substitutions. Each is asserted to appear EXACTLY once before use: a
# silent no-op substitution would compare a fold against itself and report zero
# collisions, which is the flattering direction (gotcha #53 — a run that measured
# nothing looks exactly like a run with nothing to find).
MODE_PRICES_FROM = """                SELECT vm_id, adj_opening_probability AS mode_price"""
MODE_PRICES_TO = """                SELECT vm_id, source, adj_opening_probability AS mode_price"""

MODE_GROUPBY_FROM = """                GROUP BY vm_id, adj_opening_probability, eligible"""
MODE_GROUPBY_TO = """                GROUP BY vm_id, source, adj_opening_probability, eligible"""

JOIN_FROM = """                  ON mp.vm_id = ro.vm_id AND mp.mode_price = ro.adj_opening_probability"""
# CAL-P090 shipped this as three lines, not one — matched here VERBATIM, because
# these anchors are also read in reverse to reconstruct the pre-fix chain, and an
# anchor that is merely equivalent is an anchor that finds nothing.
JOIN_TO = """                  ON mp.vm_id = ro.vm_id
                  AND mp.source = ro.source
                  AND mp.mode_price = ro.adj_opening_probability"""

CELL_TAIL = """
SELECT
    d.source                                             AS source,
    d.category                                           AS category,
    LEAST(FLOOR(d.adj_opening_probability * 10)::int, 9) AS bucket_idx,
    COUNT(*)                                             AS n
FROM deduped d
GROUP BY 1, 2, 3
"""


def _substitute(chain: str, pairs: list[tuple[str, str]]) -> str:
    out = chain
    for src, dst in pairs:
        n = out.count(src)
        if n != 1:
            raise SystemExit(
                f"ABORT: anchor appears {n} times, expected exactly 1. The chain has "
                f"moved and this script would otherwise compare a fold against itself "
                f"and report zero collisions.\n  anchor: {src!r}"
            )
        out = out.replace(src, dst)
    return out


#: FROM -> TO, i.e. source-BLIND -> source-SCOPED. Read in reverse to go the
#: other way. Which direction this script needs depends on which side of the
#: CAL-P090 fix the checked-out source is on, and it works that out rather than
#: assuming — see :func:`build_chains`.
SOURCE_SCOPE_PAIRS = [
    (MODE_PRICES_FROM, MODE_PRICES_TO),
    (MODE_GROUPBY_FROM, MODE_GROUPBY_TO),
    (JOIN_FROM, JOIN_TO),
]


def _all_present(chain: str, anchors) -> bool:
    return all(chain.count(a) == 1 for a in anchors)


def build_chains() -> tuple[str, str, str]:
    """``(unscoped, blind_mode_scoped, source_scoped_mode)`` chains.

    DIRECTION-AWARE, because the module's SQL changed under this script.

    Before CAL-P090 the checked-out source WAS the source-blind chain and the
    source-scoped variant had to be synthesised. After CAL-P090 it is the other
    way round. Either way the three chains this returns mean the same three
    things, so the printed cost comparison stays comparable across the fix.

    The refusal in the ``else`` arm is the point of the whole function. If the
    anchors match NEITHER state, the chain has moved for some third reason and
    the honest answer is to stop: substituting nothing would hand
    ``run_chain_plan`` two identical chains, which plans to two identical costs,
    which reads exactly like "the source-blindness costs nothing" — the
    flattering direction, arrived at by measuring nothing (gotcha #53).
    """
    from app.tasks.precompute_calibration import _calibration_population_ctes

    unscoped = _calibration_population_ctes()
    prod = _calibration_population_ctes(market_info_extra=MARKET_INFO_SCOPE)

    blind_anchors = [src for src, _ in SOURCE_SCOPE_PAIRS]
    scoped_anchors = [dst for _, dst in SOURCE_SCOPE_PAIRS]

    if _all_present(prod, blind_anchors):
        # Pre-CAL-P090 source: production is blind; synthesise the scoped one.
        return unscoped, prod, _substitute(prod, SOURCE_SCOPE_PAIRS)
    if _all_present(prod, scoped_anchors):
        # Post-CAL-P090 source: production is scoped; synthesise the blind one,
        # so the pre-fix cost line is still produced next to the after.
        reverse = [(dst, src) for src, dst in SOURCE_SCOPE_PAIRS]
        return _substitute(unscoped, reverse), _substitute(prod, reverse), prod
    raise SystemExit(
        "ABORT: `_calibration_population_ctes()` matches NEITHER the source-blind "
        "nor the source-scoped mode_prices shape. The chain has moved for a third "
        "reason; re-aim the three anchors rather than letting this script compare a "
        "fold against itself and report zero collisions."
    )


# ==========================================================================
# Instrument B — the direct, chunked upper bound.
# ==========================================================================

#: One chunk. ``:lo``/``:hi`` are inlined as integer literals (the endpoint takes
#: no bind params), and the range is half-open so chunks partition the domain.
#:
#: ``cur`` reproduces production's source-BLIND mode group; ``alt`` the
#: source-SCOPED one. Production joins on ``(vm_id, mode_price)`` only — it does
#: NOT re-check ``eligible``, even though ``eligible`` is in the GROUP BY — so
#: ``EXISTS`` here matches on ``(vm_id, p)`` exactly as ``deduped`` does.
CHUNK_CTES = """
WITH mk AS (
    SELECT fm.id AS market_id, fm.source, fm.event_id, fm.group_id
    FROM futures_markets fm
    WHERE fm.status = 'resolved'
      AND fm.event_id >= {lo} AND fm.event_id < {hi}
),
gsz AS (
    SELECT g.group_id, g.source, COUNT(*) AS group_size
    FROM futures_markets g
    WHERE g.status = 'resolved'
      AND g.group_id IS NOT NULL
      AND g.group_id IN (SELECT DISTINCT group_id FROM mk WHERE group_id IS NOT NULL)
    GROUP BY 1, 2
),
esz AS (
    SELECT event_id, source, COUNT(*) AS event_size FROM mk GROUP BY 1, 2
),
vm AS (
    SELECT mk.market_id, mk.source,
        CASE WHEN COALESCE(gsz.group_size, 0) >= 3 THEN 'g:' || mk.group_id
             WHEN esz.event_size >= 3            THEN 'e:' || mk.event_id::text
             ELSE 'm:' || mk.market_id::text
        END AS vm_id
    FROM mk
    LEFT JOIN gsz ON gsz.group_id = mk.group_id AND gsz.source = mk.source
    LEFT JOIN esz ON esz.event_id = mk.event_id AND esz.source = mk.source
),
oc AS (
    SELECT vm.vm_id, vm.source,
           COALESCE(fo.calibration_probability, fo.opening_probability) AS p,
           fo.opening_probability AS op
    FROM futures_outcomes fo
    JOIN vm ON vm.market_id = fo.market_id
),
elig AS (
    SELECT vm_id, source,
           COUNT(*) FILTER (WHERE op IS NOT NULL AND op > 0 AND op < 1) AS eligible
    FROM oc GROUP BY 1, 2
),
shared AS (
    SELECT vm_id FROM elig
    WHERE vm_id LIKE 'e:%'
    GROUP BY vm_id HAVING COUNT(DISTINCT source) > 1
),
base AS (
    SELECT o.vm_id, o.source, o.p, e.eligible
    FROM oc o
    JOIN elig e ON e.vm_id = o.vm_id AND e.source = o.source
    JOIN shared s ON s.vm_id = o.vm_id
    WHERE o.p IS NOT NULL AND e.eligible >= 3
),
cur AS (
    SELECT vm_id, p, eligible, COUNT(*) AS c
    FROM base GROUP BY 1, 2, 3
    HAVING COUNT(*) > GREATEST(eligible * 0.5, 2)
),
alt AS (
    SELECT vm_id, source, p, eligible, COUNT(*) AS c
    FROM base GROUP BY 1, 2, 3, 4
    HAVING COUNT(*) > GREATEST(eligible * 0.5, 2)
)"""

#: The summary tail: five counters, one row.
SUMMARY_TAIL = """
SELECT
    (SELECT COUNT(*) FROM shared)                                   AS shared_e_vms,
    (SELECT COUNT(DISTINCT vm_id) FROM cur)                         AS vms_with_mode_price,
    COUNT(*)                                                        AS suppressed_rows_blind,
    COUNT(*) FILTER (WHERE NOT EXISTS (
        SELECT 1 FROM alt a
        WHERE a.vm_id = b.vm_id AND a.source = b.source AND a.p = b.p))
                                                                    AS cross_suppressed_rows,
    COUNT(DISTINCT b.vm_id) FILTER (WHERE NOT EXISTS (
        SELECT 1 FROM alt a
        WHERE a.vm_id = b.vm_id AND a.source = b.source AND a.p = b.p))
                                                                    AS cross_suppressed_vms
FROM base b
WHERE b.p > 0.005 AND b.p < 0.98
  AND EXISTS (SELECT 1 FROM cur c WHERE c.vm_id = b.vm_id AND c.p = b.p)
"""

#: ``event_id`` domain, measured 2026-08-22: MIN 1,273 / MAX 15,290,662 over
#: 425,927 event-linked markets, 415,185 of them ``status='resolved'``.
#:
#: The seed grid is DENSITY-AWARE, not uniform, because the domain is not:
#: measured the same day, ``[14M, 16M)`` holds 355,963 of those 415,185 rows
#: (85.7%) and ``[0, 14M)`` holds 59,222. A uniform grid puts ~86% of the work
#: in two chunks, each of which then blows the endpoint's 10 s statement
#: timeout and has to be halved six times — the first attempt at this sweep
#: spent 900 s doing exactly that and banked nothing.
EVENT_ID_LO = 1_000
EVENT_ID_HI = 16_000_000
#: Rows per 1M-wide slice, measured 2026-08-22 (row path, 9.45 s):
#: 0-1M 5,587 · 1-2M 115 · 2-3M 95 · 3-4M 66 · 4-5M 755 · 5-6M 3,863 ·
#: 6-7M 7,388 · 7-8M 1,124 · 8-9M 2,161 · 9-10M 2,881 · 10-11M 6,547 ·
#: 11-12M 4,013 · 12-13M 17,669 · 13-14M 6,958 · 14-15M 178,655 · 15-16M 177,308
DENSE_FROM = 14_000_000
SPARSE_STEP = 2_000_000
DENSE_STEP = 50_000


def seed_ranges() -> list[tuple[int, int]]:
    """Half-open ranges covering ``[EVENT_ID_LO, EVENT_ID_HI)`` with no gap."""
    out: list[tuple[int, int]] = []
    lo = EVENT_ID_LO
    while lo < DENSE_FROM:
        hi = min(lo + SPARSE_STEP, DENSE_FROM)
        out.append((lo, hi))
        lo = hi
    while lo < EVENT_ID_HI:
        hi = min(lo + DENSE_STEP, EVENT_ID_HI)
        out.append((lo, hi))
        lo = hi
    return out


#: The detail tail: name the actual colliding rows, so a non-zero bound is a
#: thing someone can go look at rather than a number in a report.
DETAIL_TAIL = """
SELECT b.vm_id, b.source, b.p, b.eligible, COUNT(*) AS rows_cross_suppressed
FROM base b
WHERE b.p > 0.005 AND b.p < 0.98
  AND EXISTS (SELECT 1 FROM cur c WHERE c.vm_id = b.vm_id AND c.p = b.p)
  AND NOT EXISTS (SELECT 1 FROM alt a
                  WHERE a.vm_id = b.vm_id AND a.source = b.source AND a.p = b.p)
GROUP BY 1, 2, 3, 4
ORDER BY 5 DESC
"""

CHUNK_SQL = CHUNK_CTES + SUMMARY_TAIL
DETAIL_SQL = CHUNK_CTES + DETAIL_TAIL


def post(sql: str, *, explain: bool = False, analyze: bool = False,
         timeout_ms: int | None = None, limit: int = 1000):
    api = os.environ.get("BAINLUCK_API")
    token = os.environ.get("ADMIN_TOKEN")
    if not api or not token:
        raise SystemExit("ABORT: source ~/.claude/.env first (BAINLUCK_API, ADMIN_TOKEN).")
    clean = strip_sql_comments(sql)
    seps = count_statement_separators(clean)
    if seps:
        raise SystemExit(f"ABORT: {seps} statement separator(s) survive comment stripping.")
    body: dict = {"sql": clean, "limit": limit}
    if explain:
        body["explain"] = True
        if analyze:
            body["analyze"] = True
        if timeout_ms is not None:
            body["timeout_ms"] = timeout_ms
    req = urllib.request.Request(
        api.rstrip("/") + "/api/admin/db-query",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=240) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        try:
            return {"http_error": exc.code, **json.loads(exc.read().decode())}
        except Exception:
            return {"http_error": exc.code}


def run_chunked(max_depth: int = 6, out_path: str | None = None) -> dict:
    """Sweep the whole ``event_id`` domain, splitting any chunk that times out.

    Partial results are flushed to ``out_path`` after every chunk. A sweep that
    dies at minute 14 of 15 must not lose its first 14 minutes — and, more to
    the point, the file must show WHICH ranges were swept, so a truncated run
    can never be mistaken for a complete one.
    """
    pending = [(lo, hi, 0) for lo, hi in seed_ranges()]
    totals = {
        "shared_e_vms": 0,
        "vms_with_mode_price": 0,
        "suppressed_rows_blind": 0,
        "cross_suppressed_rows": 0,
        "cross_suppressed_vms": 0,
    }
    chunks: list[dict] = []
    failures: list[dict] = []
    t0 = time.time()

    def snapshot(done: bool) -> dict:
        return {
            "totals": totals,
            "chunks": chunks,
            "unswept_ranges": failures,
            "pending_ranges": [{"lo": a, "hi": b, "depth": d} for a, b, d in pending],
            "complete": done and not failures and not pending,
            "wall_s": round(time.time() - t0, 1),
        }

    def flush(done: bool = False) -> None:
        if not out_path:
            return
        with open(out_path, "w") as fh:
            json.dump({"chunked": snapshot(done)}, fh, indent=1)

    while pending:
        lo, hi, depth = pending.pop(0)
        sql = CHUNK_SQL.format(lo=lo, hi=hi)
        res = post(sql, limit=10)
        if "rows" in res and res.get("rows"):
            row = res["rows"][0]
            keys = res["columns"]
            rec = {k: (int(v) if v is not None else 0) for k, v in zip(keys, row)}
            rec.update({"lo": lo, "hi": hi, "duration_ms": res.get("duration_ms")})
            chunks.append(rec)
            for k in totals:
                totals[k] += rec.get(k, 0)
            print(
                f"  [{lo:>9,}, {hi:>9,})  {res.get('duration_ms', 0):7.0f} ms  "
                f"shared_e={rec['shared_e_vms']:>5}  mode_vms={rec['vms_with_mode_price']:>5}  "
                f"suppressed={rec['suppressed_rows_blind']:>6}  CROSS={rec['cross_suppressed_rows']:>6}",
                flush=True,
            )
            flush()
            continue
        reason = (res.get("detail") or res).get("reason") if isinstance(res.get("detail"), dict) else res.get("reason")
        if depth < max_depth and (hi - lo) > 1:
            mid = lo + (hi - lo) // 2
            print(f"  [{lo:>9,}, {hi:>9,})  SPLIT (reason={reason})", flush=True)
            pending.insert(0, (mid, hi, depth + 1))
            pending.insert(0, (lo, mid, depth + 1))
            continue
        # NEVER silently drop: an unswept range is not a zero.
        print(f"  [{lo:>9,}, {hi:>9,})  UNSWEPT depth={depth} reason={reason}", flush=True)
        failures.append({"lo": lo, "hi": hi, "depth": depth, "reason": reason, "raw": res})
        flush()
    flush(done=True)
    return snapshot(done=True)


def run_resweep(prior_path: str, step: int, out_path: str | None, max_depth: int = 8) -> dict:
    """Second pass over the ranges the first sweep could not finish.

    Binary splitting is the wrong tool in the dense tail: each failed attempt
    costs the full 10 s statement timeout before it learns anything, so halving
    a range that needs to be sixteenth-ed spends 40 s to get there. This walks
    the leftover ranges at a FIXED fine step instead, and merges the result into
    the prior artifact's totals.

    The merge is by range, not by addition into an opaque counter: the output
    keeps every swept range so coverage stays auditable, and any range that
    still will not finish stays listed as unswept rather than becoming a zero.
    """
    with open(prior_path) as fh:
        prior = json.load(fh)["chunked"]
    leftovers = [(r["lo"], r["hi"]) for r in prior.get("unswept_ranges", [])]
    leftovers += [(r["lo"], r["hi"]) for r in prior.get("pending_ranges", [])]
    if not leftovers:
        print("  nothing left to sweep", flush=True)
        return prior

    fine: list[tuple[int, int, int]] = []
    for lo, hi in leftovers:
        cur = lo
        while cur < hi:
            nxt = min(cur + step, hi)
            fine.append((cur, nxt, 0))
            cur = nxt
    print(f"  {len(leftovers)} leftover range(s) -> {len(fine)} fine chunks of {step:,}", flush=True)

    totals = dict(prior["totals"])
    chunks = list(prior["chunks"])
    failures: list[dict] = []
    t0 = time.time()

    def snapshot(done: bool) -> dict:
        return {
            "totals": totals,
            "chunks": chunks,
            "unswept_ranges": failures,
            "pending_ranges": [{"lo": a, "hi": b, "depth": d} for a, b, d in fine],
            "complete": done and not failures and not fine,
            "wall_s": round(prior.get("wall_s", 0) + time.time() - t0, 1),
            "resweep_step": step,
        }

    while fine:
        lo, hi, depth = fine.pop(0)
        res = post(CHUNK_SQL.format(lo=lo, hi=hi), limit=10)
        if "rows" in res and res.get("rows"):
            rec = {k: (int(v) if v is not None else 0)
                   for k, v in zip(res["columns"], res["rows"][0])}
            rec.update({"lo": lo, "hi": hi, "duration_ms": res.get("duration_ms")})
            chunks.append(rec)
            for k in totals:
                totals[k] += rec.get(k, 0)
            if rec["shared_e_vms"] or rec["cross_suppressed_rows"]:
                print(f"  [{lo:>9,}, {hi:>9,})  {res.get('duration_ms', 0):7.0f} ms  "
                      f"shared_e={rec['shared_e_vms']:>4}  CROSS={rec['cross_suppressed_rows']:>5}",
                      flush=True)
            if out_path:
                with open(out_path, "w") as fh:
                    json.dump({"chunked": snapshot(False)}, fh, indent=1)
            continue
        reason = (res.get("detail") or res).get("reason") if isinstance(res.get("detail"), dict) else res.get("reason")
        if depth < max_depth and (hi - lo) > 1:
            mid = lo + (hi - lo) // 2
            fine.insert(0, (mid, hi, depth + 1))
            fine.insert(0, (lo, mid, depth + 1))
            continue
        print(f"  [{lo:>9,}, {hi:>9,})  UNSWEPT reason={reason}", flush=True)
        failures.append({"lo": lo, "hi": hi, "depth": depth, "reason": reason})

    out = snapshot(done=True)
    if out_path:
        with open(out_path, "w") as fh:
            json.dump({"chunked": out}, fh, indent=1)
    return out


def run_chain_plan() -> dict:
    unscoped, prod, scoped = build_chains()
    out = {}
    for label, chain in (("unscoped", unscoped), ("scoped_production", prod),
                         ("scoped_source_scoped_mode", scoped)):
        res = post("WITH " + chain + CELL_TAIL, explain=True, timeout_ms=25000, limit=10)
        cost = None
        try:
            cost = res["plan"][0]["Plan"]["Total Cost"]
            rows = res["plan"][0]["Plan"]["Plan Rows"]
        except Exception:
            rows = None
        out[label] = {"total_cost": cost, "plan_rows": rows, "plan_ms": res.get("duration_ms")}
        print(f"  {label:28s} total_cost={cost:,.0f}" if cost else f"  {label}: {res}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=None)
    ap.add_argument("--chain-plan", action="store_true",
                    help="plan-only cost evidence for the faithful chain (does not execute)")
    ap.add_argument("--max-depth", type=int, default=5)
    ap.add_argument("--resweep", default=None,
                    help="path to a prior artifact; re-sweeps its unswept/pending ranges")
    ap.add_argument("--step", type=int, default=2000, help="fine step for --resweep")
    args = ap.parse_args()

    result: dict = {
        "script": "measure_2098_mode_price_collision.py",
        "issue": 2098,
        "queue": "CAL-P087",
        "measured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "read_only": True,
    }

    if args.chain_plan:
        print("Instrument A — faithful chain, PLAN ONLY (does not execute):")
        result["chain_plan"] = run_chain_plan()
    elif args.resweep:
        print(f"Instrument B — RESWEEP of {args.resweep}:", flush=True)
        result["chunked"] = run_resweep(args.resweep, args.step, args.out)
        t = result["chunked"]["totals"]
        print("\n=== TOTALS ===")
        print(json.dumps(t, indent=1))
        print("complete:", result["chunked"]["complete"],
              "unswept:", len(result["chunked"]["unswept_ranges"]))
    else:
        print(f"Instrument B — direct chunked UPPER BOUND (read-only row path), "
              f"{len(seed_ranges())} seed ranges:", flush=True)
        result["chunked"] = run_chunked(max_depth=args.max_depth, out_path=args.out)
        t = result["chunked"]["totals"]
        print("\n=== TOTALS ===")
        print(json.dumps(t, indent=1))
        print("complete:", result["chunked"]["complete"],
              "unswept:", len(result["chunked"]["unswept_ranges"]),
              "wall_s:", result["chunked"]["wall_s"])

    if args.out:
        with open(args.out, "w") as fh:
            json.dump(result, fh, indent=1)
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
