#!/usr/bin/env python3
"""CAL-996 — photograph one calibration beat off production, in one shot.

The owed receipt (CERT-829) needs a DEFERRED beat off `8f927170` and, ideally, a
deferred beat the publish gate REFUSED. Three of the four instruments are
destroyed or moved by the next beat, so they are read together, stamped, and
written to disk rather than eyeballed:

  * `calibration:main:phase_ledger` — ONE row, overwritten every beat. It is the
    only place `staged:rebuild_*` lives: the sampler's `select_gauges` captures
    `REQUIRED_DISCLOSURE_GAUGES + OPERATIONAL_GAUGES` plus two prefixes, and no
    rebuild gauge is in any of them. Read inside its own hour or it is gone.
  * `calibration:main:staged_futures` — the cursor: served vs building bank.
    `served_covers and not covers` IS the deferral predicate.
  * the beat-gauge ring, `?full=true` — the sampler stores `outcome` verbatim
    (`"outcome": payload.get("outcome")`), so `outcome.deferred_rebuild` reaches
    it; the default form strips outcome entirely.
  * `/api/calibration` `generated_at` — did the published curve actually move.

Usage: `python3 capture.py <label>` -> `beat-<label>.json` beside this file.
"""
from __future__ import annotations

import ast
import datetime
import json
import os
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

LEDGER_SQL = (
    "SELECT identity, updated_at, payload->>'terminal', "
    "payload->>'generation', payload->'outcome', payload->'stages', "
    "payload->>'input_fingerprint', payload->>'elapsed_ms' "
    "FROM durable_state_snapshots "
    "WHERE identity IN ('calibration:main:phase_ledger', "
    "'calibration:main:staged_futures', 'calibration:main:checkpoint') "
    "ORDER BY identity"
)


def _env() -> tuple[str, str]:
    """`(api, token)` out of the untracked env file — never a tracked literal."""
    out = subprocess.run(
        ["bash", "-lc", 'source ~/.claude/.env && echo "$BAINLUCK_API" && echo "$ADMIN_TOKEN"'],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    return out[0], out[1]


def _get(url: str, token: str | None = None):
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def _jsonb(value):
    """Gotcha #40 — `db-query` serializes JSONB as a PYTHON REPR, not as JSON.

    `{'a': 1}` with single quotes and bare `None`/`True` comes back as a string,
    so `json.loads` raises on the first key. Try JSON, then `literal_eval`, and
    hand back the raw string only if both refuse — a silently-dropped payload is
    exactly the blind spot this capture exists to close.
    """
    if not isinstance(value, str):
        return value
    for parse in (json.loads, ast.literal_eval):
        try:
            return parse(value)
        except (ValueError, SyntaxError):
            continue
    return value


def _post(url: str, token: str, body: dict):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def main() -> int:
    label = sys.argv[1] if len(sys.argv) > 1 else "adhoc"
    api, token = _env()
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    shot: dict = {"captured_at": stamp, "label": label}
    shot["health"] = _get(f"{api}/api/health")

    rows = _post(f"{api}/api/admin/db-query", token, {"sql": LEDGER_SQL, "limit": 10})["rows"]
    snaps = {}
    for identity, updated, terminal, generation, outcome, stages, fp, elapsed in rows:
        snaps[identity] = {
            "updated_at": updated, "terminal": terminal, "generation": generation,
            "outcome": _jsonb(outcome), "stages": _jsonb(stages), "input_fingerprint": fp,
            "elapsed_ms": elapsed,
        }
    shot["snapshots"] = snaps

    ring = _get(f"{api}/api/admin/calibration-beat-gauges?full=true", token)
    obs = ring.get("observations") or []
    # The whole ring is ~220 KB and 167 of its rows never change; keep the tail.
    shot["ring_tail"] = obs[-6:]
    shot["ring_len"] = len(obs)

    cal = _get(f"{api}/api/calibration")
    shot["calibration"] = {
        k: cal.get(k) for k in ("generated_at", "total_outcomes", "population_version",
                                "stale", "available", "as_of", "generation")
    }

    path = os.path.join(HERE, f"beat-{label}.json")
    with open(path, "w") as fh:
        json.dump(shot, fh, indent=1, sort_keys=True, default=str)

    # -- the one-screen read ------------------------------------------------
    pl = snaps.get("calibration:main:phase_ledger", {})
    stages = pl.get("stages") or {}
    sf = (snaps.get("calibration:main:staged_futures") or {}).get("stages")
    rebuild = {k: v for k, v in stages.items() if "rebuild" in k}
    print(f"captured_at        {stamp}")
    print(f"health.commit      {shot['health'].get('commit')}")
    print(f"ledger.updated_at  {pl.get('updated_at')}   terminal={pl.get('terminal')}")
    print(f"ledger.outcome     {json.dumps(pl.get('outcome'), default=str)[:600]}")
    print(f"rebuild gauges     {json.dumps(rebuild, sort_keys=True) or '{}'}")
    for k in ("staged:rebuild_deferred", "staged:units_banked", "staged:units_partition",
              "staged:served_units", "staged:units_this_beat",
              "staged:units_completed_this_beat", "staged:cursor_resume"):
        if k in stages:
            print(f"  {k:42} {stages[k]}")
    print(f"cal.generated_at   {shot['calibration'].get('generated_at')}"
          f"  outcomes={shot['calibration'].get('total_outcomes')}")
    tail = shot["ring_tail"][-1] if shot["ring_tail"] else {}
    toc = (tail.get("outcome") or {})
    print(f"ring newest        {tail.get('generated_at')} terminal={tail.get('terminal')} "
          f"gate={toc.get('gate')} published={toc.get('published')} "
          f"deferred_rebuild={toc.get('deferred_rebuild')}")
    print(f"written            {path}")
    if sf is not None:
        print(f"staged_futures.stages present ({len(sf) if hasattr(sf, '__len__') else '?'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
