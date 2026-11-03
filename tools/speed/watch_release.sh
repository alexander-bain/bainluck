#!/bin/bash
# #10090 — watch the NEXT release of an app and roll it back automatically if it misbehaves.
#
# usage: tools/speed/watch_release.sh STREAK_LOG [APP]        (APP defaults to bainluck)
#
# Start it BEFORE the deploy (a merge to master, a config change): it records the release live now as the rollback
# target, starts a worker-ws log capture, waits up to 45 min for a newer succeeded release, then judges it:
#   1. boot check (boot_check.py on the capture): crash markers, a bad exception class, or A10 flush-lock errors
#      >= 15 in [scan+3 min, scan+13 min] -> ROLLBACK;
#   2. latency guards on the 0.5 s meter's log (streak.py writes STREAK_LOG): two consecutive minutes over 5 s
#      counting only waits that started after the release (#11908),
#      or the release's share of 0.5 s minutes more than 20 points below the 30 minutes before it -> ROLLBACK.
# PASS needs both. A rollback POSTs the recorded release id back. Every line goes to stdout; the run directory
# (printed first) keeps the capture and each check's output. Exit 0 PASS, 3 rolled back, 2 no verdict in time.
#
# A config trial: REVERT_CONFIG='{"NAME": null, "OTHER": "old"}' tools/speed/watch_release.sh LOG, then set the
# trial value. On a failing check the watch PATCHes REVERT_CONFIG back instead of rolling back the release.
# Runtime switch trials (per game / alternating) need no watch for their limit: the server caps each at 30 min
# (`app/tasks/speed_switches.py`); start and end them with tools/speed/switch.sh.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
STREAK="${1:?usage: watch_release.sh STREAK_LOG [APP]}"; APP="${2:-bainluck}"
RUN="$(mktemp -d /tmp/speed-watch-XXXXXX)"; cd "$RUN" || exit 1
say() { echo "$(date -u +%FT%TZ) $*"; }
releases() {
  python3 "$HERE/heroku_api.py" GET "/apps/$APP/releases" '' '{"Range":"version ..; order=desc, max=5"}' |
    tail -n +2 > releases.json
}
say "run dir $RUN"
releases
read -r V0 ID0 < <(python3 -c "
import json; r=[x for x in json.load(open('releases.json')) if x['status']=='succeeded'][0]; print(r['version'], r['id'])")
[ -n "${ID0:-}" ] || { say "no succeeded release to roll back to"; exit 1; }
say "$APP live now v$V0 = rollback target $ID0"
export SPEED_APP="$APP"
(python3 -W ignore "$HERE/log_capture.py" 3600 capture-worker-ws.txt "worker-ws" > capture.out 2>&1 &)

WAIT_END=$(( $(date +%s) + 2700 ))
while :; do
  releases
  read -r V1 REL < <(python3 -c "
import json; r=[x for x in json.load(open('releases.json')) if x['status']=='succeeded' and x['version']>$V0]
print(r[-1]['version'], r[-1]['created_at']) if r else print('', '')")
  [ -n "${V1:-}" ] && break
  [ "$(date +%s)" -ge "$WAIT_END" ] && { say "no new release within 45 min"; exit 2; }
  sleep 20
done
REL="${REL%Z}"; REL="${REL%%.*}Z"
LABEL="$APP v$V1"; DEADLINE=$(( $(date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$REL" +%s) + 1500 ))
START=$(date -u -j -v+2M -f "%Y-%m-%dT%H:%M:%SZ" "$REL" +%H:%M)
say "$LABEL released $REL; boot check now, latency guard from $START"
rollback() {
  if [ -n "${REVERT_CONFIG:-}" ]; then
    python3 "$HERE/heroku_api.py" PATCH "/apps/$APP/config-vars" "$REVERT_CONFIG" > rollback.txt 2>&1
    say "$LABEL $1 -> REVERTED config $REVERT_CONFIG (http $(head -1 rollback.txt))"; exit 3
  fi
  python3 "$HERE/heroku_api.py" POST "/apps/$APP/releases" "{\"release\":\"$ID0\"}" > rollback.txt 2>&1
  say "$LABEL $1 -> ROLLBACK to v$V0 (http $(head -1 rollback.txt))"; exit 3
}
BOOT=""
while :; do
  if [ -z "$BOOT" ]; then
    python3 "$HERE/boot_check.py" "$REL" capture-worker-ws.txt > boot.txt 2>&1; V=$(grep '^VERDICT' boot.txt | tail -1)
    case "$V" in "VERDICT PASS"*) BOOT=ok; say "$LABEL boot $V";; "VERDICT ROLLBACK"*) rollback "boot $V";; esac
  fi
  L=$(python3 "$HERE/latency_guard2.py" "$STREAK" "$START" 5000 10 "${REL:11:5}" 2>&1 | tail -1)
  H=$(python3 "$HERE/latency_guard3.py" "$STREAK" "${REL:11:5}" "$START" 12 20 30 2>&1 | tail -1)
  case "$H" in "VERDICT ROLLBACK"*) rollback "$H";; "VERDICT PASS"*) case "$L" in "VERDICT PASS"*) L="$L; $H";; esac;;
    *) case "$L" in "VERDICT PASS"*) L="VERDICT WAIT ($H)";; esac;; esac
  case "$L" in "VERDICT ROLLBACK"*) rollback "$L";; "VERDICT PASS"*) [ -n "$BOOT" ] && { say "$LABEL $L"; exit 0; };; esac
  [ "$(date -u +%s)" -ge "$DEADLINE" ] && { say "$LABEL no verdict by +25 min (boot=$BOOT; $L)"; exit 2; }
  sleep 30
done
