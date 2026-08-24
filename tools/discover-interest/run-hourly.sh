#!/usr/bin/env bash
# UX-P124 item 1 — drive capture-top20.sh on a fixed cadence.
#
# Bounded by COUNT, never by a wall-clock "until midnight" condition. A loop that
# tests the clock has to decide what to do when it is resumed the next day, and
# every version of that answer is wrong in one direction; a count is resumable by
# just running it again.
#
#   COUNT=13 INTERVAL=3600 ./run-hourly.sh
#
# Writes the same `pulls.jsonl` capture-top20.sh writes, appending. The first
# pull fires IMMEDIATELY (not after one interval) so a run that dies early still
# produced something.

set -u
COUNT="${COUNT:-13}"
INTERVAL="${INTERVAL:-3600}"
OUT_DIR="${OUT_DIR:-/tmp/ux-p124-captures}"
HERE="$(cd "$(dirname "$0")" && pwd)"
export OUT_DIR

mkdir -p "$OUT_DIR"
LOG="$OUT_DIR/run-hourly.log"

i=0
while [ "$i" -lt "$COUNT" ]; do
  i=$((i + 1))
  "$HERE/capture-top20.sh" >> "$LOG" 2>&1
  rc=$?
  echo "pull $i/$COUNT rc=$rc $(date -u +%H:%M:%SZ)" >> "$LOG"
  [ "$i" -lt "$COUNT" ] && sleep "$INTERVAL"
done
echo "RUN COMPLETE $COUNT pulls $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG"
