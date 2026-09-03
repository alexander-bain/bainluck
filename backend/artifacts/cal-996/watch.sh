#!/bin/bash
# CAL-996 — capture every calibration beat off `8f927170` until told to stop.
#
# The phase ledger is ONE row, overwritten by the next beat, and it is the only
# place `staged:rebuild_*` is written. So this samples on a fixed 4-minute grid
# rather than waiting for a beat to "look finished": a beat that terminates
# early still leaves its ledger up for ~56 minutes, and a sample taken during
# the rebuild is itself evidence (the gauges appear before the terminal).
#
# Also polls the refusal tripwire. A publish-gate refusal files into a deduped
# GitHub issue; #2280 is the current dedupe target for
# `category_collapse, population_shrink` and sat at 13 comments / last
# 2026-09-02T13:32:55Z when this started. A 14th comment is a refusal specimen
# and is the thing this whole watch exists to catch.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
STOP="$HERE/STOP"
LOG="$HERE/watch.log"

echo "=== watch started $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" >> "$LOG"
while [ ! -f "$STOP" ]; do
  LABEL="$(date -u +%H%M)"
  {
    echo "---- $(date -u +%Y-%m-%dT%H:%M:%SZ) ----"
    python3 "$HERE/capture.py" "$LABEL" 2>&1
    N=$(gh issue view 2280 --json comments --jq '.comments | length' 2>/dev/null)
    echo "tripwire #2280 comments = ${N:-ERR} (baseline 13)"
  } >> "$LOG" 2>&1
  for _ in $(seq 1 48); do
    [ -f "$STOP" ] && break
    sleep 5
  done
done
echo "=== watch stopped $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" >> "$LOG"
