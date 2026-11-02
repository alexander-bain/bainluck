# tools/speed — the #10090 delivery checks

The instrument for "a visible number moves within a second of the venue's" is the event page's EKG and its exact-times
panel. These scripts are the release-time checks around it, run from a laptop until the health-check Action replaces
them. Every credentialed call reads `~/.netrc` (Heroku) or `~/.claude/.env` (admin API); nothing here holds a secret.

| Script | What it does |
| --- | --- |
| `streak.py LOG` | The 0.5 s meter. Tails the app's logs and writes one line per minute to `LOG`: each venue's longest venue→screen wait from the `headline-clock` line, PASS when both are under 500 ms, and the streak. Run it in the background (not as a Monitor: it would die at the monitor's 30-minute limit). |
| `watch_release.sh LOG [APP]` | Start before a deploy or a config change. Records the live release as the rollback target, captures worker-ws logs, waits for the next release, then runs the boot check and both latency guards on the meter's `LOG`. Rolls back (or, with `REVERT_CONFIG`, restores settings) on a failure. |
| `boot_check.py ISO CAPTURE` | Crash markers, bad exception classes and flush-lock errors after a worker-ws restart. |
| `latency_guard2.py` / `latency_guard3.py` | Two consecutive minutes over 5 s; the release's share of 0.5 s minutes against the 30 minutes before it. |
| `log_capture.py SECS OUT PAT…` | Platform API log sessions, reconnecting, keeping lines that match. `SPEED_APP` picks the app. |
| `heroku_api.py METHOD PATH [BODY]` | One Platform API call; config-vars responses are redacted to the non-secret settings. |
| `switch.sh` | Start, end or read a runtime speed-switch trial (per game or alternating; the server caps each at 30 min). |
| `py311_fstring_check.py FILE…` | Refuses f-strings that only Python 3.12 parses (the dynos run 3.11). |

Typical deploy watch:

```sh
python3 -u tools/speed/streak.py /tmp/streak.log &      # if the meter is not already running
tools/speed/watch_release.sh /tmp/streak.log            # then merge the PR; the watch picks up the release
```
