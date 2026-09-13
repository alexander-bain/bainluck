#!/bin/bash
# native/152 — mutation battery for #5990 (a decided draw keeps its title-race
# chart). Each mutant is a one-line reversal of the fix; a mutant that SURVIVES
# is a hole in the guard, and a mutant the battery cannot APPLY (`NEEDLE NOT
# FOUND`) is reported as such rather than counted as a kill.
#
# M1 is the defect itself, byte for byte: the pre-#5990 `probability != nil`
# filter. If it survives, the suite proves nothing.
set -u
cd "$(dirname "$0")/.." || exit 2

RULE="ios/Bain Luck/Bain Luck/Utilities/RaceChart.swift"
VIEW="ios/Bain Luck/Bain Luck/Components/RaceChartView.swift"
PRES="ios/Bain Luck/Bain Luck/Utilities/TournamentHubPresentation.swift"
SUITES=(
  -only-testing:BainLuckTests/ASettledDrawKeepsItsChart5990Tests
  -only-testing:BainLuckTests/ChartLegendPrintsTheBoardsNumber5949Tests
  -only-testing:BainLuckTests/DecidedBoardNamesTheChampion5917Tests
  -only-testing:BainLuckTests/RaceChartTests
  -only-testing:BainLuckTests/TournamentHubRenderSmokeTests
)

run_suite() {
  xcodebuild -project "ios/Bain Luck/Bain Luck.xcodeproj" -scheme "Bain Luck" \
    -destination 'platform=iOS Simulator,name=iPhone 17' \
    -disableAutomaticPackageResolution \
    OTHER_SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox' \
    "${SUITES[@]}" test > /tmp/n152-mutant.log 2>&1
  echo $?
}

mutate() {   # name  file  needle  replacement
  local name="$1" file="$2" needle="$3" replacement="$4"
  cp "$file" /tmp/n152-mutant-backup.swift
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
  cp /tmp/n152-mutant-backup.swift "$file"
  # A BUILD failure exits 65 exactly like a test failure, so a mutant that does
  # not compile reads as a kill the guards never made. Classify on the log, not
  # on the exit code (gotcha #124: read the value, and know which story it is).
  if /usr/bin/grep -q "BUILD FAILED\|Testing cancelled because the build failed" /tmp/n152-mutant.log; then
    echo "$name: DID NOT COMPILE — not graded, rewrite the mutant"
  elif [ "$code" = "0" ]; then
    echo "$name: SURVIVED  <-- the guard does not see this"
  else
    echo "$name: killed by a test ($(/usr/bin/grep -cE "error: -\[BainLuck" /tmp/n152-mutant.log) failing assertions)"
  fi
}

echo "=== base ==="
base=$(run_suite)
echo "base exit: $base"
[ "$base" = "0" ] || { echo "BASE IS RED — battery meaningless"; exit 1; }
/usr/bin/grep -E "Executed [0-9]+ tests" /tmp/n152-mutant.log | tail -1

# M1 — THE DEFECT ITSELF. The pre-#5990 filter: a settled row is not chartable,
#      so a finished draw loses its picture.
mutate "M1 chartable-reverts-to-priced-only" "$RULE" \
  '.filter { $0.0.probability != nil || !$0.1.isEmpty }' \
  '.filter { $0.0.probability != nil }'

# M2 — drawability widened to EVERYTHING: a row with no price and no history
#      takes a slot and draws a legend entry with nothing under it.
mutate "M2 every-row-is-chartable" "$RULE" \
  '.filter { $0.0.probability != nil || !$0.1.isEmpty }' \
  '.filter { _ in true }'

# M3 — priced-first dropped: mid-tournament an eliminated player opens the
#      chart ahead of a contender still in the draw.
mutate "M3 priced-first-dropped" "$RULE" \
  'return (priced.isEmpty ? chartable : priced)' \
  'return chartable'

# M4 — the fallback inverted: once anything is priced the settled lines win,
#      which is the same defect wearing the opposite sign.
mutate "M4 fallback-inverted" "$RULE" \
  'return (priced.isEmpty ? chartable : priced)' \
  'return (priced.isEmpty ? priced : chartable)'

# M5 — THE PRICE IS RESURRECTED: the legend prints the last reading of a line
#      belonging to a question that is over ("RYBAKINA 99%", #5917).
mutate "M5 legend-prints-the-last-point" "$RULE" \
  'if entry.probability == nil, let label = legendStateLabel(entry.state) {
            return label
        }' \
  'if entry.probability == nil, entry.points.isEmpty,
           let label = legendStateLabel(entry.state) {
            return label
        }
        if entry.probability == nil, let last = entry.points.last {
            return formatProbabilityOrDash(last.probability)
        }'

# M6 — the champion is labelled with the loser word.
mutate "M6 won-and-out-swapped" "$RULE" \
  'case "won": return "Won"
        case "eliminated": return "Out"' \
  'case "won": return "Out"
        case "eliminated": return "Won"'

# M7 — an unrecognised state invents a word instead of falling through to the
#      number.
#
# THE NEEDLE IS ANCHORED ON ITS OWN CASES, and the first version of it was not:
# `default: return nil` + two braces also matches `RaceChartWindowStarts
# .start(for:)` thirty lines up, which returns `String?` too, so the mutant
# compiled, changed a window start nothing reads, and reported SURVIVED — a
# guard hole that was really a mis-aimed mutant. A battery whose needle can
# match twice grades the wrong line silently (`replace(…, 1)` takes the first).
mutate "M7 unknown-state-invents-a-word" "$RULE" \
  'case "eliminated": return "Out"
        default: return nil' \
  'case "eliminated": return "Out"
        default: return "Out"'

# M8 — the state stops travelling, so every settled legend cell reads as a
#      missing number rather than a result.
mutate "M8 state-never-carried" "$RULE" \
  'state: row.state ?? "",' \
  'state: "",'

# M9 — the view stops asking the rule and re-rounds on its own (#5949's defect
#      and #5990's, in one line).
mutate "M9 view-formats-it-itself" "$VIEW" \
  'Text(RaceChart.legendValue(entry))' \
  'Text(formatProbabilityOrDash(entry.probability))'

# M10 — the presentation nils the chart on every decided board regardless of
#       what the series holds: the fix made unreachable from one layer up.
mutate "M10 decided-board-always-loses-its-chart" "$PRES" \
  'chart: isDecided && chart.series.isEmpty ? nil : chart' \
  'chart: isDecided ? nil : chart'

echo "=== done; tree restored ==="
git -C . diff --stat -- "$RULE" "$VIEW" "$PRES"
