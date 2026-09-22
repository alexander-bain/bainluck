#!/bin/bash
# native/298 — mutation battery for the SHARE-IMAGE half of #8035 / #2874 (the
# futures card that printed 101%, and the picture of it that left the app).
#
# Sibling of tools/n297-8035-mutants.sh, which covers the card. Same classifier:
# a mutant that fails to COMPILE exits 65 exactly like a failing test, so it is
# reported as UNGRADED and never counted as a kill (gotcha #124 — read the exit
# code's meaning, not just its non-zeroness).
#
# The mutants are aimed at the two things a behavioural test cannot reach on its
# own: the renderer's `some View` body, and the caller's outcome list.
set -u
cd "$(dirname "$0")/.." || exit 2

RENDERER="ios/Bain Luck/Bain Luck/Utilities/ShareCardRenderer.swift"
CARD="ios/Bain Luck/Bain Luck/Components/DiscoverFuturesCard.swift"
SUITES=(
  -only-testing:BainLuckTests/FuturesShareImageMatchesItsCard_2874Tests
  -only-testing:BainLuckTests/DiscoverFuturesCardSumsTo100Tests
  -only-testing:BainLuckTests/ShareImageMatchesItsCard_7998Tests
)

# THE DESTINATION IS RESOLVED, NEVER TYPED (gotcha #124, and ux/1437's 20 minutes).
# `-destination 'name=<anything>'` EXITS 70 when the specifier does not match —
# and 70 means the gate NEVER RAN, which a battery reads as "no kills" rather
# than as a broken rig. Simulator names churn between Xcode releases and between
# laptops; `name=iPhone 17 Pro` was refused on this very machine while a
# simulator of that exact name was installed. So an available iPhone is resolved
# by UDID at runtime, the way tools/native-gates.sh does it.
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
    "${SUITES[@]}" test > /tmp/n298-mutant.log 2>&1
  echo $?
}

mutate() {   # name  file  needle  replacement
  local name="$1" file="$2" needle="$3" replacement="$4"
  cp "$file" /tmp/n298-subject.bak
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
    cp /tmp/n298-subject.bak "$file"; return
  fi
  local rc; rc=$(run_suite)
  cp /tmp/n298-subject.bak "$file"
  if [ "$rc" = "0" ]; then
    echo "  $name :: SURVIVED  <-- the guard does not see this"
  elif grep -q "error: .*cannot\|error: .*expected\|error: .*type" /tmp/n298-mutant.log 2>/dev/null \
       && ! grep -q "XCTAssert" /tmp/n298-mutant.log 2>/dev/null; then
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

# 1. The whole ship: the image goes back to rounding each row on its own.
mutate "image-reverts-to-per-row-rounding" "$RENDERER" \
  "renderedCardPercents(outcomes.map(\\.probability))" \
  "outcomes.map { renderedPercent(\$0.probability) }"

# 2. The image's row ignores the percent it was handed.
mutate "image-row-ignores-the-decision" "$RENDERER" \
  "Text(discoverFuturesCardPercentLabel(percent))" \
  "Text(\"\\(Int(((probability ?? 0) * 100).rounded()))%\")"

# 3. The image's hero stops sharing the decision with the rows beneath it.
mutate "image-hero-rounds-alone" "$RENDERER" \
  "Text(discoverFuturesCardPercentLabel(heroPercent))" \
  "Text(\"\\(Int(((outcomes.first?.probability ?? 0) * 100).rounded()))%\")"

# 4. The hero derivation is emptied — the mutant that survives every behavioural
#    assertion unless the VIEW's own property is read (why it is not private).
mutate "image-hero-goes-blank" "$RENDERER" \
  "rowPercents.first ?? nil" \
  "nil"

# 5. The row list hands every row a nil percent.
mutate "image-list-passes-nil" "$RENDERER" \
  "percent: printed.indices.contains(idx) ? printed[idx] : nil" \
  "percent: nil"

# 6. THE LIST. The caller filters its unpriced outcomes out again — the arm no
#    sum guard can see, because both answers sum to 100.
#
#    THIS MUTANT SURVIVED ON THE FIRST RUN and is why `discoverFuturesShareRows`
#    exists. The rule was inline in `renderedShareImage()` and guarded only by a
#    source scan for the old spelling of the filter, so the same filtering in
#    different words went unseen: a scan aimed at a phrasing, not at a behaviour.
#    The mapping is now a function a test can call, and the mutant is killed by
#    an assertion rather than by a grep.
mutate "share-rows-filter-the-field-again" "$CARD" \
  "outcomes.map { (\$0.name, \$0.probability) }" \
  "outcomes.compactMap { o -> (name: String, probability: Double?)? in
        guard let p = o.probability else { return nil }
        return (o.name, p)
    }"

# 6b. And the call site stops asking that function at all.
mutate "caller-rebuilds-the-list-itself" "$CARD" \
  "discoverFuturesShareRows(data.topOutcomes ?? [])" \
  "(data.topOutcomes ?? []).compactMap { o -> (name: String, probability: Double?)? in
            guard let p = o.probability else { return nil }
            return (o.name, p)
        }"

# 7. The pair is decided but the WRONG side keeps its own number — still sums
#    to 100, so only an equality-with-the-card assertion can see it.
mutate "image-derived-point-lands-on-the-favourite" "$RENDERER" \
  "renderedCardPercents(outcomes.map(\\.probability))" \
  "renderedCardPercents(outcomes.map(\\.probability).reversed()).reversed()"

echo
echo "known-equivalent, stated rather than hidden:"
echo "  the bar width still reads the raw probability, deliberately (a length is"
echo "  not a printed number), so mutating it is not a mutant of this ship."
