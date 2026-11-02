"""#10090 post-release boot check for worker-ws (the venue sockets), read from a log capture.

usage: boot_check.py RELEASE_CREATED_ISO CAPTURE
CAPTURE is a `log_capture.py` file of "worker-ws" lines taken from before the release. Prints, for worker-ws after
the first "Starting process" past the release:
  - both venues started (gc thresholds line per venue) and PM "startup recovery scan complete";
  - crash markers (State changed to crashed, Error R/H codes, nonzero exit) and ERROR lines of a bad class;
  - flush lock errors per venue in [scan+180 s, scan+780 s] = A10; ROLLBACK iff A10 >= 15.
Verdict lines: VERDICT ROLLBACK <why> | VERDICT PENDING <why> | VERDICT PASS."""
import datetime as dt, os, re, sys
TS = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+\+00:00) (\S+): (.*)$")
LOCK = re.compile(r"LockNotAvailable|lock timeout|lock_timeout", re.I)
CRASH = re.compile(r"State changed from \w+ to crashed|Error R1\d|Process exited with status [1-9]")
EXC = re.compile(r'"level": "(ERROR|CRITICAL)"')
BAD = re.compile(r"TypeError|NameError|AttributeError|KeyError|UnboundLocalError|RecursionError|shed_queued|handover shed|game_flush|_FlushTimings|stamp_tx|thread_time|FRESH_STAMP_WORKERS|STAMP_READ_JSON_ONCE|row_number|_read_groups")
t0 = dt.datetime.fromisoformat(sys.argv[1].replace("Z", "+00:00"))
seen, L = set(), []
SRCS = [sys.argv[2]]
for p in SRCS:
    if not os.path.exists(p) or os.path.getmtime(p) < t0.timestamp() - 400: continue
    with open(p, "rb") as f:
        text = f.read().replace(b"\0", b"").decode("utf-8", "replace")
    for raw in text.splitlines():
        m = TS.match(raw)
        if not m or raw in seen: continue
        seen.add(raw); L.append((dt.datetime.fromisoformat(m.group(1)), m.group(2), m.group(3)))
L.sort(key=lambda x: x[0])
if not L: print("VERDICT PENDING no lines"); sys.exit(0)
print("lines", len(L), "first", L[0][0], "last", L[-1][0])
marker = next((x[0] for x in L if x[0] > t0 and x[1].startswith("heroku[worker-ws") and "Starting process with command" in x[2]), None)
if not marker: print("VERDICT PENDING no worker-ws start after release"); sys.exit(0)
post = [x for x in L if x[0] >= marker]
up = next((x[0] for x in post if x[1].startswith("heroku[worker-ws") and "to up" in x[2]), None)
gc = [x for x in post if "gc thresholds" in x[2]]
scan = next((x[0] for x in post if "Polymarket WS: startup recovery scan complete" in x[2]), None)
kal = next((x[0] for x in post if x[1].startswith("app[worker-ws") and "Kalshi WS:" in x[2] and "msgs" in x[2]), None)
pmm = next((x[0] for x in post if x[1].startswith("app[worker-ws") and "Polymarket WS:" in x[2] and "msgs" in x[2]), None)
print("marker", marker, "up", up, "gc-lines", len(gc), "PM scan", scan, "first Kalshi minute", kal, "first PM minute", pmm)
crash = [x for x in post if CRASH.search(x[2])]
bad = [x for x in post if x[1].startswith("app[worker-ws") and EXC.search(x[2]) and BAD.search(x[2])]
errs = [x for x in post if x[1].startswith("app[worker-ws") and EXC.search(x[2])]
print("crash markers", len(crash)); [print("   ", x[0], x[1], x[2][:200]) for x in crash[:5]]
print("ERROR lines", len(errs), "| of which bad-class", len(bad)); [print("   ", x[0], x[2][:220]) for x in bad[:5]]
classes = {}
for x in errs:
    m = re.search(r'"message": "([^"]{0,70})', x[2]); k = m.group(1) if m else x[2][:70]
    classes[k] = classes.get(k, 0) + 1
for k, v in sorted(classes.items(), key=lambda kv: -kv[1])[:8]: print("   class", v, k)
if crash: print("VERDICT ROLLBACK worker-ws crash marker"); sys.exit(0)
if bad: print("VERDICT ROLLBACK new exception class in worker-ws"); sys.exit(0)
if not scan or not kal or not pmm: print("VERDICT PENDING venues not both minute-reporting yet"); sys.exit(0)
w0, w1 = scan + dt.timedelta(seconds=180), scan + dt.timedelta(seconds=780)
def venue(x):
    if not x[1].startswith("app[worker-ws") or not LOCK.search(x[2]): return None
    if "Polymarket WS: flush error" in x[2]: return "polymarket"
    if "Kalshi WS: flush error" in x[2]: return "kalshi"
    return None
hits = [x for x in post if w0 <= x[0] <= w1 and venue(x)]
covered = L[-1][0] >= w1
print("A10 window", w0, "->", w1, "covered", covered, "A10", len(hits), "threshold 15")
if len(hits) >= 15: print("VERDICT ROLLBACK A10 %d >= 15" % len(hits))
elif not covered: print("VERDICT PENDING A10 window not covered yet (so far %d); 3-min health PASS" % len(hits))
else: print("VERDICT PASS A10 %d < 15" % len(hits))
