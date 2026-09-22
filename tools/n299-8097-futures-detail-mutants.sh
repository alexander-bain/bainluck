#!/bin/bash
# native/299 — mutation battery for #8097, the futures DETAIL page that printed
# 60% above 41% on a two-outcome complement pair.
#
# Third in the family: tools/n297-8035-mutants.sh (the Discover card) and
# tools/n298-2874-share-image-mutants.sh (the image that card shares). Same
# classifier, same reason it exists: the three renderers on this page live in
# `some View` bodies and a computed property, so a behavioural test cannot see
# whether the view still ASKS for the decision. #8035's battery proved that gap
# is real — `caller-filters-the-field-again` SURVIVED its first run.
#
# A mutant that fails to COMPILE exits 65 exactly like a failing test, so it is
# reported UNGRADED and never counted as a kill (gotcha #124 — read the exit
# code's meaning, not just its non-zeroness).
set -u
cd "$(dirname "$0")/.." || exit 2

VIEW="ios/Bain Luck/Bain Luck/Views/FuturesDetailView.swift"
FORMAT="ios/Bain Luck/Bain Luck/Utilities/FormattingUtilities.swift"
SUITES=(
  -only-testing:BainLuckTests/FuturesDetailSumsTo100_8097Tests
  -only-testing:BainLuckTests/FuturesZeroPercentLabel5899Tests
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
    "${SUITES[@]}" test > /tmp/n299-mutant.log 2>&1
  echo $?
}

mutate() {   # name  file  needle  replacement
  local name="$1" file="$2" needle="$3" replacement="$4"
  cp "$file" /tmp/n299-subject.bak
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
    cp /tmp/n299-subject.bak "$file"; return
  fi
  local rc; rc=$(run_suite)
  cp /tmp/n299-subject.bak "$file"
  if [ "$rc" = "0" ]; then
    echo "  $name :: SURVIVED  <-- the guard does not see this"
  elif grep -q "error: .*cannot\|error: .*expected\|error: .*type" /tmp/n299-mutant.log 2>/dev/null \
       && ! grep -q "XCTAssert" /tmp/n299-mutant.log 2>/dev/null; then
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

# --- THE WIRING: each renderer goes back to rounding on its own ---------------

# 1. The 52pt hero numeral.
mutate "hero-rounds-alone" "$VIEW" \
  "percentNumber(prob * 100, renderedPercent: heroPercent)" \
  "percentNumber(prob * 100)"

# 2. The leader row's big figure.
mutate "leader-row-ignores-the-decision" "$VIEW" \
  "                            renderedPercent: percent" \
  "                            renderedPercent: nil"

# 3. Every other row.
mutate "non-leader-row-rounds-alone" "$VIEW" \
  "formatProbability(prob, renderedPercent: percent)" \
  "formatProbability(prob)"

# 4. The share sentence — the copy that LEAVES the app, and the one no reader of
#    the page can check against the page.
mutate "share-sentence-rounds-alone" "$VIEW" \
  "futuresDetailRenderedPercents(market.outcomes)[leader.id]" \
  "Optional<Int>.none"

# 5. The list stops handing the rows anything.
mutate "list-passes-nil-to-every-row" "$VIEW" \
  "percent: percents[outcome.id]" \
  "percent: nil"

# --- THE DECISION ITSELF ------------------------------------------------------

# 6. THE ORDER. Price the DISPLAYED order instead of the served field. This is
#    the mutant a sum-only guard cannot see: both orders still sum to 100, but
#    the reader's sort control starts repricing rows.
mutate "prices-the-readers-sort-order" "$VIEW" \
  "let percents = futuresDetailRenderedPercents(market.outcomes)" \
  "let percents = futuresDetailRenderedPercents(sorted)"

# 7. THE HEADLINE. Hand index 0 to the underdog, so the derived point lands on
#    the favourite — still sums to 100, still wrong, and wrong on the number the
#    reader anchors on.
mutate "headline-goes-to-the-underdog" "$VIEW" \
  "if lhs != rhs { return lhs > rhs }" \
  "if lhs != rhs { return lhs < rhs }"

# 8. The tie-break is dropped, so a 50/50 market's headline is left to
#    `sorted(by:)`, which Swift does not guarantee to be stable.
mutate "tie-break-removed" "$VIEW" \
  "return a.id < b.id" \
  "return false"

# 9. The map is emptied — every caller silently falls back to its own rounding.
mutate "decision-returns-nothing" "$VIEW" \
  "byOutcomeId[outcome.id] = percent" \
  "_ = percent"

# 10. An unpriced outcome is handed a derived integer instead of nothing, which
#     is how a withdrawn row starts printing a number no venue quoted.
mutate "unpriced-row-gets-a-derived-number" "$VIEW" \
  "guard printed.indices.contains(index), let percent = printed[index] else { continue }" \
  "let percent = (printed.indices.contains(index) ? printed[index] : nil) ?? 0"

# --- THE RULE THE OVERRIDE MUST NOT BEAT --------------------------------------

# 11. The card-level integer is allowed to win over #5899's `<1` marker, which
#     would print `0` for an outcome the venue is still pricing.
mutate "override-beats-the-sub-one-percent-rule" "$FORMAT" \
  "    if percent > 0 && percent < 1 { return \"<1\" }
    if let renderedPercent { return \"\\(renderedPercent)\" }" \
  "    if let renderedPercent { return \"\\(renderedPercent)\" }
    if percent > 0 && percent < 1 { return \"<1\" }"

# 12. Same bargain in `formatProbability`, whose guards ~77 call sites rely on.
mutate "override-beats-the-formatProbability-markers" "$FORMAT" \
  "    if pct < 1 { return \"<1%\" }
    if pct > 99 { return \">99%\" }
    if let renderedPercent { return \"\\(renderedPercent)%\" }" \
  "    if let renderedPercent { return \"\\(renderedPercent)%\" }
    if pct < 1 { return \"<1%\" }
    if pct > 99 { return \">99%\" }"

echo "=== done ==="
