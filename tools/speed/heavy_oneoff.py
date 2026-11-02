"""Run one detached command on an app and keep its output. Token from ~/.netrc, never printed.

usage: heavy_oneoff.py APP OUT "COMMAND" [MAX_SECONDS]

Creates a detached one-off dyno, opens a tail log session for that dyno at once (a session opened after the dyno
exits returns nothing), writes every line to OUT, and stops when the dyno reports its exit or MAX_SECONDS (600)
pass. Prints the dyno name and the exit line.
"""
import json
import netrc
import os
import sys
import time
import urllib.request

APP, OUT, COMMAND = sys.argv[1], sys.argv[2], sys.argv[3]
MAX_S = float(sys.argv[4]) if len(sys.argv) > 4 else 600
TOKEN = netrc.netrc(os.path.expanduser("~/.netrc")).authenticators("api.heroku.com")[2]
HEADERS = {"Accept": "application/vnd.heroku+json; version=3", "Authorization": "Bearer " + TOKEN,
           "Content-Type": "application/json"}


def post(path, body):
    req = urllib.request.Request("https://api.heroku.com" + path, data=json.dumps(body).encode(), method="POST",
                                 headers=HEADERS)
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


dyno = post(f"/apps/{APP}/dynos", {"command": COMMAND, "attach": False, "type": "run"})
name = dyno["name"]
print("dyno", name, flush=True)
end = time.time() + MAX_S
exit_line = None
with open(OUT, "a") as f:
    while time.time() < end and exit_line is None:
        try:
            url = post(f"/apps/{APP}/log-sessions", {"dyno": name, "tail": True, "lines": 1500})["logplex_url"]
            with urllib.request.urlopen(url, timeout=120) as r:
                for raw in r:
                    line = raw.decode("utf-8", "replace")
                    f.write(line)
                    f.flush()
                    if "Process exited with status" in line or "State changed from up to complete" in line:
                        exit_line = line.strip()
                        break
                    if time.time() > end:
                        break
        except Exception as e:  # noqa: BLE001 — reconnect until the deadline
            print("log session ended:", type(e).__name__, flush=True)
            time.sleep(2)
print("exit", exit_line, flush=True)
