#!/bin/bash
# native/147 — mutation battery for #5949 (the chart legend that disagreed with
# the rows beneath it). Same classifier as n147-5917-mutants.sh: a mutant that
# fails to COMPILE exits 65 exactly like a failing test and is reported as
# ungraded, never counted as a kill.
set -u
cd "$(dirname "$0")/.." || exit 2

PRES="ios/Bain Luck/Bain Luck/Utilities/TournamentHubPresentation.swift"
CHART="ios/Bain Luck/Bain Luck/Utilities/RaceChart.swift"
VIEW="ios/Bain Luck/Bain Luck/Components/RaceChartView.swift"
SUITES=(
  -only-testing:BainLuckTests/ChartLegendPrintsTheBoardsNumber5949Tests
  -only-testing:BainLuckTests/RaceChartTests
  -only-testing:BainLuckTests/TournamentHubPresentationTests
  -only-testing:BainLuckTests/DecidedBoardNamesTheChampion5917Tests
  -only-testing:BainLuckTests/TournamentHubRenderSmokeTests
)

run_suite() {
  xcodebuild -project "ios/Bain Luck/Bain Luck.xcodeproj" -scheme "Bain Luck" \
    -destination 'platform=iOS Simulator,name=iPhone 17' \
    -disableAutomaticPackageResolution \
    OTHER_SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox' \
    "${SUITES[@]}" test > /tmp/n147b-mutant.log 2>&1
  echo $?
}

mutate() {   # name  file  needle  replacement
  local name="$1" file="$2" needle="$3" replacement="$4"
  cp "$file" /tmp/n147b-mutant-backup.swift
  python3 - "$file" "$needle" "$replacement" <<'PY'
import sys
path, needle, replacement = sys.argv[1], sys.argv[2], sys.argv[3]
s = open(path).read()
if needle not in s:
    sys.exit(7)
open(path, 'w').write(s.replace(needle, replacement, 1))
PY
  if [ $? -eq 7 ]; then
    echo "$name: NEEDLE NOT FOUND — not graded"
    return
  fi
  local code
  code=$(run_suite)
  cp /tmp/n147b-mutant-backup.swift "$file"
  if /usr/bin/grep -q "BUILD FAILED\|Testing cancelled because the build failed" /tmp/n147b-mutant.log; then
    echo "$name: DID NOT COMPILE — not graded, rewrite the mutant"
  elif [ "$code" = "0" ]; then
    echo "$name: SURVIVED  <-- the guard does not see this"
  else
    echo "$name: killed by a test"
  fi
}

echo "=== base ==="
base=$(run_suite)
echo "base exit: $base"
[ "$base" = "0" ] || { echo "BASE IS RED — battery meaningless"; exit 1; }
/usr/bin/grep -E "Executed [0-9]+ tests" /tmp/n147b-mutant.log | tail -1

# M1 — the view goes back to rounding the fraction itself. THE defect.
mutate "M1 legend-re-rounds-its-own-probability" "$VIEW" \
  'Text(formatProbabilityOrDash(
                        entry.probability, renderedPercent: entry.renderedPercent))' \
  'Text(formatProbabilityOrDash(entry.probability))'

# M2 — the board stops handing its map to the chart, so the series carries
#      nothing and the legend falls back to per-row rounding.
mutate "M2 board-map-never-reaches-the-chart" "$PRES" \
  'let chart = raceChart(ordered, starts: starts, rendered: rendered)' \
  'let chart = raceChart(ordered, starts: starts)'

# M3 — the map arrives and is dropped on the floor inside the builder.
mutate "M3 series-ignores-the-map" "$CHART" \
  'renderedPercent: renderedPercents[row.entityKey],' \
  'renderedPercent: nil,'

# M4 — keyed on the wrong thing: the display name instead of the entity key.
#      Every lookup misses, silently, and the legend re-rounds again.
mutate "M4 map-keyed-on-the-display-name" "$CHART" \
  'renderedPercent: renderedPercents[row.entityKey],' \
  'renderedPercent: renderedPercents[row.displayName],'

echo "=== done; tree restored ==="
git -C . diff --stat -- "$PRES" "$CHART" "$VIEW"
