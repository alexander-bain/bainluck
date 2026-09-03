#!/bin/bash
# CAL-P982 drain babysitter — polls the bank + the served payload every 5 min.
# Progress is read from the DATABASE, never inferred from a return value
# (the v2 drain's own lesson: the return value is empty on exactly the
# iterations that decided something).
source ~/.claude/.env
LOG=/Users/bain/bainluck-dev/calibration/artifacts/cal-p982/babysit.jsonl
read -r -d '' SQL <<'SQLEOF'
SELECT
  (SELECT jsonb_array_length(payload->'committed_units') FROM durable_state_snapshots WHERE identity='calibration:main:staged_futures') AS banked,
  (SELECT jsonb_array_length(payload->'planned_units')   FROM durable_state_snapshots WHERE identity='calibration:main:staged_futures') AS planned,
  (SELECT payload->>'input_fingerprint'                  FROM durable_state_snapshots WHERE identity='calibration:main:staged_futures') AS fp,
  (SELECT updated_at::text                               FROM durable_state_snapshots WHERE identity='calibration:main:staged_futures') AS bank_updated,
  (SELECT payload->>'terminal'                           FROM durable_state_snapshots WHERE identity='calibration:main:phase_ledger') AS terminal,
  (SELECT payload->'outcome'->>'gate'                    FROM durable_state_snapshots WHERE identity='calibration:main:phase_ledger') AS gate,
  (SELECT payload->'outcome'->>'published'               FROM durable_state_snapshots WHERE identity='calibration:main:phase_ledger') AS published
SQLEOF
BODY=$(python3 -c 'import json,sys; print(json.dumps({"sql":sys.argv[1],"limit":5}))' "$SQL")

for i in $(seq 1 200); do
  export TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  export DB=$(curl -s --max-time 30 -X POST -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" "$BAINLUCK_API/api/admin/db-query" -d "$BODY")
  export CAL=$(curl -s --max-time 30 "$BAINLUCK_API/api/calibration")
  export DYNO=$(heroku ps -a bainluck 2>/dev/null | grep -c "run\.5071")
  python3 -c '
import json, os
rec = {}
try:
    d = json.loads(os.environ["DB"]); rec = dict(zip(d["columns"], d["rows"][0]))
except Exception as e:
    rec["db_error"] = str(e)[:200]
try:
    c = json.loads(os.environ["CAL"])
    rec["served_pv"] = c.get("population_version"); rec["served_at"] = c.get("generated_at")
    rec["served_status"] = c.get("status", "ok"); rec["served_avail"] = c.get("availability")
except Exception as e:
    rec["cal_error"] = str(e)[:120]
rec["ts"] = os.environ["TS"]; rec["drain_dyno"] = os.environ["DYNO"].strip()
print(json.dumps(rec, sort_keys=True))
' >> "$LOG" 2>&1
  tail -1 "$LOG"
  if echo "$CAL" | grep -q '"population_version": *"q269"'; then echo "{\"ts\":\"$TS\",\"event\":\"PUBLISHED_Q269\"}" >> "$LOG"; break; fi
  sleep 300
done
