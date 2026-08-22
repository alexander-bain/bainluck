#!/usr/bin/env python3
"""CAL-P087 — Gate 0's colour under CAL-P086B's ``published_only`` split, read NOW.

Why this exists
---------------
CAL-P086B split ``published_only`` into in-scope / out-of-scope and made an
in-scope miss FORCE ``disagrees``, and said in the same breath that this **can
turn Gate 0 red**. Fable's CAL-P087 directive: find that out before the drain
lands it, not during the attended apply.

So this script runs the SPLIT reconcile — the one on ``program/calibration-84``,
not the one deployed — against the inputs production actually has today, and
prints the colour it produces. It also prints what the PRE-SPLIT rule would have
said over the same inputs, because the whole claim is about a difference between
two rules and a single verdict cannot show one.

What it reads, and nothing else
-------------------------------
* ``GET /api/calibration`` — public, cached, the served payload. The exact object
  the twin worker passes to ``reconcile`` as ``published_buckets`` / ``staged``
  (``calibration_published_twin_worker.py:452``).
* ``GET /api/admin/calibration-twin/last`` — the twin's own last run, for the DB
  side. When that run is a failure, its ``db_cells`` is the empty mapping, and
  that IS the input reconcile would see; substituting anything else here would
  be inventing the measurement the gate is waiting for.

No writes. No fold. Nothing enqueued.

    source ~/.claude/.env
    python3 scripts/gate0_split_pre_read.py --out /tmp/gate0.json
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

from app.utils.calibration_published_twin import (  # noqa: E402
    FOLD_POPULATION_SOURCES,
    reconcile,
    tolerance_pp,
)


def get(path: str, *, auth: bool = False) -> dict:
    api = os.environ.get("BAINLUCK_API")
    token = os.environ.get("ADMIN_TOKEN")
    if not api:
        raise SystemExit("ABORT: source ~/.claude/.env first (BAINLUCK_API).")
    headers = {"Authorization": f"Bearer {token}"} if auth else {}
    req = urllib.request.Request(api.rstrip("/") + path, headers=headers)
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode())


def old_rule_verdict(rec: dict) -> str:
    """The pre-split rule, re-derived from the split reconcile's own output.

    Before CAL-P086B the verdict read ``outside`` alone; ``published_only`` was
    counted into the report and never consulted. So the old colour over these
    same inputs is exactly: unmeasurable if there is no bound, disagrees if
    anything is outside tolerance, agrees otherwise.
    """
    if rec["tolerance_pp"] is None:
        return "unmeasurable"
    return "disagrees" if rec["outside"] else "agrees"


def census(buckets: list[dict]) -> dict:
    """The in-scope / out-of-scope split of the SERVED payload, on its own.

    Independent of any DB side: this is the share of the published curve the
    fold's population can ever reach, and therefore the share the new rule holds
    to account. Cells are keyed ``(source, category)`` and buckets by
    ``bucket_idx`` WITHIN a cell — the same keys ``reconcile`` uses, including
    its collapse of the ``price_moved`` dimension, so the numbers here describe
    the gate's view rather than a tidier one.
    """
    cells_in: set = set()
    cells_out: set = set()
    keys_in: set = set()
    keys_out: set = set()
    n_in = n_out = 0
    small_in = 0
    raw_rows_in = raw_rows_out = 0
    collapsed = 0
    seen: set = set()
    for b in buckets:
        src = str(b.get("source"))
        cat = str(b.get("category"))
        idx = b.get("bucket_idx")
        n = b.get("n") or 0
        if idx is None:
            continue
        key = (src, cat, int(idx))
        in_scope = src in FOLD_POPULATION_SOURCES
        if key in seen:
            collapsed += 1
        seen.add(key)
        if in_scope:
            cells_in.add((src, cat))
            keys_in.add(key)
            n_in += n
            raw_rows_in += 1
            if n <= 2:
                small_in += 1
        else:
            cells_out.add((src, cat))
            keys_out.add(key)
            n_out += n
            raw_rows_out += 1
    return {
        "fold_population_sources": sorted(FOLD_POPULATION_SOURCES),
        "cells_in_scope": len(cells_in),
        "cells_out_of_scope": len(cells_out),
        "cells_total": len(cells_in) + len(cells_out),
        "pct_cells_out_of_scope": round(
            100.0 * len(cells_out) / max(1, len(cells_in) + len(cells_out)), 2
        ),
        "bucket_keys_in_scope": len(keys_in),
        "bucket_keys_out_of_scope": len(keys_out),
        "payload_bucket_rows_in_scope": raw_rows_in,
        "payload_bucket_rows_out_of_scope": raw_rows_out,
        "price_moved_rows_collapsed_by_reconcile": collapsed,
        "outcomes_in_scope": n_in,
        "outcomes_out_of_scope": n_out,
        "in_scope_bucket_keys_with_n_le_2": small_in,
        "sources_out_of_scope": sorted(
            {str(b.get("source")) for b in buckets
             if str(b.get("source")) not in FOLD_POPULATION_SOURCES}
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    payload = get("/api/calibration")
    twin = get("/api/admin/calibration-twin/last", auth=True)

    staged = payload.get("staged")
    buckets = payload.get("buckets") or []
    bound = tolerance_pp(staged)

    failed = twin.get("failed_run") or {}
    db_rows = failed.get("db_rows", twin.get("db_rows"))
    db_cells_n = failed.get("db_cells", twin.get("db_cells"))

    # The DB side production actually has. A failed fold banked no cells, and an
    # empty mapping is what reconcile would be handed — see gotcha #53: the
    # emptier reading is not a fact about the population.
    db_cells: dict = {}

    rec = reconcile(db_cells=db_cells, published_buckets=buckets, staged=staged)

    out = {
        "script": "gate0_split_pre_read.py",
        "queue": "CAL-P087",
        "read_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "payload": {
            "generated_at": payload.get("generated_at"),
            "total_outcomes": payload.get("total_outcomes"),
            "staged": staged,
            "tolerance_pp": bound,
        },
        "twin_last_run": {
            "artifact_generated_at": twin.get("artifact_generated_at"),
            "measured": twin.get("measured"),
            "reason": twin.get("reason"),
            "verdict": failed.get("verdict"),
            "terminal": failed.get("terminal"),
            "fold_duration_s": failed.get("fold_duration_s"),
            "timeout_ms": failed.get("timeout_ms"),
            "db_rows": db_rows,
            "db_cells": db_cells_n,
            "payload_error": failed.get("payload_error"),
        },
        "census_of_served_payload": census(buckets),
        "reconcile_over_todays_inputs": {
            "verdict_new_rule": rec["verdict"],
            "verdict_old_rule": old_rule_verdict(rec),
            "tolerance_pp": rec["tolerance_pp"],
            "compared": rec["compared"],
            "outside": len(rec["outside"]),
            "db_only": len(rec["db_only"]),
            "published_only": len(rec["published_only"]),
            "published_only_in_scope": len(rec["published_only_in_scope"]),
            "published_only_out_of_scope": len(rec["published_only_out_of_scope"]),
            "cells_db": rec["cells_db"],
            "cells_published": rec["cells_published"],
            "scope": rec["scope"],
        },
    }

    print(json.dumps(out, indent=1))
    if args.out:
        with open(args.out, "w") as fh:
            json.dump(out, fh, indent=1)
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
