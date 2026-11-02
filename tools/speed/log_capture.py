"""Tail an app's logs (app + router; no source filter) for N seconds via Platform API log sessions and keep lines
containing ANY of the patterns. Usage: log_capture.py SECS OUT PAT1 [PAT2 ...]; the app is $SPEED_APP (default
bainluck). Token from ~/.netrc, never printed. Reconnects (new tail session) if the stream drops, until SECS elapse."""
import json, netrc, os, sys, time, urllib.request
SECS = float(sys.argv[1]); OUT = sys.argv[2]; PATS = sys.argv[3:]
APP = os.environ.get("SPEED_APP", "bainluck")
tok = netrc.netrc(os.path.expanduser("~/.netrc")).authenticators("api.heroku.com")[2]
end = time.time() + SECS; kept = total = sessions = 0
with open(OUT, "a") as f:
    while time.time() < end:
        sessions += 1
        req = urllib.request.Request("https://api.heroku.com/apps/%s/log-sessions" % APP, method="POST",
            data=json.dumps({"lines": 10, "tail": True}).encode(),
            headers={"Accept": "application/vnd.heroku+json; version=3", "Authorization": "Bearer " + tok, "Content-Type": "application/json"})
        try:
            url = json.loads(urllib.request.urlopen(req, timeout=30).read())["logplex_url"]
            with urllib.request.urlopen(url, timeout=120) as r:
                while time.time() < end:
                    line = r.readline()
                    if not line: break
                    total += 1
                    s = line.decode("utf-8", "replace")
                    if any(p in s for p in PATS):
                        f.write(s); f.flush(); kept += 1
        except Exception as e:
            print("session", sessions, "ended:", type(e).__name__, flush=True); time.sleep(2)
print("sessions", sessions, "lines read", total, "kept", kept)
