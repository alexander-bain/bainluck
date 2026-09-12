#!/usr/bin/env python3
"""#5401 — the SOURCE-WIDE published population move of the Kalshi writer bar.

WHY THIS EXISTS, AND WHY IT IS NOT ``calibration_fold_opening_source.py``.
``CALIBRATION_POPULATION_DECLARATION`` states the move over the WHOLE published
population and ``evaluate_publish`` refuses the rebuild if the realised move
misses it by more than ``tolerance_pct`` — and a refusal CLEARS THE CHECKPOINT,
so a wrong declaration bins every later rebuild until another deploy corrects
it. The number therefore has to be measured, not bracketed. Three properties of
the fold script make it unable to supply it:

1. **Its default ``--max-id`` (60,097,325) is stale.** 47,767 of 316,132 Kalshi
   markets now sit above it — 15.1% of the source, including 99% of the
   ``other`` category — and a sweep at defaults silently omits them.

2. **Chunking by ``fm.id`` is not neutral.** ``event_sizes`` is computed INSIDE
   ``market_info_extra``, so an event whose markets straddle a chunk boundary is
   counted short, ``event_size >= 3`` flips, and its markets fall out of their
   grouped ``vm_id`` into singletons — changing ``is_grouped``, ``vm_stats``,
   ``field_completeness`` and the ``deduped`` ladder, i.e. changing WHICH ROWS
   THE MEASUREMENT THINKS ARE PUBLISHED. Measured: 4,553 of 13,782 Kalshi
   event-groups of size >= 3 span more than 100k ids and 1,288 span more than
   1M, so the default 1M width splits them by construction — and adaptive
   splitting on timeout makes the answer depend on where the timeouts happened.
   (Kalshi ``group_id`` is unique per market — 316,132 groups of size 1 — so the
   ``group_size >= 3`` arm never fires for this source and ``event_id`` is the
   only cross-market key that matters here.)

3. **Its ``kept_*`` verdict cannot express the second-order drop.** The writer
   bar is wired into ``field_completeness`` as well as ``deduped``, so a field
   that loses ONE member to the bar becomes PARTIAL and is dropped WHOLE —
   above-bar members included. ``VERDICT_CASE`` has no writer-bar arm but reads
   ``is_field_incomplete``, which in this branch is already computed WITH the
   bar. Counting the below-bar cohort therefore UNDERSTATES the move, in the one
   direction that trips ``population_shrink``.

WHAT THIS DOES INSTEAD. It counts ``deduped`` — the published population itself,
the CTE ``bucketed`` selects from, whose ``COUNT(*)`` is the payload's
``total_outcomes`` — twice over the same rows in the same minute:

* ``--arm baseline``  : ``is_below_writer_bar`` forced to ``false``. This is
  master's semantics EXACTLY: the branch adds one column and three
  ``AND NOT ro.is_below_writer_bar`` clauses to the builder and nothing else
  (``git diff origin/master``: 145 insertions, 0 deletions), so neutralising the
  column neutralises all three clauses at once.
* ``--arm repaired``  : the branch as it stands.

Both arms are chunked EVENT-ATOMICALLY: markets carrying an ``event_id`` are
partitioned by half-open ranges of the ``event_id`` VALUE (so every member of an
event lands in the same chunk whatever the row counts do), and markets without
one are partitioned by ``fm.id`` (they are ``m:`` singletons and cannot be
split). Ranges come from ``--boundaries``, which the caller measures with
``ntile`` and which this file does not guess.

THE CONTROL. The baseline arm's Kalshi count must reproduce the live payload's
``by_source`` Kalshi ``n`` (396,160 at q269 / 2026-09-12T00:16:35Z), within the
drift of a live table. That single number tests the max-id bound, the
event-atomic chunking and the per-source restriction at once; run it FIRST and
do not believe the repaired arm until it passes. Compare against ``by_source``
and never ``by_category`` — the latter sums to 756,873 because
``min_category_outcomes = 1000`` gates small cells out of that breakdown only.

Usage::

    python3 backend/scripts/calibration_population_move_5401.py \\
        --arm baseline --boundaries artifacts/cal-p1121/boundaries.json \\
        --out artifacts/cal-p1121/population-baseline.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tasks.precompute_calibration import (  # noqa: E402
    KALSHI_WRITER_BAR_MET,
    _calibration_population_ctes,
)

from calibration_cell_exact import (  # noqa: E402
    _strip_sql_comments,
    db_query,
)

#: The exact text the builder emits for the flag, and the inert text that
#: reproduces master. Asserted to appear EXACTLY ONCE — a builder edit that
#: renames the column or adds a second site must break this loudly rather than
#: silently measure one arm twice (which would report a move of zero and read
#: as "the repair does nothing").
_FLAG_SQL = f"(NOT {KALSHI_WRITER_BAR_MET}) AS is_below_writer_bar"
_FLAG_INERT = "false AS is_below_writer_bar"

SOURCE = "kalshi"


def chunk_sql(arm: str, predicate: str) -> str:
    """``deduped`` counted per category, for one event-atomic chunk."""
    pop = _calibration_population_ctes(
        market_info_extra=f"AND fm.source = '{SOURCE}' AND {predicate}"
    )
    if arm == "baseline":
        n = pop.count(_FLAG_SQL)
        if n != 1:
            raise RuntimeError(
                f"expected the writer-bar flag exactly once in the builder "
                f"output, found {n} — the baseline arm cannot be constructed "
                f"by substitution any more; re-derive it from origin/master"
            )
        pop = pop.replace(_FLAG_SQL, _FLAG_INERT)
    return _strip_sql_comments(
        "WITH " + pop + """
