#!/bin/bash
# CAL-P128 sigma sweep: measure cluster-bootstrap sigma on every queued
# non-bookmaker board cell. CAL-P127 lesson 4: the board's sigma column is
# row-grain, which is a claim about ROWS, not about independent observations.
# kalshi/golf already measured (artifacts/cal-p127/sigma-kalshi-golf.json).
set -u
OUT=artifacts/cal-p128
CELLS=(
  "polymarket baseball"
  "kalshi economics"
  "polymarket esports"
  "kalshi crypto"
  "kalshi tech"
  "kalshi entertainment"
  "polymarket basketball"
  "polymarket cricket"
  "polymarket golf"
  "polymarket economics"
  "polymarket hockey"
  "polymarket tech"
  # Last on purpose: the biggest cell on the board and the slowest sweep.
  # Everything above it banks before this one starts.
  "polymarket soccer"
)
for c in "${CELLS[@]}"; do
  set -- $c
  src=$1; cat=$2
  f="$OUT/sigma-$src-$cat.json"
  if [ -f "$f" ]; then echo "== SKIP $src/$cat (exists)"; continue; fi
  echo "== RUN $src/$cat  $(date -u +%H:%M:%S)"
  timeout 1800 python3 backend/scripts/calibration_cluster_sigma.py \
      --source "$src" --category "$cat" --out "$f" \
      > "$OUT/log-$src-$cat.txt" 2>&1
  echo "   exit=$? $(date -u +%H:%M:%S)"
done
echo "SWEEP COMPLETE"
