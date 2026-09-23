#!/bin/bash
# native/300 — mutation battery for #8109, the futures chart's participant table
# that printed 93% above 8% on a two-outcome complement pair.
#
# Fourth in the family: tools/n297-8035-mutants.sh (the Discover card),
# tools/n298-2874-share-image-mutants.sh (the image that card shares) and
# tools/n299-8097-futures-detail-mutants.sh (the detail page's other three
# renderers). Same classifier, same reason it exists: the wiring lives in a
# `some View` body and in computed properties, so a behavioural test cannot see
# whether the view still ASKS for the decision. #8035's battery proved that gap
# is real — `caller-filters-the-field-again` SURVIVED its first run — and
# #8097's proved it twice more.
#
# A mutant that fails to COMPILE exits 65 exactly like a failing test, so it is
# reported UNGRADED and never counted as a kill (gotcha #124 — read the exit
# code's meaning, not just its non-zeroness). That matters more here than in the
# last three: two of this ship's parameters are REQUIRED with no default, which
# is a deliberate compile-time guard, so the mutants aimed at them are expected
# to come back UNGRADED and that is the guard working rather than a hole.
set -u
cd "$(dirname "$0")/.." || exit 2

VIEW="ios/Bain Luck/Bain Luck/Components/EvolutionChartView.swift"
GEO="ios/Bain Luck/Bain Luck/Utilities/EvolutionLeaderboardGeometry.swift"
SUITES=(
  -only-testing:BainLuckTests/ChartTableSumsTo100_8109Tests
  -only-testing:BainLuckTests/FuturesZeroPercentLabel5899Tests
  -only-testing:BainLuckTests/ANullChangeIsNotSpokenAsUnchanged7285Tests
  -only-testing:BainLuckTests/EvolutionLeaderboardWidthTests
)

# THE DESTINATION IS RESOLVED, NEVER TYPED — `-destination 'name=<anything>'`
# exits 70 when the specifier does not match, and 70 means the gate NEVER RAN,
# which a battery reads as "no kills" rather than as a broken rig.
SIM_UDID="${NATIVE_SIM_UDID:-$(xcrun simctl list devices available -j | python3 -c '
import json, sys
devices = json.load(sys.stdin)["devices"]
for runtime, entries in sorted(devices.items()):
    if "iOS" not in runtime:
        continue
    for d in entries:
        if d.get("isAvailable") and d.get("name", "").startswith("iPhone"):
            print(d["udid"]); raise SystemExit
')}"
if [ -z "$SIM_UDID" ]; then
  echo "FAIL: no available iPhone simulator to run on — the battery cannot grade anything" >&2
  exit 2
fi
echo "simulator: $SIM_UDID"

run_suite() {
  xcodebuild -project "ios/Bain Luck/Bain Luck.xcodeproj" -scheme "Bain Luck" \
    -destination "platform=iOS Simulator,id=$SIM_UDID" \
    -disableAutomaticPackageResolution \
    OTHER_SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox' \
    "${SUITES[@]}" test > /tmp/n300-mutant.log 2>&1
  echo $?
}

mutate() {   # name  file  needle  replacement
  local name="$1" file="$2" needle="$3" replacement="$4"
  cp "$file" /tmp/n300-subject.bak
  python3 - "$file" "$needle" "$replacement" <<'PY'
import sys
path, needle, repl = sys.argv[1], sys.argv[2], sys.argv[3]
s = open(path).read()
if needle not in s:
    sys.stderr.write("NEEDLE NOT FOUND\n"); sys.exit(3)
open(path, 'w').write(s.replace(needle, repl, 1))
PY
  if [ $? -ne 0 ]; then
    echo "  $name :: NEEDLE NOT FOUND (battery is aimed at stale text)"
    cp /tmp/n300-subject.bak "$file"; return
  fi
  local rc; rc=$(run_suite)
  cp /tmp/n300-subject.bak "$file"
  if [ "$rc" = "0" ]; then
    echo "  $name :: SURVIVED  <-- the guard does not see this"
  elif grep -q "error: .*cannot\|error: .*expected\|error: .*type\|error: .*missing argument" /tmp/n300-mutant.log 2>/dev/null \
       && ! grep -q "XCTAssert" /tmp/n300-mutant.log 2>/dev/null; then
    echo "  $name :: UNGRADED (did not compile)"
  else
    echo "  $name :: killed (exit $rc)"
  fi
}

echo "=== baseline (unmutated) ==="
base=$(run_suite)
echo "  exit $base  $( [ "$base" = 0 ] && echo GREEN || echo 'RED -- fix before reading anything below')"
[ "$base" = 0 ] || exit 1

echo "=== mutants ==="

# --- THE WIRING: each reader goes back to rounding on its own -----------------

# 1. The drawn number — the defect itself, straight back.
mutate "drawn-row-rounds-alone" "$VIEW" \
  "                probPct, renderedPercent: renderedPercent))" \
  "                probPct))"

# 2. The SPOKEN number. A VoiceOver reader hearing 8% off a row the screen draws
#    as 7% is the same defect, and no screenshot can catch it.
mutate "spoken-row-rounds-alone" "$VIEW" \
  "EvolutionLeaderboardGeometry.spokenProb(probPct, renderedPercent: renderedPercent)" \
  "EvolutionLeaderboardGeometry.spokenProb(probPct)"

