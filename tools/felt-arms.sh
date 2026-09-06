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
# 🔴 A DEAD ARM MUST NOT EXIT 0 (CERT-1964 follow-up, LAT-P238-PROPAGATE-ARM-FAILURES). This script
# used to capture each child's `rc`, stamp it into the JSON, and then throw it away: the last command
# was always `echo done`, so the wrapper exited 0 whatever happened. Measured before the fix — with
# every one of three arms exiting 3 and NOT ONE output file written, the run still printed its normal
# per-arm progress lines, printed `done -> …`, and exited 0. A healthy run and a total wipe-out were
# byte-identical to an operator and indistinguishable to any caller. So now every arm-run must end
# holding a measurement someone can actually use, and the wrapper exits 1 naming the ones that did not.
#
# 🔴 STILL NO `set -e`, DELIBERATELY. A failing arm must not abort the loop: these arms are
# INTERLEAVED (see above), so bailing halfway would leave the surviving arms unbalanced across the
# machine drift the interleave exists to spread — turning one dead arm into a silently biased
# comparison. We run the whole grid, then fail loudly at the end with the full list.
#
# Usage: tools/felt-arms.sh <surface> [runs-per-arm] [outdir]
set -u
SURFACE="${1:?usage: felt-arms.sh <surface> [runs] [outdir]}"
REPS="${2:-5}"
OUT="${3:-/tmp/felt-arms-137}"
mkdir -p "$OUT"

# Seconds to settle between arms. 4 for a real run — back-to-back cold loads against production are
# how the cold battery ends up measuring its own 429. Overridable ONLY so the regression test can
# drive the whole grid at 0; never set it to 0 for a measurement you intend to keep.
SLEEP_S="${FELT_SLEEP_S:-4}"

# arm-name : seed JSON. Arm C is a PARSE-TIME PROXY: the boot script tests only the key prefix, so a
# synthetic value reproduces the suppression faithfully, but Firebase then fails to restore the bogus
# user and the page settles signed-out. It measures what the auth bail-out COSTS, not an authenticated
# feed fetch, and must never be reported as the latter.
ARMS=(
  "A-first:{}"
  "B-returning:{\"bainluck_session_id\":\"sess_felt_b\"}"
  "C-auth:{\"firebase:authUser:felt:[DEFAULT]\":\"{}\"}"
)

# One human-readable line per arm-run that produced no usable measurement. Emptiness IS the pass.
FAILURES=()
TOTAL=0

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
    TOTAL=$((TOTAL + 1))
    # Stamp the observed load onto the row itself. A number whose contention is not recorded beside it
    # cannot be re-read later by anyone deciding whether to trust it.
    #
    # The same pass also RULES on the arm. Its exit code is the verdict (no stderr swallow any more —
    # hiding the validator's own crash is the bug this whole change is about):
    #   0 usable · 10 no valid run · 11 all self-throttled · 12 no file · 13 unreadable/unwritable
    python3 - "$f" "$load" "$rc" <<'PY'
import json,sys
p,load,rc=sys.argv[1],float(sys.argv[2]),int(sys.argv[3])
try: d=json.load(open(p))
except FileNotFoundError: raise SystemExit(12)
except Exception: raise SystemExit(13)
rows=d.get("results",[])
for r in rows: r["load1"]=load; r["exit"]=rc
try: json.dump(d,open(p,"w"))
except Exception: raise SystemExit(13)
# 🔴 The SAME predicate felt-load.mjs uses to build its own medians (felt-load.mjs:549):
# a row counts only if a real card rendered, its seed applied, and it was not self-throttled.
# Deliberately not a second opinion — a wrapper that disagreed with the module about what
# "valid" means would pass runs the table then silently drops, which is the defect wearing a hat.
if [r for r in rows if r.get("valid") and not r.get("throttled")]: raise SystemExit(0)
if rows and all(r.get("throttled") for r in rows): raise SystemExit(11)
raise SystemExit(10)
PY
    vrc=$?
    # The child's own exit code is the ROOT CAUSE and outranks the file verdict: a crashed arm that
    # also wrote no file is one failure to report, not two, and "it crashed" is the actionable half.
    if [ "$rc" -ne 0 ]; then
      FAILURES+=("$arm rep$rep — CHILD EXITED $rc; the arm crashed and its output cannot be trusted")
    else
      case "$vrc" in
        0)  ;;
        10) FAILURES+=("$arm rep$rep — NO VALID RUN: no real card rendered, or the seed did not apply") ;;
        11) FAILURES+=("$arm rep$rep — SELF-THROTTLED (429s): re-run it, do not re-code it") ;;
        12) FAILURES+=("$arm rep$rep — NO OUTPUT FILE written at $f") ;;
        13) FAILURES+=("$arm rep$rep — OUTPUT FILE unreadable or unwritable at $f") ;;
        *)  FAILURES+=("$arm rep$rep — the validator itself failed (rc=$vrc); treat this row as unproven") ;;
      esac
    fi
    sleep "$SLEEP_S"
  done
done
# 🔴 The exit code is the whole point. `${#FAILURES[@]}` is safe on macOS bash 3.2 with `set -u`;
# expanding "${FAILURES[@]}" itself is not when the array is empty, so that only ever runs guarded.
if [ "${#FAILURES[@]}" -gt 0 ]; then
  echo
  echo "🔴 ${#FAILURES[@]} of $TOTAL arm-runs produced NO USABLE MEASUREMENT:"
  for entry in "${FAILURES[@]}"; do echo "   - $entry"; done
  echo
  echo "The table in $OUT is INCOMPLETE — do not bank it as a before/after."
  echo "An arm missing from the medians is not a slower arm; it is an absent one, and the"
  echo "comparison it was supposed to anchor cannot be made from what is left."
  exit 1
fi

echo "done -> $OUT  ($TOTAL/$TOTAL arm-runs valid)"
