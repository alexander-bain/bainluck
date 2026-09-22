#!/bin/bash
# native/297 — mutation battery for #8035 (the Discover futures card that printed
# 101%). Same classifier as tools/n147b-5949-mutants.sh: a mutant that fails to
# COMPILE exits 65 exactly like a failing test, so it is reported as UNGRADED and
# never counted as a kill.
set -u
cd "$(dirname "$0")/.." || exit 2

CARD="ios/Bain Luck/Bain Luck/Components/DiscoverFuturesCard.swift"
SUITES=(
  -only-testing:BainLuckTests/DiscoverFuturesCardSumsTo100Tests
  -only-testing:BainLuckTests/PriceAgeMarkTests
  -only-testing:BainLuckTests/RenderedPercentContractTests
)

# Resolved, never typed: `name=iPhone 17 Pro` was REFUSED on this machine with a
# simulator of that exact name installed, and the refusal exits 70 — the gate
# never ran, which a battery reads as "no kills" rather than as a broken rig
# (gotcha #124). Same resolution as tools/native-gates.sh.
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
  echo "FAIL: no available iPhone simulator to run on" >&2
  exit 2
fi

run_suite() {
  xcodebuild -project "ios/Bain Luck/Bain Luck.xcodeproj" -scheme "Bain Luck" \
    -destination "platform=iOS Simulator,id=$SIM_UDID" \
    -disableAutomaticPackageResolution \
    OTHER_SWIFT_FLAGS='$(inherited) -Xfrontend -disable-sandbox' \
    "${SUITES[@]}" test > /tmp/n297-mutant.log 2>&1
  echo $?
}

mutate() {   # name  needle  replacement
  local name="$1" needle="$2" replacement="$3"
  cp "$CARD" /tmp/n297-card.bak
  python3 - "$CARD" "$needle" "$replacement" <<'PY'
import sys
path, needle, repl = sys.argv[1], sys.argv[2], sys.argv[3]
s = open(path).read()
if needle not in s:
    sys.stderr.write("NEEDLE NOT FOUND\n"); sys.exit(3)
open(path, 'w').write(s.replace(needle, repl, 1))
PY
  if [ $? -ne 0 ]; then
    echo "  $name :: NEEDLE NOT FOUND (battery is aimed at stale text)"
    cp /tmp/n297-card.bak "$CARD"; return
  fi
  local rc; rc=$(run_suite)
  cp /tmp/n297-card.bak "$CARD"
  if [ "$rc" = "0" ]; then
    echo "  $name :: SURVIVED  <-- the guard does not see this"
  elif grep -q "error: .*cannot\|error: .*expected\|error: .*type" /tmp/n297-mutant.log 2>/dev/null \
       && ! grep -q "XCTAssert" /tmp/n297-mutant.log 2>/dev/null; then
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

# 1. The whole ship: go back to rounding each outcome on its own.
mutate "revert-to-per-outcome-rounding" \
  "renderedCardPercents(outcomes.map(\\.probability))" \
  "outcomes.map { renderedPercent(\$0.probability) }"

# 2. The row stops using the card's decision and re-derives from the raw value.
mutate "row-ignores-the-cards-decision" \
  "Text(discoverFuturesCardPercentLabel(percent))" \
  "Text(\"\\(Int(((outcome.probability ?? 0) * 100).rounded()))%\")"

# 3. The list hands every row a nil percent.
mutate "list-passes-nil" \
  "percent: percents.indices.contains(idx) ? percents[idx] : nil" \
  "percent: nil"

# 4. The label's absent-value default moves.
mutate "label-default-moves" \
  "\"\\(percent ?? 0)%\"" \
  "\"\\(percent ?? 1)%\""

# 5. The hero stops sharing the card's decision.
#    (`leaderProbability` was deleted with the last per-site rounding in #2874's
#    share-image half, so the replacement derives it inline rather than naming a
#    property that no longer exists — a mutant that cannot compile is UNGRADED,
#    which reads as "no finding" and is the quietest way for a battery to rot.)
mutate "hero-rounds-alone" \
  "Text(\"\\(leaderRenderedPercent)\")" \
  "Text(\"\\(Int(((leader?.probability ?? 0) * 100).rounded()))\")"

# 6. The pair is decided, but the WRONG side keeps its own number — the quiet
#    bug that still sums to 100.
mutate "derived-point-lands-on-the-favourite" \
  "renderedCardPercents(outcomes.map(\\.probability))" \
  "renderedCardPercents(outcomes.map(\\.probability).reversed()).reversed()"

echo
echo "known-equivalent, stated rather than hidden:"
echo "  passing outcomes.prefix(3) instead of the whole list is EQUIVALENT on this"
echo "  fixture — every card in it has 2 or 3 outcomes — so it is not run as a"
echo "  mutant. It would only diverge on a 4+ outcome card whose top two happen to"
echo "  sum into the complement band, which is the case the whole-list argument"
echo "  exists to refuse."
