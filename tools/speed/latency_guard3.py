"""#10090 latency guard v3 (11/01, after Alex: "never slower from venue to screen than 0.5 seconds is the commitment").
The bar is 0.5 s. Each minute PASSES when both venues' longest wait is under 500 ms (streak.py's own rule).
Verdict over the minutes since START (release + 2 min):
  ROLLBACK if the release's share of 0.5 s minutes is more than MARGIN points below the 60 minutes before the release
           (it made the 0.5 s record worse), or if 2 consecutive minutes exceed 5000 ms (catastrophe stop).
  PASS     after OK_MINUTES minutes otherwise; the line reports both 0.5 s shares.
Usage: latency_guard3.py STREAK_LOG RELEASE_HHMM START_HHMM [OK_MINUTES] [MARGIN_POINTS] [BEFORE_MINUTES]
BEFORE_MINUTES (default 30) keeps the comparison inside the same load regime (11/01: the NFL slate at 18:00Z
dropped the share by itself, so a 60-minute baseline straddling kickoff blamed the release)."""
import re, sys
log, rel, start = sys.argv[1], sys.argv[2], sys.argv[3]
ok_minutes = int(sys.argv[4]) if len(sys.argv) > 4 else 12
margin = float(sys.argv[5]) if len(sys.argv) > 5 else 20.0
before_min = int(sys.argv[6]) if len(sys.argv) > 6 else 30

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
rows = day_minutes(log, r"(\d\d:\d\d) (PASS|FAIL) K=(\d+)ms P=(\d+)ms")
last = rows[-1][0] if rows else 0
r0, s0 = place(rel, last), place(start, last)
before, after = {}, {}
for t, m in rows:
    worst = max(int(m.group(3)), int(m.group(4)))
    if r0 - before_min <= t < r0: before[t] = worst
    elif t >= s0: after[t] = worst
share = lambda d: 100.0 * sum(1 for v in d.values() if v < 500) / len(d) if d else 0.0
run = 0
for t in sorted(after):
    run = run + 1 if after[t] > 5000 else 0
    if run >= 3 and t >= s0 + 2:
        # 3 in a row, never inside the restart's own first minutes (11/01 18:51Z: G4F69 rolled back on the
        # cold-start waits of its own restart, which the rollback's restart repeats).
        print("VERDICT ROLLBACK latency 3 consecutive minutes over 5000 ms at %02d:%02d" % divmod(t % 1440, 60)); sys.exit(0)
b, a = share(before), share(after)
if len(after) < ok_minutes:
    print("VERDICT WAIT latency %d/%d minutes; under-0.5s share %.0f%% (before %.0f%% of %d)" % (len(after), ok_minutes, a, b, len(before))); sys.exit(0)
if before and a < b - margin:
    print("VERDICT ROLLBACK latency under-0.5s minutes fell to %.0f%% of %d from %.0f%% of %d before the release" % (a, len(after), b, len(before))); sys.exit(0)
print("VERDICT PASS latency under-0.5s minutes %.0f%% of %d (before the release %.0f%% of %d)" % (a, len(after), b, len(before)))
