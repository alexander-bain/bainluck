#!/usr/bin/env python3
"""latency/180 — one `pg_stat_statements` snapshot, keyed by queryid.

WHY A SNAPSHOT AND NOT A READ. `pg_stat_statements` is cumulative since
`stats_reset`, which here is 5 days 11 hours ago. Every deploy in that window is
inside the number, so a ranking by `total_exec_time` ranks HISTORY, not the
present. It told me that

    UPDATE futures_markets SET volume_24h=... WHERE external_id = $3

had burned 43,201 s of database time at 278 ms and 15,084 buffers a call — the
unmistakable signature of 179's missing leading column — and that statement had
already been FIXED by 179 about an hour before I read it. The row was true and
the conclusion it invited was wrong.

This is the third time today the same trap has appeared in a different costume:
`starts_24h` over an unread `starts_window_s`, `recent_durations_ms` straddling
a deploy, and now this. A cumulative counter is not a rate until it is
differenced against its own window.

Differencing two snapshots gives calls/hour and seconds/hour AS OF NOW, and a
statement whose delta is zero is dead however large its total.
"""
import json
import os
import sys
import time
import urllib.request

SQL = (
    "SELECT queryid, calls, total_exec_time, shared_blks_hit, shared_blks_read, "
    "left(query,300) AS q FROM pg_stat_statements "
    "WHERE queryid IS NOT NULL ORDER BY total_exec_time DESC"
)


def snap():
    req = urllib.request.Request(
        os.environ["BAINLUCK_API"] + "/api/admin/db-query",
        data=json.dumps({"sql": SQL, "limit": 200}).encode(),
        headers={"Authorization": "Bearer " + os.environ["ADMIN_TOKEN"],
                 "Content-Type": "application/json"})
    d = json.loads(urllib.request.urlopen(req, timeout=45).read())
    if not d.get("rows"):
        raise SystemExit(f"read failed: {json.dumps(d)[:400]}")
    return {"at": time.time(),
            "rows": {str(r[0]): {"calls": r[1], "ms": float(r[2]),
                                 "hit": r[3], "read": r[4], "q": r[5]}
                     for r in d["rows"]}}


if __name__ == "__main__":
    with open(sys.argv[1], "w") as fh:
        json.dump(snap(), fh)
    print(f"wrote {sys.argv[1]}")
