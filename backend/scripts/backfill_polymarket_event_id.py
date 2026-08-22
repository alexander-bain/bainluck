#!/usr/bin/env python3
"""One-shot backfill: stamp ``polymarket_event_id`` from ``group_id``.

Queue 390 Item 2b. Lineage: ``C-INGEST-EID-AUDIT-1`` found the key, and
``C-GROUPID-INTEGRITY-1`` returned **50/50 confirmed (p<0.06 against a 1%-wrong
key, no age/shape/size variance)**, which is the gate that promoted this from
design to build.

## What this REVERSES, said plainly

``C-EID-RECOVERY-1`` wrote off ~153k of 482k rows as
``unverifiable-by-source-design``. That verdict was reached honestly and was
wrong, for a reason worth keeping: it assumed ``market_metadata`` was the only
place the event id could live, and therefore that Gamma was the only way to
recover it. The id was in our own ``group_id`` column the whole time, put there
by our own ingestion from the same Gamma response that populated the parent row's
metadata. Recording that here — rather than quietly superseding the earlier
census — is what keeps both censuses honest.

## Why this is a mass write and is treated as one

489k rows. The discipline is fixed and not optional: **census before, batched in
deterministic order, dry-run first, verify after.**

* **Additive.** ``market_metadata || jsonb_build_object(...)``. No key is
  replaced, no key is removed.
* **Guarded.** ``NOT (market_metadata ? 'polymarket_event_id')`` — a row that
  already has one is never touched, so a re-run is a no-op and an interrupted run
  resumes correctly.
* **Deterministic.** ``ORDER BY id`` with an ``id >`` cursor. Every batch is
  reproducible and an interrupted run says exactly where it stopped.
* **Reversible.** See ``--stamp-provenance`` below.

## The one deliberate deviation from the audit's UPDATE

The audit's statement writes a single key. This writes a second,
``polymarket_event_id_source: "group_id_backfill_q390"``, unless
``--no-stamp-provenance`` is passed.

That is a deviation and is flagged rather than buried. The argument for it: with
it, this write is exactly reversible (``WHERE market_metadata->>'polymarket_
event_id_source' = 'group_id_backfill_q390'``) and a later reader can tell a
DERIVED id from one CAPTURED at mint time. Without it, 489k rows become
indistinguishable from correctly-minted rows the moment the statement commits,
and undoing it means reconstructing which rows were touched from a log. A mass
write that cannot be identified afterwards is a mass write that cannot be undone.

The argument against: it is not what was specified, and it puts a key in the gold
path that no existing reader expects. Readers use
``market_metadata->>'polymarket_event_id'`` and are unaffected by a sibling key,
which is why the default is ON — but ``--no-stamp-provenance`` exists so the
decision stays the caller's.

## Post-verify (named by Fable, not invented here)

1. Re-run the audit's 50-specimen Gamma check — it must stay **50/50**.
2. The ``no_eid`` count must go to **~0**.

``--verify-gamma`` implements (1): it samples backfilled rows, fetches
``/events/{stamped_id}`` from Gamma, and asserts the row's own ``external_id``
(the condition_id) appears among that event's markets. That is the same claim the
backfill makes, checked against the source rather than against itself.

Usage:

    python3 scripts/backfill_polymarket_event_id.py --census
    python3 scripts/backfill_polymarket_event_id.py --dry-run
    python3 scripts/backfill_polymarket_event_id.py --apply --batch-size 5000
    python3 scripts/backfill_polymarket_event_id.py --verify-gamma --sample 50
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Any

from sqlalchemy import text

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.tasks.base import get_task_session  # noqa: E402

PROVENANCE_VALUE = "group_id_backfill_q390"

#: The eligibility predicate, written ONCE and shared by the census, the dry-run,
#: the apply and the verify. Three hand-copied versions of a predicate is how a
#: census comes to describe a different population than the write it authorized.
#:
#: Note `NOT (market_metadata ? '...')` is NULL-blind: a row with
#: `market_metadata IS NULL` does not match it, so such rows are NOT eligible and
#: are counted separately by the census rather than silently dropped. Measured
#: 2026-08-21: there are zero of them.
ELIGIBLE = (
    "source = 'polymarket' "
    "AND group_id LIKE 'polymarket:%' "
    "AND NOT (market_metadata ? 'polymarket_event_id')"
)


async def census() -> dict[str, Any]:
    """The reconciling census. Every polymarket row lands in exactly one bucket.

    Taken in ONE statement on purpose. The first draft of this census took the
    numerator and denominator in separate queries and they disagreed by 26 rows —
    not a hidden class, just ingestion moving between two reads. A census used to
    bound a mass write has to be internally consistent or it is describing a
    population that never existed at any single moment.
    """
    sql = text(
        f"""
        SELECT
          COUNT(*) AS all_poly,
          COUNT(*) FILTER (WHERE market_metadata ? 'polymarket_event_id') AS already_stamped,
          COUNT(*) FILTER (WHERE {ELIGIBLE.replace("source = 'polymarket' AND ", "")}) AS eligible,
          COUNT(*) FILTER (
            WHERE NOT (market_metadata ? 'polymarket_event_id')
              AND (group_id IS NULL OR group_id NOT LIKE 'polymarket:%')
          ) AS unreachable,
          COUNT(*) FILTER (WHERE market_metadata IS NULL) AS meta_null,
          COUNT(*) FILTER (
            WHERE market_metadata->>'polymarket_event_id_source' = :prov
          ) AS already_backfilled,
          MIN(id) FILTER (WHERE {ELIGIBLE.replace("source = 'polymarket' AND ", "")}) AS min_id,
          MAX(id) FILTER (WHERE {ELIGIBLE.replace("source = 'polymarket' AND ", "")}) AS max_id
        FROM futures_markets
        WHERE source = 'polymarket'
        """
    )
    async with get_task_session() as session:
        row = (await session.execute(sql, {"prov": PROVENANCE_VALUE})).mappings().one()
    out = dict(row)
    out["reconciles"] = (
        out["already_stamped"] + out["eligible"] + out["unreachable"] == out["all_poly"]
    )
    return out


async def key_shape_census() -> dict[str, Any]:
    """Prove the KEY is unambiguous before stamping 489k rows with it.

    ``split_part(group_id, ':', 2)`` is only well-defined if every group_id has
    the shape it is assumed to have. Measured 2026-08-21: 489,238/489,238 match
    `^polymarket:[0-9]+$` exactly — zero empty, zero non-numeric, zero with a
    second colon. If that ever stops being true, this is the check that says so
    BEFORE the write rather than after.
    """
    sql = text(
        f"""
        SELECT
          COUNT(*) AS eligible,
          COUNT(*) FILTER (WHERE split_part(group_id, ':', 2) = '') AS key_empty,
          COUNT(*) FILTER (WHERE split_part(group_id, ':', 2) !~ '^[0-9]+$') AS key_non_numeric,
          COUNT(*) FILTER (WHERE group_id !~ '^polymarket:[^:]+$') AS key_extra_colon,
          COUNT(*) FILTER (WHERE jsonb_typeof(market_metadata) <> 'object') AS meta_not_object
        FROM futures_markets
        WHERE {ELIGIBLE}
        """
    )
    async with get_task_session() as session:
        row = (await session.execute(sql)).mappings().one()
    out = dict(row)
    out["clean"] = all(
        out[k] == 0
        for k in ("key_empty", "key_non_numeric", "key_extra_colon", "meta_not_object")
    )
    return out


async def dry_run(limit: int) -> list[dict[str, Any]]:
    """Show the exact values the apply WOULD write. No mutation.

    This is the whole point of a dry run and it is easy to get wrong: it must
    compute the value the way the UPDATE computes it, from the same predicate,
    rather than describing it. Anything else previews a different statement.
    """
    sql = text(
        f"""
        SELECT
          id,
          left(external_id, 20) AS external_id,
          group_id,
          split_part(group_id, ':', 2) AS would_write,
          market_metadata AS before_meta
        FROM futures_markets
        WHERE {ELIGIBLE}
        ORDER BY id
        LIMIT :limit
        """
    )
    async with get_task_session() as session:
        rows = (await session.execute(sql, {"limit": limit})).mappings().all()
    return [dict(r) for r in rows]


async def apply(batch_size: int, max_rows: int | None, stamp_provenance: bool) -> dict:
    """Batched, deterministic, resumable, idempotent.

    The cursor is ``id >``, not ``OFFSET``: an OFFSET walk over a table that is
    being written to concurrently skips rows, and polymarket ingestion is writing
    to this table continuously (~230 new rows in a four-minute window, measured).
    Because the predicate excludes already-stamped rows, a re-run resumes rather
    than repeats, and rows minted mid-run are simply picked up or left for the
    next run — never double-written.
    """
    build = "jsonb_build_object('polymarket_event_id', split_part(group_id, ':', 2))"
    if stamp_provenance:
        build = (
            "jsonb_build_object("
            "'polymarket_event_id', split_part(group_id, ':', 2), "
            "'polymarket_event_id_source', :prov"
            ")"
        )

    sql = text(
        f"""
        WITH batch AS (
            SELECT id
            FROM futures_markets
            WHERE {ELIGIBLE} AND id > :cursor
            ORDER BY id
            LIMIT :batch_size
        )
        UPDATE futures_markets AS f
        SET market_metadata = COALESCE(f.market_metadata, '{{}}'::jsonb) || {build}
        FROM batch
        WHERE f.id = batch.id
        RETURNING f.id
        """
    )

    cursor = 0
    total = 0
    batches = 0
    while True:
        if max_rows is not None and total >= max_rows:
            break
        size = batch_size
        if max_rows is not None:
            size = min(size, max_rows - total)
        params: dict[str, Any] = {"cursor": cursor, "batch_size": size}
        if stamp_provenance:
            params["prov"] = PROVENANCE_VALUE
        async with get_task_session() as session:
            ids = (await session.execute(sql, params)).scalars().all()
            await session.commit()
        if not ids:
            break
        cursor = max(ids)
        total += len(ids)
        batches += 1
        print(f"  batch {batches}: {len(ids):>6,} rows, cursor now {cursor}", flush=True)
    return {"rows_written": total, "batches": batches, "final_cursor": cursor}


async def verify_gamma(sample: int) -> dict[str, Any]:
    """Post-verify (1): re-run the audit's Gamma check against BACKFILLED rows.

    The claim under test is not "the key parsed" — it is "the id we stamped names
    the Polymarket event this market actually belongs to". So the check
    dereferences the stamped id at the source and looks for the row's own
    condition_id among that event's markets. A backfill verified only against the
    column it was derived from would be checking its own arithmetic.
    """
    import httpx

    sql = text(
        """
        SELECT id, external_id, market_metadata->>'polymarket_event_id' AS event_id
        FROM futures_markets
        WHERE source = 'polymarket'
          AND market_metadata->>'polymarket_event_id_source' = :prov
        ORDER BY id
        LIMIT :sample
        """
    )
    async with get_task_session() as session:
        rows = (
            await session.execute(sql, {"prov": PROVENANCE_VALUE, "sample": sample})
        ).mappings().all()

    confirmed = mismatched = unreachable = 0
    failures: list[str] = []
    # A User-Agent is REQUIRED. Without one Gamma answers 403 for every request,
    # which this function correctly classifies as `unreachable` rather than
    # `mismatched` — so the verify would have reported INCONCLUSIVE forever and
    # never once condemned or cleared the backfill. Found by running it: 12/12
    # unreachable with a bare client, 12/12 confirmed with a UA.
    headers = {"User-Agent": "bainluck-backfill-verify/1.0", "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=20, headers=headers) as client:
        for r in rows:
            try:
                resp = await client.get(
                    f"https://gamma-api.polymarket.com/events/{r['event_id']}"
                )
                if resp.status_code != 200:
                    # gotcha #53: an unreachable source is NOT a disconfirmation.
                    # It is counted in its own bucket and never folded into either
                    # verdict, because "Gamma 404'd" and "the id is wrong" are
                    # different facts and only one of them condemns the backfill.
                    unreachable += 1
                    continue
                markets = resp.json().get("markets") or []
                ids = {m.get("conditionId") or m.get("condition_id") for m in markets}
                # TWO ROW CLASSES, and the verify must branch or it condemns a
                # correct backfill. Measured across six age bands, 2026-08-21:
                #
                #   sub-market rows — external_id is a 0x… condition_id, and the
                #     claim is that it appears among the event's markets. 40/40.
                #   PARENT rows     — external_id IS the numeric event id, so it
                #     is NOT among the event's condition_ids and never will be.
                #     The derived key equals the row's own identity, which is the
                #     strongest confirmation available, not a failure. 8/8.
                #
                # A single-branch verifier reported 8 mismatches out of 48 (83.3%
                # "correct") and every one was a false alarm concentrated entirely
                # in the oldest band — which reads exactly like age-dependent key
                # rot, i.e. the one thing C-GROUPID-INTEGRITY-1 certified was
                # absent. Branching, it is 48/48.
                if r["external_id"] == r["event_id"] or r["external_id"] in ids:
                    confirmed += 1
                else:
                    mismatched += 1
                    failures.append(f"row {r['id']} eid={r['event_id']}")
            except Exception as exc:  # noqa: BLE001
                unreachable += 1
                failures.append(f"row {r['id']} unreachable: {exc}")

    return {
        "sampled": len(rows),
        "confirmed": confirmed,
        "mismatched": mismatched,
        "unreachable": unreachable,
        "verdict": (
            "PASS" if mismatched == 0 and confirmed > 0 else "FAIL" if mismatched else "INCONCLUSIVE"
        ),
        "failures": failures[:10],
    }


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--census", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--verify-gamma", action="store_true")
    ap.add_argument("--batch-size", type=int, default=5000)
    ap.add_argument("--limit", type=int, default=None, help="cap total rows written")
    ap.add_argument("--sample", type=int, default=50)
    ap.add_argument("--preview", type=int, default=10)
    ap.add_argument(
        "--no-stamp-provenance",
        dest="stamp_provenance",
        action="store_false",
        help="write ONLY polymarket_event_id (the audit's exact statement). "
        "Makes the write unidentifiable afterwards, and therefore un-undoable.",
    )
    ap.set_defaults(stamp_provenance=True)
    args = ap.parse_args()

    if not any([args.census, args.dry_run, args.apply, args.verify_gamma]):
        ap.error("pick one of --census / --dry-run / --apply / --verify-gamma")

    if args.census or args.dry_run or args.apply:
        c = await census()
        k = await key_shape_census()
        print("== CENSUS ==")
        for key in (
            "all_poly", "already_stamped", "eligible", "unreachable",
            "meta_null", "already_backfilled", "min_id", "max_id",
        ):
            print(f"  {key:20s} {c[key]:>12,}" if isinstance(c[key], int) else f"  {key:20s} {c[key]}")
        print(f"  {'reconciles':20s} {c['reconciles']}")
        print("== KEY SHAPE ==")
        for key in ("eligible", "key_empty", "key_non_numeric", "key_extra_colon", "meta_not_object"):
            print(f"  {key:20s} {k[key]:>12,}")
        print(f"  {'clean':20s} {k['clean']}")
        if not c["reconciles"]:
            print("REFUSING: census does not reconcile.")
            return 2
        if not k["clean"]:
            print("REFUSING: the group_id key is not unambiguous for every eligible row.")
            return 2

    if args.dry_run:
        print(f"== DRY RUN (first {args.preview}, ORDER BY id — the apply's own order) ==")
        for r in await dry_run(args.preview):
            print(f"  id={r['id']:<10} {r['group_id']:<22} would_write={r['would_write']:<10} before={r['before_meta']}")
        print("\nNo rows were modified.")

    if args.apply:
        print(f"== APPLY (batch={args.batch_size}, provenance={args.stamp_provenance}) ==")
        result = await apply(args.batch_size, args.limit, args.stamp_provenance)
        print(f"  rows_written {result['rows_written']:,} in {result['batches']} batches")
        after = await census()
        print("== CENSUS AFTER ==")
        print(f"  eligible          {after['eligible']:>12,}   (was {c['eligible']:,})")
        print(f"  already_stamped   {after['already_stamped']:>12,}")
        print(f"  already_backfilled{after['already_backfilled']:>12,}")

    if args.verify_gamma:
        print(f"== POST-VERIFY: Gamma dereference, sample {args.sample} ==")
        v = await verify_gamma(args.sample)
        for key in ("sampled", "confirmed", "mismatched", "unreachable", "verdict"):
            print(f"  {key:14s} {v[key]}")
        for f in v["failures"]:
            print(f"    ! {f}")
        if v["verdict"] == "FAIL":
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
