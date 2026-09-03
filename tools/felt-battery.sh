#!/bin/bash
# felt-battery.sh — the whole felt-number table in one pass.
#
# Every top-level tab and the pages under them, three conditions each:
#   cold   — signed-out, empty cache, unthrottled (what the rig's own network gives us)
#   warm   — the reader is already on the site and switches tab
#   slow4g — Chrome DevTools "Slow 4G" + 4x CPU, i.e. iPhone-class
#
# Artifacts land one JSON per (surface, condition) so a single bad surface can be re-run without
# re-running the table. Never `set -e` here: one surface failing must not silently truncate the
# table into a shorter one that looks complete.
OUT="${1:-/tmp/felt-2026-09-02}"
mkdir -p "$OUT"
SURFACES="discover sports usopen search event politics calibration profile"

for s in $SURFACES; do
  echo "=== COLD $s ==="
  FELT_MODE=cold node tools/felt-load.mjs "$s" 5 "$OUT/cold-$s.json" > /dev/null 2>>"$OUT/log.txt"
  echo "cold $s exit=$?" >> "$OUT/log.txt"
done

for s in $SURFACES; do
  echo "=== WARM $s ==="
  FELT_MODE=warm node tools/felt-load.mjs "$s" 5 "$OUT/warm-$s.json" > /dev/null 2>>"$OUT/log.txt"
  echo "warm $s exit=$?" >> "$OUT/log.txt"
done

for s in $SURFACES; do
  echo "=== SLOW4G $s ==="
  FELT_MODE=cold FELT_THROTTLE=slow4g FELT_CPU=4 node tools/felt-load.mjs "$s" 3 "$OUT/slow4g-$s.json" > /dev/null 2>>"$OUT/log.txt"
  echo "slow4g $s exit=$?" >> "$OUT/log.txt"
done

echo "BATTERY DONE -> $OUT"
