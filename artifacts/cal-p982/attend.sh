#!/bin/bash
# CAL-P987 attendant — the half the other two watchers do not cover.
#
# babysit.sh (5 min, ~16.7 h) breaks only on PUBLISHED; it logs `gate` but never
# reacts to it. drain_watch.sh exits 3 on `gate=refuse` but its 200x2min budget
# runs out ~14:50 PT, and the measured ETA is ~17:00-17:15 PT — so a refusal in
# the last two hours of the drain would go unflagged by both.
#
# This loop covers the terminal states through ~19:20 PT and, on a refusal,
# writes the ask into YOUR-TURN.md rather than leaving it in a log nobody reads.
# Progress is read from the DATABASE, never from a return value.
source ~/.claude/.env
DIR=/Users/bain/bainluck-dev/calibration/artifacts/cal-p982
LOG="$DIR/attend.jsonl"
YT=/Users/bain/bainluck/YOUR-TURN.md

read -r -d '' SQL <<'SQLEOF'
SELECT
  (SELECT jsonb_array_length(payload->'committed_units') FROM durable_state_snapshots WHERE identity='calibration:main:staged_futures') AS banked,
  (SELECT jsonb_array_length(payload->'planned_units')   FROM durable_state_snapshots WHERE identity='calibration:main:staged_futures') AS planned,
  (SELECT payload->>'input_fingerprint'                  FROM durable_state_snapshots WHERE identity='calibration:main:staged_futures') AS fp,
  (SELECT payload->>'population_version'                 FROM durable_state_snapshots WHERE identity='calibration:main:staged_futures') AS bank_pv,
  (SELECT payload->'outcome'->>'gate'                    FROM durable_state_snapshots WHERE identity='calibration:main:phase_ledger') AS gate,
  (SELECT payload->'outcome'->>'published'               FROM durable_state_snapshots WHERE identity='calibration:main:phase_ledger') AS published,
  (SELECT payload->'outcome'->>'reason'                  FROM durable_state_snapshots WHERE identity='calibration:main:phase_ledger') AS reason
SQLEOF
BODY=$(python3 -c 'import json,sys; print(json.dumps({"sql":sys.argv[1],"limit":5}))' "$SQL")

# `heroku ps` failing (network, auth, rate limit) prints nothing and grep -c says 0,
# which is indistinguishable from "the dyno died". Three consecutive zeros, not one.
MISSES=0

# 170 x 3 min = 8.5 h from launch (~10:55 PT) -> covers to ~19:20 PT.
for i in $(seq 1 170); do
  export TS_PT=$(TZ=America/Los_Angeles date '+%Y-%m-%dT%H:%M:%S%z')
  export DB=$(curl -s --max-time 30 -X POST -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" "$BAINLUCK_API/api/admin/db-query" -d "$BODY")
  export CAL=$(curl -s --max-time 30 "$BAINLUCK_API/api/calibration")
  export DYNO=$(heroku ps -a bainluck 2>/dev/null | grep -c "run\.5071")
  export VERDICT=$(python3 -c '
import json, os
rec = {"ts_pt": os.environ["TS_PT"], "drain_dyno_up": os.environ["DYNO"].strip()}
try:
    d = json.loads(os.environ["DB"]); rec.update(dict(zip(d["columns"], d["rows"][0])))
except Exception as e:
    rec["db_error"] = str(e)[:200]
try:
    c = json.loads(os.environ["CAL"])
    rec["served_pv"] = c.get("population_version"); rec["served_at"] = c.get("generated_at")
    rec["served_avail"] = c.get("availability"); rec["served_reason"] = c.get("reason")
except Exception as e:
    rec["cal_error"] = str(e)[:120]
# A missing dyno with the bank short of plan is its own terminal state: the drain
# died and nothing is going to finish it. Say so rather than logging 40/128 forever.
if rec.get("gate") == "refuse":
    rec["VERDICT"] = "REFUSED"
elif rec.get("served_pv") == "q269":
    rec["VERDICT"] = "PUBLISHED"
elif rec.get("drain_dyno_up") == "0" and rec.get("served_pv") != "q269":
    rec["VERDICT"] = "DRAIN_GONE"
else:
    rec["VERDICT"] = "running"
print(json.dumps(rec, sort_keys=True))
')
  echo "$VERDICT" >> "$LOG"
  V=$(printf '%s' "$VERDICT" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("VERDICT",""))' 2>/dev/null)

  case "$V" in
    PUBLISHED)
      echo "{\"ts_pt\":\"$TS_PT\",\"event\":\"PUBLISHED_Q269\"}" >> "$LOG"
      exit 0;;
    REFUSED)
      cat >> "$YT" <<YTEOF

## 🔴 CAL-P987 — the q269 publish gate REFUSED the drain candidate ($TS_PT)

The 128-unit drain finished and the gate refused it. **A refusal clears the checkpoint on purpose,
so the bank is binned and relaunching rebuilds the identical rejected candidate.** Do NOT relaunch.

Last watcher record: \`artifacts/cal-p982/attend.jsonl\` (tail -1).

What is needed from you: a decision on which way to go, because both options change code —
land Option B (\`program/calibration-982…\`, \`eb228037\`), which makes the bump declare its own
shrink and is built and unmerged; or change the population predicate. Read
\`.claude/handoff/REPORT-982-bump-declaration.md\` §6 first.
YTEOF
      exit 3;;
    DRAIN_GONE)
      MISSES=$((MISSES + 1))
      echo "{\"ts_pt\":\"$TS_PT\",\"event\":\"drain_dyno_not_listed\",\"consecutive\":$MISSES}" >> "$LOG"
      if [ "$MISSES" -ge 3 ]; then
        echo "{\"ts_pt\":\"$TS_PT\",\"event\":\"DRAIN_DYNO_GONE_BANK_SHORT\"}" >> "$LOG"
        exit 4
      fi;;
    *) MISSES=0;;
  esac
  sleep 180
done
echo "{\"ts_pt\":\"$(TZ=America/Los_Angeles date '+%Y-%m-%dT%H:%M:%S%z')\",\"event\":\"WATCH_BUDGET_EXHAUSTED\"}" >> "$LOG"