# 3. The list stops handing the rows anything. #8097's battery caught exactly
#    this survivor: every renderer correctly wired while the feeder is dead.
mutate "list-passes-nil-to-every-row" "$VIEW" \
  "                        renderedPercent: percents[index])" \
  "                        renderedPercent: nil)"

# 4. The COLUMN is sized without the decision, so a board drawing a decided
#    `100%` is measured as `99%` and clips a digit — #4373 arriving through the
#    new fix.
mutate "column-sized-without-the-decision" "$VIEW" \
  "for: rows.map(\\.outcome), at: dynamicTypeSize, renderedPercents: percents)" \
  "for: rows.map(\\.outcome), at: dynamicTypeSize, renderedPercents: [])"

# --- THE INPUT: what the decision is taken OVER --------------------------------

# 5. THE WHOLE POINT. Decide over the rows ON SCREEN instead of the served
#    field, so the `Field` filter and the `Top N` chip reprice the rows they
#    leave. A sum-only guard cannot see this: both inputs still produce a pair
#    that sums to 100.
mutate "decides-over-the-displayed-rows" "$VIEW" \
  "EvolutionLeaderboardGeometry.renderedPercents(forServedField: data?.outcomes ?? [])" \
  "EvolutionLeaderboardGeometry.renderedPercents(forServedField: displayedRows.map(\\.outcome))"

# 6. The served index is dropped and the row's POSITION on screen is used to
#    look the percent up instead — correct for an unfiltered board and silently
#    off by one for every board with a `Field` row above the fold.
mutate "looks-up-by-screen-position-not-served-index" "$VIEW" \
  "servedRenderedPercents[row.servedIndex] : nil" \
  "servedRenderedPercents[0] : nil"

# --- THE DECISION ITSELF -------------------------------------------------------

# 7. THE HEADLINE goes to the underdog, so the derived point lands on the
#    favourite. Still sums to 100, still wrong, and wrong on the number the
#    reader anchors on.
mutate "headline-goes-to-the-underdog" "$GEO" \
  "if lhs != rhs { return lhs > rhs }" \
  "if lhs != rhs { return lhs < rhs }"

# 8. The order is INHERITED from the payload rather than established. Passes
#    today, because the endpoint happens to serve descending — this mutant is
#    the one that documents why that is not good enough.
mutate "inherits-the-payload-order" "$GEO" \
  "        let headlineOrder = served.indices.sorted { a, b in" \
  "        let headlineOrder = Array(served.indices); _ = { (a: Int, b: Int) -> Bool in"

# 9. The map is never filled — every row silently falls back to its own
#    rounding, which is the defect with all the plumbing still in place.
mutate "decision-returns-nothing" "$GEO" \
  "byServedIndex[servedIndex] = printed[slot]" \
  "_ = printed[slot]"

# 10. The card rule is swapped for the scalar one. This is the single most
#     likely "tidy-up" a later reader would make, and it is the whole bug.
mutate "scalar-rule-instead-of-the-card-rule" "$GEO" \
  "let printed = renderedCardPercents(headlineOrder.map { served[\$0].currentProbability })" \
  "let printed = headlineOrder.map { renderedPercent(served[\$0].currentProbability) }"

# 11. The tie-break is dropped, so a 50/50 board's headline is left to
#     `sorted(by:)`, which Swift does not guarantee to be stable.
#     EXPECTED TO SURVIVE — see the note at the bottom.
mutate "tie-break-removed" "$GEO" \
  "            return a < b" \
  "            return false"

# --- THE RULE THE OVERRIDE MUST NOT BEAT ---------------------------------------

# 12. #5899's sub-one-percent marker is allowed to lose to the card-level
#     integer, which prints `0%` for an outcome the venue is still pricing.
mutate "override-beats-the-sub-one-percent-rule" "$GEO" \
  "        if pct < 1 && pct > 0 { return String(format: \"%.1f%%\", pct) }
        if let renderedPercent { return \"\\(renderedPercent)%\" }" \
  "        if let renderedPercent { return \"\\(renderedPercent)%\" }
        if pct < 1 && pct > 0 { return String(format: \"%.1f%%\", pct) }"

# 13. The absent marker loses to the override, so a row with no price prints a
#     number no venue quoted.
mutate "override-conjures-a-price-we-do-not-have" "$GEO" \
  "        guard let pct else { return absentProbabilityMarker }
        if pct < 1 && pct > 0" \
  "        if let renderedPercent { return \"\\(renderedPercent)%\" }
        guard let pct else { return absentProbabilityMarker }
        if pct < 1 && pct > 0"

echo "=== done ==="
echo
echo "EXPECTED NON-KILLS, stated up front so a reader can tell them from holes:"
echo
echo "  tie-break-removed :: EQUIVALENT, not a hole. When two probabilities are"
echo "    equal, first/total is 0.5 either way, so a tied pair renders 50/50"
echo "    whichever side takes index 0. The tie-break buys determinism across"
echo "    reloads, not a different number, and no behavioural test can"
echo "    distinguish it. Recorded rather than papered over with an assertion"
echo "    that cannot fail. (Same finding as #8097's twelfth mutant.)"
echo
echo "  Any mutant reported UNGRADED against a REQUIRED parameter is the"
echo "    compile-time guard working. \`renderedPercents:\` on columns(for:) and"
echo "    \`renderedPercent\` on EvolutionLeaderboardRow have no defaults"
echo "    precisely so that forgetting them cannot be a silent runtime"
echo "    fallback. A battery cannot kill what the compiler already refuses."