SELECT category,
       COUNT(*) AS n,
       COUNT(*) FILTER (WHERE is_winner) AS won,
       ROUND(SUM(adj_opening_probability)::numeric, 3) AS implied
FROM deduped
GROUP BY 1
""".strip()
    )


def _predicates(boundaries: dict) -> list[tuple[str, str]]:
    """(label, SQL predicate) for every chunk, event-atomic by construction."""
    out: list[tuple[str, str]] = []
    ev = boundaries["event_id_bounds"]
    for i in range(len(ev) - 1):
        lo, hi = ev[i], ev[i + 1]
        # Half-open on the VALUE: (lo, hi]. Every row of an event shares one
        # event_id, so an event can never straddle two of these.
        out.append((
            f"ev({lo},{hi}]",
            f"fm.event_id IS NOT NULL AND fm.event_id > {lo} "
            f"AND fm.event_id <= {hi}",
        ))
    ids = boundaries["null_event_id_bounds"]
    for i in range(len(ids) - 1):
        lo, hi = ids[i], ids[i + 1]
        out.append((
            f"noev({lo},{hi}]",
            f"fm.event_id IS NULL AND fm.id > {lo} AND fm.id <= {hi}",
        ))
    return out


def _split(label: str, predicate: str) -> list[tuple[str, str]] | None:
    """Halve a chunk's key range. Returns None when it cannot be halved.

    Splitting stays event-atomic: an ``ev`` chunk is halved on the ``event_id``
    VALUE, never on a row count, so the two halves still contain whole events.
    """
    head, rest = label.split("(", 1)
    lo, hi = (int(x) for x in rest.rstrip("]").split(","))
    if hi - lo <= 1:
        return None
    mid = lo + (hi - lo) // 2
    col = "fm.event_id" if head == "ev" else "fm.id"
    nul = "fm.event_id IS NOT NULL" if head == "ev" else "fm.event_id IS NULL"
    return [
        (f"{head}({lo},{mid}]", f"{nul} AND {col} > {lo} AND {col} <= {mid}"),
        (f"{head}({mid},{hi}]", f"{nul} AND {col} > {mid} AND {col} <= {hi}"),
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", choices=("baseline", "repaired"), required=True)
    ap.add_argument("--boundaries", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    boundaries = json.loads(Path(args.boundaries).read_text())
    stack = list(reversed(_predicates(boundaries)))

    started = time.monotonic()
    acc: dict[str, list[float]] = defaultdict(lambda: [0, 0, 0.0])
    done = 0
    irreducible: list[str] = []
    total = len(stack)
    while stack:
        label, predicate = stack.pop()
        try:
            res = db_query(chunk_sql(args.arm, predicate))
        except Exception as exc:  # QueryTimeout and friends -> halve the range
            halves = _split(label, predicate)
            if halves is None:
                print(f"  {label} IRREDUCIBLE {exc}", flush=True)
                irreducible.append(label)
                continue
            print(f"  {label} split -> {halves[0][0]} {halves[1][0]}",
                  flush=True)
            stack.append(halves[1])
            stack.append(halves[0])
            total += 1
            continue
        rows = res.get("rows") or []
        # gotcha: the row cap is 1,000 and a capped answer is silently short.
        if len(rows) >= 1000:
            raise RuntimeError(f"{label} hit the 1,000-row cap")
        for category, n, won, implied in rows:
            cell = acc[category]
            cell[0] += int(n)
            cell[1] += int(won)
            cell[2] += float(implied or 0.0)
        done += 1
        if done % 5 == 0:
            print(f"  {done}/{total} chunks, "
                  f"n={int(sum(v[0] for v in acc.values())):,}, "
                  f"{time.monotonic() - started:.0f}s", flush=True)

    rows_out = sorted(
        ({"category": k, "n": int(v[0]), "won": int(v[1]),
          "implied": round(v[2], 2)} for k, v in acc.items()),
        key=lambda r: -r["n"],
    )
    out = {
        "arm": args.arm,
        "source": SOURCE,
        "kalshi_published_outcomes": int(sum(v[0] for v in acc.values())),
        "chunks": done,
        "irreducible": irreducible,
        "elapsed_s": round(time.monotonic() - started, 1),
        "by_category": rows_out,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2) + "\n")

    print(f"\narm={args.arm}  kalshi published outcomes = "
          f"{out['kalshi_published_outcomes']:,}  "
          f"({done} chunks, {out['elapsed_s']}s, "
          f"irreducible={len(irreducible)})")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
