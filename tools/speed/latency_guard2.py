"""#10090 latency guard (11/01 variant): as latency_guard.py, but each venue's minute value is the
longest listed wait NOT labeled na_orientation (the pre-existing class G4F61 fixes; it must not roll
back an unrelated change). When all listed entries are na_orientation, the last listed bounds the rest.
Usage: latency_guard2.py STREAK_LOG START_HHMM [LIMIT_MS] [OK_MINUTES]"""
import re, sys
log, start = sys.argv[1], sys.argv[2]
limit = int(sys.argv[3]) if len(sys.argv) > 3 else 3000
ok_minutes = int(sys.argv[4]) if len(sys.argv) > 4 else 6
ENTRY = re.compile(r"(\d+):(\d+):([A-Za-z_>:]+(?:\([^)]*\))?(?:\[[^\]]*\])?)")
def venue_max(raw, fallback):
    entries = [(int(ms), label) for _e, ms, label in ENTRY.findall(raw)]
    rest = [ms for ms, label in entries if "na_orientation" not in label]
    if rest: return rest[0]
    return entries[-1][0] if entries else fallback

def day_minutes(log, pattern):
    """(absolute minute, match) for the log's rows, in file order, across UTC midnight: the log only
    carries HH:MM, so a minute far below the previous one is the next day (11/02 00:00Z: a guard keyed on
    HH:MM read 01:57 from that morning as after a 00:01 release and called a rollback)."""
    out, offset, prev = [], 0, None
    with open(log) as f:
        lines = f.readlines()
    for line in lines:
        m = re.match(pattern, line)
        if not m: continue
        h, mm = m.group(1).split(":"); t = int(h) * 60 + int(mm)
        if prev is not None and t < prev - 720: offset += 1440
        prev = t
        out.append((t + offset, m))
    return out

def place(hhmm, last):
    """HH:MM as the absolute minute nearest at or before `last` + 10."""
    h, mm = hhmm.split(":"); t = int(h) * 60 + int(mm)
    t += (last + 10 - t) // 1440 * 1440
    return t
lines = day_minutes(log, r"(\d\d:\d\d) (PASS|FAIL) K=(\d+)ms P=(\d+)ms.*?\| K (.*?) \| P (.*)$")
s0 = place(start, lines[-1][0]) if lines else 0
rows = {}
for t, m in lines:
    if t >= s0:
        rows[t] = (m.group(1), venue_max(m.group(5), int(m.group(3))), venue_max(m.group(6), int(m.group(4))))
bad_run = 0; seen = 0
for t in sorted(rows):
    minute, k, p = rows[t]; seen += 1
    bad_run = bad_run + 1 if max(k, p) > limit else 0
    if bad_run >= 2:
        print("VERDICT ROLLBACK latency %s K=%d P=%d (2 consecutive minutes over %d ms, na_orientation excluded)" % (minute, k, p, limit)); sys.exit(0)
print(("VERDICT PASS latency %d minutes, none 2x over %d ms" % (seen, limit)) if seen >= ok_minutes else "VERDICT WAIT latency %d/%d minutes" % (seen, ok_minutes))
