"""Stream main `bainluck` logs (Platform API tail sessions, reconnecting) and track the #10090 headline clock:
per minute, both venues' `headline-clock` max_ms; PASS when both < 500; streak of consecutive PASS minutes
(minutes with n=0 on a venue are skipped: no samples). One line per completed minute. Token from ~/.netrc."""
import json, netrc, os, re, sys, time, urllib.request
OUT = sys.argv[1]
tok = netrc.netrc(os.path.expanduser("~/.netrc")).authenticators("api.heroku.com")[2]
cur = {}; streak = 0; best = 0
# Resume the streak from this log's last line when it is recent (a monitor re-arm
# must not reset a streak in progress): minute HH:MM within 3 minutes of now (UTC).
try:
    last = [l for l in open(OUT) if l.strip()][-1]
    m0 = re.match(r"(\d\d):(\d\d) \S+ .*?streak=(\d+)(?: best=(\d+))?", last)
    if m0:
        now = time.gmtime(); mins = now.tm_hour * 60 + now.tm_min
        then = int(m0.group(1)) * 60 + int(m0.group(2))
        if (mins - then) % 1440 <= 3:
            streak = int(m0.group(3)); best = int(m0.group(4) or 0)
            print("resumed streak=%d best=%d from %s" % (streak, best, last[:5]), flush=True)
except Exception:
    pass
# Alex 2026-10-31 11:23 PM PT: "If there's no valid price to show, I won't count that as a
# miss. It's a miss if we have unnecessary delays." A headline input the stamp resolved with
# no reading at all (`...>stamp_no_reading`: neither the receipt nor the stamp could form a
# valid price) is not a miss. The worst list is sorted, so the first other entry is the
# venue's max; when all five listed are no-reading, the 5th bounds the rest from above.
ENTRY = re.compile(r"(\d+):(\d+):([A-Za-z_>:]+(?:\([^)]*\))?(?:\[[^\]]*\])?)")
def effective(row):
    n, mx, worst = row
    entries = [(int(ms), label) for _eid, ms, label in ENTRY.findall(worst)]
    dropped = sum(1 for _ms, label in entries if "stamp_no_reading" in label)
    if not dropped:
        return mx, 0, True
    rest = [ms for ms, label in entries if "stamp_no_reading" not in label]
    if rest:
        return rest[0], dropped, True
    bound = entries[-1][0] if entries else mx
    return bound, dropped, bound < 500 or len(entries) < 5
def done_minute(minute, rows):
    global streak, best
    k, p = rows.get("kalshi"), rows.get("polymarket")
    if not k or not p or k[0] == 0 or p[0] == 0:
        line = "%s SKIP (n=0 or missing) streak=%d" % (minute, streak)
    else:
        (ke, kd, kk), (pe, pd, pk) = effective(k), effective(p)
        ok = kk and pk and ke < 500 and pe < 500
        streak = streak + 1 if ok else 0
        best = max(best, streak)
        nr = (" novalid=K%d/P%d" % (kd, pd)) if (kd or pd) else ""
        line = "%s %s K=%dms P=%dms streak=%d best=%d%s | K %s | P %s" % (
            minute, "PASS" if ok else "FAIL", ke, pe, streak, best, nr, k[2][:160], p[2][:160])
    print(line, flush=True)
    with open(OUT, "a") as f: f.write(line + "\n")
while True:
    try:
        req = urllib.request.Request("https://api.heroku.com/apps/bainluck/log-sessions", method="POST",
            data=json.dumps({"lines": 10, "tail": True, "source": "app", "dyno": "worker-ws.1"}).encode(),
            headers={"Accept": "application/vnd.heroku+json; version=3", "Authorization": "Bearer " + tok, "Content-Type": "application/json"})
        url = json.loads(urllib.request.urlopen(req, timeout=30).read())["logplex_url"]
        with urllib.request.urlopen(url, timeout=150) as r:
            for raw in r:
                s = raw.decode("utf-8", "replace")
                if "headline-clock" not in s: continue
                m = re.search(r"\]: (\{.*\})\s*$", s)
                try: msg = json.loads(m.group(1))["message"] if m else s
                except Exception: msg = s
                v = re.search(r"live_blend_refresh\[(\w+)\]", msg)
                if not v: continue
                minute = s[11:16]
                n = re.search(r"n=(\d+)", msg); mx = re.search(r"max_ms=(\d+)", msg)
                w = re.search(r"worst=(\S+)", msg)
                rows = cur.setdefault(minute, {})
                rows[v.group(1)] = (int(n.group(1)) if n else 0, int(mx.group(1)) if mx else 0, (w.group(1) if w else "-"))
                for old in sorted(cur):
                    if old < minute and len(cur) > 1:
                        done_minute(old, cur.pop(old))
                if len(rows) == 2:
                    done_minute(minute, cur.pop(minute))
    except Exception as e:
        print("stream reconnect: %s" % type(e).__name__, flush=True); time.sleep(3)
