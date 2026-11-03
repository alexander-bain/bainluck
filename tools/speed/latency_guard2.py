"""#10090 latency guard (11/01 variant): as latency_guard.py, but each venue's minute value is the
longest listed wait NOT labeled na_orientation (the pre-existing class G4F61 fixes; it must not roll
back an unrelated change). When every listed entry is excluded, the last listed bounds the rest.

#11908: only slow waits that start after the release count. A slow wait (over LIMIT_MS) is excluded
when it started before the release (its minute's end less its length), or when its event already had a
slow wait in the 30 minutes before the release: that event's slowness predates the change. On Nov 3 a
tennis match slow on `na_proof` since 6:52 AM PT rolled back a 7:13 release.

Usage: latency_guard2.py STREAK_LOG START_HHMM [LIMIT_MS] [OK_MINUTES] [RELEASE_HHMM]
(RELEASE_HHMM defaults to START_HHMM less 2 minutes, the watch's own offset.)"""
import re, sys
log, start = sys.argv[1], sys.argv[2]
limit = int(sys.argv[3]) if len(sys.argv) > 3 else 3000
ok_minutes = int(sys.argv[4]) if len(sys.argv) > 4 else 6
ENTRY = re.compile(r"(\d+):(\d+):([A-Za-z_>:]+(?:\([^)]*\))?(?:\[[^\]]*\])?)")
BEFORE_MIN = 30


def entries_of(raw):
    return [(event, int(ms), label) for event, ms, label in ENTRY.findall(raw)]


def venue_max(raw, fallback, excluded=lambda event, ms: False):
    entries = entries_of(raw)
    rest = [ms for event, ms, label in entries
            if "na_orientation" not in label and not excluded(event, ms)]
    if rest: return rest[0]
    return entries[-1][1] if entries else fallback

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
r0 = place(sys.argv[5], lines[-1][0]) if len(sys.argv) > 5 and lines else s0 - 2
# (venue, event) pairs already slow in the 30 minutes before the release.
pre_slow = set()
for t, m in lines:
    if r0 - BEFORE_MIN <= t < r0:
        for venue, raw in (("K", m.group(5)), ("P", m.group(6))):
            pre_slow |= {(venue, event) for event, ms, _ in entries_of(raw) if ms > limit}


def excluded_for(venue, t):
    # A wait listed in minute t ended by the minute's close; it began before the release when its
    # length reaches back past it.
    return lambda event, ms: ms > limit and (
        (venue, event) in pre_slow or (t + 1) * 60_000 - ms < r0 * 60_000)


rows = {}
for t, m in lines:
    if t >= s0:
        rows[t] = (m.group(1), venue_max(m.group(5), int(m.group(3)), excluded_for("K", t)),
                   venue_max(m.group(6), int(m.group(4)), excluded_for("P", t)))
bad_run = 0; seen = 0
for t in sorted(rows):
    minute, k, p = rows[t]; seen += 1
    bad_run = bad_run + 1 if max(k, p) > limit else 0
    if bad_run >= 2:
        print("VERDICT ROLLBACK latency %s K=%d P=%d (2 consecutive minutes over %d ms, na_orientation and pre-release waits excluded)" % (minute, k, p, limit)); sys.exit(0)
print(("VERDICT PASS latency %d minutes, none 2x over %d ms" % (seen, limit)) if seen >= ok_minutes else "VERDICT WAIT latency %d/%d minutes" % (seen, ok_minutes))
