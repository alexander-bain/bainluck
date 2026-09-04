#!/bin/bash
# lane1/090: wait for the anchor-schedule sentinel's first real beat (06:40 UTC
# Fri 2026-09-04) and capture what it did. Read-only.
#
# heroku logs are EPERM-blocked in the sandbox, so the durable channel is the
# _tracked_run ledger: record_task_success stores the task's whole returned dict
# under `last_result_summary`, which carries terminal/complete/stopped_by/pages/
# examined/eligible/by_verdict/moves/elapsed_seconds/filing.
set -u
OUT=/Users/bain/bainluck-dev/lane1/artifacts/lane1-090-anchor-sentinel-run.detached.json
LOG=/Users/bain/bainluck-dev/lane1/artifacts/lane1-090-anchor-sentinel-watch.detached.log
source ~/.claude/.env

: > "$LOG"
say() { echo "[$(date -u +%H:%M:%SZ)] $*" >> "$LOG"; }

# Sleep until 06:43Z — three minutes past the fire, so a fast run is already
# banked and a slow one is at least started (starts_24h moves before the work).
TARGET=$(date -u -j -f "%Y-%m-%d %H:%M:%S" "$(date -u +%Y-%m-%d) 06:43:00" +%s 2>/dev/null)
NOW=$(date -u +%s)
if [ "$TARGET" -le "$NOW" ]; then TARGET=$((TARGET + 86400)); fi
say "sleeping $((TARGET - NOW))s until 06:43Z"
sleep $((TARGET - NOW))

# Poll for up to 25 minutes. The run has a 300s inner deadline and an 840s soft
# limit, so a run that is still going at 07:08Z has blown both and that silence
# is itself the finding.
for i in $(seq 1 25); do
  BODY=$(curl -s --max-time 30 -H "Authorization: Bearer $ADMIN_TOKEN" \
    "$BAINLUCK_API/api/admin/celery/task-metrics/anchor_schedule_sentinel")
  echo "$BODY" > "$OUT"
  say "poll $i: $(echo "$BODY" | head -c 200)"
  if ! echo "$BODY" | grep -q '"no_data"'; then
    say "LEDGER HAS DATA — stopping"
    break
  fi
  sleep 60
done

# Whatever happened, snapshot the surrounding evidence too.
{
  echo "=== task-metrics ==="; cat "$OUT"
  echo; echo "=== schedule-adherence (anchor rows) ==="
  curl -s --max-time 30 -H "Authorization: Bearer $ADMIN_TOKEN" \
    "$BAINLUCK_API/api/admin/celery/schedule-adherence" \
    | python3 -c "import json,sys;d=json.load(sys.stdin);print(json.dumps([x for k,v in d.items() if isinstance(v,list) for x in v if 'anchor_schedule' in json.dumps(x)],indent=2))" 2>&1
  echo; echo "=== health ==="
  curl -s --max-time 30 "$BAINLUCK_API/api/health"
} >> "$LOG" 2>&1

say "DONE"
