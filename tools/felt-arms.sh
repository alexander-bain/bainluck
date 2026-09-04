#!/bin/bash
# felt-arms.sh — the three-arm felt run, INTERLEAVED (latency/137).
#
# 🔴 WHY INTERLEAVED RATHER THAN "5 OF A, THEN 5 OF B". The arms differ by one localStorage key and
# nothing else, so any drift in the machine between block A and block B lands entirely on the
# comparison. This laptop's load average moved between 3.8 and 7.9 inside twenty minutes — corporate
# telemetry agents, not this session — which is more than enough to manufacture or erase a 400 ms
# difference. Running A,B,C,A,B,C,... spreads that drift across all three arms instead of confounding
# with them. It does not make a loaded machine clean; it makes the arms comparable ON one.
#
# 🔴 NO FELT_CPU. The rig's CPU multiplier is what turns background contention into the measurement
# (latency/137's queue said so, and the load numbers above are why). Slow-4G at 562 ms RTT is
# network-bound, which is the honest constraint for this comparison anyway.
#
# Every run records the 1-minute load average beside it, so a row taken during a spike can be seen
# rather than averaged in silently.
#
# Usage: tools/felt-arms.sh <surface> [runs-per-arm] [outdir]
set -u
SURFACE="${1:?usage: felt-arms.sh <surface> [runs] [outdir]}"
REPS="${2:-5}"
OUT="${3:-/tmp/felt-arms-137}"
mkdir -p "$OUT"

# arm-name : seed JSON. Arm C is a PARSE-TIME PROXY: the boot script tests only the key prefix, so a
# synthetic value reproduces the suppression faithfully, but Firebase then fails to restore the bogus
# user and the page settles signed-out. It measures what the auth bail-out COSTS, not an authenticated
# feed fetch, and must never be reported as the latter.
ARMS=(
  "A-first:{}"
  "B-returning:{\"bainluck_session_id\":\"sess_felt_b\"}"
  "C-auth:{\"firebase:authUser:felt:[DEFAULT]\":\"{}\"}"
)

for rep in $(seq 1 "$REPS"); do
  for entry in "${ARMS[@]}"; do
    arm="${entry%%:*}"; seed="${entry#*:}"
    load=$(uptime | sed 's/.*averages: //' | awk '{print $1}' | tr -d ',')
    f="$OUT/$SURFACE-$arm-r$rep.json"
    echo "[$(date +%H:%M:%S)] load1=$load  $SURFACE  $arm  rep $rep"
    env FELT_MODE=cold FELT_THROTTLE=slow4g FELT_PACE_MS=0 FELT_ARM="$arm" \
        ${seed:+FELT_SEED_LS="$seed"} \
        node tools/felt-load.mjs "$SURFACE" 1 "$f" >>"$OUT/$SURFACE.log" 2>&1
    rc=$?
    # Stamp the observed load onto the row itself. A number whose contention is not recorded beside it
    # cannot be re-read later by anyone deciding whether to trust it.
    python3 - "$f" "$load" "$rc" <<'PY' 2>/dev/null
import json,sys
p,load,rc=sys.argv[1],float(sys.argv[2]),int(sys.argv[3])
try: d=json.load(open(p))
except Exception: raise SystemExit
for r in d.get("results",[]): r["load1"]=load; r["exit"]=rc
json.dump(d,open(p,"w"))
PY
    sleep 4
  done
done
echo "done -> $OUT"
