#!/bin/bash
# native/147 — mutation battery for the #5917 native arm (the decided title
# board). Each mutant is a one-line reversal of the fix; a mutant that SURVIVES
# is a hole in the guard, and a mutant the battery cannot APPLY (`NEEDLE NOT
# FOUND`) is reported as such rather than counted as a kill.
set -u
cd "$(dirname "$0")/.." || exit 2

PRES="ios/Bain Luck/Bain Luck/Utilities/TournamentHubPresentation.swift"
SUITES=(
  -only-testing:BainLuckTests/DecidedBoardNamesTheChampion5917Tests
  -only-testing:BainLuckTests/TournamentHubPresentationTests
  -only-testing:BainLuckTests/RaceChartTests
  -only-testing:BainLuckTests/TournamentHubRenderSmokeTests
)

run_suite() {
  xcodebuild -project "ios/Bain Luck/Bain Luck.xcodeproj" -scheme "Bain Luck" \
    -destination 'platform=iOS Simulator,name=iPhone 17' \
    -disableAutomaticPackageResolution \
    OTHER_SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox' \
    "${SUITES[@]}" test > /tmp/n147-mutant.log 2>&1
  echo $?
}

mutate() {   # name  file  needle  replacement
  local name="$1" file="$2" needle="$3" replacement="$4"
  cp "$file" /tmp/n147-mutant-backup.swift
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
  cp /tmp/n147-mutant-backup.swift "$file"
  # A BUILD failure exits 65 exactly like a test failure, so a mutant that does
  # not compile reads as a kill the guards never made. Classify on the log, not
  # on the exit code (gotcha #124: read the value, and know which story it is).
  if /usr/bin/grep -q "BUILD FAILED\|Testing cancelled because the build failed" /tmp/n147-mutant.log; then
    echo "$name: DID NOT COMPILE — not graded, rewrite the mutant"
  elif [ "$code" = "0" ]; then
    echo "$name: SURVIVED  <-- the guard does not see this"
  else
    echo "$name: killed by a test ($(/usr/bin/grep -cE "error: -\[BainLuck" /tmp/n147-mutant.log) failing assertions)"
  fi
}

echo "=== base ==="
base=$(run_suite)
echo "base exit: $base"
[ "$base" = "0" ] || { echo "BASE IS RED — battery meaningless"; exit 1; }
grep -E "Executed [0-9]+ tests" /tmp/n147-mutant.log | tail -1

# M1 — the original filter, restored. The decided board vanishes again.
mutate "M1 decided-board-is-filtered-out-again" "$PRES" \
  'let field = isDecided
            ? board.rows
            : board.rows.filter { ($0.state ?? "live") == "live" }' \
  'let field = board.rows.filter { ($0.state ?? "live") == "live" }'

# M2 — the champion is priced again: the state switch falls through to the
#      probability, which is null, so the row prints a dash.
mutate "M2 won-row-falls-through-to-the-price" "$PRES" \
  'case "won": return "Won"' \
  'case "won": return formatProbabilityOrDash(row.probability, renderedPercent: renderedPercent)'

# M3 — an eliminated row prints the dash instead of the result.
mutate "M3 eliminated-row-prints-a-dash" "$PRES" \
  'case "eliminated": return "Out"' \
  'case "eliminated": return formatProbabilityOrDash(row.probability, renderedPercent: renderedPercent)'

# M4 — the champion is no longer pinned to the top of her own board.
mutate "M4 champion-not-pinned-first" "$PRES" \
  'if let champion {
                if lhs.id == champion.id { return true }
                if rhs.id == champion.id { return false }
            }' \
  ''

# M5 — an unresolvable winner key falls back to the first row, so the board
#      names the wrong player with total confidence.
mutate "M5 unresolved-winner-names-row-zero" "$PRES" \
  'if board.decided != nil { return nil }' \
  'if board.decided != nil { return board.rows.first }'

# M6 — only `decided` counts, so half a contract deletes the card.
mutate "M6 won-row-alone-is-not-decided" "$PRES" \
  'let isDecided = board.decided != nil || board.rows.contains { $0.state == "won" }' \
  'let isDecided = board.decided != nil'

# M7 — the empty chart frame comes back on a decided board.
mutate "M7 empty-chart-frame-on-a-decided-board" "$PRES" \
  'chart: isDecided && chart.series.isEmpty ? nil : chart' \
  'chart: chart'

# M8 — the trim note tells a reader the champion is still in the draw.
mutate "M8 final-standings-note-reverts" "$PRES" \
  '? "Top \(shown.count) of \(ordered.count) in the final standings"' \
  '? "Top \(shown.count) of \(ordered.count) still in the draw"'

# M9 — the "nobody is priced YET" promise on a finished tournament.
mutate "M9 empty-note-promises-a-price-anyway" "$PRES" \
  '? (response.boards.contains { $0.decided != nil }
                ? nil : "Nobody is priced to win the title yet.")' \
  '? "Nobody is priced to win the title yet."'

# M10 — the answer is dropped and the standings stand alone.
mutate "M10 settled-sentence-deleted" "$PRES" \
  'settledNote: isDecided
                ? (champion.map { "Settled · \($0.displayName) won the title." }
                    ?? "Settled · this draw is decided.")
                : nil' \
  'settledNote: nil'

# M11 — everything is decided, so a live board fills its six rows with players
#       who are out of the tournament.
mutate "M11 every-board-treated-as-decided" "$PRES" \
  'let isDecided = board.decided != nil || board.rows.contains { $0.state == "won" }' \
  'let isDecided = true'

echo "=== done; tree restored ==="
git -C . diff --stat -- "$PRES"
