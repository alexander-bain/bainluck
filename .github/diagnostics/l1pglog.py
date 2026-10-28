"""#11681 diagnostic-only postgres log reducer. DIAGNOSTIC ONLY, DO NOT MERGE.

Reads `docker logs` of the postgres:15 service (prefix '%m [%p] ') on stdin and
writes a CSV that keeps timing and statement KIND only. SQL text, DETAIL /
STATEMENT / CONTEXT / HINT continuation lines (where parameters would appear)
and anything after the first keyword are dropped.
Columns: ts (server log time = statement END), pid, level, duration_ms, phase
(statement/parse/bind/execute or msg), kind (first SQL keyword or message
class), dnpl (1 if the statement names dnpl_authority).
"""

import csv
import re
import sys

LINE = re.compile(r"^\s*(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3}) UTC \[(\d+)\] (\w+):\s+(.*)$")
DUR = re.compile(r"^duration: ([0-9.]+) ms\s+(statement|parse|bind|execute)(?: [^:]*)?: (.*)$")
DROP = ("DETAIL:", "STATEMENT:", "CONTEXT:", "HINT:", "QUERY:")


def kind(sql):
    head = sql.lstrip().upper()
    if head.startswith("SET LOCAL "):
        return "SET_LOCAL_" + head[10:].split(None, 1)[0].rstrip("=;")[:24]
    word = re.split(r"[\s;(]", head, 1)[0]
    return word[:16] if word.isalpha() else "OTHER"


out = csv.writer(sys.stdout)
out.writerow(["ts", "pid", "level", "duration_ms", "phase", "kind", "dnpl"])
for raw in sys.stdin:
    m = LINE.match(raw)
    if not m:
        continue
    ts, pid, level, msg = m.groups()
    if level in DROP or msg.startswith(DROP) or level in ("DETAIL", "STATEMENT", "CONTEXT", "HINT", "QUERY"):
        continue
    d = DUR.match(msg)
    if d:
        ms, phase, sql = d.groups()
        out.writerow([ts, pid, level, ms, phase, kind(sql), int("dnpl_authority" in sql)])
    else:
        # Message class only: the first five words, never a quoted value.
        words = re.sub(r"\"[^\"]*\"|'[^']*'", "_", msg).split()[:5]
        out.writerow([ts, pid, level, "", "msg", " ".join(words)[:60], 0])
