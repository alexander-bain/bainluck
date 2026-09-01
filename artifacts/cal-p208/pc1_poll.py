#!/usr/bin/env python3
"""PC-1 poller for CAL-P208 — CERT-697's first post-deploy beat.

Samples both bank-bearing rows (ITEM 1b) once a minute and appends one JSON
object per sample to ``pc1-observations.jsonl``. Reads only; writes nothing to
production.

Two things are being watched, and they become visible at DIFFERENT times:

* the cursor's ``input_fingerprint`` re-stamp — written by ``save_staged_cursor``
  on the FIRST banked unit, so ~2-6 min into the beat;
* ``staged:cursor_reason:*`` — a ledger key, and the ledger is a BEAT-END row
  (``P203-1``), so ~18 min into the beat.

A sample is never skipped on error: a failed read is recorded as such, because a
gap that looks like "nothing happened" is exactly the ambiguity gotcha #53 warns
about.
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = os.environ["BAINLUCK_API"].rstrip("/")
TOK = os.environ["ADMIN_TOKEN"]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pc1-observations.jsonl")

WIDE = "e2040f90154fae876f0fb65f5abf74c3"
NARROW = "78143607db6fd8116af5fadeffef6799"
BASELINE_BANK = 70

SQL = """
SELECT s.identity,
       s.updated_at,
       s.payload->>'generation'        AS generation,
       s.payload->>'owner'             AS owner,
       s.payload->>'input_fingerprint' AS stamped_fp,
       s.payload->>'terminal'          AS terminal,
       jsonb_array_length(COALESCE(s.payload->'committed_units','[]'::jsonb)) AS bank_now,
       jsonb_array_length(COALESCE(s.payload->'served_units','[]'::jsonb))    AS served_units,
       (SELECT jsonb_object_agg(k, v)
          FROM jsonb_each_text(COALESCE(s.payload->'stages','{}'::jsonb)) AS e(k, v)
         WHERE k LIKE 'staged:cursor%' OR k IN (
               'staged:units_banked','staged:units_this_beat',
               'staged:units_completed_this_beat','staged:units_cancelled',
               'staged:served_units','staged:served_at','staged:beats_to_publish'))
         AS gauges,
       now() AS read_at
  FROM durable_state_snapshots s
 WHERE s.identity IN ('calibration:main:staged_futures','calibration:main:phase_ledger')
"""


def query():
    body = json.dumps({"sql": SQL, "limit": 10}).encode()
    req = urllib.request.Request(
        f"{API}/api/admin/db-query", data=body,
        headers={"Authorization": f"Bearer {TOK}", "Content-Type": "application/json"},
    )
    try:
        raw = urllib.request.urlopen(req, timeout=35).read().decode()
    except Exception as exc:  # noqa: BLE001 — a failed sample is still a sample
        return {"error": repr(exc)}
    try:
        d = json.loads(raw)
    except Exception:  # noqa: BLE001
        return {"error": "unparseable", "raw": raw[:400]}
    if "rows" not in d:
        return {"error": "refused", "raw": raw[:400]}
    cols = d["columns"]
    out = {}
    for row in d["rows"]:
        r = dict(zip(cols, row))
        out["cursor" if r["identity"].endswith("staged_futures") else "ledger"] = r
    return out


def verdict(sample):
    """The three pre-registered arms, evaluated on every sample."""
    if "error" in sample:
        return {"arm1_token": "READ-FAILED", "arm2_bank": "READ-FAILED",
                "arm3_restamp": "READ-FAILED"}
    cur = sample.get("cursor") or {}
    led = sample.get("ledger") or {}
    # gotcha #40: admin db-query serialises JSONB as a PYTHON REPR, so
    # jsonb_object_agg arrives as a str, not a dict. Iterating it without this
    # walks the string's characters and silently reports zero tokens.
    gauges = led.get("gauges") or {}
    if isinstance(gauges, str):
        import ast
        try:
            gauges = ast.literal_eval(gauges)
        except Exception:  # noqa: BLE001
            gauges = {"<unparseable>": gauges[:200]}
    tokens = sorted(k.rsplit(":", 1)[-1] for k in gauges if k.startswith("staged:cursor_reason:"))
    bank = cur.get("bank_now")
    fp = cur.get("stamped_fp")
    return {
        "arm1_token": tokens or ["<none>"],
        "arm2_bank": bank,
        "arm2_pass": (bank is not None and bank >= BASELINE_BANK),
        "arm2_wiped": bank == 0,
        "arm3_restamp": ("NARROW (re-stamped)" if fp == NARROW
                         else "WIDE (not yet)" if fp == WIDE else f"other:{fp}"),
    }


def main():
    deadline = time.time() + float(sys.argv[1] if len(sys.argv) > 1 else 3600)
    n = 0
    while time.time() < deadline:
        n += 1
        s = query()
        rec = {"n": n, "wall_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
               "sample": s, "verdict": verdict(s)}
        with open(OUT, "a") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
        v = rec["verdict"]
        print(f"[{rec['wall_utc']}] #{n} bank={v['arm2_bank']} "
              f"token={v['arm1_token']} fp={v['arm3_restamp']}", flush=True)
        time.sleep(60)


if __name__ == "__main__":
    main()
