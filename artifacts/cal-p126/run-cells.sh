#!/bin/bash
# CAL-P126 — exact per-cell phantom + bucket delta, ordered by HEADLINE WEIGHT
# PER UNIT COST (published outcomes in a price_moved cohort, divided by resolved
# markets, which is what Stage A is charged by). Sequential on purpose: the lane
# rule is that heavy measurement never runs beside another heavy measurement.
set -u
cd /Users/bain/bainluck-dev/calibration
OUT=artifacts/cal-p126

# cell : roster-buckets : buckets   (wider partitions for the big cells; the
# unit reader re-plans on the SQL char cap anyway, this just saves the retries)
CELLS="
kalshi:hockey:32:32
kalshi:basketball:64:128
polymarket:weather:32:64
kalshi:baseball:128:128
polymarket:golf:32:32
polymarket:politics:32:32
polymarket:entertainment:32:32
kalshi:soccer:64:128
kalshi:football:64:64
polymarket:economics:64:64
"

for spec in $CELLS; do
    src="${spec%%:*}";  rest="${spec#*:}"
    cat="${rest%%:*}";  rest="${rest#*:}"
    rb="${rest%%:*}";   bk="${rest##*:}"
    f="$OUT/cell-$src-$cat.json"
    if [ -f "$f" ]; then echo "SKIP $src/$cat (already measured)"; continue; fi
    echo "=== $src/$cat (roster-buckets=$rb buckets=$bk) $(date -u +%H:%M:%SZ)"
    timeout 5400 python3 -u backend/scripts/calibration_phantom_curve.py \
        --cell --source "$src" --category "$cat" \
        --roster-cache "$OUT/roster-$src-$cat.json" \
        --roster-buckets "$rb" --buckets "$bk" --out "$f"
    echo "    exit $?"
done
echo "BATCH DONE $(date -u +%H:%M:%SZ)"
